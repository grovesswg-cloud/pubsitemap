"""LORD Automation — Article Writer
Uses Claude to write LORD-voice Bulletin articles from raw news items.
"""
import json
import logging
import re

import anthropic

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, LORD_VOICE

log = logging.getLogger('lord.writer')

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


BULLETIN_SYSTEM = f"""\
You are a senior editor at LORD, an independent music publication.

{LORD_VOICE}

THE BULLETIN — format rules:
• News only. Short. Factual. Never speculative. Always linked to source.
• The Bulletin reports the record. It does not editorialize or predict.
• 300–500 words in the body.
• Open with one declarative sentence that states the fact cleanly.
• Follow with context: who, what, why it matters historically or culturally.
• Close with what this moment adds to the record — never opinion, always documented fact.
• Use <p> tags for paragraphs. No headers inside the body. No bullet points.

Return ONLY a valid JSON object with these exact keys — no markdown fences, no extra text:
{{
  "title": "Headline: factual, compelling, no clickbait, max 12 words",
  "deck": "One italic-style sentence that frames the story without repeating the headline",
  "body": "<p>Body HTML with <p> tags...</p>",
  "genre": "Single genre label, e.g. Hip-Hop, R&B, Pop, Rock, Jazz, Electronic, Country, Latin, Classical",
  "tags": ["tag1", "tag2", "tag3"],
  "imageQuery": "MUST use the actual artist or band name — e.g. 'Olivia Rodrigo performing live' or 'Drake concert stage'. Never use generic descriptions like 'pop singer on stage' or 'concert crowd'."
}}
"""


def _strip_fences(text: str) -> str:
    """Remove any markdown code fences Claude may have included."""
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    return text.strip()


def write_bulletin(news_item: dict) -> dict:
    """
    Generate a LORD Bulletin article from a raw news item.
    Returns a dict ready to pass to publisher.publish_article().
    """
    from datetime import datetime, timezone

    prompt = f"""\
Write a LORD Bulletin article based on this music news item.

SOURCE HEADLINE: {news_item['title']}
SUMMARY: {news_item.get('summary', '')[:800]}
SOURCE NAME: {news_item.get('source', 'Unknown')}
SOURCE URL: {news_item.get('link', '')}

Transform this raw news into a LORD Bulletin. Stay entirely within the facts reported.
Add historical or cultural context only when you can state it as documented fact.
Do not speculate, editorialize, or add opinion."""

    client = _get_client()
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1200,
        system=BULLETIN_SYSTEM,
        messages=[{'role': 'user', 'content': prompt}],
    )

    raw = message.content[0].text
    cleaned = _strip_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.error("JSON parse failed. Raw response:\n%s", raw[:500])
        raise ValueError(f"Article writer returned invalid JSON: {exc}") from exc

    # Merge source metadata
    data['type']      = 'bulletin'
    data['date']      = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    data['source']    = news_item.get('source', '')
    data['sourceUrl'] = news_item.get('link', '')

    return data
