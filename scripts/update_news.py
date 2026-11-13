
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
MAX_IMAGE_CHECKS = 30


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


def image_from_article(url):
    if not valid_url(url):
        return ""

    try:
        raw, final_url, content_type = fetch(
            url,
            timeout=6,
            limit=500_000,
        )

        if (
            "html" not in content_type.lower()
            and not raw.lstrip().lower().startswith(
                (b"<!doctype", b"<html")
            )
        ):
            return ""

        parser = ImageParser()
        parser.feed(raw.decode("utf-8", errors="replace"))

        for candidate in parser.images:
            candidate = normalize_url(
                urllib.parse.urljoin(final_url, candidate)
            )

            if not candidate:
                continue

            if candidate.lower().split("?")[0].endswith(
                (".svg", ".gif")
            ):
                continue

            return candidate

    except (
        OSError,
        ValueError,
        UnicodeError,
        TimeoutError,
        RuntimeError,
    ):
        pass

    return ""


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
    resolved = 0
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

            image = (
                image_from_feed(item)
                or (normalize_url(old_article.get("image", "")) if old_article.get("image_type") == "article" and "/VI/_next/static/media/meta." not in str(old_article.get("image", "")) else "")
            )

            if not image and image_checks < MAX_IMAGE_CHECKS:
                hostname = (
                    urllib.parse.urlsplit(url).hostname or ""
                )

                image_checks += 1
                image = image_from_article(url)
                if image:
                    resolved += 1

            if image and "/VI/_next/static/media/meta." in image:
                image = ""
            if image:
                article["image"] = image
                article["image_type"] = "article"

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
            retained = dict(old_article)
            if retained.get("image_type") != "article" or "/VI/_next/static/media/meta." in str(retained.get("image", "")):
                retained.pop("image", None)
                retained.pop("image_type", None)
            articles.append(retained)
            seen.add(key)

    if not articles:
        print("No articles found. Existing news.json preserved.")
        return

    print("Publisher image checks:", image_checks, "| publisher images found:", resolved)
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
