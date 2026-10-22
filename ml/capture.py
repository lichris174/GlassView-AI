"""Capture screenshots for the dataset, one session at a time.

    python -m ml.capture --session banking-fake-01 --interval 3

Every ``interval`` seconds it grabs the primary monitor and saves the frame only
if it differs from the last saved one (perceptual hash), so idle screens do not
flood the dataset with near-copies. Each frame's metadata (time, foreground app,
window title) goes to ``meta.jsonl`` in the session folder. Stop with Ctrl+C.

Run it only during deliberate sessions with fake data. Anything on screen is
captured, including real secrets; see docs/LABELING_GUIDE.md.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

from .paths import raw_dir

# Frames whose hashes differ in fewer bits than this are treated as duplicates.
# dHash is 64 bits; 6 bits is roughly "a cursor moved or a clock ticked".
DEFAULT_DUP_BITS = 6


# --- perceptual hash ---------------------------------------------------------
def dhash(image: Image.Image, size: int = 8) -> int:
    """Difference hash: 64 bits recording whether each pixel is brighter than its
    right-hand neighbour on a tiny grayscale thumbnail. Small visual changes flip
    few bits; a different screen flips many."""
    small = image.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    px = small.load()
    bits = 0
    for y in range(size):
        for x in range(size):
            bits = (bits << 1) | int(px[x, y] > px[x + 1, y])
    return bits


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def is_near_duplicate(a: int, b: int | None, max_bits: int = DEFAULT_DUP_BITS) -> bool:
    return b is not None and hamming(a, b) < max_bits


# --- foreground window (Windows; best effort elsewhere) -----------------------
def foreground_window() -> tuple[str, str]:
    """(process name, window title) of the focused window, or ("", "") if unknown.

    Recorded so the dataset can be summarized by app and so near-identical
    frames from one app can be kept on the same side of the train/test split.
    """
    if sys.platform != "win32":
        return "", ""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    title_buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title_buf, 512)

    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_query_limited_information = 0x1000
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid.value)
    name = ""
    if handle:
        try:
            path_buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, path_buf, ctypes.byref(size)):
                name = Path(path_buf.value).name
        finally:
            kernel32.CloseHandle(handle)
    return name, title_buf.value


# --- capture loop --------------------------------------------------------------
@dataclass(frozen=True)
class FrameMeta:
    file: str
    session: str
    captured_at: str
    process: str
    window_title: str
    width: int
    height: int
    dhash: str


_SESSION_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def validate_session(name: str) -> str:
    """Session names become folder names and split keys, so keep them plain."""
    if not _SESSION_RE.match(name):
        raise argparse.ArgumentTypeError(
            "session must be lowercase letters, digits, '-' or '_' (max 64 chars)"
        )
    return name


def grab_primary() -> Image.Image:
    import mss  # imported here so the pure helpers above need no capture deps

    factory = getattr(mss, "MSS", None) or mss.mss  # MSS in mss>=10, mss() before
    with factory() as sct:
        shot = sct.grab(sct.monitors[1])  # [0] is the union of all monitors
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def save_frame(image: Image.Image, session_dir: Path, session: str, h: int) -> FrameMeta:
    now = datetime.now()
    name = now.strftime("%Y%m%d-%H%M%S-%f")[:-3] + ".png"
    image.save(session_dir / name, optimize=False)
    process, title = foreground_window()
    meta = FrameMeta(
        file=name,
        session=session,
        captured_at=now.isoformat(timespec="milliseconds"),
        process=process,
        window_title=title,
        width=image.width,
        height=image.height,
        dhash=f"{h:016x}",
    )
    with (session_dir / "meta.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(meta)) + "\n")
    return meta


def run(session: str, interval: float, max_frames: int | None, dup_bits: int) -> int:
    session_dir = raw_dir() / session
    session_dir.mkdir(parents=True, exist_ok=True)
    print(f"Capturing to {session_dir} every {interval}s. Ctrl+C to stop.")
    last: int | None = None
    saved = skipped = 0
    try:
        while max_frames is None or saved < max_frames:
            image = grab_primary()
            h = dhash(image)
            if is_near_duplicate(h, last, dup_bits):
                skipped += 1
            else:
                meta = save_frame(image, session_dir, session, h)
                last = h
                saved += 1
                print(f"  saved {meta.file}  [{meta.process or '?'}]")
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    print(f"Done: {saved} saved, {skipped} skipped as near-duplicates.")
    return saved


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--session", required=True, type=validate_session,
                   help="name for this capture session, e.g. banking-fake-01")
    p.add_argument("--interval", type=float, default=3.0, help="seconds between grabs")
    p.add_argument("--max-frames", type=int, default=None, help="stop after N saved frames")
    p.add_argument("--dup-bits", type=int, default=DEFAULT_DUP_BITS,
                   help="hash distance below which a frame counts as a duplicate")
    args = p.parse_args(argv)
    run(args.session, args.interval, args.max_frames, args.dup_bits)


if __name__ == "__main__":
    main()
