"""Update GTA VI headlines and optional article images, using Python stdlib only.

Images are best-effort: not all feeds or publisher sites expose a reusable image.
"""
import datetime as dt
import email.utils
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'news.json'
QUERY = '"Grand Theft Auto VI" OR "GTA 6" Rockstar when:7d'
URL = 'https://news.google.com/rss/search?' + urllib.parse.urlencode(
    {'q': QUERY, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; LeonidaFilesNewsBot/1.1)'}


class ImageMetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image = ''

    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'meta' or self.image:
            return
        a = dict(attrs)
        key = (a.get('property') or a.get('name') or '').lower()
        if key in ('og:image', 'twitter:image', 'twitter:image:src'):
            self.image = html.unescape(a.get('content') or '')


def safe_https(value):
    try:
        p = urllib.parse.urlparse(value)
        return value if p.scheme == 'https' and p.hostname else ''
    except ValueError:
        return ''


def find_image(item, article_url):
    # Google News RSS rarely supplies media images, but check before looking at a publisher.
    for elem in item.iter():
        if elem.tag.endswith(('thumbnail', 'content', 'enclosure')):
            candidate = elem.attrib.get('url', '')
            if safe_https(candidate) and (elem.attrib.get('type', '').startswith('image/') or elem.tag.endswith(('thumbnail', 'content'))):
                return candidate
    # Don't scrape Google News redirect pages. Publisher pages may expose an og:image.
    host = urllib.parse.urlparse(article_url).hostname or ''
    if host in ('news.google.com', 'google.com') or host.endswith('.google.com'):
        return ''
    try:
        req = urllib.request.Request(article_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=5) as response:
            content_type = response.headers.get('Content-Type', '')
            if 'html' not in content_type:
                return ''
            page = response.read(180_000).decode('utf-8', errors='ignore')
        parser = ImageMetaParser()
        parser.feed(page)
        return safe_https(urllib.parse.urljoin(article_url, parser.image)) if parser.image else ''
    except (OSError, ValueError, TimeoutError):
        return ''


req = urllib.request.Request(URL, headers=HEADERS)
with urllib.request.urlopen(req, timeout=30) as response:
    xml = response.read(2_000_000)
channel = ET.fromstring(xml)
existing = {'articles': []}
if OUTPUT.exists():
    try:
        existing = json.loads(OUTPUT.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        pass
old_by_title = {str(a.get('title', '')).lower(): a for a in existing.get('articles', []) if isinstance(a, dict)}
articles = []
seen = set()
for item in channel.findall('./channel/item'):
    title = (item.findtext('title') or '').strip()
    url = (item.findtext('link') or '').strip()
    source = (item.findtext('source') or 'News coverage').strip()
    if not title or not safe_https(url):
        continue
    if not any(word in title.lower() for word in ('gta 6', 'gta vi', 'grand theft auto')):
        continue
    key = title.lower()
    if key in seen:
        continue
    seen.add(key)
    raw_date = item.findtext('pubDate') or ''
    try:
        published = email.utils.parsedate_to_datetime(raw_date).date().isoformat()
    except (TypeError, ValueError):
        published = ''
    article = {'title': title[:230], 'url': url, 'source': source[:90], 'published': published}
    image = old_by_title.get(key, {}).get('image', '') or find_image(item, url)
    if safe_https(image):
        article['image'] = image
    articles.append(article)
    if len(articles) >= 30:
        break
for old in existing.get('articles', []):
    if not isinstance(old, dict):
        continue
    key = str(old.get('title', '')).lower()
    if key not in seen and safe_https(str(old.get('url', ''))):
        articles.append(old)
        seen.add(key)
result = {'updated': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), 'articles': articles[:30]}
if result['articles'] == existing.get('articles', []):
    print('No new stories')
else:
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Updated headlines:', len(result['articles']))
