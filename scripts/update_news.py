"""Update a conservative headline-only GTA VI news feed using stdlib."""
import datetime as dt
import email.utils
import json
import pathlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'news.json'
QUERY = '"Grand Theft Auto VI" OR "GTA 6" Rockstar when:7d'
URL = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': QUERY, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
headers = {'User-Agent': 'Mozilla/5.0 (compatible; LeonidaFilesNewsBot/1.0)'}
req = urllib.request.Request(URL, headers=headers)
with urllib.request.urlopen(req, timeout=30) as response:
    xml = response.read(2_000_000)
channel = ET.fromstring(xml)
existing = {'articles': []}
if OUTPUT.exists():
    try: existing = json.loads(OUTPUT.read_text(encoding='utf-8'))
    except (ValueError, OSError): pass
articles = []
seen = set()
for item in channel.findall('./channel/item'):
    title = (item.findtext('title') or '').strip()
    url = (item.findtext('link') or '').strip()
    source = (item.findtext('source') or 'News coverage').strip()
    if not title or not url or not url.startswith('https://'): continue
    if not any(word in title.lower() for word in ('gta 6', 'gta vi', 'grand theft auto')): continue
    key = title.lower()
    if key in seen: continue
    seen.add(key)
    raw_date = item.findtext('pubDate') or ''
    try: published = email.utils.parsedate_to_datetime(raw_date).date().isoformat()
    except (TypeError, ValueError): published = ''
    articles.append({'title': title[:230], 'url': url, 'source': source[:90], 'published': published})
for old in existing.get('articles', []):
    key = str(old.get('title','')).lower()
    if key not in seen and str(old.get('url','')).startswith('https://'):
        articles.append(old)
        seen.add(key)
result = {'updated': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), 'articles': articles[:30]}
# Only update timestamp when stories change, avoiding pointless deployments.
if result['articles'] == existing.get('articles', []):
    print('No new stories')
else:
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Updated headlines:', len(result['articles']))
