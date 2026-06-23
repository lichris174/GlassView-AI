"""Golden eval cases: the input prompt plus the criteria a good answer meets.

A case is pure data (JSON), so the golden set grows by editing fixtures, not
code. Image cases reference a file under the golden directory's ``fixtures/``;
text-only cases omit the image and exercise reasoning without a screenshot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# cases.py -> evals -> glassview_ai -> server -> apps -> <repo root>
DEFAULT_GOLDEN = Path(__file__).resolve().parents[4] / "evals" / "golden"


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    image: str | None = None  # path relative to the golden dir, or None
    contains_all: list[str] = field(default_factory=list)
    contains_any: list[str] = field(default_factory=list)
    not_contains: list[str] = field(default_factory=list)
    regex: str | None = None

    def image_path(self, golden_dir: Path) -> Path | None:
        return (golden_dir / self.image) if self.image else None


def load_cases(golden_dir: Path | str = DEFAULT_GOLDEN) -> list[EvalCase]:
    """Load ``cases.json`` from the golden directory into EvalCase objects."""
    golden_dir = Path(golden_dir)
    raw = json.loads((golden_dir / "cases.json").read_text(encoding="utf-8"))
    cases = [EvalCase(**c) for c in raw]
    ids = [c.id for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate eval case ids: {sorted(dupes)}")
    return cases
