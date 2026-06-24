#!/usr/bin/env python3
"""
Comprehensive image refresh for all LORD articles.
Replaces album covers, stock photos, duplicates, and low-quality images
with the best available photos from Wikipedia / Wikimedia Commons / Openverse.
"""
import json
import re
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from image_sourcer import _try_editorial, fetch_wikimedia_commons

logging.basicConfig(level=logging.INFO, format='%(levelname)s  %(message)s')
log = logging.getLogger('refresh')

SITE_DIR      = Path(__file__).parent.parent / 'site'
ARTICLES_DIR  = SITE_DIR / 'articles'
ARTICLES_JSON = SITE_DIR / 'api' / 'articles.json'

# ── Known best images (pre-researched for quality + landscape) ─────────────────
KNOWN = {
    # (url, credit, credit_url, alt_text, provider)
    'OVOFest_2017': (
        'https://upload.wikimedia.org/wikipedia/commons/8/87/OVOFest_2017%2Bnumerous_artists.jpg',
        'joel din / Wikimedia Commons', 'https://commons.wikimedia.org/wiki/File:OVOFest_2017%2Bnumerous_artists.jpg',
        'OVO Fest 2017', 'Wikimedia',
    ),
    'Drake_July_2016': (
        'https://upload.wikimedia.org/wikipedia/commons/2/28/Drake_July_2016.jpg',
        'The Come Up Show / Wikimedia Commons', 'https://commons.wikimedia.org/wiki/File:Drake_July_2016.jpg',
        'Drake', 'Wikimedia',
    ),
    'Drake_Carter_Effect': (
        'https://upload.wikimedia.org/wikipedia/commons/1/15/Drake_at_The_Carter_Effect_2017_%2836818935200%29_%28cropped%29.jpg',
        'Wikipedia — Drake (musician)', 'https://en.wikipedia.org/wiki/Drake_(musician)',
        'Drake', 'Wikipedia',
    ),
    'Missy_Wireless_1': (
        'https://upload.wikimedia.org/wikipedia/commons/2/2d/Missy_Elliott_-_Wireless_Festival_2010_%281%29.jpg',
        'joanneconlon / Wikimedia Commons', 'https://commons.wikimedia.org/wiki/File:Missy_Elliott_-_Wireless_Festival_2010_(1).jpg',
        'Missy Elliott performing at Wireless Festival 2010', 'Wikimedia',
    ),
    'Missy_Elliot_portrait': (
        'https://upload.wikimedia.org/wikipedia/commons/7/77/Missy_Elliot.jpg',
        'Wikipedia — Missy Elliott', 'https://en.wikipedia.org/wiki/Missy_Elliott',
        'Missy Elliott', 'Wikipedia',
    ),
    'Missy_Wireless_2': (
        'https://upload.wikimedia.org/wikipedia/commons/3/3c/Missy_Elliott_-_Wireless_Festival_2010_%282%29.jpg',
        'joanneconlon / Wikimedia Commons', 'https://commons.wikimedia.org/wiki/File:Missy_Elliott_-_Wireless_Festival_2010_(2).jpg',
        'Missy Elliott at Wireless Festival 2010', 'Wikimedia',
    ),
    'Conor_Oberst_namkung': (
        'https://upload.wikimedia.org/wikipedia/commons/6/6e/Flickr_-_moses_namkung_-_Conor_Oberst_2.jpg',
        'Moses Namkung / Wikimedia Commons', 'https://commons.wikimedia.org/wiki/File:Flickr_-_moses_namkung_-_Conor_Oberst_2.jpg',
        'Conor Oberst', 'Wikimedia',
    ),
    'Jim_James_2011': (
        'https://upload.wikimedia.org/wikipedia/commons/f/f0/Jim_James_8-12-11.jpg',
        'Wikimedia Commons', 'https://commons.wikimedia.org/wiki/File:Jim_James_8-12-11.jpg',
        'Jim James', 'Wikimedia',
    ),
    'Rodrigo_Lollapalooza': (
        'https://upload.wikimedia.org/wikipedia/commons/2/2d/Olivia_Rodrigo_-_Lollapalooza_Argentina_Concert_2025_01.jpg',
        'Wikimedia Commons', 'https://commons.wikimedia.org/wiki/File:Olivia_Rodrigo_-_Lollapalooza_Argentina_Concert_2025_01.jpg',
        'Olivia Rodrigo performing at Lollapalooza Argentina 2025', 'Wikimedia',
    ),
}


