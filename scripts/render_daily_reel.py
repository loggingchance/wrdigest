#!/usr/bin/env python3
"""Render the daily vertical Woods Run video used for Instagram Reels and YouTube Shorts."""
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
import json, os, subprocess, tempfile

W,H,FPS=1080,1920,30
BG=(248,244,234); GROUND=(232,225,212); FOREST=(36,74,52); INK=(38,40,34); MUTED=(103,105,95); WARM=(239,231,216); LINE=(207,198,183)
REG="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"; BOLD="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SERIF="/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"; SERIF_BOLD="/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

def ft(p,n): return ImageFont.truetype(p,n)
def wrap(d,t,f,m):
    out=[]; line=""
    for w in t.split():
        q=w if not line else line+" "+w
        if d.textbbox((0,0),q,font=f)[2] <= m: line=q
        else:
            if line: out.append(line)
            line=w
    if line: out.append(line)
    return out
def multiline(d,x,y,t,f,fill,width,spacing=14):
    for line in wrap(d,t,f,width):
        d.text((x,y),line,font=f,fill=fill); y=d.textbbox((x,y),line,font=f)[3]+spacing
    return y
def base():
    im=Image.new("RGB",(W,H),GROUND); d=ImageDraw.Draw(im)
    d.rectangle([28,28,W-28,H-28],fill=BG,outline=LINE,width=2); d.rectangle([28,28,W-28,38],fill=FOREST)
    return im,d
def text(el): return " ".join(el.get_text(" ",strip=True).split()) if el else ""

issues=json.loads(Path("data/issues.json").read_text())
issue=issues[0]; date=issue["date"]; display=issue["displayDate"]
html=Path(date.replace("-","/")+"/index.html")
if not html.exists(): raise SystemExit(f"Missing {html}")
soup=BeautifulSoup(html.read_text(encoding="utf-8"),"html.parser")
stories=[]
for sec in soup.select("section.issue-section"):
    if "special-opportunity" in (sec.get("class") or []): continue
    for art in sec.select("article.story"):
        region=text(art.select_one(".region-label")) or "WOODS RUN"
        h=text(art.find("h3"))
        paras=[text(p) for p in art.find_all("p") if "story-source" not in (p.get("class") or []) and "region-label" not in (p.get("class") or []) and "watch-line" not in (p.get("class") or [])]
        body=paras[0] if paras else ""
        if len(body)>360: body=body[:357].rsplit(" ",1)[0]+"…"
        watch=text(art.select_one(".watch-line"))
        if watch.lower().startswith("watch:"): watch=watch[6:].strip()
        if h and body: stories.append({"region":region,"headline":h,"body":body,"watch":watch})
stories=stories[:5]
if not stories: raise SystemExit("No reel stories found")

tmp=Path(tempfile.mkdtemp(prefix="woodsrun-reel-"))
frames=[]
im,d=base(); d.text((90,150),"WOODS RUN DIGEST",font=ft(BOLD,72),fill=INK); d.text((90,250),display.upper(),font=ft(BOLD,31),fill=FOREST)
y=430; y=multiline(d,90,y,"What is moving in the woods, at the mill, and around the market.",ft(SERIF,66),INK,880,18)
d.line((90,y+50,990,y+50),fill=LINE,width=2); d.text((90,H-220),"Daily forestry & forest products intelligence",font=ft(REG,30),fill=MUTED); d.text((90,H-170),"from The Forest Business School",font=ft(REG,30),fill=MUTED)
p=tmp/"00.png"; im.save(p); frames.append((p,2.5))
for i,s in enumerate(stories,1):
    im,d=base(); d.text((90,105),"WOODS RUN DIGEST",font=ft(BOLD,34),fill=INK); d.text((90,170),s["region"],font=ft(BOLD,28),fill=FOREST); d.text((915,170),f"{i}/{len(stories)}",font=ft(BOLD,26),fill=MUTED); d.line((90,230,990,230),fill=LINE,width=2)
    y=310; y=multiline(d,90,y,s["headline"],ft(SERIF_BOLD,54),INK,880,18); y+=55; d.rectangle([90,y,990,y+8],fill=FOREST); y+=70; y=multiline(d,90,y,s["body"],ft(SERIF,44),FOREST,880,12)
    if s["watch"]:
        top=min(max(y+60,1270),1490); d.rounded_rectangle([90,top,990,top+230],radius=18,fill=WARM,outline=LINE,width=2); d.text((125,top+30),"WATCH",font=ft(BOLD,25),fill=FOREST); multiline(d,125,top+82,s["watch"],ft(REG,34),INK,820,10)
    d.text((90,H-155),"woodsrun.forestenterprise.org",font=ft(BOLD,27),fill=FOREST)
    p=tmp/f"{i:02d}.png"; im.save(p); frames.append((p,4.6))
im,d=base(); d.text((90,130),"THE FOREST BUSINESS SCHOOL",font=ft(BOLD,42),fill=FOREST); d.text((90,215),"More from the people behind Woods Run",font=ft(SERIF,43),fill=INK)
rows=[("Continuing Education","www.forestenterprise.org"),("Consulting","www.northeastforests.com"),("Pubs & Apps","www.loggingchance.com")]
y=430
for label,url in rows:
    d.text((90,y),label,font=ft(BOLD,30),fill=MUTED); y+=52; y=multiline(d,90,y,url,ft(SERIF_BOLD,51),FOREST,900,6); y+=55; d.line((90,y,990,y),fill=LINE,width=2); y+=50
d.text((90,H-290),"Links in bio",font=ft(BOLD,48),fill=INK); d.text((90,H-205),"woodsrun.forestenterprise.org",font=ft(BOLD,28),fill=FOREST)
p=tmp/"99.png"; im.save(p); frames.append((p,4.0))

concat=tmp/"frames.txt"
with concat.open("w") as fh:
    for img,dur in frames:
        fh.write(f"file '{img}'\n")
        fh.write(f"duration {dur}\n")
    fh.write(f"file '{frames[-1][0]}'\n")
out=Path("assets/videos")/(date+".mp4"); out.parent.mkdir(parents=True,exist_ok=True)
subprocess.run([
    "ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),
    "-vf",f"fps={FPS},scale={W}:{H},format=yuv420p",
    "-c:v","libx264","-preset","medium","-crf","20","-movflags","+faststart",str(out)
],check=True)
print(out)
