"""LORD Automation — Image Sourcer
Fetches editorial images from multiple free providers:
  1. Wikipedia        — lead artist portrait from their Wikipedia page (no key)
  2. Wikimedia Commons — direct hi-res search, resolution-filtered (no key)
  3. Openverse        — CC-licensed Wikimedia/StockSnap content (no key)
  4. Unsplash         — stock photography for generic fallbacks only (key required)
  5. Pixabay          — CC0 library for generic fallbacks only (key required)
  6. Pexels           — stock photography for generic fallbacks only (key required)
  7. Openverse/Flickr — last resort for artist queries (variable quality)

Stock APIs (Unsplash/Pixabay/Pexels) are NEVER used for artist-specific queries —
they return random strangers instead of the actual artist.
"""
import logging
import random
import re

import requests

from config import UNSPLASH_ACCESS_KEY, PEXELS_API_KEY, PIXABAY_API_KEY, GETTY_API_KEY

log = logging.getLogger('lord.images')

# Minimum image width to accept — prevents blurry upscaled images in the hero slot.
# Article hero is displayed at ~1200px wide (16:9 ratio). 800px is the floor.
MIN_IMAGE_WIDTH = 800

MUSIC_FALLBACK_QUERIES = [
    'concert stage lights',
    'vinyl record turntable',
    'recording studio microphone',
    'music festival crowd',
    'musician performance live',
]

# Page title patterns that indicate an album/song/tour page rather than an artist bio.
# Used to skip non-portrait lead images in Wikipedia and Commons searches.
_SKIP_TITLE_CONTAINS = (
    '(album)', '(ep)', '(song)', '(single)', '(tour)', '(soundtrack)',
    '(film)', '(television series)', '(video)', 'discography', 'filmography',
    'songs written by', 'awards and', 'list of', 'wikipedia:',
)


def _wiki_headers() -> dict:
    return {
        'User-Agent': 'LORD-Music-Publication/1.0 (lord.music)',
        'Referer': 'https://en.wikipedia.org/',
    }


def _is_skip_title(title: str) -> bool:
    t = title.lower()
    return any(p in t for p in _SKIP_TITLE_CONTAINS)


def fetch_wikipedia(query: str) -> dict | None:
    """
    Fetch the lead image from a Wikipedia article matching the query.
    Skips album/tour/song pages so the result is always an artist portrait.
    """
    try:
        search_resp = requests.get(
            'https://en.wikipedia.org/w/api.php',
            params={
                'action':      'query',
                'list':        'search',
                'srsearch':    query,
                'srnamespace': 0,
                'srlimit':     5,
                'format':      'json',
            },
            headers=_wiki_headers(),
            timeout=10,
        )
        if search_resp.status_code != 200:
            return None

        results = search_resp.json().get('query', {}).get('search', [])
        if not results:
            return None

        # Descriptions that indicate the page is about a song/release/event, not a person/band
        _SKIP_DESC_WORDS = (
            ' song', ' single', ' album', ' ep ', ' soundtrack', ' compilation',
            ' track', ' remix', ' video', ' film ', ' movie', ' game ',
            ' tour', ' concert tour', ' festival', ' poster', ' residency',
        )

        # Anchor token: the first meaningful word of the query is the artist/band name.
        # The matched Wikipedia page MUST mention it, or we reject the result — this
        # prevents a query like "Beabadoobee arena tour" from matching "The Eras Tour".
        _STOPWORDS = {'the', 'a', 'an', 'of', 'and', 'live', 'concert',
                      'performing', 'tour', 'festival', 'stage', 'crowd'}
        anchor = ''
        for w in re.findall(r"[a-z0-9']+", query.lower()):
            if w not in _STOPWORDS:
                anchor = w
                break

        # Try each result until we find a valid artist/band page with a usable image
        for r in results:
            if _is_skip_title(r['title']):
                continue

            summary_resp = requests.get(
                f'https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(r["title"])}',
                headers=_wiki_headers(),
                timeout=10,
            )
            if summary_resp.status_code != 200:
                continue

            page = summary_resp.json()

            # Skip pages whose description reveals it's a release/event, not an artist
            desc_lower = (page.get('description') or '').lower()
            if any(w in desc_lower for w in _SKIP_DESC_WORDS):
                continue

            # Reject pages that don't mention the artist name from the query.
            # Guards against full-text search matching an unrelated artist's page.
            if anchor:
                title_lower = r['title'].lower()
                extract_lower = (page.get('extract') or '')[:300].lower()
                if anchor not in title_lower and anchor not in desc_lower \
                        and anchor not in extract_lower:
                    continue

            thumbnail = page.get('thumbnail')
            if not thumbnail:
                continue

            # Skip if the thumbnail itself is tiny — indicates a low-res original
            if thumbnail.get('width', 0) < 200:
                continue

            title = r['title']
            break
        else:
            return None  # no usable artist page found

        # Strip /thumb/ prefix to get the original full-resolution file
        thumb_url = thumbnail['source']  # type: ignore[index]  # set in loop above
        m = re.match(
            r'(https://upload\.wikimedia\.org/wikipedia/[^/]+)/thumb(/[^/]+/[^/]+/[^/]+)/\d+px-.+',
            thumb_url,
        )
        full_url = (m.group(1) + m.group(2)) if m else thumb_url

        page_url = page.get('content_urls', {}).get('desktop', {}).get('page',
                   f'https://en.wikipedia.org/wiki/{title}')

        return {
            'url':       full_url,
            'thumbUrl':  thumb_url,
            'credit':    f'Wikipedia — {title}',
            'creditUrl': page_url,
            'altText':   page.get('description') or title,
            'provider':  'Wikipedia',
            'evidenceTier': 'AUTHORITATIVE',
        }
    except Exception as exc:
        log.warning("Wikipedia error: %s", exc)
        return None


