#!/usr/bin/env python3
"""Free, API-key-free GTA VI headline monitor. Does not invent gameplay claims."""
import datetime as dt
import email.utils
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"feature-updates.json"
QUERIES=[
 ("Rockstar official","Grand Theft Auto VI site:rockstargames.com"),
 ("Rockstar YouTube","GTA VI Rockstar Games official trailer site:youtube.com"),
 ("Rockstar social","GTA VI Rockstar Games announcement site:x.com OR site:twitter.com"),
 ("Gaming reports",'"GTA 6" gameplay features Rockstar IGN GameSpot Eurogamer'),
 ("Jason and Lucia",'"GTA VI" Lucia Jason relationship gameplay'),
]
TOPIC_PATTERNS=[
 ("story",r"lucia|jason|romance|relationship|story|characters|plot|narrative"),
 ("police",r"police|wanted|cop|arrest|crime system"),
 ("vehicles",r"vehicle|car |driving|boat|motorcycle|aircraft"),
 ("combat",r"combat|gun|weapon|fighting|injur"),
 ("money",r"money|economy|business|property|cash"),
 ("customization",r"customiz|clothing|outfit|tattoo|hair"),
 ("activities",r"activities|activity|sports|fishing|minigame"),
 ("technology",r"graphics|performance|fps|npc|technology|engine"),
 ("world",r"map|world|leonida|vice city|region|environment|location"),
]
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (LEONIDA research RSS monitor)"})
    with urllib.request.urlopen(req,timeout=18) as r:return r.read(1500000)
def gather():
    found={}
    for label,query in QUERIES:
        url="https://news.google.com/rss/search?q="+urllib.parse.quote(query)+"&hl=en-US&gl=US&ceid=US:en"
        try:root=ET.fromstring(fetch(url))
        except Exception as exc:
            print("Feed unavailable",label,str(exc)[:100]);continue
        for item in root.findall(".//item")[:12]:
            title=html.unescape(item.findtext("title","")).strip()
            link=item.findtext("link","").strip()
            publisher=item.findtext("source","").strip() or label
            if not title or not link.startswith("https://"):continue
            try:
                date=email.utils.parsedate_to_datetime(item.findtext("pubDate","")).astimezone(dt.timezone.utc)
                if date<dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=45):continue
            except Exception:continue
            key=re.sub(r"[^a-z0-9]","",title.lower())[:110]
            found[key]={"title":title[:220],"url":link,"publisher":publisher,"published":date.date().isoformat(),"discovery":label}
    return sorted(found.values(),key=lambda x:x["published"],reverse=True)[:45]
def classify(items):
    result=[]
    for item in items:
        title=item["title"]
        topic=next((topic for topic,pattern in TOPIC_PATTERNS if re.search(pattern,title,re.I)),None)
        if not topic:continue
        # Only quote the headline, not a fabricated gameplay description.
        publisher=item["publisher"]
        status="official" if publisher.lower()=="rockstar games" else "reported"
        if re.search(r"rumor|rumour|leak|theory|speculat|might|could|alleged",title,re.I):
            status="unverified"
        result.append({"topic":topic,"title":title[:90],
            "summary":"Headline reported by "+publisher+": "+title[:195],
            "status":status,"source_url":item["url"],
            "source_title":publisher+": "+title,"published":item["published"]})
        if len(result)>=12:break
    return result
def main():
    headlines=gather()
    old={}
    if OUTPUT.exists():
        try:old=json.loads(OUTPUT.read_text(encoding="utf-8"))
        except Exception:pass
    if not headlines and old.get("sources"):
        print("No fresh sources; keeping last successful feed.");return
    data={"updated":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
          "mode":"source-monitoring","updates":classify(headlines),
          "sources":headlines[:30],
          "notice":"Free automatic headline monitoring, not AI fact-checking. Summaries repeat source headlines; read original articles before treating a claim as confirmed."}
    OUTPUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Updated",len(data["sources"]),"sources and",len(data["updates"]),"topic headlines; no API key.")
if __name__=="__main__":main()
