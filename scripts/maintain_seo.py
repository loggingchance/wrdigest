#!/usr/bin/env python3
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://woodsrun.forestenterprise.org"

def attr(html, pattern, default=""):
    m = re.search(pattern, html, re.S)
    return m.group(1).strip() if m else default

changed = []
for p in sorted(ROOT.glob("20??/??/??/index.html")):
    html = p.read_text(encoding="utf-8")
    if 'application/ld+json' in html:
        continue
    title = attr(html, r"<title>(.*?)</title>", "Woods Run Digest")
    desc = attr(html, r'<meta name="description" content="([^"]*)"', "Daily forestry and forest-products intelligence from The Forest Business School.")
    canonical = attr(html, r'<link rel="canonical" href="([^"]*)"', BASE + "/" + str(p.relative_to(ROOT).parent).replace("\\","/") + "/")
    m = re.search(r"/(20\d\d)/(\d\d)/(\d\d)/", canonical)
    if not m:
        continue
    date = "-".join(m.groups())
    schema = {
      "@context":"https://schema.org","@type":"NewsArticle","headline":title,
      "description":desc,"datePublished":date,"dateModified":date,
      "mainEntityOfPage":{"@type":"WebPage","@id":canonical},
      "image":[f"{BASE}/assets/cards/{date}.png"],
      "publisher":{"@type":"Organization","name":"The Forest Business School","url":"https://www.forestenterprise.org"},
      "isPartOf":{"@type":"WebSite","name":"Woods Run Digest","url":BASE+"/"}
    }
    block = '<meta name="robots" content="index,follow,max-image-preview:large"><meta name="author" content="The Forest Business School"><script type="application/ld+json">' + json.dumps(schema,separators=(",",":")).replace("<","\\u003c") + "</script>"
    html = html.replace("</head>", block + "</head>", 1)
    p.write_text(html, encoding="utf-8")
    changed.append(str(p.relative_to(ROOT)))
print("\n".join(changed))
