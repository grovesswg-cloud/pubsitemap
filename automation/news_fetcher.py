"""LORD Automation — News Fetcher
Pulls trending music news from RSS feeds and optionally NewsAPI.
"""
import random
import time
import logging
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from config import RSS_FEEDS, NEWS_API_KEY

log = logging.getLogger('lord.news')


def _parse_entry_date(entry) -> datetime | None:
    """Parse a feedparser entry date into a timezone-aware datetime."""
    parsed = entry.get('published_parsed') or entry.get('updated_parsed')
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def fetch_rss_feeds(max_per_feed: int = 8) -> list[dict]:
    """Fetch recent items from all configured RSS feeds."""
    items = []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=72)

    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, request_headers={'User-Agent': 'LORD/1.0'})
            source_name = feed.feed.get('title', url)

            for entry in feed.entries[:max_per_feed]:
                title = (entry.get('title') or '').strip()
                if not title:
                    continue

                summary = (
                    entry.get('summary')
                    or entry.get('description')
                    or ''
                ).strip()

                link = entry.get('link', '')

                pub_date = _parse_entry_date(entry)
                # Include items without a parseable date (assume recent)
                if pub_date and pub_date < cutoff:
                    continue

                items.append({
                    'title':     title,
                    'summary':   summary[:1200],
                    'link':      link,
                    'published': pub_date.isoformat() if pub_date else '',
                    'source':    source_name,
                })

        except Exception as exc:
            log.warning("RSS feed failed (%s): %s", url, exc)

    return items


def fetch_newsapi(limit: int = 15) -> list[dict]:
    """Fetch music headlines from NewsAPI (requires NEWS_API_KEY)."""
    if not NEWS_API_KEY:
        return []

    try:
        resp = requests.get(
            'https://newsapi.org/v2/everything',
            params={
                'q':        '(music OR album OR rapper OR singer OR artist OR concert) AND NOT (stock OR market)',
                'language': 'en',
                'sortBy':   'publishedAt',
                'pageSize': limit,
                'apiKey':   NEWS_API_KEY,
            },
            timeout=12,
        )
        data = resp.json()
        if data.get('status') != 'ok':
            log.warning("NewsAPI error: %s", data.get('message', 'unknown'))
            return []

        return [
            {
                'title':     a['title'],
                'summary':   a.get('description') or '',
                'link':      a['url'],
                'published': a.get('publishedAt', ''),
                'source':    a['source']['name'],
            }
            for a in data.get('articles', [])
            if a.get('title') and '[Removed]' not in a.get('title', '')
        ]
    except Exception as exc:
        log.warning("NewsAPI fetch failed: %s", exc)
        return []


def deduplicate(items: list[dict]) -> list[dict]:
    """Remove near-duplicate items by title prefix."""
    seen: set[str] = set()
    unique: list[dict] = []
    for item in items:
        key = item['title'].lower().strip()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def get_trending_music_news() -> list[dict]:
    """Return a de-duplicated, shuffled list of current music news items."""
    items: list[dict] = []

    if NEWS_API_KEY:
        items.extend(fetch_newsapi())

    rss_items = fetch_rss_feeds()
    random.shuffle(rss_items)
    items.extend(rss_items)

    return deduplicate(items)
