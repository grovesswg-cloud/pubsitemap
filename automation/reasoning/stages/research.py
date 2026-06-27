"""Groves Engine — Stage 1: Research

Populates two fields of the ReasoningBrief:

  publication_memory  — what this publication has already said about this subject
  positioning         — what the broader critical conversation has said; where the gap is

Both are stubs in this implementation. PR-006.5 (Publication Intelligence) enriches
publication_memory with pattern analysis across 200 articles. PR-006.6 (Editorial
Positioning Engine) enriches positioning with real-time critical discourse mapping.

The interfaces are stable. The stub data is enough to prevent LORD from repeating
prior positions on the same artist and to surface the dominant critical angle from
the incoming news context.

Failure mode: fail-open. If this stage errors, the brief proceeds with empty
memory and empty positioning. The reasoning stages still run.
"""
from __future__ import annotations
import logging
import unicodedata
import re

log = logging.getLogger('engine.research')


def _normalise(text: str) -> str:
    text = unicodedata.normalize('NFKD', text)
    text = text.casefold()
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def run(subject: dict, articles_index: dict) -> tuple[dict, dict]:
    """
    Args:
        subject:        The article subject. Keys used: artist, album, title (news headline),
                        summary (news body), source.
        articles_index: The publication's articles.json content (full dict with 'articles' list).

    Returns:
        (publication_memory, positioning) — both dicts, safe to include in ReasoningBrief.
    """
    publication_memory = _build_publication_memory(subject, articles_index)
    positioning = _build_positioning(subject)
    return publication_memory, positioning


# ── Publication Memory ─────────────────────────────────────────────────────────

def _build_publication_memory(subject: dict, articles_index: dict) -> dict:
    """Scan articles index for prior coverage of this subject.

    Returns a dict with:
      prior_coverage    — list of human-readable summary strings for each prior article
      previous_ratings  — list of {album, rating} for prior reviews of this artist
      coverage_count    — total prior articles about this artist
    """
    artist = _normalise(subject.get('artist', '') or subject.get('artistName', ''))
    album = _normalise(subject.get('album', '') or subject.get('albumName', ''))

    prior_coverage: list[str] = []
    previous_ratings: list[dict] = []

    articles = articles_index.get('articles', [])
    for a in articles:
        # Match on artist name in tags or artistName field
        a_artist = _normalise(a.get('artistName', ''))
        a_tags = [_normalise(t) for t in a.get('tags', [])]

        artist_match = (
            (artist and a_artist and a_artist == artist) or
            (artist and any(artist in tag or tag in artist for tag in a_tags if len(tag) > 3))
        )

        if not artist_match:
            continue

        a_title = a.get('title', '')
        a_date = a.get('date', '')
        a_type = a.get('type', 'bulletin')
        a_rating = a.get('rating', '')
        a_album = a.get('albumName', '')

        summary = f"{a_date} [{a_type.upper()}] {a_title}"
        if a_rating:
            summary += f" — rated {a_rating}"
        prior_coverage.append(summary)

        if a_type in ('review', 'classic-review') and a_rating:
            previous_ratings.append({'album': a_album, 'rating': a_rating, 'date': a_date})

    if prior_coverage:
        log.info("Publication memory: %d prior articles found for artist '%s'", len(prior_coverage), artist)
    else:
        log.info("Publication memory: no prior coverage found for artist '%s'", artist)

    return {
        'prior_coverage': prior_coverage,
        'previous_ratings': previous_ratings,
        'coverage_count': len(prior_coverage),
    }


# ── Editorial Positioning ──────────────────────────────────────────────────────

def _build_positioning(subject: dict) -> dict:
    """Extract the dominant critical angle from available news context.

    Stub implementation: parses the subject summary to identify what the
    incoming news is emphasising, and flags it as 'consensus' so the
    reasoning stages can position around it.

    PR-006.6 replaces this with multi-source discourse mapping.

    Returns a dict with:
      consensus       — what the incoming news/criticism is emphasising
      underexplored   — where there may be room to contribute (stub: empty)
    """
    summary = subject.get('summary', '') or subject.get('context', '')
    title = subject.get('title', '') or ''

    # Stub: the consensus is whatever the news source is emphasising.
    # The underexplored angle is left for the reasoning stages to determine.
    consensus = ''
    if summary:
        # Use the first 300 chars of the summary as the consensus signal.
        consensus = summary[:300].strip()
    elif title:
        consensus = title

    if consensus:
        log.info("Editorial positioning: consensus signal captured (%d chars)", len(consensus))
    else:
        log.info("Editorial positioning: no consensus signal available — reasoning will proceed without it")

    return {
        'consensus': consensus,
        'underexplored': '',  # PR-006.6 fills this
    }
