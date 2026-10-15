"""Run a system on a split and score it, leaving a self-describing run folder.

    python -m ml.evaluate run --system ocr_regex --split test
    python -m ml.evaluate pick-threshold results/<val-run> --target-recall 0.95
    python -m ml.evaluate score results/<run> --threshold 0.42
    python -m ml.evaluate compare results/<run-a> results/<run-b>

Each run writes ``results/<timestamp>-<system>-<split>/`` containing:

- ``manifest.json``: what produced the numbers (git commit and whether the tree
  was dirty, the frozen split's hash, system config, machine, threshold).
- ``predictions.jsonl``: every predicted box and per-frame latency, so scores
  can be recomputed without re-running the model.
- ``metrics.json``: point estimates with 95% session-bootstrap intervals.

Latency is the wall time of ``predict()`` alone (image already decoded), so it
includes everything a system needs per frame: OCR for ocr_regex, PNG encoding
plus the HTTP round trip for qwen_vl. The first frames are excluded as warmup
(model load, caches). Intervals are approximate: with ~10 test sessions a
percentile bootstrap under-covers, so ``num_sessions`` is reported beside them.

Any number quoted in the README or a resume should be traceable to one of
these folders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Protocol

from PIL import Image

from . import metrics as M
from .labels import Box, label_path, load_labels
from .paths import raw_dir, splits_file

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "results"
# First frames include model load and cache warm-up; leave them out of latency.
WARMUP_FRAMES = 3
# Headline metrics that get bootstrap intervals (the rest are point estimates).
CI_METRICS = (
    "region_recall",
    "pixel_recall",
    "blur_precision",
    "clean_false_blur_rate",
    "sensitive_frame_recall",
)


class Predictor(Protocol):
    name: str
    config: dict

    def predict(self, image: Image.Image) -> list[Box]: ...


# --- dataset -----------------------------------------------------------------
def load_split(split: str) -> tuple[list[tuple[str, list[Box]]], dict]:
    """Labeled frames of a split as (frame path, ground truth), plus split info."""
    manifest = json.loads(splits_file().read_text(encoding="utf-8"))
    info = manifest["splits"][split]
    frames, unlabeled = [], []
    for frame in sorted(info["files"]):
        with Image.open(raw_dir() / frame) as im:
            gts = load_labels(frame, im.width, im.height)
        if gts is None:
            unlabeled.append(frame)
        else:
            frames.append((frame, gts))
    return frames, {
        "split": split,
        "hash": info["hash"],
        "labels_hash": labels_hash([f for f, _ in frames]),
        "unlabeled": unlabeled,
    }


def labels_hash(frames: list[str]) -> str:
    """Hash of the label files for these frames. The split hash pins the images;
    this pins the answers, so a relabel after a run is detected at scoring time."""
    h = hashlib.sha256()
    for frame in sorted(frames):
        h.update(f"{frame}\n".encode())
        h.update(label_path(frame).read_bytes())
    return h.hexdigest()


def session_of(frame: str) -> str:
    return frame.split("/", 1)[0]


# --- provenance --------------------------------------------------------------
def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _gpu() -> str:
    try:
        return subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def provenance() -> dict:
    return {
        "git_commit": _git("rev-parse", "HEAD"),
        # A dirty tree means the commit alone does not reproduce the run.
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "gpu": _gpu(),
    }


# --- run + score ---------------------------------------------------------------
def _box_json(b: Box) -> dict:
    # Coordinates to 0.01 px; scores at full precision, because rounding them
    # creates ties that change AP and the threshold picked on val.
    return {k: round(v, 2) if isinstance(v, float) and k != "score" else v
            for k, v in asdict(b).items()}


def predict_split(predictor: Predictor, frames: list[tuple[str, list[Box]]], out: Path) -> None:
    with (out / "predictions.jsonl").open("w", encoding="utf-8") as f:
        for i, (frame, _) in enumerate(frames, 1):
            with Image.open(raw_dir() / frame) as im:
                image = im.convert("RGB")
            t0 = time.perf_counter()
            boxes = predictor.predict(image)
            ms = (time.perf_counter() - t0) * 1000
            f.write(json.dumps({
                "frame": frame, "latency_ms": round(ms, 2), "boxes": [_box_json(b) for b in boxes]
            }) + "\n")
            print(f"  [{i}/{len(frames)}] {frame}  {len(boxes)} box(es)  {ms:.0f} ms")


def load_predictions(run: Path) -> dict[str, dict]:
    rows = (json.loads(line) for line in (run / "predictions.jsonl").open(encoding="utf-8"))
    return {
        r["frame"]: {"latency_ms": r["latency_ms"], "boxes": [Box(**b) for b in r["boxes"]]}
        for r in rows
    }


def _clean(v: float) -> float | None:
    """JSON has no NaN; an undefined metric (e.g. a class absent from the split) is null."""
    return None if isinstance(v, float) and math.isnan(v) else round(v, 4)


def score(run: Path, threshold: float, coverage: float = M.DEFAULT_COVERAGE) -> dict:
    """Score saved predictions against the split's current labels."""
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    frames, split_info = load_split(manifest["split"]["split"])
    if split_info["hash"] != manifest["split"]["hash"]:
        raise SystemExit("Split hash changed since this run; the frozen test set was modified.")
    preds = load_predictions(run)
    # Frames labeled after the run (it was made with --allow-partial) have no
    # predictions; they are skipped and counted rather than crashing.
    skipped = [f for f, _ in frames if f not in preds]
    frames = [(f, g) for f, g in frames if f in preds]
    labels_changed = labels_hash([f for f, _ in frames]) != manifest["split"].get("labels_hash")

    # AP sweeps every confidence level, so it uses all predictions; privacy
    # metrics describe the deployed system, so they use the operating threshold.
    all_preds = [(session_of(f), g, preds[f]["boxes"]) for f, g in frames]
    stats = [M.frame_stats(s, g, M.above(p, threshold), coverage) for s, g, p in all_preds]
    values = {**M.privacy_metrics(stats), **M.detection_metrics([(g, p) for _, g, p in all_preds])}
    cis = {k: M.bootstrap_ci(stats, lambda st, k=k: M.privacy_metrics(st)[k]) for k in CI_METRICS}

    latencies = [preds[f]["latency_ms"] for f, _ in frames][WARMUP_FRAMES:]
    result = {
        "threshold": threshold,
        "coverage": coverage,
        "num_frames": len(frames),
        "skipped_frames": skipped,
        # True means labels were edited after the predictions were made (e.g.
        # fixing mistakes). Scores are then against the new labels; say so.
        "labels_changed_since_run": labels_changed,
        "num_sessions": len({s.session for s in stats}),
        "num_clean_frames": sum(s.clean for s in stats),
        "num_regions": {
            c: sum(s.gt_count.get(c, 0) for s in stats) for c in sorted(
                {c for s in stats for c in s.gt_count}
            )
        },
        "metrics": {k: _clean(v) for k, v in values.items()},
        "ci95": {k: [_clean(lo), _clean(hi)] for k, (lo, hi) in cis.items()},
        "latency_ms": {
            "median": _clean(statistics.median(latencies)) if latencies else None,
            "p95": _clean(_p95(latencies)) if latencies else None,
            "warmup_frames_excluded": WARMUP_FRAMES,
        },
    }
    name = "metrics.json" if threshold == manifest["threshold"] else f"metrics-t{threshold:g}.json"
    (run / name).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _p95(values: list[float]) -> float:
    vals = sorted(values)
    return vals[min(len(vals) - 1, math.ceil(0.95 * len(vals)) - 1)]