def fetch_wikimedia_commons(query: str, prefer_portrait: bool = False) -> dict | None:
    """
    Search Wikimedia Commons directly for a high-resolution artist photo.
    - Requires images at least MIN_IMAGE_WIDTH pixels wide
    - Prefers JPEGs over PNGs (photos vs. graphics)
    - Skips files whose names suggest album covers, logos, or posters
    - When prefer_portrait=True, portrait images (ratio < 1.1) score higher than wide shots
    - No API key required
    """
    try:
        # Search for files in the File: namespace
        search_resp = requests.get(
            'https://commons.wikimedia.org/w/api.php',
            params={
                'action':      'query',
                'list':        'search',
                'srsearch':    f'{query} filetype:bitmap',
                'srnamespace': 6,
                'srlimit':     15,
                'format':      'json',
            },
            headers=_wiki_headers(),
            timeout=10,
        )
        if search_resp.status_code != 200:
            return None

        results = search_resp.json().get('query', {}).get('search', [])
        if not results:
            return None

        # Filter out non-photo filenames upfront
        _skip_file_keywords = (
            'logo', 'signature', ' sig.', 'icon', 'album', 'cover',
            'poster', 'artwork', 'single', 'promo', 'flag', 'coat_of',
        )
        candidates_titles = []
        for r in results:
            title_lower = r['title'].lower()
            if not any(kw in title_lower for kw in _skip_file_keywords):
                candidates_titles.append(r['title'])

        if not candidates_titles:
            return None

        # Batch-fetch dimensions + URL
        info_resp = requests.get(
            'https://commons.wikimedia.org/w/api.php',
            params={
                'action':  'query',
                'titles':  '|'.join(candidates_titles[:10]),
                'prop':    'imageinfo',
                'iiprop':  'url|size|extmetadata',
                'format':  'json',
            },
            headers=_wiki_headers(),
            timeout=10,
        )
        if info_resp.status_code != 200:
            return None

        pages = info_resp.json().get('query', {}).get('pages', {})

        best_candidates = []
        for page in pages.values():
            info = page.get('imageinfo', [{}])[0]
            url   = info.get('url', '')
            width = info.get('width', 0)

            # Require minimum resolution
            if width < MIN_IMAGE_WIDTH:
                continue
            # Prefer JPEGs (photographs), tolerate PNG if large enough
            if url.lower().endswith('.svg'):
                continue

            meta     = info.get('extmetadata', {})
            raw_cred = meta.get('Artist', {}).get('value', '') or \
                       meta.get('Credit', {}).get('value', '') or ''
            credit   = re.sub(r'<[^>]+>', '', raw_cred).strip() or 'Wikimedia Commons'
            title    = page.get('title', 'File:photo').replace('File:', '')
            page_url = (
                'https://commons.wikimedia.org/wiki/' +
                requests.utils.quote(page.get('title', '').replace(' ', '_'))
            )
            height  = info.get('height', 0)
            is_jpeg = url.lower().endswith(('.jpg', '.jpeg'))
            is_portrait = (width / height < 1.1) if height else False
            best_candidates.append({
                'url':        url,
                'width':      width,
                'height':     height,
                'is_jpeg':    is_jpeg,
                'is_portrait': is_portrait,
                'credit':     credit,
                'creditUrl':  page_url,
                'altText':    title,
                'provider':   'Wikimedia',
            })

        if not best_candidates:
            return None

        # Sort: JPEGs first, then portrait preference when requested, then width descending
        best_candidates.sort(
            key=lambda x: (x['is_jpeg'], x['is_portrait'] if prefer_portrait else False, x['width']),
            reverse=True,
        )
        best = best_candidates[0]
        result = {k: v for k, v in best.items() if k not in ('width', 'height', 'is_jpeg', 'is_portrait')}
        result['evidenceTier'] = 'AUTHORITATIVE'
        return result

    except Exception as exc:
        log.warning("Wikimedia Commons error: %s", exc)
        return None


