#!/usr/bin/env python3
"""One-time script: update hero images for articles that have album covers / stock photos."""
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from image_sourcer import _try_editorial, fetch_wikipedia, fetch_wikimedia_commons

logging.basicConfig(level=logging.INFO, format='%(levelname)s  %(message)s')
log = logging.getLogger('update')

SITE_DIR      = Path(__file__).parent.parent / 'site'
ARTICLES_DIR  = SITE_DIR / 'articles'
ARTICLES_JSON = SITE_DIR / 'api' / 'articles.json'

# Articles that need a better image and the best query to find one
TARGETS = [
    {
        'id':     '20260624-the-strokes-cover-the-walkmens-heaven-with-hamilton-leithauser-in-boston',
        'query':  'The Strokes band Julian Casablancas',
        'reason': 'Currently shows album cover PNG, not an artist photo',
    },
    {
        'id':     '20260624-drake-and-the-art-of-disappearing-in-plain-sight',
        'query':  'Drake rapper musician',
        'reason': 'Currently shows 2025 tour poster, not an artist photo',
    },
    {
        'id':     '20260624-turnstile-announce-2026-north-american-tour-with-eclectic-opener-lineup',
        'query':  'Turnstile band hardcore punk',
        'reason': 'Currently shows a Pixabay generic stock photo',
    },
    {
        'id':     '20260623-the-second-act-nobody-saw-coming-everyone-says-hi',
        'query':  'Everyone Says Hi band',
        'reason': 'Image may be an album cover — try to get an artist photo instead',
    },
]

# ── HTML hero-block regex ──────────────────────────────────────────────────────
# Matches the full hero block regardless of credit line presence.
_HERO_RE = re.compile(
    r'    <div class="article-hero-image">\n.*?    </div>',
    re.DOTALL,
)


def _build_hero_html(img: dict, title: str) -> str:
    url      = img.get('url', '')
    alt      = img.get('altText', title)
    credit   = img.get('credit', '')
    cred_url = img.get('creditUrl', '#')
    provider = img.get('provider', '')

    if credit:
        provider_suffix = f' / {provider}' if provider else ''
        credit_html = (
            f'\n      <div class="article-image-credit">'
            f'Photo: <a href="{cred_url}" target="_blank" rel="noopener noreferrer">'
            f'{credit}</a>{provider_suffix}</div>'
        )
    else:
        credit_html = ''

    return (
        f'    <div class="article-hero-image">\n'
        f'      <img src="{url}" alt="{alt}" loading="eager">{credit_html}\n'
        f'    </div>'
    )


def update_article(article_id: str, query: str, reason: str, index_articles: list) -> bool:
    html_path = ARTICLES_DIR / f'{article_id}.html'
    if not html_path.exists():
        log.warning("HTML file not found: %s", html_path.name)
        return False

    log.info("── %s", article_id)
    log.info("   Reason : %s", reason)
    log.info("   Query  : %s", query)

    img = _try_editorial(query)
    if not img:
        log.warning("   No image found — skipping")
        return False

    if img.get('embedType') == 'getty':
        log.info("   Getty embed — skipping HTML update (would need embed block)")
        return False

    log.info("   Found  : [%s] %s", img.get('provider', '?'), img.get('url', '')[:80])
    log.info("   Credit : %s", img.get('credit', ''))

    # Find the article title for alt text fallback
    article_entry = next((a for a in index_articles if a['id'] == article_id), {})
    title = article_entry.get('title', query)

    # Update HTML
    html = html_path.read_text(encoding='utf-8')
    new_hero = _build_hero_html(img, title)
    updated_html, n_subs = _HERO_RE.subn(new_hero, html, count=1)
    if n_subs == 0:
        log.warning("   Hero block not found in HTML — skipping")
        return False

    html_path.write_text(updated_html, encoding='utf-8')
    log.info("   HTML updated ✓")

    # Update articles.json entry
    for entry in index_articles:
        if entry['id'] == article_id:
            entry['image']         = img.get('url', '')
            entry['imageProvider'] = img.get('provider', '')
            break

    return True


def main() -> None:
    with open(ARTICLES_JSON, encoding='utf-8') as f:
        index = json.load(f)

    changed = 0
    for target in TARGETS:
        if update_article(target['id'], target['query'], target['reason'], index['articles']):
            changed += 1

    if changed:
        with open(ARTICLES_JSON, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        log.info("\nUpdated %d article(s) and saved articles.json", changed)
    else:
        log.info("\nNo articles updated.")


if __name__ == '__main__':
    main()
