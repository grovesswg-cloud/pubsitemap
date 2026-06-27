"""Groves Engine — Editorial Intelligence Engine

Orchestrates the reasoning stages and returns a ReasoningBrief.

The engine is publication-agnostic. It does not import editorial documents,
load publications configs, or know which publication it is serving.
The caller provides:
  — editorial_context: the publication's full criticism context string
  — articles_index: the publication's articles index (for publication memory)
  — subject: the article subject (artist/album/news item)
  — article_type: 'review' | 'feature-criticism' | 'feature-context'

The engine is not invoked for bulletins. Bulletins are journalism and use
the bulletin pipeline (article_writer.py) directly.

Stage routing by article type:
  review              — all stages
  feature-criticism   — all stages (adapted: subject is a body of work, not a single record)
  feature-context     — research + thesis + outline (no observation stage;
                         context-oriented features don't require close listening)
"""
from __future__ import annotations
import logging

import anthropic

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from reasoning.brief import ReasoningBrief, derive_thesis_confidence
from reasoning.stages import context, observation, thesis as thesis_stage, outline as outline_stage

log = logging.getLogger('engine')

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def run(
    subject: dict,
    editorial_context: str,
    articles_index: dict,
    article_type: str = 'review',
) -> ReasoningBrief:
    """Run the full editorial reasoning pipeline for a review or feature.

    Args:
        subject:          Article subject. For reviews: {artist, album, context, year}.
                          For features: {title, summary, source, link}.
                          For targeted features: {artist, album, context}.
        editorial_context: The publication's full criticism context string.
                           For LORD: load_criticism_context() from editorial/__init__.py.
        articles_index:   The publication's full articles index dict (articles.json content).
        article_type:     'review' | 'feature-criticism' | 'feature-context'

    Returns:
        ReasoningBrief — complete editorial brief ready for the writer.

    Raises:
        ValueError if any fail-closed stage fails.
    """
    log.info("Editorial Intelligence Engine: starting %s reasoning for subject '%s'",
             article_type,
             subject.get('artist') or subject.get('title', 'unknown'))

    client = _get_client()
    model = ANTHROPIC_MODEL

    # Inject article_type into subject so stages can adapt word targets, framing, etc.
    subject = {**subject, '_article_type': article_type}

    brief = ReasoningBrief()

    # ── Stage 1: Context ───────────────────────────────────────────────────────
    # Fail-open: errors here do not abort the pipeline.
    try:
        pub_memory, positioning = context.run(subject, articles_index)
        brief.publication_memory = pub_memory
        brief.positioning = positioning
        log.info("Stage 1 (Context): complete — %d prior articles, consensus=%s",
                 pub_memory.get('coverage_count', 0), bool(positioning.get('consensus')))
    except Exception as exc:
        log.warning("Stage 1 (Context): failed (%s) — proceeding with empty memory", exc)
        brief.publication_memory = {'prior_coverage': [], 'previous_ratings': [], 'coverage_count': 0}
        brief.positioning = {'consensus': '', 'underexplored': ''}

    # ── Stage 2: Observation + Interpretation ──────────────────────────────────
    # Skipped for feature-context (no close listening required).
    # Fail-closed for review and feature-criticism.
    if article_type in ('review', 'feature-criticism'):
        obs, interps, obs_weaknesses = observation.run(subject, editorial_context, client, model)
        brief.observations = obs
        brief.interpretations = interps
        # Weaknesses from observation are carried into the brief; outline stage may refine them.
        brief.weaknesses = obs_weaknesses
        log.info("Stage 2 (Observation): %d observations, %d interpretations", len(obs), len(interps))
    else:
        log.info("Stage 2 (Observation): skipped for article_type=%s", article_type)

    # ── Stage 3–6: Synthesis + Perspective + Thesis + Counterargument ──────────
    # Fail-closed for all types that reach this stage.
    synthesis, perspective, selected_thesis, rejected, counterargument = thesis_stage.run(
        subject=subject,
        observations=brief.observations,
        interpretations=brief.interpretations,
        publication_memory=brief.publication_memory,
        positioning=brief.positioning,
        editorial_context=editorial_context,
        client=client,
        model=model,
    )
    brief.synthesis = synthesis
    brief.perspective = perspective
    brief.thesis = selected_thesis
    brief.rejected_theses = rejected
    brief.counterargument = counterargument
    log.info("Stage 3–6 (Thesis): thesis selected — '%s...'", selected_thesis[:80])

    # ── Stage 7–8: Evidence Map + Outline ──────────────────────────────────────
    # Fail-closed for all types.
    evidence, weaknesses, outline, editor_notes, confidence = outline_stage.run(
        subject=subject,
        thesis=selected_thesis,
        synthesis=synthesis,
        counterargument=counterargument,
        observations=brief.observations,
        interpretations=brief.interpretations,
        editorial_context=editorial_context,
        client=client,
        model=model,
    )
    brief.evidence = evidence
    # Outline stage refines weaknesses — use its output (more specific than observation stage)
    if weaknesses:
        brief.weaknesses = weaknesses
    brief.outline = outline
    brief.editor_notes = editor_notes
    brief.confidence = confidence
    # thesis_confidence is derived mechanically from the evidence map — distinct
    # from the holistic self-report above. Confidence must survive the pipeline.
    brief.thesis_confidence = derive_thesis_confidence(evidence)
    log.info("Stage 7–8 (Outline): %d evidence items, %d paragraphs, confidence=%s, thesis_confidence=%s",
             len(evidence), len(outline), confidence, brief.thesis_confidence)

    log.info("Editorial Intelligence Engine: complete — brief ready (confidence=%s, thesis_confidence=%s, thesis='%s...')",
             confidence, brief.thesis_confidence, selected_thesis[:60])
    return brief
