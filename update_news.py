"""Refresh LEONIDA GTA VI headlines and best-effort publisher images (stdlib only).

Feeds can omit images or block scraping. Missing images are normal, not a failure.
"""
import datetime as dt
import email.utils
import html
from html.parser import HTMLParser
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "news.json"
QUERY = '"Grand Theft Auto VI" OR "GTA 6" Rockstar'
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LeonidaFilesNewsBot/2.0)", "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8"}
BING = "https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": QUERY, "format": "rss"})
GOOGLE = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": QUERY + " when:7d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
MAX_ITEMS = 30
MAX_IMAGE_CHECKS = 18


def fetch(url, timeout=8, limit=900_000):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(limit), resp.geturl(), resp.headers.get("Content-Type", "")


def valid_https(url):
    try:
        p = urllib.parse.urlsplit(url)
        return p.scheme == "https" and bool(p.netloc) and not p.username and not p.password
    except ValueError:
        return False


def normalize_url(url):
    url = html.unescape((url or "").strip())
    if url.startswith("//"):
        url = "https:" + url
    # Bing RSS sometimes wraps publisher URLs in its own tracking redirect.
    p = urllib.parse.urlsplit(url)
    if p.netloc.endswith("bing.com"):
        qs = urllib.parse.parse_qs(p.query)
        for key in ("url", "u", "r"):
            for value in qs.get(key, []):
                if valid_https(value):
                    return value
    return url if valid_https(url) else ""


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.candidates = []
        self.canonical = ""

    def handle_starttag(self, tag, attrs):
        a = {str(k).lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            kind = (a.get("property") or a.get("name") or "").lower()
            if kind in {"og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src"}:
                self.candidates.append(a.get("content", ""))
        elif tag == "link" and "canonical" in a.get("rel", "").lower():
            self.canonical = a.get("href", "")


def image_from_rss(item):
    for child in item.iter():
        tag = child.tag.lower().split("}")[-1]
        if tag in {"thumbnail", "content", "enclosure"}:
            kind = child.attrib.get("type", "")
            candidate = normalize_url(child.attrib.get("url", ""))
            if candidate and (tag != "enclosure" or kind.startswith("image/")):
                return candidate
    description = html.unescape(item.findtext("description") or "")
    match = re.search(r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']+)', description, re.I)
    return normalize_url(match.group(1)) if match else ""


def image_from_publisher(url):
    if not url or "news.google.com" in urllib.parse.urlsplit(url).netloc:
        return ""
    try:
        raw, final_url, content_type = fetch(url, timeout=6, limit=450_000)
        if "html" not in content_type.lower() and not raw.lstrip().startswith((b"<!DOCTYPE", b"<html", b"<HTML")):
            return ""
        parser = MetadataParser()
        parser.feed(raw.decode("utf-8", "replace"))
        for candidate in parser.candidates:
            candidate = normalize_url(urllib.parse.urljoin(final_url, html.unescape(candidate)))
            if candidate and not candidate.lower().endswith((".svg", ".gif")):
                return candidate
    except (OSError, ValueError, UnicodeError, TimeoutError, RuntimeError):
        pass
    return ""


def read_existing():
    try:
        obj = json.loads(OUTPUT.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) and isinstance(obj.get("articles"), list) else {"articles": []}
    except (OSError, ValueError):
        return {"articles": []}


def items_from_feed(feed_url):
    try:
        raw, _, _ = fetch(feed_url, timeout=15, limit=2_000_000)
        root = ET.fromstring(raw)
        return root.findall("./channel/item")
    except (OSError, ET.ParseError, ValueError) as exc:
        print("Feed unavailable:", type(exc).__name__)
        return []


def main():
    existing = read_existing()
    old_by_title = {str(a.get("title", "")).casefold(): a for a in existing["articles"] if isinstance(a, dict)}
    articles, seen = [], set()
    checks = 0

    # Bing News often exposes publisher URLs directly; Google News is fallback.
    for feed in (BING, GOOGLE):
        for item in items_from_feed(feed):
            title = (item.findtext("title") or "").strip()
            if not title or not any(x in title.casefold() for x in ("gta 6", "gta vi", "grand theft auto")):
                continue
            key = title.casefold()
            if key in seen:
                continue
            url = normalize_url(item.findtext("link") or "")
            if not url:
                continue
            source = (item.findtext("source") or "News coverage").strip()
            try:
                published = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
            except (ValueError, TypeError):
                published = ""
            article = {"title": title[:230], "url": url, "source": source[:90], "published": published}
            old = old_by_title.get(key, {})
            picture = image_from_rss(item) or normalize_url(old.get("image", ""))
            if not picture and checks < MAX_IMAGE_CHECKS and "news.google.com" not in urllib.parse.urlsplit(url).netloc:
                checks += 1
                picture = image_from_publisher(url)
            if picture:
                article["image"] = picture
            articles.append(article)
            seen.add(key)
            if len(articles) >= MAX_ITEMS:
                break
        if len(articles) >= MAX_ITEMS:
            break

    # Retain older stories if the feeds return fewer than 30.
    for old in existing["articles"]:
        if len(articles) >= MAX_ITEMS:
            break
        if not isinstance(old, dict):
            continue
        key = str(old.get("title", "")).casefold()
        if key and key not in seen and normalize_url(old.get("url", "")):
            articles.append(old)
            seen.add(key)

    if not articles:
        print("No feed stories found; keeping existing news.json unchanged")
        return
    if articles == existing["articles"]:
        print("No changes to publish | with images:", sum(bool(a.get("image")) for a in articles))
        return
    result = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "articles": articles}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Updated headlines:", len(articles), "| with images:", sum(bool(a.get("image")) for a in articles))


if __name__ == "__main__":
    main()
