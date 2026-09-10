#!/usr/bin/env python3
"""Stage the original FBS quote-card image selected from Dropbox.

The daily ChatGPT task writes quote metadata plus a short-lived Dropbox download URL to
``data/quote_post.json``. This script downloads that exact JPG and copies it into the
stable public repository path used by Buffer. It does not redraw, restyle, or otherwise
re-render the card.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

POST_FILE = Path("data/quote_post.json")
ASSET_DIR = Path("assets/quote-posts")
MAX_IMAGE_BYTES = 20 * 1024 * 1024


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


def validate_download_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        fail("dropboxDownloadUrl must use HTTPS")
    host = (parsed.hostname or "").lower()
    if not (host == "dropboxusercontent.com" or host.endswith(".dropboxusercontent.com")):
        fail(f"Unexpected Dropbox download host: {host or '(missing)'}")


def looks_like_image(data: bytes, content_type: str) -> bool:
    if data.startswith(b"\xff\xd8\xff"):
        return True
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    return content_type.lower().startswith("image/")


def download_original(url: str) -> bytes:
    validate_download_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "WoodsRunDigest/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read(MAX_IMAGE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        body = exc.read(500).decode("utf-8", errors="replace")
        fail(f"Dropbox image download failed with HTTP {exc.code}: {body}")
    except Exception as exc:
        fail(f"Dropbox image download failed: {exc}")

    if not data:
        fail("Dropbox returned an empty quote-card file")
    if len(data) > MAX_IMAGE_BYTES:
        fail(f"Quote-card image exceeds {MAX_IMAGE_BYTES} bytes")
    if not looks_like_image(data, content_type):
        fail(f"Dropbox response is not an image (Content-Type: {content_type!r})")
    return data


def main() -> None:
    if not POST_FILE.exists():
        fail(f"Missing {POST_FILE}")

    prepared = json.loads(POST_FILE.read_text(encoding="utf-8"))
    required = ("date", "quoteIndex", "filename", "source", "dropboxDownloadUrl")
    for field in required:
        if prepared.get(field) in (None, ""):
            fail(f"{POST_FILE} is missing {field}")

    data = download_original(str(prepared["dropboxDownloadUrl"]).strip())
    target = staged_path(prepared)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    print(f"Staged original Dropbox quote card unchanged: {target} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
