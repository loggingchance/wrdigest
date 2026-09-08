#!/usr/bin/env python3
"""Render today's prepared FBS quote card locally into a stable public repo path.

The scheduled ChatGPT task writes only ordinary quote metadata/text to data/quote_post.json.
No Dropbox download URL or other temporary credential crosses into the public repository.
This script turns that safe payload into the social image inside GitHub Actions, after which
Buffer receives a stable raw.githubusercontent.com URL.
"""

from __future__ import annotations

import json
import math
import random
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

POST_FILE = Path("data/quote_post.json")
ASSET_DIR = Path("assets/quote-posts")
WIDTH, HEIGHT = 1536, 1024

PARCHMENT = (235, 225, 199)
INK = (54, 49, 39)
MUTED_INK = (92, 82, 62)
GREEN = (54, 79, 56)
LIGHT_GREEN = (105, 119, 91)
LINE = (120, 105, 76)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def safe_filename(name: str) -> str:
    name = Path(name).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    if not stem:
        return "quote-card.jpg"
    if not Path(stem).suffix:
        stem += ".jpg"
    return stem


def staged_path(prepared: dict) -> Path:
    return ASSET_DIR / f"{prepared['date']}_{safe_filename(prepared['filename'])}"


def font_path(*names: str) -> str:
    roots = [
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation2"),
        Path("/usr/share/fonts/truetype/liberation"),
    ]
    for root in roots:
        for name in names:
            p = root / name
            if p.exists():
                return str(p)
    fail(f"Could not locate a usable font: {', '.join(names)}")


def load_fonts(quote_size: int) -> dict[str, ImageFont.FreeTypeFont]:
    serif = font_path("DejaVuSerif.ttf", "LiberationSerif-Regular.ttf")
    serif_bold = font_path("DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf")
    serif_italic = font_path("DejaVuSerif-Italic.ttf", "LiberationSerif-Italic.ttf")
    sans = font_path("DejaVuSans.ttf", "LiberationSans-Regular.ttf")
    sans_bold = font_path("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf")
    return {
        "title": ImageFont.truetype(serif_bold, 54),
        "quote": ImageFont.truetype(serif_italic, quote_size),
        "attrib": ImageFont.truetype(serif, 32),
        "url": ImageFont.truetype(sans_bold, 25),
        "small": ImageFont.truetype(sans, 18),
    }


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = word if not line else f"{line} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def fit_quote(draw: ImageDraw.ImageDraw, quote: str, max_width: int, max_height: int):
    for size in range(66, 39, -2):
        fonts = load_fonts(size)
        lines = wrap_text(draw, quote, fonts["quote"], max_width)
        line_height = int(size * 1.34)
        if len(lines) * line_height <= max_height:
            return fonts, lines, line_height
    fonts = load_fonts(40)
    lines = wrap_text(draw, quote, fonts["quote"], max_width)
    return fonts, lines, 54


def draw_parchment_texture(draw: ImageDraw.ImageDraw, seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(2100):
        x = rng.randrange(WIDTH)
        y = rng.randrange(HEIGHT)
        r = rng.choice((1, 1, 1, 2))
        delta = rng.choice((-10, -7, -5, 5, 7))
        c = tuple(max(0, min(255, v + delta)) for v in PARCHMENT)
        draw.ellipse((x-r, y-r, x+r, y+r), fill=c)


def draw_leaf(draw: ImageDraw.ImageDraw, cx: float, cy: float, scale: float, angle: float) -> None:
    pts = []
    for i in range(12):
        a = i * math.pi / 6
        radius = scale * (1.0 if i % 2 == 0 else 0.58)
        x = radius * math.cos(a)
        y = radius * math.sin(a) * 0.72
        ca, sa = math.cos(angle), math.sin(angle)
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    draw.line(pts + [pts[0]], fill=LINE, width=2)
    tip = (cx + scale * 1.15 * math.cos(angle), cy + scale * 1.15 * math.sin(angle))
    draw.line((cx, cy, tip[0], tip[1]), fill=LINE, width=2)


def draw_tree(draw: ImageDraw.ImageDraw) -> None:
    trunk_x = 1175
    base_y = 845
    top_y = 260
    draw.line((trunk_x, base_y, trunk_x - 10, top_y + 180), fill=GREEN, width=8)
    draw.line((trunk_x + 15, base_y, trunk_x + 6, top_y + 185), fill=GREEN, width=5)
    branches = [
        ((1170, 510), (1040, 390)), ((1170, 510), (1280, 370)),
        ((1168, 430), (1080, 310)), ((1172, 425), (1250, 300)),
        ((1165, 590), (1010, 510)), ((1178, 585), (1335, 505)),
    ]
    for a, b in branches:
        draw.line((*a, *b), fill=GREEN, width=4)
    canopy = [
        (1010, 330, 1135, 455), (1080, 245, 1210, 395), (1195, 250, 1325, 400),
        (1260, 340, 1390, 480), (990, 430, 1120, 565), (1200, 420, 1375, 575),
    ]
    for box in canopy:
        draw.ellipse(box, outline=LIGHT_GREEN, width=3)
    for leaf in [
        (1035, 300, 22, -0.5), (1080, 250, 18, 0.2), (1300, 280, 22, 0.8),
        (1360, 390, 20, -0.2), (1020, 505, 21, 0.4), (1320, 520, 21, -0.7),
    ]:
        draw_leaf(draw, *leaf)


def draw_log_end(draw: ImageDraw.ImageDraw) -> None:
    cx, cy, r = 1290, 750, 110
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=LINE, width=4)
    for rr in (84, 59, 34, 12):
        draw.ellipse((cx-rr, cy-rr, cx+rr, cy+rr), outline=LINE, width=2)
    draw.line((cx-5, cy-5, cx+90, cy-55), fill=LINE, width=2)
    draw.line((cx, cy, cx-62, cy+72), fill=LINE, width=2)


