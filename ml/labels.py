"""Ground-truth boxes: the class list, the Box type, and YOLO label I/O.

Labels live at ``<data>/labels/<session>/<frame>.txt``, mirroring the raw
frames. Each line is YOLO format: ``class_id cx cy w h`` with coordinates
normalized to 0..1. An empty file means "labeled, nothing sensitive", which is
different from a missing file ("not labeled yet") and is what lets the
false-blur rate be measured.

    python -m ml.labels import <label-studio-export.json>       # JSON export
    python -m ml.labels import <label-studio-yolo-export-dir>   # YOLO export
    python -m ml.labels import <export> --force                 # overwrite edits

Both imports match Label Studio's renamed uploads back to raw frames by file
name. Every file is converted and validated (frame match, known classes) before
any label is written, so a bad export changes nothing. An existing label file
whose content differs from the export is not overwritten without ``--force``:
labels corrected by hand after the export (e.g. the 2026-10-21 overlay audit)
would otherwise be silently undone by re-importing a stale export.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from .paths import data_root, raw_dir

# Order is the YOLO class id. Never reorder: existing label files depend on it.
CLASSES: tuple[str, ...] = (
    "credential",
    "api_key",
    "financial",
    "private_message",
    "personal_id",
)


@dataclass(frozen=True)
class Box:
    """Axis-aligned box in pixel coordinates (x1, y1) top-left, (x2, y2) bottom-right."""

    cls: str
    x1: float
    y1: float
    x2: float
    y2: float
    score: float = 1.0  # ground truth is always 1.0; predictions carry confidence

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)


def labels_dir() -> Path:
    return data_root() / "labels"


def label_path(frame: str) -> Path:
    """Label file for a frame path like "session/frame.png"."""
    return labels_dir() / Path(frame).with_suffix(".txt")


def parse_yolo(text: str, width: int, height: int) -> list[Box]:
    boxes = []
    for n, line in enumerate(text.splitlines(), 1):
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 5:
            raise ValueError(f"line {n}: expected 5 fields, got {len(parts)}")
        cid, cx, cy, w, h = int(parts[0]), *map(float, parts[1:])
        if not 0 <= cid < len(CLASSES):
            raise ValueError(f"line {n}: unknown class id {cid}")
        boxes.append(Box(
            CLASSES[cid],
            (cx - w / 2) * width, (cy - h / 2) * height,
            (cx + w / 2) * width, (cy + h / 2) * height,
        ))
    return boxes


def to_yolo(boxes: list[Box], width: int, height: int) -> str:
    lines = []
    for b in boxes:
        cx, cy = (b.x1 + b.x2) / 2 / width, (b.y1 + b.y2) / 2 / height
        w, h = (b.x2 - b.x1) / width, (b.y2 - b.y1) / height
        lines.append(f"{CLASSES.index(b.cls)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return "\n".join(lines) + ("\n" if lines else "")


def load_labels(frame: str, width: int, height: int) -> list[Box] | None:
    """Boxes for a frame, or None if the frame has not been labeled."""
    path = label_path(frame)
    if not path.exists():
        return None
    return parse_yolo(path.read_text(encoding="utf-8"), width, height)


# --- Label Studio import -----------------------------------------------------
# Normalized coordinates that differ by less than this are the same box: exports
# round differently (JSON percentages vs YOLO's 6 decimals).
SAME_BOX_TOL = 1e-4


def _same_labels(a: str, b: str) -> bool:
    """Same boxes (any order, within SAME_BOX_TOL), however the text is formatted."""
    try:
        ba, bb = parse_yolo(a, 1, 1), parse_yolo(b, 1, 1)
    except ValueError:
        return a == b

    def key(x: Box) -> tuple:
        return (x.cls, x.x1, x.y1, x.x2, x.y2)

    def close(p: Box, q: Box) -> bool:
        return p.cls == q.cls and all(
            abs(u - v) <= SAME_BOX_TOL for u, v in zip(key(p)[1:], key(q)[1:], strict=True)
        )

    return len(ba) == len(bb) and all(
        close(p, q) for p, q in zip(sorted(ba, key=key), sorted(bb, key=key), strict=True)
    )


def _check(text: str, source: str) -> str:
    """Validate a planned label file; any malformed line aborts the whole import."""
    try:
        parse_yolo(text, 1, 1)
    except ValueError as e:
        raise SystemExit(f"{source}: {e}; nothing imported.") from e
    return text


def _resolve(candidates: dict[Path, list[tuple[str, str]]], problems: list[str]) -> dict[Path, str]:
    """One label per frame. Several export entries for the same frame that
    disagree are reported and left out rather than letting the last one win."""
    planned = {}
    for target, entries in candidates.items():
        if all(_same_labels(entries[0][0], text) for text, _ in entries[1:]):
            planned[target] = entries[0][0]
        else:
            names = ", ".join(src for _, src in entries)
            problems.append(f"{target.parent.name}/{target.name}: export entries disagree "
                            f"({names}); not imported")
    return planned


def _write_labels(planned: dict[Path, str], force: bool) -> None:
    """Write every planned label file, or none of them.

    Refuses (unless ``force``) when an existing label has different boxes from
    the import: it may hold corrections made after the export was taken.
    """
    conflicts = sorted(
        str(path) for path, text in planned.items()
        if path.exists() and not _same_labels(path.read_text(encoding="utf-8"), text)
    )
    if conflicts and not force:
        shown = "\n  ".join(conflicts[:10]) + ("\n  ..." if len(conflicts) > 10 else "")
        raise SystemExit(
            f"{len(conflicts)} existing label file(s) differ from this export and would be "
            f"overwritten (hand corrections made after the export would be lost):\n  {shown}\n"
            "Re-export from an up-to-date project, or pass --force to overwrite."
        )
    for path, text in planned.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def import_yolo_export(
    export_dir: Path, raw: Path, dest: Path, force: bool = False
) -> tuple[int, list[str]]:
    """Copy label files from a Label Studio YOLO export into ``dest``.

    Label Studio renames uploads to ``<random>-<original name>``, so each label
    is matched to a raw frame by its original file name. Returns (imported,
    problems). Class ids are remapped by NAME using the export's classes.txt,
    since Label Studio may number classes in a different order than CLASSES.
    Nothing is written if any file has an unknown class id, and differing
    existing labels are kept unless ``force`` (see ``_write_labels``).
    """
    remap = {i: i for i in range(len(CLASSES))}
    classes_txt = export_dir / "classes.txt"
    if classes_txt.exists():
        exported = [c.strip() for c in classes_txt.read_text().splitlines() if c.strip()]
        unknown = set(exported) - set(CLASSES)
        if unknown:
            raise SystemExit(f"Export has classes not in {CLASSES}: {sorted(unknown)}")
        remap = {i: CLASSES.index(name) for i, name in enumerate(exported)}

    frames = sorted(raw.glob("*/*.png"))
    candidates: dict[Path, list[tuple[str, str]]] = {}
    problems: list[str] = []
    for txt in sorted((export_dir / "labels").glob("*.txt")):
        match = [f for f in frames if txt.stem.endswith(f.stem)]
        if len(match) != 1:
            problems.append(f"{txt.name}: {'no' if not match else 'ambiguous'} frame match")
            continue
        frame = match[0]
        lines = []
        for n, line in enumerate(txt.read_text(encoding="utf-8").splitlines(), 1):
            parts = line.split()
            if parts:
                try:
                    cid = int(parts[0])
                except ValueError:
                    raise SystemExit(f"{txt.name}: line {n}: class id {parts[0]!r} is not an "
                                     "integer; nothing imported.") from None
                if cid not in remap:
                    raise SystemExit(f"Unknown class id {cid} in {txt.name}; nothing imported.")
                lines.append(" ".join([str(remap[cid]), *parts[1:]]))
        text = _check("\n".join(lines) + ("\n" if lines else ""), txt.name)
        candidates.setdefault(dest / frame.parent.name / f"{frame.stem}.txt", []).append(
            (text, txt.name)
        )

    # An exported image with no label file was labeled "nothing sensitive".
    # Writing an empty label keeps it a clean frame instead of "unlabeled",
    # which would silently drop it from the false-blur-rate denominator.
    exported_labels = {t.stem for t in (export_dir / "labels").glob("*.txt")}
    for img in sorted((export_dir / "images").glob("*")):
        if img.stem in exported_labels:
            continue
        match = [f for f in frames if img.stem.endswith(f.stem)]
        if len(match) == 1:
            candidates.setdefault(dest / match[0].parent.name / f"{match[0].stem}.txt", []).append(
                ("", img.name)
            )
    planned = _resolve(candidates, problems)
    _write_labels(planned, force)
    return len(planned), problems


def import_json_export(
    tasks: list[dict], raw: Path, dest: Path, force: bool = False
) -> tuple[int, list[str]]:
    """Write labels from a Label Studio JSON export (``label-studio export <id> JSON``).

    JSON needs no image download, unlike the YOLO export. Boxes are stored as
    percentages of the image with a top-left origin. A submitted annotation with
    no boxes becomes an empty label file (clean frame). A skipped (cancelled)
    annotation writes nothing, so the frame stays "not labeled yet". Every task
    is checked before anything is written; differing existing labels are kept
    unless ``force`` (see ``_write_labels``).
    """
    frames = sorted(raw.glob("*/*.png"))
    candidates: dict[Path, list[tuple[str, str]]] = {}
    problems: list[str] = []
    for task in tasks:
        name = Path(task["data"]["image"]).stem
        match = [f for f in frames if name.endswith(f.stem)]
        if len(match) != 1:
            problems.append(f"{name}: {'no' if not match else 'ambiguous'} frame match")
            continue
        done = [a for a in task.get("annotations", []) if not a.get("was_cancelled")]
        if not done:
            problems.append(f"{match[0].parent.name}/{match[0].name}: skipped, not labeled")
            continue
        lines = []
        for r in done[-1]["result"]:
            v = r.get("value", {})
            for cls in v.get("rectanglelabels", []):
                if cls not in CLASSES:
                    raise SystemExit(f"Unknown class {cls!r} in {name}; nothing imported.")
                w, h = v["width"] / 100, v["height"] / 100
                cx, cy = v["x"] / 100 + w / 2, v["y"] / 100 + h / 2
                lines.append(f"{CLASSES.index(cls)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        text = _check("\n".join(lines) + ("\n" if lines else ""), name)
        candidates.setdefault(dest / match[0].parent.name / f"{match[0].stem}.txt", []).append(
            (text, name)
        )
    planned = _resolve(candidates, problems)
    _write_labels(planned, force)
    return len(planned), problems


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Label utilities.")
    sub = p.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import", help="import a Label Studio YOLO export dir or JSON file")
    imp.add_argument("export", type=Path)
    imp.add_argument("--force", action="store_true",
                     help="overwrite existing label files that differ from the export")
    args = p.parse_args(argv)

    if args.export.suffix == ".json":
        tasks = json.loads(args.export.read_text(encoding="utf-8"))
        n, problems = import_json_export(tasks, raw_dir(), labels_dir(), args.force)
    else:
        n, problems = import_yolo_export(args.export, raw_dir(), labels_dir(), args.force)
    print(f"Imported {n} label file(s) into {labels_dir()}")
    for line in problems:
        print(f"  ! {line}")


if __name__ == "__main__":
    main()
