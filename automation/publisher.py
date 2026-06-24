"""LORD Automation — Publisher
Generates article HTML pages and maintains the articles index.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import ARTICLES_DIR, ARTICLES_JSON, API_DIR, SITE_DIR, GOOGLE_INDEXING_KEY, SITE_DOMAIN

log = logging.getLogger('lord.publisher')

# ─── Shared site header/footer partials ───────────────────────────────────────

def _header(active: str = '') -> str:
    def _a(href, label, key):
        cls = ' class="active"' if active == key else ''
        return f'<a href="{href}"{cls}>{label}</a>'

    return f"""\
  <header class="site-header">
    <div class="header-rule-top">
      <div class="rule-gold"></div>
      <div class="rule-gold"></div>
    </div>
    <div class="header-inner">
      <a href="../index.html" class="site-wordmark">LORD</a>
      <nav class="site-nav">
        {_a('../sections/features.html', 'Features', 'feature')}
        {_a('../sections/reviews.html', 'Reviews', 'review')}
        {_a('../sections/bulletin.html', 'Bulletin', 'bulletin')}
        {_a('../sections/about.html', 'About', '')}
      </nav>
    </div>
    <div class="header-sub container">
      <span class="header-tagline">Music &mdash; Power &mdash; Sovereignty</span>
      <span class="header-domain"><em>Lord.music</em> &mdash; Est. MMXXVI</span>
    </div>
    <div class="header-rule-bottom">
      <div class="rule-gold"></div>
      <div class="rule-gold"></div>
    </div>
  </header>"""


def _footer() -> str:
    return """\
  <footer class="site-footer">
    <div class="footer-rule-top"></div>
    <div class="footer-inner">
      <div class="footer-brand">
        <div class="footer-wordmark">LORD</div>
        <div class="footer-tagline">Music. Power. Sovereignty.</div>
        <div class="footer-est">Est. MMXXVI &mdash; lord.music</div>
      </div>
      <nav class="footer-nav-grid">
        <a href="../sections/features.html">Features</a>
        <a href="../sections/reviews.html">Reviews</a>
        <a href="../sections/bulletin.html">Bulletin</a>
        <a href="../sections/about.html">About</a>
      </nav>
      <div class="footer-statement">
        LORD is an independent online music publication. All editorial content is copyright LORD MMXXVI.
        Reproduction without written permission is prohibited. Editorial independence is non-negotiable.
      </div>
    </div>
    <div class="footer-bottom">
      <span class="footer-copy">&copy; LORD MMXXVI &mdash; All rights reserved.</span>
      <span class="footer-copy">lord.music</span>
    </div>
  </footer>"""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-{2,}', '-', text)
    text = text.strip('-')
    return text[:80]


def _type_label(article_type: str) -> str:
    return {
        'bulletin':  'The Bulletin',
        'review':    'The Review',
        'feature':   'The Feature',
        'sermon':    'The Sermon',
        'archive':   'The Archive',
        'interview': 'The Interview',
        'culture':   'Culture',
    }.get(article_type, article_type.capitalize())


def _format_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return d.strftime('%B %d, %Y')
    except ValueError:
        return date_str


def _build_inline_image_html(image: dict) -> str:
    """Build an inline <figure> block to inject between body paragraphs."""
    url      = image.get('url', '')
    alt      = image.get('altText', '')
    credit   = image.get('credit', '')
    cred_url = image.get('creditUrl', '#')
    provider = image.get('provider', '')

    if credit:
        provider_suffix = f' / {provider}' if provider else ''
        caption = (
            f'<figcaption class="article-image-credit">'
            f'Photo: <a href="{cred_url}" target="_blank" rel="noopener noreferrer">'
            f'{credit}</a>{provider_suffix}</figcaption>'
        )
    else:
        caption = ''

    return (
        f'\n    <figure class="article-inline-image">\n'
        f'      <img src="{url}" alt="{alt}" loading="lazy">\n'
        f'      {caption}\n'
        f'    </figure>\n'
    )


def _inject_inline_images(body_html: str, images: list[dict]) -> str:
    """Insert inline image blocks at evenly spaced paragraph breaks in the body."""
    if not images:
        return body_html

    # Collect the character position after each </p> tag
    ends = [m.end() for m in re.finditer(r'</p>', body_html, re.IGNORECASE)]
    n = len(ends)

    # Need at least 4 paragraphs and enough room to space images
    if n < 4 or not images:
        return body_html

    # Insertion points: divide the safe zone (skip first 2, last 2 paragraphs)
    # evenly among the images
    n_imgs = len(images)
    safe_ends = ends[2:-2]          # exclude first and last 2 paragraphs
    step = max(1, len(safe_ends) // (n_imgs + 1))
    insert_positions = [safe_ends[min(step * (i + 1), len(safe_ends) - 1)] for i in range(n_imgs)]

    # Deduplicate while preserving order
    insert_positions = sorted(set(insert_positions))

    # Build result by inserting in reverse order (so positions stay valid)
    result = body_html
    for pos, img in zip(reversed(insert_positions), reversed(images[:len(insert_positions)])):
        result = result[:pos] + _build_inline_image_html(img) + result[pos:]

    return result


# ─── HTML generation ──────────────────────────────────────────────────────────

def _build_article_html(data: dict) -> str:
    title       = data.get('title', '')
    deck        = data.get('deck', '')
    body        = data.get('body', '')
    article_type = data.get('type', 'bulletin')
    date_str    = data.get('date', '')
    source      = data.get('source', '')
    source_url  = data.get('sourceUrl', '')
    image_url      = data.get('image', '')
    image_alt      = data.get('imageAlt', title)
    img_credit     = data.get('imageCredit', '')
    img_cred_url   = data.get('imageCreditUrl', '#')
    img_provider   = data.get('imageProvider', '')
    image_embed_html = data.get('imageEmbedHtml', '')
    rating        = data.get('rating', '')
    genre         = data.get('genre', '')

    inline_images = data.get('inlineImages', [])
    if inline_images:
        body = _inject_inline_images(body, inline_images)

    type_label    = _type_label(article_type)
    formatted_date = _format_date(date_str)

    og_image_meta = (
        f'  <meta property="og:image" content="{image_url}">'
        if image_url else ''
    )

    review_badge = (
        f'      <div class="review-badge">{rating}</div>'
        if article_type == 'review' and rating else ''
    )
    genre_badge = (
        f'      <span class="genre-badge">{genre}</span>'
        if genre else ''
    )

    if image_embed_html:
        # Getty (or other JS-based) embed — rendered as a widget, not a plain <img>
        image_block = f"""\
    <div class="article-hero-image article-hero-embed">
{image_embed_html}
    </div>"""
    elif image_url:
        if img_credit:
            provider_suffix = f' / {img_provider}' if img_provider else ''
            credit_html = (
                f'\n      <div class="article-image-credit">'
                f'Photo: <a href="{img_cred_url}" target="_blank" rel="noopener noreferrer">'
                f'{img_credit}</a>{provider_suffix}</div>'
            )
        else:
            credit_html = ''
        image_block = f"""\
    <div class="article-hero-image">
      <img src="{image_url}" alt="{image_alt}" loading="eager">
      {credit_html}
    </div>"""
    else:
        image_block = ''

    source_block = ''
    if source_url:
        source_block = f"""\
    <div class="article-source">
      Source: <a href="{source_url}" target="_blank" rel="noopener noreferrer">{source or source_url}</a>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} &mdash; LORD</title>
  <meta name="description" content="{deck}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{deck}">
  <meta property="og:site_name" content="LORD">
{og_image_meta}
  <meta name="theme-color" content="#080808">
  <link rel="icon" type="image/svg+xml" href="../assets/images/favicon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700&family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500;1,600&family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../assets/css/style.css">