# ── HTML manipulation helpers ──────────────────────────────────────────────────

_HERO_RE = re.compile(
    r'(\s*<div class="article-hero-image">\n)(\s*<img src=")([^"]*)(".*?</div>)',
    re.DOTALL,
)

_INLINE_RE = re.compile(
    r'(<figure class="article-inline-image">\n\s*<img src=")([^"]*)("[^>]*>)\n(\s*<figcaption[^>]*>)(.*?)(</figcaption>)',
    re.DOTALL,
)


def _img_tag(url, alt, extra='loading="lazy"'):
    return f'<img src="{url}" alt="{alt}" {extra}>'


def _credit_html_hero(credit, cred_url, provider):
    if not credit:
        return ''
    suf = f' / {provider}' if provider else ''
    return (
        f'\n      <div class="article-image-credit">'
        f'Photo: <a href="{cred_url}" target="_blank" rel="noopener noreferrer">'
        f'{credit}</a>{suf}</div>'
    )


def _credit_html_inline(credit, cred_url, provider):
    suf = f' / {provider}' if provider else ''
    return (
        f'<figcaption class="article-image-credit">'
        f'Photo: <a href="{cred_url}" target="_blank" rel="noopener noreferrer">'
        f'{credit}</a>{suf}</figcaption>'
    )


def img_block(k):
    """Build a hero + inline image dict tuple from KNOWN lookup key."""
    url, credit, cred_url, alt, provider = KNOWN[k]
    return {'url': url, 'credit': credit, 'creditUrl': cred_url, 'altText': alt, 'provider': provider}


def replace_hero(html: str, img: dict) -> str:
    url      = img['url']
    credit   = img.get('credit', '')
    cred_url = img.get('creditUrl', '#')
    provider = img.get('provider', '')
    alt      = img.get('altText', '')
    cred_html = _credit_html_hero(credit, cred_url, provider)
    new_block = (
        f'    <div class="article-hero-image">\n'
        f'      <img src="{url}" alt="{alt}" loading="eager">{cred_html}\n'
        f'    </div>'
    )
    hero_re = re.compile(r'    <div class="article-hero-image">\n.*?    </div>', re.DOTALL)
    updated, n = hero_re.subn(new_block, html, count=1)
    if n == 0:
        log.warning("    Hero block not found")
    return updated


def replace_inline(html: str, index: int, img: dict) -> str:
    """Replace the Nth inline image (0-based) in the HTML body."""
    url      = img['url']
    credit   = img.get('credit', '')
    cred_url = img.get('creditUrl', '#')
    provider = img.get('provider', '')
    alt      = img.get('altText', '')
    figcap   = _credit_html_inline(credit, cred_url, provider)

    new_figure = (
        f'    <figure class="article-inline-image">\n'
        f'      <img src="{url}" alt="{alt}" loading="lazy">\n'
        f'      {figcap}\n'
        f'    </figure>'
    )

    inline_re = re.compile(r'    <figure class="article-inline-image">.*?    </figure>', re.DOTALL)
    matches = list(inline_re.finditer(html))
    if index >= len(matches):
        log.warning("    Inline index %d not found (only %d inlines)", index, len(matches))
        return html

    m = matches[index]
    return html[:m.start()] + new_figure + html[m.end():]


# ── Per-article update plans ───────────────────────────────────────────────────

def update_drake(html: str) -> str:
    log.info("  Drake: new hero (OVOFest landscape) + fix inline images")
    html = replace_hero(html, img_block('OVOFest_2017'))
    html = replace_inline(html, 0, img_block('Drake_July_2016'))
    html = replace_inline(html, 1, img_block('Drake_Carter_Effect'))
    return html


