"""LORD Automation — Album Finder
Discovers current album releases from news and selects classic albums for monthly reviews.
"""
import json
import logging
import re
from datetime import datetime, timezone

from config import ANTHROPIC_MODEL, ANTHROPIC_API_KEY

log = logging.getLogger('lord.albums')

import anthropic
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    return text.strip()


def _get_reviewed_albums(index: dict) -> list[dict]:
    """Return list of already-reviewed albums from the article index."""
    return [
        {'title': a.get('title', ''), 'tags': a.get('tags', [])}
        for a in index.get('articles', [])
        if a.get('type') == 'review'
    ]


def extract_album_from_news(news_items: list[dict], reviewed: list[dict] | None = None) -> dict | None:
    """
    Use Claude to identify a current album release from news headlines.
    Returns dict with {artist, album, context, imageQuery} or None.
    reviewed: list of already-reviewed album dicts to avoid repeating.
    """
    if not news_items:
        return None

    headlines = '\n'.join(
        f"- {item['title']}: {item.get('summary', '')[:200]}"
        for item in news_items[:20]
    )

    already_reviewed = ''
    if reviewed:
        already_reviewed = '\n\nAlready covered (do NOT select these artists or albums again):\n' + '\n'.join(
            f"- {r.get('title', '')}" for r in reviewed[:30]
        )

    prompt = f"""\
From these music news headlines, identify ONE newly released album worth reviewing.
Prioritize major artist releases, debut albums, or highly anticipated releases from the current month.{already_reviewed}

Headlines:
{headlines}

Return ONLY a valid JSON object:
{{
  "artist": "Artist Name",
  "album": "Album Title",
  "context": "Brief context about the album from the news (1-2 sentences)",
  "imageQuery": "Unsplash search string for a relevant editorial image"
}}

If no clear current album release is found, return:
{{"artist": null, "album": null, "context": null, "imageQuery": null}}
"""

    client = _get_client()
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=500,
        messages=[{'role': 'user', 'content': prompt}],
    )

    raw = _strip_fences(message.content[0].text)
    try:
        data = json.loads(raw)
        if data.get('artist') and data.get('album'):
            return data
        return None
    except json.JSONDecodeError:
        log.warning("Failed to parse album extraction response")
        return None


def pick_classic_album(reviewed: list[dict], attempted: list[str] | None = None) -> dict:
    """
    Use Claude to select a classic album (10+ years old) for the monthly historical review.
    Returns dict with {artist, album, year, context, imageQuery}.

    attempted: flat list of "Artist — Album" strings that were selected this session
    but failed to publish (wrong image, parse error, etc.). Passed to the prompt so
    Claude doesn't re-select the same candidate.
    """
    cutoff_year = datetime.now(tz=timezone.utc).year - 10
    reviewed_summary = '\n'.join(
        f"- {r.get('title', '')}" for r in reviewed[:30]
    ) or '(none yet)'

    attempted_summary = ''
    if attempted:
        attempted_summary = '\n\nAlso do NOT select these (attempted this session but failed to publish):\n' + '\n'.join(
            f"- {a}" for a in attempted[:20]
        )

    prompt = f"""\
Select one classic album (released {cutoff_year} or earlier) for LORD to give a historical reassessment review.

Already reviewed (do not repeat these):
{reviewed_summary}{attempted_summary}

Choose an album that is:
- Culturally significant and still resonant today
- Not already in the reviewed list above
- From a diverse range of genres, eras, and artists
- Worth reassessing — either underrated, overrated, or newly relevant in context

Return ONLY a valid JSON object:
{{
  "artist": "Artist Name",
  "album": "Album Title",
  "year": 1994,
  "context": "Why this album demands reassessment now (1-2 sentences)",
  "imageQuery": "Unsplash search string for a relevant editorial image"
}}
"""

    client = _get_client()
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=500,
        messages=[{'role': 'user', 'content': prompt}],
    )

    raw = _strip_fences(message.content[0].text)
    try:
        data = json.loads(raw)
        if data.get('artist') and data.get('album'):
            return data
    except json.JSONDecodeError:
        pass

    log.warning("Failed to parse classic album response — using fallback")
    return {
        'artist': 'Lauryn Hill',
        'album': 'The Miseducation of Lauryn Hill',
        'year': 1998,
        'context': 'A record that redefined what a debut could say. Still unmatched.',
        'imageQuery': 'recording studio microphone vintage soul music',
    }
