
"""Update LEONIDA GTA VI news with article images when available.

Uses Python's standard library only.
Missing images are normal; headlines still work without them.
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
MAX_ITEMS = 30
MAX_IMAGE_CHECKS = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LeonidaFilesNewsBot/3.0)",
    "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
}

FEEDS = [
    "https://www.bing.com/news/search?"
    + urllib.parse.urlencode({"q": QUERY, "format": "rss"}),

    "https://news.google.com/rss/search?"
    + urllib.parse.urlencode({
        "q": QUERY + " when:7d",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }),
]


def fetch(url, timeout=10, limit=900_000):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return (
            response.read(limit),
            response.geturl(),
            response.headers.get("Content-Type", ""),
        )


def valid_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def normalize_url(url):
    url = html.unescape(str(url or "").strip())

    if url.startswith("//"):
        url = "https:" + url

    if not valid_url(url):
        return ""

    parsed = urllib.parse.urlsplit(url)

    if parsed.hostname and parsed.hostname.endswith(".bing.com"):
        parameters = urllib.parse.parse_qs(parsed.query)

        for key in ("url", "u", "r"):
            for candidate in parameters.get(key, []):
                if valid_url(candidate):
                    return candidate

    return url


class ImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return

        attributes = dict(attrs)
        name = (
            attributes.get("property")
            or attributes.get("name")
            or ""
        ).lower()

        if name in {
            "og:image",
            "og:image:url",
            "og:image:secure_url",
            "twitter:image",
            "twitter:image:src",
        }:
            image = attributes.get("content", "")
            if image:
                self.images.append(image)


def image_from_feed(item):
    # Try RSS media thumbnails, content and image enclosures.
    for element in item.iter():
        tag = element.tag.lower().split("}")[-1]

        if tag in ("thumbnail", "content", "enclosure"):
            url = normalize_url(element.attrib.get("url", ""))
            kind = element.attrib.get("type", "").lower()

            if not url:
                continue

            if tag == "enclosure" and not kind.startswith("image/"):
                continue

            if url.lower().split("?")[0].endswith((".svg", ".gif")):
                continue

            return url

    # Some RSS feeds include an image in the description.
    description = html.unescape(
        item.findtext("description") or ""
    )

    match = re.search(
        r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']+)',
        description,
        re.IGNORECASE,
    )

    if match:
        return normalize_url(match.group(1))

    return ""


def publisher_from_google(url):
    """Best-effort extraction of a publisher URL from a Google News article page.

    Google sometimes changes its markup and may not expose a publisher URL.
    Do not mistake internal Google links for the original article.
    """
    if not valid_url(url):
        return ""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host != "news.google.com":
        return url
    try:
        raw, final, content_type = fetch(url, timeout=7, limit=700_000)
        final_host = urllib.parse.urlsplit(final).hostname or ""
        if final_host != "news.google.com" and valid_url(final):
            return final
        page = html.unescape(raw.decode("utf-8", "replace"))
        # Google News may include the source URL in its rendered markup.
        patterns = [
            r'data-n-au=["\'](https?://[^"\']+)',
            r'data-url=["\'](https?://[^"\']+)',
            r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'](https?://[^"\']+)',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, page, re.I):
                candidate = normalize_url(match.group(1))
                domain = urllib.parse.urlsplit(candidate).hostname or ""
                if candidate and not domain.endswith(('google.com', 'googleusercontent.com')):
                    return candidate
    except (OSError, ValueError, UnicodeError, TimeoutError, RuntimeError):
        pass
    return ""


def image_from_article(url):
    """Find the publisher's preview image, including via Google News redirects."""
    publisher = publisher_from_google(url)
    if not publisher:
        return "", ""
    try:
        raw, final_url, content_type = fetch(publisher, timeout=7, limit=700_000)
        if 'html' not in content_type.lower() and not raw.lstrip().lower().startswith((b'<!doctype', b'<html')):
            return "", publisher
        parser = ImageParser()
        parser.feed(raw.decode('utf-8', errors='replace'))
        for candidate in parser.images:
            candidate = normalize_url(urllib.parse.urljoin(final_url, candidate))
            if candidate and not candidate.lower().split('?')[0].endswith(('.svg', '.gif')):
                return candidate, final_url
        return "", final_url
    except (OSError, ValueError, UnicodeError, TimeoutError, RuntimeError):
        return "", publisher


