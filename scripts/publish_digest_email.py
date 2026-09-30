#!/usr/bin/env python3
"""Create/send the exact same-date Woods Run Digest broadcast through Resend.

This is intentionally idempotent. It never clones a prior-date broadcast.
It reads the newest issue from data/issues.json and the canonical dated page,
creates a same-date broadcast only when one does not exist, and sends only a
validated same-date draft.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

API = "https://api.resend.com"
SEGMENT_ID = os.environ.get("WOODS_RUN_SEGMENT_ID", "").strip()
API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
FROM = "Steve Bick | Woods Run Digest <no_reply@forestenterprise.org>"
REPLY_TO = "steve@northeastforests.com"

def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)

def request(method: str, path: str, body: dict | None = None) -> dict:
    if not API_KEY:
        fail("RESEND_API_KEY secret is not configured")
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "WoodsRunDigest/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        fail(f"Resend HTTP {exc.code}: {exc.read().decode(errors='replace')}")

def latest_issue() -> dict:
    issues = json.loads(Path("data/issues.json").read_text())
    if not issues:
        fail("data/issues.json is empty")
    issue = issues[0]
    for key in ("date", "displayDate", "url", "summary"):
        if not issue.get(key):
            fail(f"latest issue missing {key}")
    return issue

def canonical_html(issue: dict) -> str:
    y, m, d = issue["date"].split("-")
    path = Path(y) / m / d / "index.html"
    if not path.exists():
        fail(f"canonical page missing: {path}")
    html = path.read_text()
    if issue["displayDate"] not in html or issue["url"] not in html:
        fail("canonical page does not match newest issue metadata")
    return html

def text_from_html(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def email_html(issue: dict, page_html: str) -> str:
    # Use the canonical article body as source and wrap it in stable email-safe markup.
    body = page_html.split("<main>",1)[1].split("</main>",1)[0] if "<main>" in page_html else page_html
    # Strip site navigation/header/footer and retain article content. The canonical
    # page is authoritative; links remain absolute or site-root relative.
    body = re.sub(r"<header[\s\S]*?</header>", "", body, flags=re.I)
    body = body.replace('href="/', 'href="https://woodsrun.forestenterprise.org/')
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="X-UA-Compatible" content="IE=edge"></head><body style="margin:0;background-color:#f2eee5;"><table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f2eee5"><tr><td align="center" style="padding-top:24px;padding-right:12px;padding-bottom:24px;padding-left:12px;"><table width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="#fffdf8" style="width:100%;max-width:600px;background-color:#fffdf8;"><tr><td style="padding-top:28px;padding-right:30px;padding-bottom:28px;padding-left:30px;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:23px;color:#333333;"><p style="font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:34px;color:#1f3b2b;font-weight:bold;">WOODS RUN DIGEST</p><p style="font-family:Georgia,'Times New Roman',serif;font-size:26px;line-height:32px;color:#222222;">{issue['displayDate']}</p>{body}<p style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:18px;color:#777777;"><a href="{{{{{{RESEND_UNSUBSCRIBE_URL}}}}}}" style="color:#777777;">Unsubscribe</a></p></td></tr></table></td></tr></table></body></html>"""

def list_broadcasts() -> list[dict]:
    data = request("GET", "/broadcasts")
    return data.get("data", data if isinstance(data, list) else [])

def main() -> None:
    if not SEGMENT_ID:
        fail("WOODS_RUN_SEGMENT_ID is missing")
    issue = latest_issue()
    page = canonical_html(issue)
    subject = f"Woods Run Digest — {issue['displayDate']}"
    url = "https://woodsrun.forestenterprise.org" + issue["url"]
    broadcasts = list_broadcasts()
    exact = [b for b in broadcasts if b.get("name") == subject]
    if exact:
        b = exact[0]
        if b.get("status") == "sent":
            print(f"Same-date broadcast already sent: {b.get('id')}")
            return
        broadcast_id = b["id"]
        detail = request("GET", f"/broadcasts/{broadcast_id}")
        content = (detail.get("html") or "") + "\n" + (detail.get("text") or "")
        if issue["displayDate"] not in content or url not in content:
            fail("existing same-date draft failed date/URL validation; refusing to send stale content")
    else:
        html = email_html(issue, page)
        text = text_from_html(page) + f"\n\nRead today's edition: {url}"
        created = request("POST", "/broadcasts", {
            "name": subject,
            "segment_id": SEGMENT_ID,
            "from": FROM,
            "reply_to": [REPLY_TO],
            "subject": subject,
            "preview_text": issue.get("socialText") or issue["summary"],
            "html": html,
            "text": text,
        })
        broadcast_id = created.get("id")
        if not broadcast_id:
            fail(f"broadcast creation returned no id: {created}")
    request("POST", f"/broadcasts/{broadcast_id}/send", {})
    print(f"Sent same-date broadcast: {broadcast_id}")

if __name__ == "__main__":
    main()