def update_missy(html: str) -> str:
    log.info("  Missy Elliott: Wireless Festival hero (3050x1714) + replace album covers")
    html = replace_hero(html, img_block('Missy_Wireless_1'))
    html = replace_inline(html, 0, img_block('Missy_Elliot_portrait'))
    html = replace_inline(html, 1, img_block('Missy_Wireless_2'))
    return html


def update_conor(html: str) -> str:
    log.info("  Conor Oberst: replace Lifted album cover inline with concert photo")
    html = replace_inline(html, 0, img_block('Conor_Oberst_namkung'))
    return html


def update_jim_james(html: str) -> str:
    log.info("  Jim James: replace Eternally Even album cover inline")
    html = replace_inline(html, 1, img_block('Jim_James_2011'))
    return html


def update_olivia_review(html: str) -> str:
    log.info("  Olivia Rodrigo review: replace SOUR album cover inline")
    html = replace_inline(html, 0, img_block('Rodrigo_Lollapalooza'))
    return html


def update_everyone_says_hi(html: str) -> str:
    """Hero is an album cover; try to find a real band photo, fix The Aces inline."""
    log.info("  Everyone Says Hi: replace album-cover hero + remove unrelated band inline")
    # Try to get a band photo from editorial sources
    img = _try_editorial('Everyone Says Hi British indie band')
    if img and 'everyone_says_hi.jpg' not in img.get('url', '').lower():
        html = replace_hero(html, img)
        log.info("    New hero: [%s] %s", img.get('provider'), img.get('url', '')[:70])
    else:
        log.info("    No better hero found — keeping current")

    # Replace inline 2 (The Aces — wrong band)
    img2 = _try_editorial('Kaiser Chiefs Ricky Wilson indie rock')
    if not img2:
        img2 = _try_editorial('British indie rock band concert')
    if img2:
        html = replace_inline(html, 1, img2)
        log.info("    New inline 2: [%s] %s", img2.get('provider'), img2.get('url', '')[:70])
    return html


# ── Article JSON update ────────────────────────────────────────────────────────

def update_json_hero(entries: list, article_id: str, img: dict) -> None:
    for entry in entries:
        if entry['id'] == article_id:
            entry['image']         = img.get('url', '')
            entry['imageProvider'] = img.get('provider', '')
            break


# ── Main ──────────────────────────────────────────────────────────────────────

UPDATES = {
    '20260624-drake-and-the-art-of-disappearing-in-plain-sight':                        (update_drake,       'OVOFest_2017'),
    '20260623-missy-elliott-didnt-predict-the-future-she-built-it':                     (update_missy,       'Missy_Wireless_1'),
    '20260623-conor-oberst-has-always-been-writing-the-same-confession':                (update_conor,       None),
    '20260623-jim-james-returns-from-the-archive-with-something-alive':                 (update_jim_james,   None),
    '20260623-rodrigo-turns-the-wound-into-the-weapon':                                 (update_olivia_review, None),
    '20260623-the-second-act-nobody-saw-coming-everyone-says-hi':                       (update_everyone_says_hi, None),
}


def main():
    with open(ARTICLES_JSON, encoding='utf-8') as f:
        index = json.load(f)

    changed = 0
    for article_id, (update_fn, hero_key) in UPDATES.items():
        html_path = ARTICLES_DIR / f'{article_id}.html'
        if not html_path.exists():
            log.warning("Missing: %s", article_id)
            continue

        log.info("── %s", article_id)
        html = html_path.read_text('utf-8')
        updated = update_fn(html)

        if updated != html:
            html_path.write_text(updated, 'utf-8')
            log.info("  Saved ✓")
            changed += 1

        if hero_key:
            update_json_hero(index['articles'], article_id, img_block(hero_key))

    with open(ARTICLES_JSON, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    log.info("\nUpdated %d articles + articles.json", changed)


if __name__ == '__main__':
    main()