</head>
<body>

{_header(active=article_type)}

  <article class="article-page">

    <header class="article-header">
      <div class="article-eyebrow">{type_label}</div>
{review_badge}
{genre_badge}
      <h1 class="article-title">{title}</h1>
      <p class="article-deck">{deck}</p>
      <div class="article-meta-bar">
        <span class="meta-type">{type_label}</span>
        <span>&mdash;</span>
        <span class="meta-date">{formatted_date}</span>
      </div>
    </header>

{image_block}

    <div class="article-body">
{body}
    </div>

{source_block}

  </article>

{_footer()}

</body>
</html>
"""


# ─── Index management ─────────────────────────────────────────────────────────

def load_index() -> dict:
    if ARTICLES_JSON.exists():
        with open(ARTICLES_JSON, encoding='utf-8') as f:
            return json.load(f)
    return {'articles': [], 'lastUpdated': None}


def save_index(data: dict) -> None:
    API_DIR.mkdir(parents=True, exist_ok=True)
    data['lastUpdated'] = datetime.now(tz=timezone.utc).isoformat()
    with open(ARTICLES_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_duplicate(news_title: str, index: dict) -> bool:
    """Return True if a news headline already exists in the index."""
    key = news_title.lower().strip()[:60]
    for entry in index.get('articles', []):
        if key in entry.get('title', '').lower():
            return True
    return False


def is_artist_covered(artist: str, index: dict, days: int = 30) -> bool:
    """Return True if any article about this artist was published within the last `days` days."""
    from datetime import timedelta
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d')
    artist_slug = slugify(artist)
    artist_lower = artist.lower()
    for entry in index.get('articles', []):
        if entry.get('date', '') < cutoff:
            continue
        for tag in entry.get('tags', []):
            if artist_slug in tag or tag in artist_slug:
                return True
        if artist_lower in entry.get('title', '').lower():
            return True
    return False


def count_today(index: dict) -> int:
    """Count all articles published today (UTC)."""
    today = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    return sum(1 for a in index.get('articles', []) if a.get('date') == today)


def count_today_by_type(index: dict, article_type: str) -> int:
    """Count articles of a specific type published today (UTC)."""
    today = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    return sum(
        1 for a in index.get('articles', [])
        if a.get('date') == today and a.get('type') == article_type
    )


# ─── Sitemap ──────────────────────────────────────────────────────────────────

STATIC_URLS = [
    ('/', '1.0', 'daily'),
    ('/sections/features.html', '0.8', 'daily'),
    ('/sections/reviews.html',  '0.8', 'daily'),
    ('/sections/bulletin.html', '0.8', 'daily'),
    ('/sections/about.html',    '0.5', 'monthly'),
]

def generate_sitemap(index: dict) -> None:
    """Write site/sitemap.xml from the current article index."""
    domain = SITE_DOMAIN.rstrip('/')
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    for path, priority, changefreq in STATIC_URLS:
        lines += [
            '  <url>',
            f'    <loc>{domain}{path}</loc>',
            f'    <changefreq>{changefreq}</changefreq>',
            f'    <priority>{priority}</priority>',
            '  </url>',
        ]

    for article in index.get('articles', []):
        url_path = article.get('url', '')
        date     = article.get('date', '')
        if not url_path:
            continue
        lines += [
            '  <url>',
            f'    <loc>{domain}/{url_path}</loc>',
            f'    <lastmod>{date}</lastmod>',
            '    <changefreq>never</changefreq>',
            '    <priority>0.7</priority>',
            '  </url>',
        ]

    lines.append('</urlset>')
    sitemap_path = SITE_DIR / 'sitemap.xml'
    sitemap_path.write_text('\n'.join(lines), encoding='utf-8')
    log.info("Sitemap written: %d URLs", len(index.get('articles', [])) + len(STATIC_URLS))


def ping_google_indexing(article_url: str) -> None:
    """Submit a single article URL to the Google Indexing API."""
    if not GOOGLE_INDEXING_KEY:
        return
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account

        creds_info = json.loads(GOOGLE_INDEXING_KEY)
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/indexing'],
        )
        creds.refresh(google.auth.transport.requests.Request())
        r = requests.post(
            'https://indexing.googleapis.com/v3/urlNotifications:publish',
            headers={'Authorization': f'Bearer {creds.token}'},
            json={'url': article_url, 'type': 'URL_UPDATED'},
            timeout=15,
        )
        log.info("Google Indexing API: %s %s", r.status_code, article_url)
    except Exception as exc:
        log.warning("Google Indexing API failed: %s", exc)


# ─── Main publish function ────────────────────────────────────────────────────

def publish_article(data: dict, images: 'list[dict] | dict | None' = None) -> dict:
    """
    Write one article HTML file, update the index, and return the index entry.
    images: list of image dicts (index 0 = hero, rest = inline), or a single dict, or None.
    """
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    API_DIR.mkdir(parents=True, exist_ok=True)

    # Normalise images to a list
    if isinstance(images, dict):
        images = [images]
    elif not images:
        images = []

    # Attach hero image metadata
    hero = images[0] if images else None
    if hero:
        data['image']          = hero.get('url', '')
        data['imageAlt']       = hero.get('altText', data.get('title', ''))
        data['imageCredit']    = hero.get('credit', '')
        data['imageCreditUrl'] = hero.get('creditUrl', '#')
        data['imageProvider']  = hero.get('provider', '')
        if hero.get('embedType') == 'getty':
            data['imageEmbedHtml'] = hero.get('embedHtml', '')

    # Store inline images for body injection
    data['inlineImages'] = images[1:] if len(images) > 1 else []

    # Build filename
    date_prefix = data.get('date', datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')).replace('-', '')
    base_slug   = slugify(data.get('title', 'untitled'))
    filename    = f"{date_prefix}-{base_slug}.html"
    filepath    = ARTICLES_DIR / filename

    # Avoid collisions
    counter = 1
    while filepath.exists():
        filename = f"{date_prefix}-{base_slug}-{counter}.html"
        filepath = ARTICLES_DIR / filename
        counter += 1

    # Write HTML
    html = _build_article_html(data)
    filepath.write_text(html, encoding='utf-8')
    log.info("Wrote article: %s", filepath.name)

    # Build index entry
    entry = {
        'id':         filename.replace('.html', ''),
        'title':      data.get('title', ''),
        'deck':       data.get('deck', ''),
        'type':       data.get('type', 'bulletin'),
        'genre':      data.get('genre', ''),
        'date':       data.get('date', ''),
        'url':        f"articles/{filename}",
        'image':      data.get('image', ''),
        'tags':       data.get('tags', []),
        'source':     data.get('source', ''),
        'sourceUrl':  data.get('sourceUrl', ''),
        'artistName': data.get('artistName', ''),
        'albumName':  data.get('albumName', ''),
    }

    # Prepend (newest first)
    index = load_index()
    index['articles'].insert(0, entry)
    save_index(index)
    log.info("Index updated — total articles: %d", len(index['articles']))

    # Regenerate sitemap and notify Google via the Indexing API.
    # (The legacy sitemap ping endpoint was retired by Google in 2023 and
    # now always returns 404 — Search Console re-crawls the sitemap on its
    # own schedule, so we only submit the new URL to the Indexing API.)
    generate_sitemap(index)
    full_url = f"{SITE_DOMAIN.rstrip('/')}/{entry['url']}"
    ping_google_indexing(full_url)

    return entry
