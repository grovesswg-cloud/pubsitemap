"""LORD Automation — Publisher
Generates article HTML pages and maintains the articles index.
"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from config import ARTICLES_DIR, ARTICLES_JSON, API_DIR

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
        {_a('../sections/sermon.html', 'Sermon', 'sermon')}
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
        <a href="../sections/sermon.html">Sermon</a>
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


# ─── HTML generation ──────────────────────────────────────────────────────────

def _build_article_html(data: dict) -> str:
    title       = data.get('title', '')
    deck        = data.get('deck', '')
    body        = data.get('body', '')
    article_type = data.get('type', 'bulletin')
    date_str    = data.get('date', '')
    source      = data.get('source', '')
    source_url  = data.get('sourceUrl', '')
    image_url   = data.get('image', '')
    image_alt   = data.get('imageAlt', title)
    img_credit  = data.get('imageCredit', '')
    img_cred_url = data.get('imageCreditUrl', '#')
    rating      = data.get('rating', '')  # for reviews

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

    if image_url:
        credit_html = (
            f'\n      <div class="article-image-credit">'
            f'Photo: <a href="{img_cred_url}" target="_blank" rel="noopener noreferrer">'
            f'{img_credit}</a> / Unsplash</div>'
        ) if img_credit else ''
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


def count_today(index: dict) -> int:
    """Count how many articles have been published today (UTC)."""
    today = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    return sum(1 for a in index.get('articles', []) if a.get('date') == today)


# ─── Main publish function ────────────────────────────────────────────────────

def publish_article(data: dict, image: dict | None = None) -> dict:
    """
    Write one article HTML file, update the index, and return the index entry.
    """
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    API_DIR.mkdir(parents=True, exist_ok=True)

    # Attach image data
    if image:
        data['image']         = image['url']
        data['imageAlt']      = image.get('altText', data.get('title', ''))
        data['imageCredit']   = image.get('credit', '')
        data['imageCreditUrl'] = image.get('creditUrl', '#')

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
        'id':        filename.replace('.html', ''),
        'title':     data.get('title', ''),
        'deck':      data.get('deck', ''),
        'type':      data.get('type', 'bulletin'),
        'date':      data.get('date', ''),
        'url':       f"articles/{filename}",
        'image':     data.get('image', ''),
        'tags':      data.get('tags', []),
        'source':    data.get('source', ''),
        'sourceUrl': data.get('sourceUrl', ''),
    }

    # Prepend (newest first)
    index = load_index()
    index['articles'].insert(0, entry)
    save_index(index)
    log.info("Index updated — total articles: %d", len(index['articles']))

    return entry
