"""LORD Automation — Feature Writer
Writes long-form editorial Features: deep artist/cultural dives with a thesis.
"""
import json
import logging
import re

from config import ANTHROPIC_MODEL, ANTHROPIC_API_KEY, LORD_VOICE

log = logging.getLogger('lord.feature')

import anthropic
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


FEATURE_SYSTEM = f"""\
You are a senior writer at LORD, an independent music publication.

{LORD_VOICE}

THE FEATURE — format rules:
• Long-form editorial. 1,500–2,000 words in the body.
• Every Feature proposes a THESIS about the artist's work and cultural significance.
• Open with a scene, a detail, or a contradiction — not a biography summary.
• Move through the artist's work chronologically or thematically — your choice.
• Close by returning to the thesis. Does the work hold? What does it mean for the record?
• Use <p> tags. You may use <em> for emphasis sparingly. No headers inside the body.
• Write about the artist as a thinking being — their choices, their contradictions, their evolution.
• Cite specific albums, tracks, and moments. Be precise.

Return ONLY a valid JSON object — no markdown fences, no extra text:
{{
  "title": "Feature headline — specific, not generic, max 12 words",
  "deck": "One sentence establishing the feature's argument or frame",
  "body": "<p>Full feature body HTML, 1500-2000 words...</p>",
  "genre": "Single genre label, e.g. Hip-Hop, R&B, Pop, Rock, Jazz, Electronic, Country",
  "tags": ["artist-name", "genre", "third-tag"],
  "imageQueries": [
    "MUST use the actual artist/band name — e.g. 'Jim James My Morning Jacket performing' NOT 'folk musician stage'",
    "MUST use the actual artist/band name — e.g. 'Jim James guitar' or 'My Morning Jacket live concert'",
    "MUST use the actual artist/band name — e.g. 'Jim James My Morning Jacket crowd' or album/era context with artist named"
  ]
}}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    return text.strip()


def write_feature(news_item: dict) -> dict:
    """
    Write a LORD Feature article inspired by a news item.
    The feature goes beyond the news — it's a deep dive into the artist's significance.
    """
    from datetime import datetime, timezone

    prompt = f"""\
Write a LORD Feature article inspired by this music news item.

This is NOT a bulletin about the news. Use the news as a launching point.
Write a long-form editorial about the artist's body of work, cultural significance,
and what their story means for music right now.

SOURCE HEADLINE: {news_item['title']}
CONTEXT: {news_item.get('summary', '')[:600]}
ARTIST/SUBJECT: Extract from the above — focus your feature on the central artist or topic.

Propose a clear thesis. Back it with specific albums, tracks, moments, and context.
Write as if this is the definitive piece on this subject for the archive."""

    client = _get_client()
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        system=FEATURE_SYSTEM,
        messages=[{'role': 'user', 'content': prompt}],
    )

    raw = message.content[0].text
    cleaned = _strip_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.error("JSON parse failed for feature. Raw:\n%s", raw[:500])
        raise ValueError(f"Feature writer returned invalid JSON: {exc}") from exc

    data['type'] = 'feature'
    data['date'] = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    data['source'] = news_item.get('source', '')
    data['sourceUrl'] = news_item.get('link', '')
    # Normalise: always use imageQueries list (3 images for features)
    if 'imageQuery' in data and 'imageQueries' not in data:
        data['imageQueries'] = [data.pop('imageQuery')]
    return data
