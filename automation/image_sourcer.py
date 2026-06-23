"""LORD Automation — Image Sourcer
Fetches editorial images from multiple free providers:
  1. Unsplash   — high-quality editorial photography (requires key)
  2. Openverse  — CC-licensed content from Flickr, Wikipedia, etc. (no key needed)
  3. Pixabay    — large CC0 library including concert/artist shots (requires key)
  4. Pexels     — editorial stock photography fallback (requires key)
All images are properly attributed to the original photographer and source.
"""
import logging
import random

import requests

from config import UNSPLASH_ACCESS_KEY, PEXELS_API_KEY, PIXABAY_API_KEY

log = logging.getLogger('lord.images')

MUSIC_FALLBACK_QUERIES = [
    'concert stage lights',
    'vinyl record turntable',
    'recording studio microphone',
    'music festival crowd',
    'musician performance live',
]


def fetch_unsplash(query: str, orientation: str = 'landscape') -> dict | None:
    """Fetch one random image from Unsplash matching the query."""
    if not UNSPLASH_ACCESS_KEY:
        return None
    try:
        resp = requests.get(
            'https://api.unsplash.com/photos/random',
            params={
                'query':          query,
                'orientation':    orientation,
                'content_filter': 'high',
            },
            headers={'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}'},
            timeout=10,
        )
        if resp.status_code != 200:
            log.warning("Unsplash %s for '%s'", resp.status_code, query)
            return None

        d = resp.json()
        return {
            'url':        d['urls']['regular'],
            'fullUrl':    d['urls']['full'],
            'thumbUrl':   d['urls']['small'],
            'credit':     d['user']['name'],
            'creditUrl':  d['user']['links']['html'] + '?utm_source=lord_music&utm_medium=referral',
            'altText':    d.get('alt_description') or query,
            'provider':   'Unsplash',
        }
    except Exception as exc:
        log.warning("Unsplash error: %s", exc)
        return None


def fetch_openverse(query: str) -> dict | None:
    """
    Fetch a CC-licensed image from Openverse (searches Flickr, Wikipedia, and others).
    No API key required. Requires attribution.
    """
    try:
        resp = requests.get(
            'https://api.openverse.org/v1/images/',
            params={
                'q':         query,
                'license':   'cc0,by,by-sa,by-nc,by-nd',
                'per_page':  10,
                'mature':    False,
            },
            headers={'User-Agent': 'LORD-Music-Publication/1.0'},
            timeout=12,
        )
        if resp.status_code != 200:
            log.warning("Openverse %s for '%s'", resp.status_code, query)
            return None

        results = resp.json().get('results', [])
        if not results:
            return None

        # Pick a random result from the top 5 for variety
        d = random.choice(results[:5])

        creator = d.get('creator', '').strip()
        creator_url = d.get('creator_url', '') or d.get('foreign_landing_url', '#')
        source = d.get('source', 'openverse')
        source_label = {
            'flickr':           'Flickr',
            'wikimedia_commons': 'Wikimedia',
            'stocksnap':        'StockSnap',
            'rawpixel':         'Rawpixel',
            'europeana':        'Europeana',
            'met':              'The Met',
            'smithsonian':      'Smithsonian',
        }.get(source, source.replace('_', ' ').title())

        return {
            'url':       d['url'],
            'thumbUrl':  d.get('thumbnail', d['url']),
            'credit':    creator or source_label,
            'creditUrl': creator_url,
            'altText':   d.get('title', '') or query,
            'provider':  source_label,
        }
    except Exception as exc:
        log.warning("Openverse error: %s", exc)
        return None


def fetch_pixabay(query: str) -> dict | None:
    """Fetch a CC0 image from Pixabay matching the query."""
    if not PIXABAY_API_KEY:
        return None
    try:
        resp = requests.get(
            'https://pixabay.com/api/',
            params={
                'key':         PIXABAY_API_KEY,
                'q':           query,
                'image_type':  'photo',
                'orientation': 'horizontal',
                'safesearch':  'true',
                'per_page':    10,
                'min_width':   800,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            log.warning("Pixabay %s for '%s'", resp.status_code, query)
            return None

        hits = resp.json().get('hits', [])
        if not hits:
            return None

        p = random.choice(hits[:5])
        return {
            'url':       p.get('largeImageURL') or p['webformatURL'],
            'thumbUrl':  p['previewURL'],
            'credit':    p.get('user', 'Pixabay'),
            'creditUrl': p['pageURL'],
            'altText':   query,
            'provider':  'Pixabay',
        }
    except Exception as exc:
        log.warning("Pixabay error: %s", exc)
        return None


def fetch_pexels(query: str) -> dict | None:
    """Fetch one image from Pexels matching the query."""
    if not PEXELS_API_KEY:
        return None
    try:
        resp = requests.get(
            'https://api.pexels.com/v1/search',
            params={'query': query, 'per_page': 5, 'orientation': 'landscape'},
            headers={'Authorization': PEXELS_API_KEY},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        photos = resp.json().get('photos', [])
        if not photos:
            return None

        p = random.choice(photos[:5])
        return {
            'url':       p['src']['large'],
            'fullUrl':   p['src']['original'],
            'thumbUrl':  p['src']['small'],
            'credit':    p['photographer'],
            'creditUrl': p['photographer_url'],
            'altText':   p.get('alt') or query,
            'provider':  'Pexels',
        }
    except Exception as exc:
        log.warning("Pexels error: %s", exc)
        return None


def _try_all(query: str) -> dict | None:
    """Try all configured providers in priority order for a single query."""
    return (
        fetch_unsplash(query)
        or fetch_openverse(query)
        or fetch_pixabay(query)
        or fetch_pexels(query)
    )


def get_article_image(primary_query: str) -> dict | None:
    """
    Source one image for an article.
    Priority: Unsplash → Openverse → Pixabay → Pexels → music fallbacks.
    """
    image = _try_all(primary_query)
    if image:
        return image

    for fallback in MUSIC_FALLBACK_QUERIES:
        image = _try_all(fallback)
        if image:
            return image

    log.info("No image sourced — article will render with branded placeholder")
    return None


def get_article_images(queries: list[str]) -> list[dict]:
    """
    Fetch one unique image per query string.
    Used for multi-image articles (features: 3 images, reviews: 2 images).
    Falls back through music fallbacks if a query returns no result or a duplicate.
    """
    images: list[dict] = []
    used_urls: set[str] = set()

    for query in queries:
        if not query:
            continue
        for attempt in [query] + MUSIC_FALLBACK_QUERIES:
            img = _try_all(attempt)
            if img and img['url'] not in used_urls:
                used_urls.add(img['url'])
                images.append(img)
                break

    return images
