"""Assign capture sessions to train / val / test and freeze the test set.

    python -m ml.splits assign            # first run: create splits.json
    python -m ml.splits assign            # later runs: new sessions go to train
    python -m ml.splits verify            # prove the test set has not changed

Two rules keep the reported numbers honest:

1. **Whole sessions, not frames, are split.** Frames from one session are
   near-copies of each other (same app, same fake account). If some landed in
   train and others in test, the model would be graded on screens it has
   effectively already seen, and test scores would be inflated.
2. **The test set is frozen.** Its file list and a SHA-256 of every file are
   recorded once. Later captures can only be added to train, and ``verify``
   fails if any test file was changed, removed, or added.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .paths import raw_dir, splits_file

SPLITS = ("train", "val", "test")
# Fewer sessions than this cannot fill three disjoint splits meaningfully.
MIN_SESSIONS = 5


@dataclass(frozen=True)
class Session:
    name: str
    files: tuple[str, ...]  # frame paths relative to the raw dir, e.g. "s1/x.png"


def scan_sessions(root: Path) -> list[Session]:
    sessions = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        frames = tuple(f"{d.name}/{f.name}" for f in sorted(d.glob("*.png")))
        if frames:
            sessions.append(Session(d.name, frames))
    return sessions


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def set_hash(entries: dict[str, str]) -> str:
    """One hash for a whole split: changes if any file is added, removed, or edited."""
    lines = "\n".join(f"{path} {digest}" for path, digest in sorted(entries.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def assign_sessions(
    sessions: list[Session], test_frac: float, val_frac: float, seed: int
) -> dict[str, list[str]]:
    """Shuffle sessions with a fixed seed, then fill test, then val, by frame count.

    Deterministic: the same sessions and seed always give the same split.
    """
    order = sorted(sessions, key=lambda s: s.name)
    random.Random(seed).shuffle(order)
    total = sum(len(s.files) for s in order)
    targets = {"test": test_frac * total, "val": val_frac * total}
    out: dict[str, list[str]] = {k: [] for k in SPLITS}
    filled = {"test": 0, "val": 0}
    for s in order:
        split = next((k for k in ("test", "val") if filled[k] < targets[k]), "train")
        out[split].append(s.name)
        if split in filled:
            filled[split] += len(s.files)
    return out


def build_manifest(
    root: Path, sessions: list[Session], assignment: dict[str, list[str]], meta: dict
) -> dict:
    by_name = {s.name: s for s in sessions}
    splits = {}
    for split in SPLITS:
        files = {f: sha256_file(root / f) for n in assignment[split] for f in by_name[n].files}
        splits[split] = {
            "sessions": sorted(assignment[split]),
            "num_frames": len(files),
            "files": files,
            "hash": set_hash(files),
        }
    return {**meta, "splits": splits}


def assign(
    root: Path, out: Path, test_frac: float, val_frac: float, seed: int
) -> dict:
    sessions = scan_sessions(root)
    if not sessions:
        raise SystemExit(f"No sessions with frames under {root}")

    if out.exists():
        prev = json.loads(out.read_text(encoding="utf-8"))
        known = {n for sp in prev["splits"].values() for n in sp["sessions"]}
        assignment = {k: list(prev["splits"][k]["sessions"]) for k in SPLITS}
        new = [s.name for s in sessions if s.name not in known]
        # The test set is frozen, and val stays fixed so model selection stays
        # comparable across runs; anything captured later is training data.
        assignment["train"] += new
        meta = {k: prev[k] for k in ("created_at", "seed", "test_frac", "val_frac")}
        manifest = build_manifest(root, sessions, assignment, meta)
        if manifest["splits"]["test"]["hash"] != prev["splits"]["test"]["hash"]:
            raise SystemExit("Test files changed since the split was frozen; run verify.")
        if new:
            print(f"Added {len(new)} new session(s) to train: {', '.join(new)}")
    else:
        if len(sessions) < MIN_SESSIONS:
            raise SystemExit(
                f"Only {len(sessions)} session(s); capture at least {MIN_SESSIONS} "
                "before freezing the split."
            )
        assignment = assign_sessions(sessions, test_frac, val_frac, seed)
        meta = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "seed": seed,
            "test_frac": test_frac,
            "val_frac": val_frac,
        }
        manifest = build_manifest(root, sessions, assignment, meta)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify(root: Path, manifest_path: Path) -> list[str]:
    """Return a list of problems with the frozen test set (empty means intact)."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    test = manifest["splits"]["test"]
    problems = []
    for path, digest in test["files"].items():
        f = root / path
        if not f.exists():
            problems.append(f"missing: {path}")
        elif sha256_file(f) != digest:
            problems.append(f"modified: {path}")
    for name in test["sessions"]:
        on_disk = {f"{name}/{p.name}" for p in (root / name).glob("*.png")}
        problems += [f"added: {p}" for p in sorted(on_disk - test["files"].keys())]
    return problems


def summary(manifest: dict) -> str:
    rows = [
        f"{k:<5} {sp['num_frames']:>5} frames  {len(sp['sessions']):>3} sessions  "
        f"hash {sp['hash'][:12]}"
        for k, sp in manifest["splits"].items()
    ]
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Train/val/test split by capture session.")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("assign")
    a.add_argument("--test-frac", type=float, default=0.35)
    a.add_argument("--val-frac", type=float, default=0.15)
    a.add_argument("--seed", type=int, default=0)
    sub.add_parser("verify")
    args = p.parse_args(argv)

    root, out = raw_dir(), splits_file()
    if args.cmd == "assign":
        print(summary(assign(root, out, args.test_frac, args.val_frac, args.seed)))
        print(f"Wrote {out}")
    else:
        problems = verify(root, out)
        print("\n".join(problems) or "Test set intact.")
        sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