def fetch_getty(query: str) -> dict | None:
    """
    Search Getty Images Editorial API and return an embeddable image dict.
    Requires GETTY_API_KEY. Returns embedType='getty' with the oEmbed HTML snippet.
    Free editorial embeds — displayed with Getty watermark/attribution widget.
    """
    if not GETTY_API_KEY:
        return None
    try:
        search_resp = requests.get(
            'https://api.gettyimages.com/v3/search/images/editorial',
            params={
                'phrase':              query,
                'fields':              'id,title,display_sizes',
                'page_size':           5,
                'editorial_segments':  'news',
                'sort_order':          'most_popular',
            },
            headers={'Api-Key': GETTY_API_KEY},
            timeout=10,
        )
        if search_resp.status_code != 200:
            log.warning("Getty search %s for '%s'", search_resp.status_code, query)
            return None

        images = search_resp.json().get('images', [])
        if not images:
            return None

        image   = images[0]
        img_id  = image['id']
        title   = image.get('title', query)

        # Resolve the embed HTML via Getty's oEmbed endpoint (no API key needed here)
        oembed_resp = requests.get(
            'https://embed.gettyimages.com/oembed',
            params={
                'url':    f'https://www.gettyimages.com/detail/{img_id}',
                'format': 'json',
            },
            timeout=10,
        )
        if oembed_resp.status_code != 200:
            log.warning("Getty oEmbed %s for id %s", oembed_resp.status_code, img_id)
            return None

        embed_html = oembed_resp.json().get('html', '')
        if not embed_html:
            return None

        # Pull the best available display thumbnail for og:image / index preview
        thumb_url = ''
        for size_name in ('comp', 'preview', 'thumb'):
            for size in image.get('display_sizes', []):
                if size.get('name') == size_name:
                    thumb_url = size.get('uri', '')
                    break
            if thumb_url:
                break

        return {
            'embedType':    'getty',
            'embedHtml':    embed_html,
            'url':          thumb_url,
            'thumbUrl':     thumb_url,
            'credit':       'Getty Images',
            'creditUrl':    f'https://www.gettyimages.com/detail/{img_id}',
            'altText':      title,
            'provider':     'Getty',
            'evidenceTier': 'AUTHORITATIVE',
        }
    except Exception as exc:
        log.warning("Getty error: %s", exc)
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
            'url':          d['urls']['regular'],
            'fullUrl':      d['urls']['full'],
            'thumbUrl':     d['urls']['small'],
            'credit':       d['user']['name'],
            'creditUrl':    d['user']['links']['html'] + '?utm_source=lord_music&utm_medium=referral',
            'altText':      d.get('alt_description') or query,
            'provider':     'Unsplash',
            'evidenceTier': 'LOW_CONFIDENCE',
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

        # Non-Flickr sources (Wikimedia/StockSnap/Rawpixel) are more reliable;
        # Flickr is a crowdsourced last-resort with variable identity accuracy.
        evidence_tier = 'ACCEPTABLE' if exclude_flickr else 'LOW_CONFIDENCE'
        return {
            'url':          d['url'],
            'thumbUrl':     d.get('thumbnail', d['url']),
            'credit':       creator or source_label,
            'creditUrl':    creator_url,
            'altText':      d.get('title', '') or query,
            'provider':     source_label,
            'evidenceTier': evidence_tier,
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
            'url':          p.get('largeImageURL') or p['webformatURL'],
            'thumbUrl':     p['previewURL'],
            'credit':       p.get('user', 'Pixabay'),
            'creditUrl':    p['pageURL'],
            'altText':      query,
            'provider':     'Pixabay',
            'evidenceTier': 'LOW_CONFIDENCE',
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
            'url':          p['src']['large'],
            'fullUrl':      p['src']['original'],
            'thumbUrl':     p['src']['small'],
            'credit':       p['photographer'],
            'creditUrl':    p['photographer_url'],
            'altText':      p.get('alt') or query,
            'provider':     'Pexels',
            'evidenceTier': 'LOW_CONFIDENCE',
        }
    except Exception as exc:
        log.warning("Pexels error: %s", exc)
        return None