def fallback_thumbnail(title):
    """Optional keyword-based Bing image thumbnail, NOT an article photograph.

    Bing's thumbnail service is external and may fail or return an unrelated
    image. The website already falls back to its LEONIDA graphic on errors.
    """
    # Use only GTA VI-related terms; do not feed a potentially misleading
    # full headline to a generic image-search service.
    lower = title.lower()
    topic = 'Vice City' if ('vice city' in lower or 'miami' in lower) else 'Grand Theft Auto VI'
    if 'lucia' in lower: topic = 'Grand Theft Auto VI Lucia'
    elif 'jason' in lower: topic = 'Grand Theft Auto VI Jason'
    elif 'vehicle' in lower or 'car' in lower: topic = 'Grand Theft Auto VI cars'
    elif 'map' in lower or 'world' in lower: topic = 'Grand Theft Auto VI Leonida'
    return 'https://tse1.mm.bing.net/th?' + urllib.parse.urlencode({'q': topic + ' Rockstar Games', 'w': 640, 'h': 360, 'c': 7})


def read_existing():
    try:
        data = json.loads(
            OUTPUT.read_text(encoding="utf-8")
        )

        if isinstance(data, dict) and isinstance(
            data.get("articles"), list
        ):
            return data

    except (OSError, ValueError):
        pass

    return {"articles": []}


def read_feed(url):
    try:
        raw, _, _ = fetch(
            url,
            timeout=15,
            limit=2_000_000,
        )

        root = ET.fromstring(raw)
        return root.findall("./channel/item")

    except (OSError, ValueError, ET.ParseError) as error:
        print("Feed unavailable:", type(error).__name__)
        return []


def main():
    existing = read_existing()

    old_articles = [
        article
        for article in existing["articles"]
        if isinstance(article, dict)
    ]

    old_by_title = {
        str(article.get("title", "")).casefold(): article
        for article in old_articles
    }

    articles = []
    seen = set()
    image_checks = 0

    for feed_url in FEEDS:
        items = read_feed(feed_url)

        for item in items:
            title = (item.findtext("title") or "").strip()

            if not title:
                continue

            title_lower = title.casefold()

            if not any(
                phrase in title_lower
                for phrase in (
                    "gta 6",
                    "gta vi",
                    "grand theft auto",
                )
            ):
                continue

            if title_lower in seen:
                continue

            url = normalize_url(
                item.findtext("link") or ""
            )

            if not url:
                continue

            source = (
                item.findtext("source") or "News coverage"
            ).strip()

            try:
                published = email.utils.parsedate_to_datetime(
                    item.findtext("pubDate") or ""
                ).date().isoformat()
            except (ValueError, TypeError):
                published = ""

            article = {
                "title": title[:230],
                "url": url,
                "source": source[:90],
                "published": published,
            }

            old_article = old_by_title.get(title_lower, {})

            image = image_from_feed(item)
            if not image and old_article.get("image_kind") == "publisher":
                image = normalize_url(old_article.get("image", ""))

            if not image and image_checks < MAX_IMAGE_CHECKS:
                image_checks += 1
                image, publisher_url = image_from_article(url)
                if publisher_url and valid_url(publisher_url):
                    article["url"] = publisher_url

            if image:
                article["image"] = image
                article["image_kind"] = "publisher"
            else:
                # Search thumbnails are illustrative, not the article's photo.
                # A failed thumbnail still displays the existing LEONIDA graphic.
                article["image"] = fallback_thumbnail(title)
                article["image_kind"] = "illustrative"

            articles.append(article)
            seen.add(title_lower)

            if len(articles) >= MAX_ITEMS:
                break

        if len(articles) >= MAX_ITEMS:
            break

    # Keep older headlines when the feeds return fewer stories.
    for old_article in old_articles:
        if len(articles) >= MAX_ITEMS:
            break

        title = str(old_article.get("title", ""))
        key = title.casefold()

        if (
            key
            and key not in seen
            and normalize_url(old_article.get("url", ""))
        ):
            articles.append(old_article)
            seen.add(key)

    if not articles:
        print("No articles found. Existing news.json preserved.")
        return

    image_count = sum(
        bool(article.get("image"))
        for article in articles
    )

    if articles == existing["articles"]:
        print(
            "No changes to publish",
            "| headlines:", len(articles),
            "| with images:", image_count,
        )
        return

    result = {
        "updated": dt.datetime.now(
            dt.timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC"),
        "articles": articles,
    }

    OUTPUT.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    print(
        "Updated headlines:", len(articles),
        "| with images:", image_count,
    )


if __name__ == "__main__":
    main()
