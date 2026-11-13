
"""Update GTA VI news headlines and optional article images using Python stdlib."""
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
OUTPUT = ROOT / 'news.json'
QUERY = '"Grand Theft Auto VI" OR "GTA 6" Rockstar when:7d'
URL = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({
    'q': QUERY,
    'hl': 'en-US',
    'gl': 'US',
    'ceid': 'US:en'
})
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; LeonidaFilesNewsBot/1.1)'
}


class ImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image = ''

    def handle_starttag(self, tag, attrs):
        if tag != 'meta':
            return

        a = dict(attrs)
        if (
            a.get('property', '').lower() in (
                'og:image', 'og:image:url', 'og:image:secure_url'
            )
            or a.get('name', '').lower() in (
                'twitter:image', 'twitter:image:src'
            )
        ):
            candidate = html.unescape(
                a.get('content', '')
            ).strip()

            if not self.image and candidate.startswith('https://'):
                self.image = candidate


def request(url, limit=2_000_000, timeout=12):
    req = urllib.request.Request(url, headers=HEADERS)

    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(limit), response.geturl()


def image_from_item(item):
    # Look for images in RSS metadata.
    for child in item.iter():
        tag = child.tag.lower().split('}')[-1]

        if tag in ('thumbnail', 'content', 'enclosure'):
            candidate = child.attrib.get('url', '')

            if (
                candidate.startswith('https://')
                and (
                    tag != 'enclosure'
                    or child.attrib.get('type', '').startswith('image/')
                )
            ):
                return candidate

    # Look for images inside the RSS description.
    desc = html.unescape(item.findtext('description') or '')

    m = re.search(
        r'<img\b[^>]*\bsrc=["\'](https://[^"\']+)',
        desc,
        re.I
    )

    return html.unescape(m.group(1)) if m else ''


def image_from_article(url):
    # Some Google News links cannot be resolved.
    try:
        raw, final_url = request(url, 400_000, 8)

        parser = ImageParser()
        parser.feed(raw.decode('utf-8', 'replace'))

        return parser.image

    except (OSError, ValueError, UnicodeError, TimeoutError):
        return ''


raw, _ = request(URL, timeout=30)
channel = ET.fromstring(raw)

existing = {'articles': []}

if OUTPUT.exists():
    try:
        existing = json.loads(
            OUTPUT.read_text(encoding='utf-8')
        )
    except (ValueError, OSError):
        pass

old_by_title = {
    str(a.get('title', '')).casefold(): a
    for a in existing.get('articles', [])
    if isinstance(a, dict)
}

articles = []
seen = set()

for item in channel.findall('./channel/item'):
    title = (item.findtext('title') or '').strip()
    url = (item.findtext('link') or '').strip()
    source = (
        item.findtext('source') or 'News coverage'
    ).strip()

    if not title or not url.startswith('https://'):
        continue

    if not any(
        word in title.lower()
        for word in ('gta 6', 'gta vi', 'grand theft auto')
    ):
        continue

    key = title.casefold()

    if key in seen:
        continue

    seen.add(key)

    try:
        published = email.utils.parsedate_to_datetime(
            item.findtext('pubDate') or ''
        ).date().isoformat()
    except (TypeError, ValueError):
        published = ''

    article = {
        'title': title[:230],
        'url': url,
        'source': source[:90],
        'published': published
    }

    old = old_by_title.get(key, {})

    image = image_from_item(item) or old.get('image', '')

    if not image:
        image = image_from_article(url)

    if isinstance(image, str) and image.startswith('https://'):
        article['image'] = image

    articles.append(article)

    if len(articles) >= 30:
        break


for old in existing.get('articles', []):
    if not isinstance(old, dict):
        continue

    key = str(old.get('title', '')).casefold()

    if (
        key
        and key not in seen
        and str(old.get('url', '')).startswith('https://')
    ):
        articles.append(old)
        seen.add(key)

    if len(articles) >= 30:
        break


if articles == existing.get('articles', []):
    print('No changes to publish')

else:
    result = {
        'updated': dt.datetime.now(
            dt.timezone.utc
        ).strftime('%Y-%m-%d %H:%M UTC'),
        'articles': articles
    }

    OUTPUT.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        ) + '\n',
        encoding='utf-8'
    )

    print(
        'Updated headlines:',
        len(articles),
        '| with images:',
        sum('image' in a for a in articles)
    )
