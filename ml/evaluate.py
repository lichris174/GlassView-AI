"""Run a system on a split and score it, leaving a self-describing run folder.

    python -m ml.evaluate run --system ocr_regex --split test
    python -m ml.evaluate pick-threshold results/<val-run> --target-recall 0.95
    python -m ml.evaluate score results/<run> --threshold 0.42 [--coverage 0.9]
    python -m ml.evaluate compare results/<run-a> results/<run-b> [--coverage 0.9]

Each run writes ``results/<timestamp>-<system>-<split>/`` containing:

- ``manifest.json``: what produced the numbers (git commit and whether the tree
  was dirty, the frozen split's hash, per-frame label digests, system config,
  machine, threshold and where it came from, coverage).
- ``predictions.jsonl``: every predicted box and per-frame latency, so scores
  can be recomputed without re-running the model.
- ``metrics.json``: point estimates with 95% session-bootstrap intervals, at the
  run's own threshold and coverage. Re-scoring at any other operating point
  (``score --threshold`` / ``--coverage``) writes ``metrics-t<X>[-c<Y>].json``
  instead, with its ``threshold_source`` recorded, so the run's own numbers are
  never overwritten by a hand-picked threshold.

Latency is the wall time of ``predict()`` alone (image already decoded), so it
includes everything a system needs per frame: OCR for ocr_regex, PNG encoding
plus the HTTP round trip for qwen_vl. The first frames are excluded as warmup
(model load, caches). Intervals are approximate: the frozen test split has only
5 sessions, and a percentile bootstrap over that few under-covers, so
``num_sessions`` and the count of undefined replicates are reported beside them.

AP caveat: the baselines give every box the same score, so their AP is a single
precision/recall point (about recall x precision), not comparable to the AP of a
detector with real confidences. Compare baselines on the privacy metrics.

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
    labeled = [f for f, _ in frames]
    return frames, {
        "split": split,
        "hash": info["hash"],
        # Kept for manifests written before label_digests existed.
        "labels_hash": labels_hash(labeled),
        "label_digests": label_digests(labeled),
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


def label_digests(frames: list[str]) -> dict[str, str]:
    """SHA-256 of each frame's label file. Lets scoring compare exactly the frames
    it scores, whatever subset of the run's frames has predictions."""
    return {f: hashlib.sha256(label_path(f).read_bytes()).hexdigest() for f in sorted(frames)}


def _labels_changed(split_manifest: dict, frames: list[str]) -> list[str] | bool:
    """Scored frames whose labels differ from the run's. Old manifests only hold
    one hash over all frames, which is exact only when every frame was scored."""
    stored = split_manifest.get("label_digests")
    if stored is None:
        return labels_hash(frames) != split_manifest.get("labels_hash")
    now = label_digests(frames)
    return [f for f in frames if stored.get(f) != now[f]]


def _image_size(frame: str) -> tuple[int, int]:
    with Image.open(raw_dir() / frame) as im:  # reads the header only
        return im.size


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


def _clipped(frame: str, boxes: list[Box]) -> list[Box]:
    """Predictions cut to the frame, so off-screen area never counts as blurred."""
    return M.clip_boxes(boxes, *_image_size(frame))


