#!/usr/bin/env python3
"""GTA VI topic research. Runs on GitHub Actions; never embeds API credentials in the site."""
import datetime as dt
import email.utils
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "feature-updates.json"
TOPICS = ["world","story","combat","police","vehicles","money","customization","activities","technology"]
QUERIES = [
    ("Rockstar official", 'Grand Theft Auto VI site:rockstargames.com'),
    ("Rockstar YouTube", 'GTA VI Rockstar Games official trailer site:youtube.com'),
    ("Rockstar social", 'GTA VI Rockstar Games announcement site:x.com OR site:twitter.com'),
    ("Gaming reports", '"GTA 6" gameplay features Rockstar IGN GameSpot Eurogamer'),
    ("Jason and Lucia", '"GTA VI" Lucia Jason relationship gameplay'),
]
UA = {"User-Agent":"LeonidaFilesResearchBot/1.0 (public fan site; RSS reader)"}
def get(url):
    req = urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=18) as response:
        return response.read(1_500_000)
def items():
    found = {}
    for label,query in QUERIES:
        url = "https://news.google.com/rss/search?q="+urllib.parse.quote(query)+"&hl=en-US&gl=US&ceid=US:en"
        try:
            root=ET.fromstring(get(url))
        except Exception as exc:
            print("RSS source unavailable:",label,str(exc)[:150])
            continue
        for item in root.findall(".//item")[:12]:
            title=html.unescape(item.findtext("title","")).strip()
            link=item.findtext("link","").strip()
            source=item.findtext("source","").strip()
            date=item.findtext("pubDate","")
            if not title or not link.startswith("https://"):
                continue
            try:
                published=email.utils.parsedate_to_datetime(date).astimezone(dt.timezone.utc)
                if published < dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=45):continue
            except Exception:continue
            key=re.sub(r"[^a-z0-9]","",title.lower())[:100]
            found[key]={"title":title[:220],"url":link,"publisher":source or label,"published":published.date().isoformat(),"discovery":label}
    return sorted(found.values(),key=lambda a:a["published"],reverse=True)[:45]

SYSTEM = """You are a cautious GTA VI research editor. Return ONLY JSON object with "updates": list.
Each update must have: topic (one of world,story,combat,police,vehicles,money,customization,activities,technology),
title (max 90 chars), summary (one or two short factual sentences, max 320 chars),
status (official,reported,unverified), source_url, source_title.
Use ONLY the supplied headlines and links, not prior knowledge. Do NOT infer gameplay features from vague headlines.
A source_title should identify the publisher and headline.
"official" ONLY when the headline itself is explicitly an announcement from Rockstar Games or a first-party platform about its own service.
"reported" means a specific claim attributed to a named publication, NOT independently confirmed.
"unverified" means speculation or rumor; do not include unless clearly labeled.
If a headline does not establish a concrete new detail, omit it.
For Twitter/X and YouTube headlines, distinguish a publisher's description from an official Rockstar statement.
Do not claim journalists personally play-tested the game unless explicitly stated.
Do not claim a story or relationship outcome as fact without an explicit source.
Do not include repeated or contradictory claims. Max 12 updates.
Return JSON only, no markdown."""
def generate(headlines):
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key:
        print("OPENAI_API_KEY not set; collecting sources without inventing feature claims.")
        return []
    payload={"model":os.getenv("OPENAI_MODEL","gpt-4.1-mini"),"temperature":0.1,
      "messages":[{"role":"system","content":SYSTEM},{"role":"user","content":"Recent GTA VI coverage (headline metadata only, not article body). Extract only defensible, source-attributed updates:\n"+json.dumps(headlines,ensure_ascii=False)}],
      "response_format":{"type":"json_object"}}
    req=urllib.request.Request("https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=75) as response:
        data=json.load(response)
    return json.loads(data["choices"][0]["message"]["content"]).get("updates",[])
def validate(candidates,headlines):
    allowed={x["url"]:x for x in headlines}
    output=[]
    for row in candidates:
        if not isinstance(row,dict):continue
        topic=row.get("topic")
        url=row.get("source_url")
        status=row.get("status")
        if topic not in TOPICS or url not in allowed or status not in ("official","reported","unverified"):continue
        source=allowed[url]
        title=str(row.get("title","")).strip()[:90]
        summary=str(row.get("summary","")).strip()[:320]
        if not title or len(summary)<25:continue
        # Official requires the indexed publisher to be Rockstar Games or a platform first party.
        if status=="official" and not any(v in source["publisher"].lower() for v in ("rockstar games","playstation.blog","xbox wire")):
            status="reported"
        output.append({"topic":topic,"title":title,"summary":summary,"status":status,
          "source_url":url,"source_title":source["publisher"]+": "+source["title"],"published":source["published"]})
    return output[:12]
def main():
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    headlines=items()
    existing={}
    if OUTPUT.exists():
        try:existing=json.loads(OUTPUT.read_text(encoding="utf-8"))
        except Exception:pass
    try:
        updates=validate(generate(headlines),headlines)
    except Exception as exc:
        print("AI processing failed; preserving existing updates:",str(exc)[:250])
        updates=existing.get("updates",[])
    # Without an AI key, retain previous curated updates; source links still refresh.
    if not os.getenv("OPENAI_API_KEY"):
        updates=existing.get("updates",[])
    result={"updated":now,"mode":"AI-assisted" if os.getenv("OPENAI_API_KEY") else "source-monitoring",
      "updates":updates[:12],"sources":headlines[:30],
      "notice":"AI-assisted summaries are based on indexed headlines and can be incomplete. Follow the original source to verify details. This is not an official Rockstar feed."}
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Saved",len(result["sources"]),"source links and",len(result["updates"]),"topic updates.")
if __name__=="__main__":main()