def draw_lumber_stack(draw: ImageDraw.ImageDraw) -> None:
    x, y = 1015, 845
    widths = [300, 285, 315, 270]
    for i, w in enumerate(widths):
        yy = y + i * 25
        draw.rectangle((x, yy, x+w, yy+17), outline=LINE, width=2)
        for tick in range(x + 35, x + w, 62):
            draw.line((tick, yy+2, tick+18, yy+15), fill=LINE, width=1)


def render(prepared: dict, target: Path) -> None:
    quote = str(prepared["quote"]).strip().strip('"')
    attribution = str(prepared["attribution"]).strip()

    image = Image.new("RGB", (WIDTH, HEIGHT), PARCHMENT)
    draw = ImageDraw.Draw(image)
    seed = int(prepared.get("quoteIndex", 0)) * 1000003 + sum(map(ord, prepared["date"]))
    draw_parchment_texture(draw, seed)

    draw.rectangle((42, 40, WIDTH-42, HEIGHT-42), outline=LINE, width=2)
    draw.line((950, 175, 950, 900), fill=(151, 135, 103), width=2)
    draw.line((92, 154, 900, 154), fill=GREEN, width=4)

    fonts, lines, line_height = fit_quote(draw, quote, 780, 495)

    draw.text((92, 72), "The Forest Business School", font=fonts["title"], fill=GREEN)
    draw.text((99, 125), "FIELD NOTES · WORK · WOODS · ENTERPRISE", font=fonts["small"], fill=MUTED_INK)

    qx, qy = 108, 255
    open_quote_font = ImageFont.truetype(font_path("DejaVuSerif.ttf", "LiberationSerif-Regular.ttf"), 90)
    draw.text((82, 205), "“", font=open_quote_font, fill=(126, 111, 82))
    for line in lines:
        draw.text((qx, qy), line, font=fonts["quote"], fill=INK)
        qy += line_height
    draw.text((qx, qy + 34), f"— {attribution}", font=fonts["attrib"], fill=MUTED_INK)

    draw_tree(draw)
    draw_log_end(draw)
    draw_lumber_stack(draw)

    draw.line((1030, 205, 1390, 205), fill=(160, 145, 112), width=1)
    draw.text((1030, 175), "HARDWOOD / WORKING FOREST", font=fonts["small"], fill=MUTED_INK)
    for i in range(5):
        yy = 230 + i * 17
        draw.line((1360, yy, 1410, yy), fill=(160, 145, 112), width=1)

    draw.text((1110, 950), "www.forestenterprise.org", font=fonts["url"], fill=GREEN)

    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "JPEG", quality=92, optimize=True)
    print(f"Rendered quote card: {target} ({target.stat().st_size} bytes)")


def main() -> None:
    if not POST_FILE.exists():
        fail(f"Missing {POST_FILE}")
    prepared = json.loads(POST_FILE.read_text(encoding="utf-8"))
    required = ("date", "quoteIndex", "filename", "source", "attribution", "quote")
    for field in required:
        if prepared.get(field) in (None, ""):
            fail(f"{POST_FILE} is missing {field}")

    target = staged_path(prepared)
    render(prepared, target)


if __name__ == "__main__":
    main()
