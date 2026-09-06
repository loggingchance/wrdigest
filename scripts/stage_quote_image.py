#!/usr/bin/env python3
"""Download today's prepared quote card from Dropbox into a stable public repo path.

Buffer's API requires media URLs that resolve directly to a publicly accessible file.
Dropbox share/raw links may redirect or otherwise be rejected by Buffer, so the GitHub
workflow stages the selected card in this repository first. The publisher then points
Buffer at raw.githubusercontent.com.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

POST_FILE = Path("data/quote_post.json")
ASSET_DIR = Path("assets/quote-posts")


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def safe_filename(name: str) -> str:
    name = Path(name).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return stem or "quote-card.jpg"


def staged_path(prepared: dict) -> Path:
    return ASSET_DIR / f"{prepared['date']}_{safe_filename(prepared['filename'])}"


def looks_like_image(data: bytes) -> bool:
    return (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP")
    )


def main() -> None:
    if not POST_FILE.exists():
        fail(f"Missing {POST_FILE}")
    prepared = json.loads(POST_FILE.read_text(encoding="utf-8"))
    for field in ("date", "filename", "imageUrl"):
        if not prepared.get(field):
            fail(f"{POST_FILE} is missing {field}")

    target = staged_path(prepared)
    target.parent.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(
        prepared["imageUrl"],
        headers={
            "User-Agent": "WoodsRunDigest/1.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        fail(f"Could not download quote card: HTTP {exc.code}")
    except Exception as exc:
        fail(f"Could not download quote card: {exc}")

    if len(data) < 1024:
        fail(f"Downloaded quote card is unexpectedly small ({len(data)} bytes)")
    if not looks_like_image(data):
        fail(f"Downloaded quote card is not a recognized JPG/PNG/WebP image (Content-Type: {content_type})")

    target.write_bytes(data)
    print(f"Staged quote card: {target} ({len(data)} bytes; {content_type or 'unknown type'})")


if __name__ == "__main__":
    main()
