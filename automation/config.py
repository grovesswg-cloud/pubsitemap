"""LORD Automation — Configuration"""
import os
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT_DIR     = Path(__file__).parent.parent
SITE_DIR     = ROOT_DIR / 'site'
ARTICLES_DIR = SITE_DIR / 'articles'
SECTIONS_DIR = SITE_DIR / 'sections'
API_DIR      = SITE_DIR / 'api'
ARTICLES_JSON = API_DIR / 'articles.json'

# ─── API Keys (set via environment variables / GitHub Secrets) ─────────────────
ANTHROPIC_API_KEY    = os.getenv('ANTHROPIC_API_KEY', '')
UNSPLASH_ACCESS_KEY  = os.getenv('UNSPLASH_ACCESS_KEY', '')
NEWS_API_KEY         = os.getenv('NEWS_API_KEY', '')      # optional: newsapi.org
PEXELS_API_KEY       = os.getenv('PEXELS_API_KEY', '')   # optional: pexels.com
PIXABAY_API_KEY      = os.getenv('PIXABAY_API_KEY', '')  # optional: pixabay.com
GETTY_API_KEY        = os.getenv('GETTY_API_KEY', '')    # optional: gettyimages.com editorial embeds
GOOGLE_INDEXING_KEY  = os.getenv('GOOGLE_INDEXING_KEY', '')  # optional: Google Indexing API service account JSON
GOOGLE_GEMINI_API_KEY  = os.getenv('GOOGLE_GEMINI_API_KEY', '')   # required for fact + vision verification
GEMINI_FACT_MODEL      = os.getenv('GEMINI_FACT_MODEL',   'gemini-2.5-flash')  # override to upgrade model
GEMINI_VISION_MODEL    = os.getenv('GEMINI_VISION_MODEL', 'gemini-2.5-flash')  # must support vision input

# Public domain for sitemap + indexing API (no trailing slash)
SITE_DOMAIN = os.getenv('SITE_DOMAIN', 'https://lordmedia.live')

# ─── Publication schedule ─────────────────────────────────────────────────────
PUBLISH_TIMES_UTC = ['06:00', '09:00', '12:00', '15:00', '18:00', '21:00']

# ─── Content model ────────────────────────────────────────────────────────────
DEFAULT_ARTICLE_TYPE  = 'bulletin'
MAX_BULLETINS_PER_DAY = 6
MAX_FEATURES_PER_DAY  = 3
MAX_REVIEWS_PER_DAY   = 3

# Model to use for article writing. Override per-site via ANTHROPIC_MODEL env var.
ANTHROPIC_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6')

# ─── RSS news sources ─────────────────────────────────────────────────────────
# All free, no API key required. Covers broad music news landscape.
RSS_FEEDS = [
    'https://www.rollingstone.com/music/music-news/feed/',
    'https://www.nme.com/news/music/feed',
    'https://consequence.net/feed/',
    'https://www.theguardian.com/music/rss',
    'https://pitchfork.com/rss/news/feed.json',
    'https://www.billboard.com/feed/',
    'https://hypebeast.com/music/feed',
    'https://stereogum.com/feed/',
    'https://uproxx.com/music/feed/',
    'https://www.complex.com/music/rss',
]

# ─── Quality Pipeline Feature Flags ──────────────────────────────────────────
# Toggle any stage off instantly via environment variable (e.g. on API outage).
# Metadata validation is on by default; all others are off until their PR lands.
QUALITY_METADATA_VALIDATION = os.getenv('QUALITY_METADATA_VALIDATION', 'true').lower()  == 'true'
QUALITY_FACT_VERIFICATION   = os.getenv('QUALITY_FACT_VERIFICATION',   'false').lower() == 'true'
QUALITY_FACT_FAIL_OPEN      = os.getenv('QUALITY_FACT_FAIL_OPEN',      'false').lower() == 'true'
QUALITY_IMAGE_VALIDATION    = os.getenv('QUALITY_IMAGE_VALIDATION',    'false').lower() == 'true'
QUALITY_IMAGE_FAIL_OPEN     = os.getenv('QUALITY_IMAGE_FAIL_OPEN',     'false').lower() == 'true'
QUALITY_EDITORIAL_REVIEW      = os.getenv('QUALITY_EDITORIAL_REVIEW',      'false').lower() == 'true'
QUALITY_EDITORIAL_FAIL_OPEN   = os.getenv('QUALITY_EDITORIAL_FAIL_OPEN',   'false').lower() == 'true'
QUALITY_SEO_VALIDATION        = os.getenv('QUALITY_SEO_VALIDATION',        'false').lower() == 'true'

# ─── Editorial Intelligence Engine ────────────────────────────────────────────
# When true (default), reviews and features run the full reasoning pipeline
# before writing. Set REASONING_ENGINE=false to use the direct-writer path
# for quality comparison or debugging.
REASONING_ENGINE = os.getenv('REASONING_ENGINE', 'true').lower() == 'true'
