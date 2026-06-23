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
ANTHROPIC_API_KEY   = os.getenv('ANTHROPIC_API_KEY', '')
UNSPLASH_ACCESS_KEY = os.getenv('UNSPLASH_ACCESS_KEY', '')
NEWS_API_KEY        = os.getenv('NEWS_API_KEY', '')     # optional: newsapi.org
PEXELS_API_KEY      = os.getenv('PEXELS_API_KEY', '')  # optional: fallback images

# ─── Publication schedule ─────────────────────────────────────────────────────
# Three bulletins per day. Times are UTC for GitHub Actions cron.
PUBLISH_TIMES_UTC = ['08:00', '14:00', '20:00']

# ─── Content model ────────────────────────────────────────────────────────────
DEFAULT_ARTICLE_TYPE  = 'bulletin'
MAX_BULLETINS_PER_DAY = 3

# Model to use for article writing.
# Haiku is recommended for bulletins — fast, cheap, more than capable for short news.
# Override per-site via ANTHROPIC_MODEL env var.
# Haiku 4.5:   claude-haiku-4-5-20251001   (~$5-6/month for 15 sites)
# Sonnet 4.6:  claude-sonnet-4-6            (~$20-22/month for 15 sites)
ANTHROPIC_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')

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

# ─── LORD Voice prompt (injected into every generation request) ───────────────
LORD_VOICE = """
LORD is an independent online music publication with an authoritative, literary editorial voice.

TONE SPECTRUM:
- Authoritative but not arrogant
- Reverent but not sycophantic
- Precise but not cold
- Literary but not inaccessible
- Critical but not cruel

LORD WRITES LIKE THIS:
- Feature lede: "Kendrick Lamar does not make albums. He builds indictments."
- Review opener: "The record opens on silence. Two full seconds of it. Then the snare."
- Closing line: "The question the album raises is the question it refuses to answer. That is the point."

LORD NEVER WRITES LIKE THIS:
- Hype: "This album is a MASTERPIECE. You NEED to hear this!!"
- Clickbait: "You won't believe what this artist said..."
- Vague praise: "The production is amazing and the lyrics really hit different."
- Opinion as fact: "Everyone agrees this is the best rap album of the decade."
- Apology writing: "It might not be for everyone, but some could argue that..."
"""