def score(
    run: Path,
    threshold: float,
    coverage: float = M.DEFAULT_COVERAGE,
    threshold_source: str | None = None,
) -> dict:
    """Score saved predictions against the split's current labels.

    At the run's own threshold and coverage, with no ``threshold_source``, this
    (re)writes ``metrics.json``. Anything else is a different operating point:
    it goes to ``metrics-t<threshold>[-c<coverage>].json`` with its source
    recorded (``threshold_source``, default "manual").
    """
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    frames, split_info = load_split(manifest["split"]["split"])
    if split_info["hash"] != manifest["split"]["hash"]:
        raise SystemExit("Split hash changed since this run; the frozen test set was modified.")
    preds = load_predictions(run)
    # Frames labeled after the run (it was made with --allow-partial) have no
    # predictions; they are skipped and counted rather than crashing.
    skipped = [f for f, _ in frames if f not in preds]
    frames = [(f, g) for f, g in frames if f in preds]
    changed = _labels_changed(manifest["split"], [f for f, _ in frames])

    # AP sweeps every confidence level, so it uses all predictions; privacy
    # metrics describe the deployed system, so they use the operating threshold.
    all_preds = [(session_of(f), g, _clipped(f, preds[f]["boxes"])) for f, g in frames]
    stats = [M.frame_stats(s, g, M.above(p, threshold), coverage) for s, g, p in all_preds]
    values = {**M.privacy_metrics(stats), **M.detection_metrics([(g, p) for _, g, p in all_preds])}
    cis = {k: M.bootstrap_interval(stats, lambda st, k=k: M.privacy_metrics(st)[k])
           for k in CI_METRICS}

    same_threshold = threshold == manifest["threshold"]
    own = (threshold_source is None and same_threshold
           and coverage == manifest.get("coverage", M.DEFAULT_COVERAGE))
    # Re-scoring the run's threshold at another coverage keeps its provenance.
    source = threshold_source or (
        manifest.get("threshold_source", "fixed") if same_threshold else "manual"
    )
    latencies = [preds[f]["latency_ms"] for f, _ in frames][WARMUP_FRAMES:]
    result = {
        "threshold": threshold,
        "threshold_source": source,
        "coverage": coverage,
        "num_frames": len(frames),
        "skipped_frames": skipped,
        # True means labels were edited after the predictions were made (e.g.
        # fixing mistakes). Scores are then against the new labels; say so.
        "labels_changed_since_run": bool(changed),
        **({"labels_changed_frames": changed} if isinstance(changed, list) and changed else {}),
        "num_sessions": len({s.session for s in stats}),
        "num_clean_frames": sum(s.clean for s in stats),
        # Zero-area label boxes: ignored by every metric, counted so they get fixed.
        "num_degenerate_gt_ignored": sum(s.gt_degenerate for s in stats),
        "num_regions": {
            c: sum(s.gt_count.get(c, 0) for s in stats) for c in sorted(
                {c for s in stats for c in s.gt_count}
            )
        },
        "metrics": {k: _clean(v) for k, v in values.items()},
        "ci95": {k: [_clean(iv.lo), _clean(iv.hi)] for k, iv in cis.items()},
        # Replicates where the metric was undefined (e.g. no clean frame drawn)
        # are left out; too many and the interval above is null.
        "ci95_undefined_replicates": {k: iv.undefined for k, iv in cis.items()},
        "bootstrap_replicates": next(iter(cis.values())).n,
        "latency_ms": {
            "median": _clean(statistics.median(latencies)) if latencies else None,
            "p95": _clean(_p95(latencies)) if latencies else None,
            "warmup_frames_excluded": WARMUP_FRAMES,
        },
    }
    name = "metrics.json" if own else _metrics_name(threshold, coverage)
    (run / name).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _metrics_name(threshold: float, coverage: float) -> str:
    # repr is the shortest exact form, so distinct thresholds never share a file
    # (":g" would map 0.4200001 and 0.42 to the same name).
    cov = "" if coverage == M.DEFAULT_COVERAGE else f"-c{float(coverage)!r}"
    return f"metrics-t{float(threshold)!r}{cov}.json"


def _p95(values: list[float]) -> float:
    vals = sorted(values)
    return vals[min(len(vals) - 1, math.ceil(0.95 * len(vals)) - 1)]


