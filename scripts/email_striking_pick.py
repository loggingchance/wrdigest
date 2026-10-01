#!/usr/bin/env python3
"""Email today's prepared Woods Run striking pick through Resend."""
import json, os, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo("America/Denver")
api_key=os.environ.get("RESEND_API_KEY","").strip()
if not api_key: raise SystemExit("RESEND_API_KEY is not configured")
issues=json.loads(Path("data/issues.json").read_text(encoding="utf-8"))
if not issues: raise SystemExit("No Woods Run issues found")
issue=issues[0]
today=datetime.now(TZ).date().isoformat()
if issue.get("date") != today:
    raise SystemExit(f"Newest issue is {issue.get('date')}, not {today}; no email sent")
pick=(issue.get("strikingText") or "").strip()
if not pick:
    raise SystemExit("Today's issue has no strikingText; no email sent")
if len(pick)>260:
    raise SystemExit(f"strikingText is {len(pick)} chars; maximum is 260")
subject=f"Woods Run Striking Pick — {issue.get('displayDate', today)}"
source=(issue.get("cardTeaser") or issue.get("summary") or "").strip()
text=f"{pick}\n\nSource item: {source}\n"
html=f"""<!doctype html><html><body style="font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.5">
<div style="max-width:640px;margin:auto;border-top:5px solid #244a34;padding:24px">
<div style="font-family:Georgia,serif;font-size:24px;color:#1f3b2b;margin-bottom:18px">Woods Run Striking Pick</div>
<div style="font-size:19px;line-height:1.45;margin-bottom:20px">{pick}</div>
<div style="font-size:13px;color:#666">Source item: {source}</div>
</div></body></html>"""
payload=json.dumps({
 "from":"Steve Bick | Woods Run Digest <no_reply@forestenterprise.org>",
 "to":["steve@northeastforests.com"],
 "reply_to":["steve@northeastforests.com"],
 "subject":subject,"text":text,"html":html,
 "headers":{"X-Entity-Ref-ID":f"woods-run-striking-email-{today}"}
}).encode()
req=urllib.request.Request("https://api.resend.com/emails",data=payload,method="POST",headers={
 "Authorization":f"Bearer {api_key}","Content-Type":"application/json",
 "Idempotency-Key":f"woods-run-striking-email-{today}",
 "User-Agent":"WoodsRunDigest-StrikingEmail/1.0"})
try:
 with urllib.request.urlopen(req,timeout=30) as response:
  result=json.loads(response.read().decode())
except urllib.error.HTTPError as exc:
 raise SystemExit(f"Resend HTTP {exc.code}: {exc.read().decode(errors='replace')}")
if not result.get("id"): raise SystemExit(f"Resend returned no email id: {result}")
print(f"RESEND_EMAIL_ID={result['id']}")
print(f"SUBJECT={subject}")
