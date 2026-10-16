"""Ground-truth boxes: the class list, the Box type, and YOLO label I/O.

Labels live at ``<data>/labels/<session>/<frame>.txt``, mirroring the raw
frames. Each line is YOLO format: ``class_id cx cy w h`` with coordinates
normalized to 0..1. An empty file means "labeled, nothing sensitive", which is
different from a missing file ("not labeled yet") and is what lets the
false-blur rate be measured.

    python -m ml.labels import <label-studio-yolo-export-dir>
"""

from __future__ import annotations

import argparse
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
def import_yolo_export(export_dir: Path, raw: Path, dest: Path) -> tuple[int, list[str]]:
    """Copy label files from a Label Studio YOLO export into ``dest``.

    Label Studio renames uploads to ``<random>-<original name>``, so each label
    is matched to a raw frame by its original file name. Returns (imported,
    problems). Class ids are remapped by NAME using the export's classes.txt,
    since Label Studio may number classes in a different order than CLASSES.
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
    imported, problems = 0, []
    for txt in sorted((export_dir / "labels").glob("*.txt")):
        match = [f for f in frames if txt.stem.endswith(f.stem)]
        if len(match) != 1:
            problems.append(f"{txt.name}: {'no' if not match else 'ambiguous'} frame match")
            continue
        frame = match[0]
        target = dest / frame.parent.name / f"{frame.stem}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for line in txt.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts:
                lines.append(" ".join([str(remap[int(parts[0])]), *parts[1:]]))
        target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        imported += 1

    # An exported image with no label file was labeled "nothing sensitive".
    # Writing an empty label keeps it a clean frame instead of "unlabeled",
    # which would silently drop it from the false-blur-rate denominator.
    exported_labels = {t.stem for t in (export_dir / "labels").glob("*.txt")}
    for img in sorted((export_dir / "images").glob("*")):
        if img.stem in exported_labels:
            continue
        match = [f for f in frames if img.stem.endswith(f.stem)]
        if len(match) == 1:
            target = dest / match[0].parent.name / f"{match[0].stem}.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
            imported += 1
    return imported, problems


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Label utilities.")
    sub = p.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import", help="import a Label Studio YOLO export")
    imp.add_argument("export_dir", type=Path)
    args = p.parse_args(argv)

    n, problems = import_yolo_export(args.export_dir, raw_dir(), labels_dir())
    print(f"Imported {n} label file(s) into {labels_dir()}")
    for line in problems:
        print(f"  ! {line}")


if __name__ == "__main__":
    main()
