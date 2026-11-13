#!/usr/bin/env python3
"""Refresh GTA VI gallery images from the already collected news image feed."""
import datetime as dt
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NEWS=ROOT/"news.json"
OUTPUT=ROOT/"photo-updates.json"
WORDS={
 "story":r"lucia|jason|relationship|story|character|protagonist",
 "world":r"vice city|leonida|map|world|location|florida|region|environment",
 "combat":r"combat|shooting|gunplay|weapons|fighting",
 "police":r"police|cops|wanted|crime|heist",
 "vehicles":r"car|vehicle|driving|motorcycle|boat",
 "money":r"money|economy|cash|business|property",
 "customization":r"outfit|customization|clothing|hair|tattoo",
 "activities":r"activity|activities|sports|minigame|fishing",
 "technology":r"graphics|technology|npc|performance|engine|ai",
}
def valid(url):
    return isinstance(url,str) and url.startswith("https://") and not re.search(r"\.(?:svg|gif)(?:\?|$)",url,re.I)
def main():
    articles=json.loads(NEWS.read_text(encoding="utf-8")).get("articles",[])
    photos=[];seen=set()
    for item in articles:
        url=item.get("image")
        if not valid(url) or url.split("?")[0] in seen:continue
        title=str(item.get("title",""))[:200]
        article_url=item.get("url","")
        if not valid(article_url):continue
        seen.add(url.split("?")[0])
        topic=next((key for key,pat in WORDS.items() if re.search(pat,title,re.I)),"world")
        photos.append({"image":url,"title":title,"topic":topic,
                       "source":str(item.get("source","News publisher"))[:90],
                       "article_url":article_url,"published":item.get("published","")})
        if len(photos)>=24:break
    previous={}
    if OUTPUT.exists():
        try:previous=json.loads(OUTPUT.read_text(encoding="utf-8"))
        except Exception:pass
    if not photos and previous.get("photos"):
        print("No fresh image links; keeping previous photo feed")
        return
    payload={"updated":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "photos":photos,"note":"Images are article thumbnails owned by their publishers or rights holders. They illustrate coverage, not necessarily new in-game screenshots."}
    OUTPUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Published",len(photos),"GTA VI photo links")
if __name__=="__main__":main()
