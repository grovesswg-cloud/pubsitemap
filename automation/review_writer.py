"""LORD Automation — Review Writer
Writes LORD Reviews: current album reviews and classic album reassessments.
"""
import json
import logging
import re

from config import ANTHROPIC_MODEL, ANTHROPIC_API_KEY, LORD_VOICE

log = logging.getLogger('lord.review')

import anthropic
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


REVIEW_SYSTEM = f"""\
You are a senior critic at LORD, an independent music publication.

{LORD_VOICE}

THE REVIEW — format rules:
• 800–1,200 words in the body.
• Open on the record itself — a moment, a sound, a texture. Not on the artist's biography.
• Move through the album — specific tracks, production choices, lyrics, key moments.
• Compare to the artist's previous work where relevant.
• End with a final verdict that earns the rating.
• Use <p> tags. You may use <em> for emphasis sparingly. No headers inside the body.

RATING SCALE (choose exactly one):
  Dormant   — Fails to ignite. Not without merit, but not alive.
  Rising    — A promising statement. Worth hearing. Not yet essential.
  Sovereign — Commands attention. A record that matters. Strong and fully realised.
  Eternal   — A landmark. Will outlast its moment. Essential listening.
  Monument  — Once-in-a-generation. Redefines what music can be.

The rating must be earned by the argument. Never hedge.

Return ONLY a valid JSON object — no markdown fences, no extra text:
{{
  "title": "Review headline — specific, not generic, max 12 words",
  "deck": "One sentence that stakes LORD's position on this record",
  "body": "<p>Full review body HTML, 800-1200 words...</p>",
  "rating": "Sovereign",
  "tags": ["artist-name", "album-title", "genre"],
  "imageQueries": [
    "Hero image — artist or album feel, e.g. 'musician portrait dark studio'",
    "Mid-review image — sonic texture, e.g. 'vinyl record close up light'"
  ]
}}
"""


CLASSIC_REVIEW_SYSTEM = f"""\
You are a senior critic at LORD, an independent music publication.

{LORD_VOICE}

THE ARCHIVE REVIEW — format rules:
• This is a historical reassessment of a classic album (10+ years old).
• 800–1,200 words in the body.
• Open by establishing why this record demands reassessment NOW — not just when it was released.
• Move through the record with the benefit of hindsight: what holds, what aged poorly, what was missed.
• Be willing to revise received opinion. If a celebrated record has curdled, say so.
  If an overlooked record has become essential, crown it.
• End with a definitive statement: this is where this record stands in history.
• Use <p> tags. You may use <em> for emphasis sparingly. No headers inside the body.

RATING SCALE (choose exactly one):
  Dormant / Rising / Sovereign / Eternal / Monument

Return ONLY a valid JSON object — no markdown fences, no extra text:
{{
  "title": "Review headline — specific, max 12 words",
  "deck": "One sentence establishing the reassessment's core argument",
  "body": "<p>Full review body HTML, 800-1200 words...</p>",
  "rating": "Eternal",
  "tags": ["artist-name", "album-title", "genre", "classic"],
  "imageQueries": [
    "Hero image — artist era feel, e.g. 'musician black and white portrait'",
    "Mid-review image — vintage or archival texture, e.g. 'old vinyl record sleeve'"
  ]
}}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    return text.strip()


def write_review(album_info: dict) -> dict:
    """
    Write a LORD Review for a current album release.
    album_info: {artist, album, context, imageQuery}
    """
    from datetime import datetime, timezone

    prompt = f"""\
Write a LORD Review of this album.

ARTIST: {album_info['artist']}
ALBUM: {album_info['album']}
CONTEXT: {album_info.get('context', '')}

Review this album on its own terms. Be specific about tracks, production, and lyrics.
Stake a clear position and justify it with the rating."""

    client = _get_client()
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2500,
        system=REVIEW_SYSTEM,
        messages=[{'role': 'user', 'content': prompt}],
    )

    raw = message.content[0].text
    cleaned = _strip_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.error("JSON parse failed for review. Raw:\n%s", raw[:500])
        raise ValueError(f"Review writer returned invalid JSON: {exc}") from exc

    data['type'] = 'review'
    data['date'] = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    data['albumName'] = album_info.get('album', '')
    data['artistName'] = album_info.get('artist', '')
    if 'imageQuery' in data and 'imageQueries' not in data:
        data['imageQueries'] = [data.pop('imageQuery')]
    if not data.get('imageQueries') and album_info.get('imageQuery'):
        data['imageQueries'] = [album_info['imageQuery']]
    return data


def write_classic_review(album_info: dict) -> dict:
    """
    Write a LORD Archive Review reassessing a classic album (10+ years old).
    album_info: {artist, album, year, context, imageQuery}
    """
    from datetime import datetime, timezone

    prompt = f"""\
Write a LORD Archive Review reassessing this classic album.

ARTIST: {album_info['artist']}
ALBUM: {album_info['album']}
YEAR RELEASED: {album_info.get('year', '')}
WHY NOW: {album_info.get('context', '')}

Reassess this record with the benefit of time. What does it mean today?
What did contemporary criticism get wrong or right? Where does it stand in history?"""

    client = _get_client()
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2500,
        system=CLASSIC_REVIEW_SYSTEM,
        messages=[{'role': 'user', 'content': prompt}],
    )

    raw = message.content[0].text
    cleaned = _strip_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.error("JSON parse failed for classic review. Raw:\n%s", raw[:500])
        raise ValueError(f"Classic review writer returned invalid JSON: {exc}") from exc

    data['type'] = 'review'
    data['isClassic'] = True
    data['date'] = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    data['albumName'] = album_info.get('album', '')
    data['artistName'] = album_info.get('artist', '')
    if 'imageQuery' in data and 'imageQueries' not in data:
        data['imageQueries'] = [data.pop('imageQuery')]
    if not data.get('imageQueries') and album_info.get('imageQuery'):
        data['imageQueries'] = [album_info['imageQuery']]
    return data
