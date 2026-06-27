"""LORD Automation — Feature Writer
Writes long-form editorial Features: deep artist/cultural dives with a thesis.
"""
import json
import logging
import re

from config import ANTHROPIC_MODEL, ANTHROPIC_API_KEY
from editorial import load_criticism_context
from json_utils import parse_writer_json

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

{load_criticism_context()}

ABSOLUTE RULE — NO INVENTED ENTITIES:
Every artist, band, album, song, tour, label, and project you mention MUST be real
and already publicly reported. Never invent, fabricate, or speculate about any
name — not a band name, not an album title, not a project. If you are not certain
something exists, do not write it. This is non-negotiable.

YOUR ROLE IN THIS PIPELINE:
When a ReasoningBrief is provided, the editorial reasoning is already done. You are
the stylist. You are bound on the ARGUMENT layer (thesis, evidence, weaknesses, the
overall argument — do not change these or invent new ones) and sovereign on the
PROSE layer (language, transitions, opening image, metaphor, rhythm — these are
yours; you are not a printer). If you become convinced of a stronger thesis while
writing, render the assigned one faithfully and add a top-level "editor_flag" field
naming the alternative — do not silently override it.

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
    "MUST name the PRIMARY artist this feature is about — e.g. 'Jim James performing'",
    "MUST name the SAME primary artist again — e.g. 'Jim James guitar' or 'Jim James live'",
    "MUST name the SAME primary artist again — e.g. 'Jim James portrait' or 'Jim James concert'"
  ]
}}

IMAGE RULES — read carefully:
• Every published photo MUST be of the PRIMARY artist this feature is about — the act the headline names.
• ALL THREE image queries must name THAT SAME primary artist. Never a photographer, producer, collaborator, festival, or any other act mentioned in the body.
• Never use generic descriptions ('folk musician stage', 'concert crowd'). Always the real name.
• The first tag in "tags" MUST be the primary artist's name.
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    return text.strip()


def write_feature(news_item: dict, brief=None) -> dict:
    """
    Write a LORD Feature article inspired by a news item.
    The feature goes beyond the news — it's a deep dive into the artist's significance.
    brief: optional ReasoningBrief from the Editorial Intelligence Engine.
           When provided, the writer renders the brief into prose rather than
           reasoning from scratch.
    """
    from datetime import datetime, timezone

    if brief is not None:
        prompt = f"""\
Write a LORD Feature article. The editorial reasoning is complete — render it into prose.

SOURCE HEADLINE: {news_item['title']}

{brief.to_writer_context()}

This is NOT a bulletin about the news. The news is the launching point.
Execute the outline. The thesis, evidence, and structure are decided.
Write as if this is the definitive piece on this subject for the archive.
Do not invent new arguments. Do not omit the weaknesses."""
    else:
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
    try:
        data = parse_writer_json(raw)
    except ValueError as exc:
        log.error("JSON parse failed for feature. Raw:\n%s", raw[:500])
        raise

    data['type'] = 'feature'
    data['date'] = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    data['source'] = news_item.get('source', '')
    data['sourceUrl'] = news_item.get('link', '')
    # Normalise: always use imageQueries list (3 images for features)
    if 'imageQuery' in data and 'imageQueries' not in data:
        data['imageQueries'] = [data.pop('imageQuery')]
    return data
