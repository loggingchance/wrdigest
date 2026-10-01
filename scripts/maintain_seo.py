#!/usr/bin/env python3
import html as html_lib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://woodsrun.forestenterprise.org"

def write_if_changed(path, content, changed):
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old != content:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        changed.append(str(path.relative_to(ROOT)))

def attr(html, pattern, default=""):
    m = re.search(pattern, html, re.S)
    return m.group(1).strip() if m else default

def strip_tags(value):
    return html_lib.unescape(re.sub(r"<[^>]+>", "", value)).strip()

def issue_path(issue):
    y, m, d = issue["date"].split("-")
    return ROOT / y / m / d / "index.html"

issues = json.loads((ROOT / "data/issues.json").read_text(encoding="utf-8"))
if not issues:
    raise SystemExit("data/issues.json is empty")

# Enforce newest-first ordering so all generated surfaces use the same canonical latest issue.
issues = sorted(issues, key=lambda x: x["date"], reverse=True)
latest = issues[0]
latest_path = issue_path(latest)
if not latest_path.exists():
    raise SystemExit(f"Canonical latest issue page missing: {latest_path.relative_to(ROOT)}")

changed = []

# 1. Add NewsArticle structured data to issue pages that do not already have it.
for issue in issues:
    p = issue_path(issue)
    if not p.exists():
        continue
    page = p.read_text(encoding="utf-8")
    if 'application/ld+json' in page:
        continue
    title = attr(page, r"<title>(.*?)</title>", f"Woods Run Digest — {issue['displayDate']}")
    desc = attr(page, r'<meta name="description" content="([^"]*)"', issue.get("summary", "Daily forestry and forest-products intelligence from The Forest Business School."))
    canonical = attr(page, r'<link rel="canonical" href="([^"]*)"', BASE + issue["url"])
    schema = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": strip_tags(title),
        "description": html_lib.unescape(desc),
        "datePublished": issue["date"],
        "dateModified": issue["date"],
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "image": [f"{BASE}/assets/cards/{issue['date']}.png"],
        "publisher": {"@type": "Organization", "name": "The Forest Business School", "url": "https://www.forestenterprise.org"},
        "isPartOf": {"@type": "WebSite", "name": "Woods Run Digest", "url": BASE + "/"},
    }
    block = (
        '<meta name="robots" content="index,follow,max-image-preview:large">'
        '<meta name="author" content="The Forest Business School">'
        '<script type="application/ld+json">'
        + json.dumps(schema, separators=(",", ":")).replace("<", "\\u003c")
        + "</script>"
    )
    page = page.replace("</head>", block + "</head>", 1)
    write_if_changed(p, page, changed)

# 2. Homepage latest block from the canonical latest issue.
latest_html = latest_path.read_text(encoding="utf-8")
headlines = [strip_tags(x) for x in re.findall(r"<h3>(.*?)</h3>", latest_html, re.S)]
bullets = headlines[:3]
if len(bullets) < 3:
    fallback = [latest.get("cardTeaser", ""), latest.get("strikingText", ""), latest.get("summary", "")]
    for item in fallback:
        if item and item not in bullets:
            bullets.append(item)
        if len(bullets) == 3:
            break
latest_block = (
    '<section class="latest-section" aria-labelledby="latest-heading">'
    '<div class="section-heading-row"><div><p class="section-kicker">Latest edition</p>'
    f'<h2 id="latest-heading">{html_lib.escape(latest["displayDate"])}</h2></div>'
    '<span class="edition-date">Daily edition</span></div>'
    '<div class="launch-card latest-callout"><ul class="morning-list">'
    + "".join(f"<li>{html_lib.escape(x)}</li>" for x in bullets)
    + "</ul>"
    f'<a class="read-edition" href="{latest["url"]}">Read the full {html_lib.escape(latest["displayDate"])} edition →</a>'
    "</div></section>"
)
home_path = ROOT / "index.html"
home = home_path.read_text(encoding="utf-8")
new_home, n = re.subn(r'<section class="latest-section"\b.*?</section>', latest_block, home, count=1, flags=re.S)
if n != 1:
    raise SystemExit("Could not locate homepage latest-section")
write_if_changed(home_path, new_home, changed)

# 3. Static archive fallback regenerated from data/issues.json.
archive_items = []
for issue in issues:
    summary = html_lib.escape(issue.get("summary", ""))
    display = html_lib.escape(issue["displayDate"])
    url = issue["url"]
    archive_items.append(
        f'<article class="archive-item"><time datetime="{issue["date"]}">{display}</time>'
        f'<h2><a href="{url}">{display}</a></h2>'
        f'<a class="archive-link" href="{url}">Read edition →</a><p>{summary}</p></article>'
    )
archive_section = '<section class="archive-list" data-archive-list aria-live="polite">' + "".join(archive_items) + "</section>"
archive_path = ROOT / "archive/index.html"
archive_html = archive_path.read_text(encoding="utf-8")
new_archive, n = re.subn(r'<section class="archive-list"\b.*?</section>', archive_section, archive_html, count=1, flags=re.S)
if n != 1:
    raise SystemExit("Could not locate archive-list section")
write_if_changed(archive_path, new_archive, changed)

# 4. Sitemap generated from the same canonical issue list.
fixed = [
    BASE + "/",
    BASE + "/archive/",
    BASE + "/research/",
    BASE + "/subscribe/",
]
lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
lines.extend(f"  <url><loc>{url}</loc></url>" for url in fixed)
lines.extend(f'  <url><loc>{BASE}{issue["url"]}</loc><lastmod>{issue["date"]}</lastmod></url>' for issue in issues)
lines.append("</urlset>")
write_if_changed(ROOT / "sitemap.xml", "\n".join(lines) + "\n", changed)

print("\n".join(changed))