def run(
    predictor: Predictor,
    split: str,
    threshold: float,
    allow_partial: bool,
    threshold_source: str = "fixed",
    coverage: float = M.DEFAULT_COVERAGE,
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
        "coverage": coverage,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        **provenance(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    predict_split(predictor, frames, out)
    manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
    manifest["config"] = predictor.config  # may gain run stats, e.g. parse failures
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    score(out, threshold, coverage)
    return out


def _significant(lo: float, hi: float) -> bool:
    """The interval excludes 0. An undefined (NaN) interval shows nothing."""
    if math.isnan(lo) or math.isnan(hi):
        return False
    return not (lo <= 0 <= hi)


def compare(
    run_a: Path,
    run_b: Path,
    threshold_a: float,
    threshold_b: float,
    coverage: float = M.DEFAULT_COVERAGE,
) -> dict:
    """Paired difference (a minus b) on the frames both runs share."""
    ma = json.loads((run_a / "manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((run_b / "manifest.json").read_text(encoding="utf-8"))
    if ma["split"]["hash"] != mb["split"]["hash"]:
        raise SystemExit("Runs were made on different splits; a paired comparison is invalid.")
    pa, pb = load_predictions(run_a), load_predictions(run_b)
    frames, _ = load_split(ma["split"]["split"])
    frames = [(f, g) for f, g in frames if f in pa and f in pb]

    def stats(preds: dict[str, dict], threshold: float) -> list[M.FrameStats]:
        return [M.frame_stats(session_of(f), g, M.above(_clipped(f, preds[f]["boxes"]), threshold),
                              coverage) for f, g in frames]

    sa, sb = stats(pa, threshold_a), stats(pb, threshold_b)
    # Five metrics with no multiple-comparison correction: treat "significant"
    # as descriptive, and name in advance the one metric a claim rests on.
    out: dict = {"num_frames": len(frames), "num_sessions": len({session_of(f) for f, _ in frames}),
                 "coverage": coverage}
    for k in CI_METRICS:
        d, iv = M.paired_bootstrap_interval(sa, sb, lambda st, k=k: M.privacy_metrics(st)[k])
        out[k] = {"diff": _clean(d), "ci95": [_clean(iv.lo), _clean(iv.hi)],
                  "undefined_replicates": iv.undefined,
                  "significant": _significant(iv.lo, iv.hi)}
    return out


def _pick(val_run: Path, target_recall: float) -> tuple[float, float, bool]:
    manifest = json.loads((val_run / "manifest.json").read_text(encoding="utf-8"))
    if manifest["split"]["split"] == "test":
        raise SystemExit("Pick thresholds on val, never on test.")
    frames, _ = load_split(manifest["split"]["split"])
    preds = load_predictions(val_run)
    triples = [(session_of(f), g, _clipped(f, preds[f]["boxes"])) for f, g in frames if f in preds]
    return M.choose_threshold(triples, target_recall, manifest.get("coverage", M.DEFAULT_COVERAGE))


def _manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def _run_threshold(run_dir: Path) -> float:
    return _manifest(run_dir)["threshold"]


def _run_coverage(run_dir: Path) -> float:
    # Manifests from before coverage was recorded were all scored at the default.
    return _manifest(run_dir).get("coverage", M.DEFAULT_COVERAGE)


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
    r.add_argument("--coverage", type=float, default=None,
                   help=f"default: the --threshold-from run's, else {M.DEFAULT_COVERAGE}")
    s = sub.add_parser("score")
    s.add_argument("run_dir", type=Path)
    s.add_argument("--threshold", type=float, default=None,
                   help="re-score at this threshold (written to metrics-t<X>.json); "
                        "default: the run's own")
    s.add_argument("--coverage", type=float, default=None,
                   help="share of a region that must be blurred to count as protected; "
                        "default: the run's own")
    t = sub.add_parser("pick-threshold")
    t.add_argument("run_dir", type=Path)
    t.add_argument("--target-recall", type=float, required=True)
    c = sub.add_parser("compare")
    c.add_argument("run_a", type=Path)
    c.add_argument("run_b", type=Path)
    c.add_argument("--coverage", type=float, default=None,
                   help="default: the runs' own (they must agree)")
    args = p.parse_args(argv)

    if args.cmd == "run":
        threshold, source = args.threshold, "fixed"
        coverage = M.DEFAULT_COVERAGE if args.coverage is None else args.coverage
        if args.threshold_from:
            # The threshold was fit for the val run's coverage; it means
            # something else at another one.
            val_coverage = _run_coverage(args.threshold_from)
            if args.coverage is not None and args.coverage != val_coverage:
                raise SystemExit(f"--coverage {args.coverage} differs from the val run's "
                                 f"{val_coverage}; its threshold was picked for that coverage.")
            coverage = val_coverage
            threshold, recall, met = _pick(args.threshold_from, args.target_recall)
            if not met:
                raise SystemExit(f"Val run never reaches recall {args.target_recall} "
                                 f"(best {recall:.3f}); lower the target.")
            source = f"{args.threshold_from.name} @ target_recall={args.target_recall}"
        out = run(build(args.system), args.split, threshold, args.allow_partial, source, coverage)
        print(json.dumps(json.loads((out / "metrics.json").read_text())["metrics"], indent=2))
        print(f"Run saved to {out}")
    elif args.cmd == "score":
        coverage = _run_coverage(args.run_dir) if args.coverage is None else args.coverage
        own = _run_threshold(args.run_dir)
        threshold = own if args.threshold is None else args.threshold
        # A threshold typed by hand is recorded as such; repeating the run's own
        # keeps the run's provenance.
        source = None if threshold == own else "manual (score --threshold)"
        result = score(args.run_dir, threshold, coverage, threshold_source=source)
        print(json.dumps(result, indent=2))
    elif args.cmd == "pick-threshold":
        threshold, recall, met = _pick(args.run_dir, args.target_recall)
        print(json.dumps({"threshold": threshold, "val_recall": recall, "met": met}))
    else:
        coverage = args.coverage
        if coverage is None:
            coverage = _run_coverage(args.run_a)
            if coverage != _run_coverage(args.run_b):
                raise SystemExit("Runs were scored at different coverage; pass --coverage.")
        result = compare(
            args.run_a, args.run_b, _run_threshold(args.run_a), _run_threshold(args.run_b), coverage
        )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
