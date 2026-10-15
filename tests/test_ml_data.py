"""Dataset tooling: duplicate detection and the frozen session-level split."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from ml.capture import dhash, hamming, is_near_duplicate, validate_session
from ml.splits import Session, assign, assign_sessions, scan_sessions, verify


# --- perceptual hash ---------------------------------------------------------
def _screen(text_rows: int, shift: int = 0) -> Image.Image:
    img = Image.new("RGB", (320, 200), "white")
    d = ImageDraw.Draw(img)
    for i in range(text_rows):
        d.rectangle([10 + shift, 10 + i * 18, 200 + shift, 20 + i * 18], fill="black")
    return img


def test_dhash_ignores_tiny_change_but_not_new_screen() -> None:
    base = dhash(_screen(5))
    # A one-pixel nudge (cursor blink, clock tick) stays a duplicate.
    assert is_near_duplicate(dhash(_screen(5, shift=1)), base)
    # A visibly different screen does not.
    different = Image.new("RGB", (320, 200), "white")
    ImageDraw.Draw(different).ellipse([60, 20, 260, 180], fill="black")
    assert hamming(dhash(different), base) >= 6


def test_first_frame_is_never_a_duplicate() -> None:
    assert not is_near_duplicate(dhash(_screen(3)), None)


def test_session_names_are_validated() -> None:
    assert validate_session("banking-fake_01") == "banking-fake_01"
    for bad in ("", "../etc", "Has Space", "UPPER"):
        with pytest.raises(argparse.ArgumentTypeError):
            validate_session(bad)


# --- splits ------------------------------------------------------------------
def _make_raw(root: Path, sessions: dict[str, int]) -> None:
    for name, n in sessions.items():
        d = root / name
        d.mkdir(parents=True)
        for i in range(n):
            _screen(i % 7 + 1, shift=i).save(d / f"{i:03d}.png")


def scan_sessions_from(spec: dict[str, int]) -> list[Session]:
    """In-memory sessions for pure assignment tests (no files needed)."""
    return [Session(n, tuple(f"{n}/{i}.png" for i in range(k))) for n, k in spec.items()]


def test_sessions_are_never_split_across_sets() -> None:
    sessions = scan_sessions_from({"a": 4, "b": 4, "c": 4, "d": 4, "e": 4})
    out = assign_sessions(sessions, test_frac=0.35, val_frac=0.15, seed=0)
    names = [n for split in out.values() for n in split]
    assert sorted(names) == ["a", "b", "c", "d", "e"]  # each exactly once
    assert out["test"] and out["train"]


def test_assignment_is_deterministic() -> None:
    sessions = scan_sessions_from({f"s{i}": 3 for i in range(10)})
    a = assign_sessions(sessions, 0.35, 0.15, seed=7)
    b = assign_sessions(list(reversed(sessions)), 0.35, 0.15, seed=7)
    assert a == b


def test_new_sessions_go_to_train_and_test_stays_frozen(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "splits.json"
    _make_raw(raw, {f"s{i}": 3 for i in range(6)})
    first = assign(raw, out, 0.35, 0.15, seed=0)

    _make_raw(raw, {"later": 3})
    second = assign(raw, out, 0.35, 0.15, seed=0)
    assert "later" in second["splits"]["train"]["sessions"]
    assert second["splits"]["test"] == first["splits"]["test"]
    assert verify(raw, out) == []


def test_verify_detects_tampering(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "splits.json"
    _make_raw(raw, {f"s{i}": 3 for i in range(6)})
    manifest = assign(raw, out, 0.35, 0.15, seed=0)
    test_session = manifest["splits"]["test"]["sessions"][0]
    victim = next(iter(manifest["splits"]["test"]["files"]))

    _screen(6, shift=40).save(raw / victim)  # edit a test frame
    _screen(2).save(raw / test_session / "extra.png")  # sneak one in
    problems = verify(raw, out)
    assert f"modified: {victim}" in problems
    assert f"added: {test_session}/extra.png" in problems


def test_scan_reads_sessions_from_disk(tmp_path: Path) -> None:
    _make_raw(tmp_path, {"x": 2, "y": 1})
    (tmp_path / "empty").mkdir()
    found = {s.name: len(s.files) for s in scan_sessions(tmp_path)}
    assert found == {"x": 2, "y": 1}


def test_refuses_to_freeze_with_too_few_sessions(tmp_path: Path) -> None:
    _make_raw(tmp_path / "raw", {"only": 3})
    with pytest.raises(SystemExit):
        assign(tmp_path / "raw", tmp_path / "splits.json", 0.35, 0.15, seed=0)