def _try_editorial(query: str) -> dict | None:
    """Try artist-specific sources only: Getty, Wikipedia, Wikimedia Commons, Openverse.
    Stock photo APIs are NOT used here — they return random strangers when
    queried for a specific artist name instead of actual photos of that person.

    HERO IMAGE POLICY: The result of this function is used as the article hero / card
    thumbnail. It must show the artist as the main subject with their face fully visible.
    Portrait close-ups are preferred over wide concert/stage shots — those belong inline.
    Wikimedia Commons search runs with prefer_portrait=True so portrait images score higher
    when multiple candidates exist.

    Priority: Getty editorial (highest quality, requires key) → Wikipedia portrait →
              Wikimedia Commons hi-res search (portrait-preferred) → Openverse/Wikimedia →
              Openverse/Flickr (last resort).
    """
    return (
        fetch_getty(query)                                         # Best quality — requires GETTY_API_KEY
        or fetch_wikipedia(query)
        or fetch_wikimedia_commons(query, prefer_portrait=True)   # Prefer close-up portraits for hero
        or fetch_openverse(query, exclude_flickr=True)            # Openverse non-Flickr sources
        or fetch_openverse(query)                                  # Flickr only as last resort
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
    Source one image for an article — editorial sources ONLY.

    Every image LORD publishes must show the actual artist. Stock photo APIs
    return random strangers, so they are never used: if no editorial photo of
    the artist is found, we return None and the article renders with a branded
    placeholder rather than a wrong-person photo.
    """
    image = _try_editorial(primary_query)
    if image:
        return image

    log.info("No artist photo found — article will render with branded placeholder")
    return None


def get_article_images(queries: list[str]) -> list[dict]:
    """
    Fetch one unique editorial image per query string.
    Used for multi-image articles (features: 3 images, reviews: 2 images).

    Editorial sources ONLY — no stock fallback. If a query returns no photo of
    the artist, that slot is simply skipped. A feature with one verified photo
    of the artist is always better than one padded with random strangers.
    """
    images: list[dict] = []
    used_urls: set[str] = set()

    for query in queries:
        if not query:
            continue
        img = _try_editorial(query)
        if img and img['url'] not in used_urls:
            used_urls.add(img['url'])
            images.append(img)

    return images