def run(
    predictor: Predictor,
    split: str,
    threshold: float,
    allow_partial: bool,
    threshold_source: str = "fixed",
) -> Path:
    frames, split_info = load_split(split)
    if split_info["unlabeled"] and not allow_partial:
        raise SystemExit(
            f"{len(split_info['unlabeled'])} frame(s) in '{split}' are not labeled; "
            "label them or pass --allow-partial (the run will record which were skipped)."
        )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RESULTS / f"{stamp}-{predictor.name}-{split}"
    out.mkdir(parents=True)
    manifest = {
        "system": predictor.name,
        "config": predictor.config,
        "split": split_info,
        "threshold": threshold,
        # "fixed", or the val run it was picked from, so a threshold tuned on
        # test cannot pass silently.
        "threshold_source": threshold_source,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        **provenance(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    predict_split(predictor, frames, out)
    manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
    manifest["config"] = predictor.config  # may gain run stats, e.g. parse failures
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    score(out, threshold)
    return out


def compare(run_a: Path, run_b: Path, threshold_a: float, threshold_b: float) -> dict:
    """Paired difference (a minus b) on the frames both runs share."""
    ma = json.loads((run_a / "manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((run_b / "manifest.json").read_text(encoding="utf-8"))
    if ma["split"]["hash"] != mb["split"]["hash"]:
        raise SystemExit("Runs were made on different splits; a paired comparison is invalid.")
    pa, pb = load_predictions(run_a), load_predictions(run_b)
    frames, _ = load_split(ma["split"]["split"])
    frames = [(f, g) for f, g in frames if f in pa and f in pb]
    sa = [M.frame_stats(session_of(f), g, M.above(pa[f]["boxes"], threshold_a)) for f, g in frames]
    sb = [M.frame_stats(session_of(f), g, M.above(pb[f]["boxes"], threshold_b)) for f, g in frames]
    # Five metrics with no multiple-comparison correction: treat "significant"
    # as descriptive, and name in advance the one metric a claim rests on.
    out: dict = {"num_frames": len(frames), "num_sessions": len({session_of(f) for f, _ in frames})}
    for k in CI_METRICS:
        d, lo, hi = M.paired_bootstrap_diff(sa, sb, lambda st, k=k: M.privacy_metrics(st)[k])
        out[k] = {"diff": _clean(d), "ci95": [_clean(lo), _clean(hi)],
                  "significant": not (lo <= 0 <= hi)}
    return out


def _pick(val_run: Path, target_recall: float) -> tuple[float, float, bool]:
    manifest = json.loads((val_run / "manifest.json").read_text(encoding="utf-8"))
    if manifest["split"]["split"] == "test":
        raise SystemExit("Pick thresholds on val, never on test.")
    frames, _ = load_split(manifest["split"]["split"])
    preds = load_predictions(val_run)
    triples = [(session_of(f), g, preds[f]["boxes"]) for f, g in frames if f in preds]
    return M.choose_threshold(triples, target_recall)


def _run_threshold(run_dir: Path) -> float:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["threshold"]


def main(argv: list[str] | None = None) -> None:
    from .baselines import SYSTEMS, build

    p = argparse.ArgumentParser(description="Evaluate sensitive-region detectors.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--system", required=True, choices=sorted(SYSTEMS))
    r.add_argument("--split", default="val", choices=("train", "val", "test"))
    r.add_argument("--threshold", type=float, default=0.0)
    r.add_argument("--threshold-from", type=Path, default=None,
                   help="val run to pick the threshold from (uses --target-recall)")
    r.add_argument("--target-recall", type=float, default=0.95)
    r.add_argument("--allow-partial", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("run_dir", type=Path)
    s.add_argument("--threshold", type=float, default=None)
    t = sub.add_parser("pick-threshold")
    t.add_argument("run_dir", type=Path)
    t.add_argument("--target-recall", type=float, required=True)
    c = sub.add_parser("compare")
    c.add_argument("run_a", type=Path)
    c.add_argument("run_b", type=Path)
    args = p.parse_args(argv)

    if args.cmd == "run":
        threshold, source = args.threshold, "fixed"
        if args.threshold_from:
            threshold, recall, met = _pick(args.threshold_from, args.target_recall)
            if not met:
                raise SystemExit(f"Val run never reaches recall {args.target_recall} "
                                 f"(best {recall:.3f}); lower the target.")
            source = f"{args.threshold_from.name} @ target_recall={args.target_recall}"
        out = run(build(args.system), args.split, threshold, args.allow_partial, source)
        print(json.dumps(json.loads((out / "metrics.json").read_text())["metrics"], indent=2))
        print(f"Run saved to {out}")
    elif args.cmd == "score":
        threshold = _run_threshold(args.run_dir) if args.threshold is None else args.threshold
        print(json.dumps(score(args.run_dir, threshold), indent=2))
    elif args.cmd == "pick-threshold":
        threshold, recall, met = _pick(args.run_dir, args.target_recall)
        print(json.dumps({"threshold": threshold, "val_recall": recall, "met": met}))
    else:
        result = compare(
            args.run_a, args.run_b, _run_threshold(args.run_a), _run_threshold(args.run_b)
        )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
