"""Render synthetic screens to PNG + YOLO labels with a headless browser.

    python -m ml.synth.render --count 1500            # into <data>/synth/v1
    python -m ml.synth.render --count 24 --preview    # also draw boxes to check

Each screen randomizes the app template, theme (light/dark, accent, font,
size), window size, browser zoom, and whether two apps are tiled side by side.
Boxes come from ``data-s`` elements, clipped to what is actually visible
(scrolled-off or overflow-hidden parts are cut), so labels match pixels.
The same ``--seed`` always produces the same dataset.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from faker import Faker
from PIL import Image, ImageDraw

from ..labels import CLASSES, Box, to_yolo
from ..paths import data_root
from . import templates as T

SIZES = ((1280, 720), (1366, 768), (1440, 900), (1536, 864), (1600, 900), (1920, 1080),
         (2560, 1440), (1280, 800))
SCALES = (1.0, 1.25, 1.5)
FONTS = ("Segoe UI", "Arial", "Calibri", "Verdana", "Tahoma", "Georgia", "Trebuchet MS")
MONO = ("Consolas", "Cascadia Mono", "Courier New", "Lucida Console")
# Visible boxes smaller than this (CSS px) are dropped: unreadable at that size.
MIN_SIDE = 4

# Reads every tagged element's box, intersected with each clipping ancestor and
# the viewport, so hidden overflow never becomes a label.
EXTRACT_JS = """
() => {
  const vw = innerWidth, vh = innerHeight, out = [];
  for (const el of document.querySelectorAll('[data-s]')) {
    let r = el.getBoundingClientRect();
    let x1 = r.left, y1 = r.top, x2 = r.right, y2 = r.bottom;
    for (let p = el.parentElement; p; p = p.parentElement) {
      const o = getComputedStyle(p).overflow;
      if (o !== 'visible') {
        const q = p.getBoundingClientRect();
        x1 = Math.max(x1, q.left); y1 = Math.max(y1, q.top);
        x2 = Math.min(x2, q.right); y2 = Math.min(y2, q.bottom);
      }
    }
    x1 = Math.max(0, x1); y1 = Math.max(0, y1); x2 = Math.min(vw, x2); y2 = Math.min(vh, y2);
    if (x2 - x1 > 0 && y2 - y1 > 0) out.push([el.dataset.s, x1, y1, x2, y2]);
  }
  return out;
}
"""


def theme_css(r: random.Random) -> str:
    dark = r.random() < 0.5
    hue = r.randrange(360)
    bg, fg = (f"hsl({hue} 12% {r.randrange(6, 16)}%)", "#e8e8e8") if dark else \
             (f"hsl({hue} 20% {r.randrange(94, 100)}%)", "#1d1d1f")
    panel = f"hsl({hue} 12% {r.randrange(14, 22)}%)" if dark else f"hsl({hue} 15% {r.randrange(88, 96)}%)"
    border = "#ffffff1f" if dark else "#0000001a"
    return f"""
    :root {{ --bg:{bg}; --fg:{fg}; --panel:{panel}; --border:{border};
      --muted:{'#9aa0a6' if dark else '#6b6f76'}; --accent:hsl({r.randrange(360)} 70% 55%); }}
    * {{ box-sizing:border-box; }}
    html,body {{ margin:0; height:100%; background:var(--bg); color:var(--fg);
      font-family:'{r.choice(FONTS)}',sans-serif; font-size:{r.randrange(12, 17)}px; overflow:hidden; }}
    .screen {{ display:flex; height:100%; gap:{r.choice((0, 0, 4, 8))}px; }}
    .pane {{ flex:1; min-width:0; display:flex; flex-direction:column; overflow:hidden;
      border:1px solid var(--border); }}
    .chrome {{ height:34px; display:flex; align-items:center; gap:8px; padding:0 10px;
      background:var(--panel); border-bottom:1px solid var(--border); }}
    .url {{ flex:1; background:var(--bg); border-radius:14px; padding:4px 12px; color:var(--muted); }}
    .taskbar {{ position:fixed; bottom:0; left:0; right:0; height:40px; background:var(--panel);
      border-top:1px solid var(--border); }}
    .app {{ flex:1; min-height:0; overflow:hidden; display:flex; }}
    .row {{ display:flex; flex-direction:row; }} .col {{ display:flex; flex-direction:column; }}
    .wrap {{ flex-wrap:wrap; }} .gap {{ gap:10px; }} .grow {{ flex:1; min-height:0; min-width:0; overflow:hidden; }}
    .between {{ justify-content:space-between; }} .pad {{ padding:{r.randrange(12, 28)}px; }}
    .center {{ align-items:center; justify-content:center; }}
    .side {{ width:{r.randrange(160, 260)}px; background:var(--panel); border-right:1px solid var(--border);
      padding:10px; overflow:hidden; flex-shrink:0; }}
    .brand {{ font-weight:700; margin:4px 6px 12px; }}
    .nav {{ padding:6px 8px; border-radius:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .nav.on {{ background:var(--accent); color:white; }}
    .bar {{ display:flex; align-items:center; gap:8px; padding:10px 14px; border-bottom:1px solid var(--border); }}
    .thread {{ padding:12px; display:flex; flex-direction:column; gap:12px; overflow:hidden; }}
    .msg {{ display:flex; gap:10px; }} .msg.mine {{ flex-direction:row-reverse; text-align:right; }}
    .msg.mine .text {{ background:var(--accent); color:white; }}
    .text {{ background:var(--panel); padding:7px 11px; border-radius:12px; display:inline-block; }}
    .av {{ width:32px; height:32px; border-radius:50%; color:white; display:flex; align-items:center;
      justify-content:center; font-size:12px; flex-shrink:0; }}
    .meta {{ font-size:.85em; margin-bottom:3px; }} .muted {{ color:var(--muted); }}
    .composer {{ padding:10px; border-top:1px solid var(--border); }} .composer input {{ width:100%; }}
    .list {{ width:{r.randrange(320, 480)}px; overflow:hidden; border-right:1px solid var(--border); flex-shrink:0; }}
    .mailrow {{ padding:9px 12px; border-bottom:1px solid var(--border); white-space:nowrap; overflow:hidden;
      text-overflow:ellipsis; }}
    input,textarea,button {{ font:inherit; color:var(--fg); background:var(--bg); border:1px solid var(--border);
      border-radius:6px; padding:8px 10px; }}
    button {{ background:var(--accent); color:white; border:none; }}
    .panel,.card {{ background:var(--panel); border:1px solid var(--border); border-radius:10px; }}
    .card {{ padding:14px; min-width:180px; }} .big {{ font-size:1.6em; font-weight:600; }}
    .field {{ padding:8px 10px; border:1px solid var(--border); border-radius:6px; }}
    .mono,.code,.term {{ font-family:'{r.choice(MONO)}',monospace; }}
    .code {{ margin:0; padding:12px; line-height:1.55; overflow:hidden; background:var(--bg); }}
    .ln {{ display:inline-block; width:3em; color:var(--muted); user-select:none; }}
    .tabs {{ display:flex; background:var(--panel); border-bottom:1px solid var(--border); }}
    .tab {{ padding:8px 14px; color:var(--muted); }} .tab.on {{ color:var(--fg); border-bottom:2px solid var(--accent); }}
    .term {{ margin:0; padding:14px; background:{'#0c0c0c' if r.random() < .6 else 'var(--bg)'};
      color:{'#cccccc' if dark else 'var(--fg)'}; line-height:1.5; white-space:pre-wrap; overflow:hidden; }}
    .accent {{ color:var(--accent); }}
    table {{ border-collapse:collapse; width:100%; }} td {{ padding:6px 10px; border-bottom:1px solid var(--border); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px; overflow:hidden; }}
    .thumb {{ height:110px; border-radius:8px; margin-bottom:8px;
      background:linear-gradient(135deg,hsl({r.randrange(360)} 50% 60%),hsl({r.randrange(360)} 50% 40%)); }}
    .chart {{ height:220px; align-items:flex-end; gap:6px; padding:10px; }}
    .barc {{ flex:1; background:var(--accent); border-radius:3px 3px 0 0; }}
    .idcard {{ width:340px; padding:14px; border-radius:12px; background:hsl({r.randrange(360)} 35% 82%); color:#222; }}
    .photo {{ width:80px; height:100px; border-radius:6px; background:#8a8f99; }}
    """


def screen_html(r: random.Random, fk: Faker) -> tuple[str, list[str]]:
    """A whole screen: one or two tiled panes, optional browser bar and taskbar."""
    n = 2 if r.random() < 0.3 else 1
    names = []
    panes = []
    for _ in range(n):
        pool = T.SENSITIVE if r.random() < 0.7 else T.CLEAN
        name = r.choice(sorted(pool))
        names.append(name)
        chrome = (f'<div class="chrome"><span class="muted">&#9664; &#9654; &#10227;</span>'
                  f'<div class="url">https://{fk.domain_name()}/{fk.uri_path()}</div></div>'
                  if r.random() < 0.6 else "")
        panes.append(f'<div class="pane">{chrome}{pool[name](r, fk)}</div>')
    taskbar = '<div class="taskbar"></div>' if r.random() < 0.4 else ""
    page = (f"<!doctype html><html><head><meta charset='utf-8'><style>{theme_css(r)}</style></head>"
            f"<body><div class='screen'>{''.join(panes)}</div>{taskbar}</body></html>")
    return page, names


def render(count: int, out: Path, seed: int, preview: bool) -> None:
    from playwright.sync_api import sync_playwright

    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    r = random.Random(seed)
    fk = Faker("en_US")
    fk.seed_instance(seed)
    per_class = dict.fromkeys(CLASSES, 0)
    with sync_playwright() as pw, (out / "meta.jsonl").open("w", encoding="utf-8") as meta:
        browser = pw.chromium.launch()
        contexts = {s: browser.new_context(device_scale_factor=s) for s in SCALES}
        for i in range(count):
            scale = r.choice(SCALES)
            w, h = r.choice(SIZES)
            vw, vh = int(w / scale), int(h / scale)  # CSS px so the PNG is w x h
            page = contexts[scale].new_page()
            page.set_viewport_size({"width": vw, "height": vh})
            html, names = screen_html(r, fk)
            page.set_content(html, wait_until="load")
            raw = page.evaluate(EXTRACT_JS)
            name = f"synth-{seed}-{i:05d}"
            page.screenshot(path=str(out / "images" / f"{name}.png"))
            page.close()
            boxes = [Box(c, x1 * scale, y1 * scale, x2 * scale, y2 * scale)
                     for c, x1, y1, x2, y2 in raw
                     if min(x2 - x1, y2 - y1) >= MIN_SIDE]
            with Image.open(out / "images" / f"{name}.png") as im:
                iw, ih = im.size
            (out / "labels" / f"{name}.txt").write_text(to_yolo(boxes, iw, ih), encoding="utf-8")
            for b in boxes:
                per_class[b.cls] += 1
            meta.write(json.dumps({"file": f"{name}.png", "templates": names, "size": [iw, ih],
                                   "scale": scale, "boxes": len(boxes)}) + "\n")
            if (i + 1) % 50 == 0 or i + 1 == count:
                print(f"  {i + 1}/{count}")
        browser.close()
    print("Boxes per class:", per_class)
    if preview:
        draw_preview(out, min(count, 24))


COLORS = {"credential": "#ff3b30", "api_key": "#ff9500", "financial": "#34c759",
          "private_message": "#0a84ff", "personal_id": "#bf5af2"}


def draw_preview(out: Path, n: int) -> Path:
    """Contact sheet of the first ``n`` screens with their boxes, for a quick eyeball."""
    from ..labels import parse_yolo

    thumbs = []
    for img in sorted((out / "images").glob("*.png"))[:n]:
        im = Image.open(img).convert("RGB")
        boxes = parse_yolo((out / "labels" / f"{img.stem}.txt").read_text(), *im.size)
        d = ImageDraw.Draw(im)
        for b in boxes:
            d.rectangle([b.x1, b.y1, b.x2, b.y2], outline=COLORS[b.cls], width=max(3, im.width // 400))
            d.text((b.x1 + 4, b.y1 + 2), b.cls, fill=COLORS[b.cls])
        im.thumbnail((640, 400))
        thumbs.append(im)
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 640, rows * 400), "white")
    for k, t in enumerate(thumbs):
        sheet.paste(t, ((k % cols) * 640, (k // cols) * 400))
    path = out / "preview.jpg"
    sheet.save(path, quality=85)
    print(f"Preview: {path}")
    return path


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Render synthetic labeled screens.")
    p.add_argument("--count", type=int, default=1500)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--name", default="v1", help="output folder under <data>/synth/")
    p.add_argument("--preview", action="store_true")
    args = p.parse_args(argv)
    render(args.count, data_root() / "synth" / args.name, args.seed, args.preview)


if __name__ == "__main__":
    main()
