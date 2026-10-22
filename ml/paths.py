"""Where the dataset lives on disk.

Screenshots are kept OUTSIDE the repo and outside OneDrive by default, so a
captured screen can never be committed or synced to the cloud by accident.
Override with the GLASSVIEW_DATA environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    override = os.environ.get("GLASSVIEW_DATA")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "GlassView" / "dataset"


def raw_dir() -> Path:
    """Captured sessions: raw/<session>/<frame>.png plus raw/<session>/meta.jsonl."""
    return data_root() / "raw"


def splits_file() -> Path:
    """The frozen train/val/test assignment (see ml/splits.py)."""
    return data_root() / "splits.json"
