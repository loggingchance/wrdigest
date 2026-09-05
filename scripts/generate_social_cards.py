#!/usr/bin/env python3
"""Generate date-specific social share cards for Woods Run Digest.

Reads data/issues.json and writes 1200x630 PNG cards to assets/cards/YYYY-MM-DD.png.
The layout remains fixed while the background shade changes by weekday so a new
edition is visually obvious in a social feed.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ISSUES_FILE = ROOT / "data" / "issues.json"
ART_FILE = ROOT / "assets" / "woodsrun-header.webp"
OUT_DIR = ROOT / "assets" / "cards"

WIDTH, HEIGHT = 1200, 630
FOREST = "#244a34"
INK = "#262822"
MUTED = "#556059"
PAPER = "#f8f4ea"

DAY_COLORS = {
    "Monday": "#d8c89c",      # warm straw
    "Tuesday": "#c9d3b7",     # pale sage
    "Wednesday": "#d9c1ad",   # light clay
    "Thursday": "#bcc8cf",    # muted blue-gray
    "Friday": "#d6bf8a",      # light ochre
    "Saturday": "#bfc7a6",    # soft olive
    "Sunday": "#d2cbc1",      # warm gray parchment
}

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONT_SANS_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
FONT_SANS = FONT_DIR / "DejaVuSans.ttf"
FONT_SERIF_BOLD = FONT_DIR / "DejaVuSerif-Bold.ttf"
FONT_SERIF = FONT_DIR / "DejaVuSerif.ttf"


def rgb(hex_value: str) -> tuple[int, int, int]:
    value = hex_value.lstrip("#")
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def render_card(date_string: str, output: Path) -> None:
    edition_date = date.fromisoformat(date_string)
    weekday = edition_date.strftime("%A")

    base = Image.new("RGB", (WIDTH, HEIGHT), DAY_COLORS[weekday]).convert("RGBA")
    paper_glaze = Image.new("RGBA", base.size, (*rgb(PAPER), 135))
    base = Image.alpha_composite(base, paper_glaze)

    # Use the same forestry sketch language as the site masthead, but keep it
    # subordinate to the date and publication name.
    artwork = Image.open(ART_FILE).convert("RGBA")
    scale = WIDTH / artwork.width
    artwork = artwork.resize((WIDTH, round(artwork.height * scale)), Image.Resampling.LANCZOS)
    artwork = ImageEnhance.Contrast(artwork.convert("RGB")).enhance(1.05).convert("RGBA")
    artwork.putalpha(145)
    art_y = HEIGHT - artwork.height
    base.alpha_composite(artwork, (0, art_y))
    tint = Image.new("RGBA", (WIDTH, artwork.height), (*rgb(DAY_COLORS[weekday]), 55))
    base.alpha_composite(tint, (0, art_y))

    draw = ImageDraw.Draw(base)
    draw.rectangle((0, 0, WIDTH, 12), fill=FOREST)
    draw.text((72, 65), "WOODS RUN DIGEST", font=font(FONT_SANS_BOLD, 42), fill=INK)
    draw.text((72, 122), weekday.upper(), font=font(FONT_SANS_BOLD, 21), fill=FOREST)
    draw.text((72, 170), edition_date.strftime("%B %-d, %Y"), font=font(FONT_SERIF_BOLD, 73), fill=INK)
    draw.line((72, 275, 1128, 275), fill=FOREST, width=2)
    draw.text((72, 300), "Daily forestry & forest products intelligence", font=font(FONT_SERIF, 29), fill=INK)
    draw.text((72, 345), "from The Forest Business School", font=font(FONT_SANS, 22), fill=MUTED)

    draw.rounded_rectangle((72, 405, 515, 456), radius=12, fill=(*rgb(PAPER), 215), outline=FOREST, width=2)
    draw.text((95, 418), "woodsrun.forestenterprise.org", font=font(FONT_SANS_BOLD, 20), fill=FOREST)
    draw.text((72, 574), "Prepared from public sources · Links lead to original material", font=font(FONT_SANS, 15), fill="#464842")

    output.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(output, "PNG", optimize=True)


def main() -> None:
    issues = json.loads(ISSUES_FILE.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for issue in issues:
        date_string = issue["date"]
        render_card(date_string, OUT_DIR / f"{date_string}.png")
        print(f"generated assets/cards/{date_string}.png")


if __name__ == "__main__":
    main()
