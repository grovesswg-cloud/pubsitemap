"""LORD Automation — Image Sourcer
Fetches editorial images from multiple free providers:
  1. Wikipedia  — official artist portrait from Wikipedia page (no key needed)
  2. Unsplash   — high-quality editorial photography (requires key)
  3. Openverse  — CC-licensed content from Flickr, Wikipedia, etc. (no key needed)
  4. Pixabay    — large CC0 library including concert/artist shots (requires key)
  5. Pexels     — editorial stock photography fallback (requires key)
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


def fetch_wikipedia(query: str) -> dict | None:
    """
    Fetch the lead image from a Wikipedia article matching the query.
    Uses Wikipedia's search + summary APIs — no key required.
    Best for artist/band portraits (returns the exact photo on their Wikipedia page).
    """
    try:
        # Step 1: search Wikipedia for the most relevant article
        search_resp = requests.get(
            'https://en.wikipedia.org/w/api.php',
            params={
                'action':    'query',
                'list':      'search',
                'srsearch':  query,
                'srnamespace': 0,
                'srlimit':   3,
                'format':    'json',
            },
            headers={'User-Agent': 'LORD-Music-Publication/1.0 (lord.music)', 'Referer': 'https://en.wikipedia.org/'},
            timeout=10,
        )
        if search_resp.status_code != 200:
            return None

        results = search_resp.json().get('query', {}).get('search', [])
        if not results:
            return None

        # Skip list/disambiguation pages — pick the first real article
        skip_prefixes = ('list of', 'discography', 'filmography', 'bibliography',
                         'songs written', 'awards and', 'wikipedia:')
        title = None
        for r in results:
            if not any(r['title'].lower().startswith(p) for p in skip_prefixes):
                title = r['title']
                break
        if not title:
            title = results[0]['title']  # fallback: take whatever we have
        summary_resp = requests.get(
            f'https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}',
            headers={'User-Agent': 'LORD-Music-Publication/1.0 (lord.music)', 'Referer': 'https://en.wikipedia.org/'},
            timeout=10,
        )
        if summary_resp.status_code != 200:
            return None

        page = summary_resp.json()
        thumbnail = page.get('thumbnail')
        if not thumbnail:
            return None

        # Use the original full-resolution file by stripping /thumb/ and size prefix.
        # Requesting 1200px thumbnails returns 400 when the original is smaller.
        thumb_url = thumbnail['source']
        import re
        # https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/File.jpg/320px-File.jpg
        # →  https://upload.wikimedia.org/wikipedia/commons/a/ab/File.jpg
        m = re.match(
            r'(https://upload\.wikimedia\.org/wikipedia/[^/]+)/thumb(/[^/]+/[^/]+/[^/]+)/\d+px-.+',
            thumb_url,
        )
        full_url = (m.group(1) + m.group(2)) if m else thumb_url

        page_url = page.get('content_urls', {}).get('desktop', {}).get('page', f'https://en.wikipedia.org/wiki/{title}')

        return {
            'url':       full_url,
            'thumbUrl':  thumb_url,
            'credit':    f'Wikipedia — {title}',
            'creditUrl': page_url,
            'altText':   page.get('description') or title,
            'provider':  'Wikipedia',
        }
    except Exception as exc:
        log.warning("Wikipedia error: %s", exc)
        return None


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


def fetch_openverse(query: str, exclude_flickr: bool = False) -> dict | None:
    """
    Fetch a CC-licensed image from Openverse (searches Flickr, Wikipedia, and others).
    No API key required. Requires attribution.
    Set exclude_flickr=True to prefer Wikimedia/StockSnap over Flickr (higher quality).
    """
    try:
        params: dict = {
            'q':         query,
            'license':   'cc0,by,by-sa,by-nc,by-nd',
            'per_page':  10,
            'mature':    False,
        }
        if exclude_flickr:
            params['source'] = 'wikimedia_commons,stocksnap,rawpixel,europeana'

        resp = requests.get(
            'https://api.openverse.org/v1/images/',
            params=params,
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


def _try_editorial(query: str) -> dict | None:
    """Try artist-specific sources only: Wikipedia and Openverse/Wikimedia.
    Stock photo APIs are NOT used here — they return random strangers when
    queried for a specific artist name instead of actual photos of that person.
    """
    return (
        fetch_wikipedia(query)
        or fetch_openverse(query, exclude_flickr=True)   # Wikimedia Commons/StockSnap
        or fetch_openverse(query)                         # Flickr as last resort
    )


def _try_stock(query: str) -> dict | None:
    """Try stock photo APIs. Only suitable for generic music queries, never artist names."""
    return (
        fetch_unsplash(query)
        or fetch_pixabay(query)
        or fetch_pexels(query)
    )


def _try_all(query: str) -> dict | None:
    """Try editorial sources first, then stock APIs as a fallback."""
    return _try_editorial(query) or _try_stock(query)


def get_article_image(primary_query: str) -> dict | None:
    """
    Source one image for an article.
    Uses editorial sources (Wikipedia, Openverse/Wikimedia) for the artist query.
    Falls back to stock APIs only with generic music imagery — never artist names —
    so we never return a random stranger instead of the actual artist.
    """
    image = _try_editorial(primary_query)
    if image:
        return image

    for fallback in MUSIC_FALLBACK_QUERIES:
        image = _try_stock(fallback)
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
        # Try editorial sources with the artist query first
        img = _try_editorial(query)
        if img and img['url'] not in used_urls:
            used_urls.add(img['url'])
            images.append(img)
            continue
        # Fall back to stock APIs with generic music queries only
        for fallback in MUSIC_FALLBACK_QUERIES:
            img = _try_stock(fallback)
            if img and img['url'] not in used_urls:
                used_urls.add(img['url'])
                images.append(img)
                break

    return images
