#!/usr/bin/env python3
"""Generate date-specific social share cards for Woods Run Digest.

Reads data/issues.json and writes 1200x630 PNG cards to assets/cards/YYYY-MM-DD.png.
New issues may provide cardTeaser and cardSubhead fields. When present, those
become the dominant daily element while Woods Run branding, date, weekday color,
footer illustration, and URL remain consistent. Older issues without teaser
fields retain the legacy date-led layout.
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


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if text_width(draw, trial, fnt) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def fit_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: Path,
    max_width: int,
    max_lines: int,
    start_size: int,
    min_size: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for size in range(start_size, min_size - 1, -1):
        fnt = font(font_path, size)
        lines = wrap_text(draw, text, fnt, max_width)
        if len(lines) <= max_lines:
            return fnt, lines
    fnt = font(font_path, min_size)
    lines = wrap_text(draw, text, fnt, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and text_width(draw, last + "…", fnt) > max_width:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return fnt, lines


def add_artwork(base: Image.Image, weekday: str) -> None:
    artwork = Image.open(ART_FILE).convert("RGBA")
    scale = WIDTH / artwork.width
    artwork = artwork.resize((WIDTH, round(artwork.height * scale)), Image.Resampling.LANCZOS)
    artwork = ImageEnhance.Contrast(artwork.convert("RGB")).enhance(1.05).convert("RGBA")
    artwork.putalpha(118)
    art_y = HEIGHT - artwork.height
    base.alpha_composite(artwork, (0, art_y))
    tint = Image.new("RGBA", (WIDTH, artwork.height), (*rgb(DAY_COLORS[weekday]), 70))
    base.alpha_composite(tint, (0, art_y))


def render_teaser_card(base: Image.Image, issue: dict, edition_date: date, weekday: str) -> None:
    draw = ImageDraw.Draw(base)
    draw.rectangle((0, 0, WIDTH, 12), fill=FOREST)

    # Compact masthead preserves the established identity while giving the
    # daily reporting teaser most of the visual weight.
    draw.text((72, 54), "WOODS RUN DIGEST", font=font(FONT_SANS_BOLD, 38), fill=INK)
    date_label = f"{weekday.upper()} · {edition_date.strftime('%B %-d, %Y')}"
    draw.text((72, 108), date_label, font=font(FONT_SANS_BOLD, 19), fill=FOREST)
    draw.line((72, 148, 1128, 148), fill=FOREST, width=2)

    teaser = str(issue.get("cardTeaser", "")).strip()
    subhead = str(issue.get("cardSubhead", "")).strip()

    teaser_font, teaser_lines = fit_wrapped_text(
        draw, teaser, FONT_SERIF_BOLD, 1010, 3, 52, 39
    )
    y = 178
    line_gap = 10
    for line in teaser_lines:
        draw.text((72, y), line, font=teaser_font, fill=INK)
        bbox = draw.textbbox((72, y), line, font=teaser_font)
        y = bbox[3] + line_gap

    if subhead:
        y += 10
        sub_font, sub_lines = fit_wrapped_text(
            draw, subhead, FONT_SANS, 1010, 2, 27, 22
        )
        for line in sub_lines:
            draw.text((72, y), line, font=sub_font, fill=MUTED)
            bbox = draw.textbbox((72, y), line, font=sub_font)
            y = bbox[3] + 7

    # A quiet separator keeps the reporting content distinct from the footer art.
    separator_y = min(max(y + 18, 410), 450)
    draw.line((72, separator_y, 1128, separator_y), fill=FOREST, width=1)

    draw.rounded_rectangle((72, 470, 515, 521), radius=12, fill=(*rgb(PAPER), 220), outline=FOREST, width=2)
    draw.text((95, 483), "woodsrun.forestenterprise.org", font=font(FONT_SANS_BOLD, 20), fill=FOREST)
    draw.text((72, 574), "Prepared from public sources · Links lead to original material", font=font(FONT_SANS, 15), fill="#464842")


def render_legacy_card(base: Image.Image, edition_date: date, weekday: str) -> None:
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


def render_card(issue: dict, output: Path) -> None:
    date_string = issue["date"]
    edition_date = date.fromisoformat(date_string)
    weekday = edition_date.strftime("%A")

    base = Image.new("RGB", (WIDTH, HEIGHT), DAY_COLORS[weekday]).convert("RGBA")
    paper_glaze = Image.new("RGBA", base.size, (*rgb(PAPER), 135))
    base = Image.alpha_composite(base, paper_glaze)
    add_artwork(base, weekday)

    if str(issue.get("cardTeaser", "")).strip():
        render_teaser_card(base, issue, edition_date, weekday)
    else:
        render_legacy_card(base, edition_date, weekday)

    output.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(output, "PNG", optimize=True)


def main() -> None:
    issues = json.loads(ISSUES_FILE.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for issue in issues:
        date_string = issue["date"]
        render_card(issue, OUT_DIR / f"{date_string}.png")
        mode = "teaser" if str(issue.get("cardTeaser", "")).strip() else "legacy"
        print(f"generated assets/cards/{date_string}.png ({mode})")


if __name__ == "__main__":
    main()
