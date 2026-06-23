"""LORD Automation — Image Sourcer
Fetches editorial images from Unsplash (primary) or Pexels (fallback).
Per brand guidelines, images must be properly attributed and never AI-generated.
"""
import logging

import requests

from config import UNSPLASH_ACCESS_KEY, PEXELS_API_KEY

log = logging.getLogger('lord.images')

MUSIC_FALLBACK_QUERIES = [
    'concert stage lights',
    'vinyl record turntable',
    'recording studio microphone',
    'music festival crowd',
    'guitar musician performance',
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
            log.warning("Unsplash returned %s for query '%s'", resp.status_code, query)
            return None

        d = resp.json()
        return {
            'url':         d['urls']['regular'],     # ~1080px wide
            'fullUrl':     d['urls']['full'],
            'thumbUrl':    d['urls']['small'],
            'credit':      d['user']['name'],
            'creditUrl':   d['user']['links']['html'] + '?utm_source=lord_music&utm_medium=referral',
            'altText':     d.get('alt_description') or query,
            'unsplashId':  d['id'],
            'provider':    'unsplash',
        }
    except Exception as exc:
        log.warning("Unsplash error: %s", exc)
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

        p = photos[0]
        return {
            'url':       p['src']['large'],
            'fullUrl':   p['src']['original'],
            'thumbUrl':  p['src']['small'],
            'credit':    p['photographer'],
            'creditUrl': p['photographer_url'],
            'altText':   p.get('alt') or query,
            'provider':  'pexels',
        }
    except Exception as exc:
        log.warning("Pexels error: %s", exc)
        return None


def get_article_image(primary_query: str) -> dict | None:
    """
    Attempt to source a relevant image for an article.
    Tries Unsplash first, then Pexels, then generic music fallbacks.
    Returns None if no image service is configured.
    """
    # Try the AI-suggested query first
    image = fetch_unsplash(primary_query) or fetch_pexels(primary_query)
    if image:
        return image

    # Try music-specific fallbacks
    for fallback in MUSIC_FALLBACK_QUERIES:
        image = fetch_unsplash(fallback) or fetch_pexels(fallback)
        if image:
            return image

    log.info("No image sourced — article will render with branded placeholder")
    return None
