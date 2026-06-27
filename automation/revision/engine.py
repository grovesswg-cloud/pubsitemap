"""Groves Engine — Editorial Revision Engine

The publication's internal editor. Runs AFTER the writer has produced a draft
and BEFORE the draft reaches the quality gates. Where the Editorial Intelligence
Engine decides what to argue, the Revision Engine checks whether the prose
actually delivered it — and fixes the highest-impact places where it did not.

Like the reasoning engine, this is publication-agnostic. It does not load
editorial documents or know which publication it serves. The caller provides:
  — draft:             the article dict the writer produced (must contain 'body')
  — brief:             the ReasoningBrief the writer rendered (may be None on the
                       legacy path; the critique then runs craft-only)
  — editorial_context: the publication's full criticism context string

It is not invoked for bulletins. Bulletins are journalism, not criticism — a
different cognitive profile that does not pass through editorial revision.

Pipeline (a single disciplined pass — not a loop):
  1. Critique  — structured markup, fidelity + craft layers          (fail-closed)
  2. Plan      — mechanical triage to the highest-impact subset       (deterministic)
  3. Rewrite   — targeted rewrites of only the selected paragraphs    (fail-closed)

The result is a RevisionReport carrying the full critique (the record), the
plan, the rewritten paragraphs, and the revised body. The caller swaps in
report.revised_body when report.revised is True; the existing quality gates
then validate the revised draft.
"""
from __future__ import annotations
import logging

import anthropic

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from revision.report import RevisionReport
from revision.paragraphs import split_paragraphs, apply_revisions
from revision.stages import critique as critique_stage
from revision.stages import plan as plan_stage
from revision.stages import rewrite as rewrite_stage

log = logging.getLogger('revision.engine')

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def run(
    draft: dict,
    brief,
    editorial_context: str,
    article_type: str = 'review',
    *,
    paragraph_cap: int | None = None,
) -> RevisionReport:
    """Run one editorial revision pass over a draft.

    Args:
        draft:             The writer's article dict. Must contain 'body' (HTML).
        brief:             The ReasoningBrief the writer rendered, or None.
        editorial_context: The publication's full criticism context string.
        article_type:      'review' | 'feature' (informs critique framing only).
        paragraph_cap:     Optional override for the max paragraphs rewritten.

    Returns:
        RevisionReport — critique, plan, rewritten paragraphs, and revised body.

    Raises:
        ValueError if a fail-closed stage fails (critique or rewrite).
    """
    body = draft.get('body', '') or ''
    log.info("Editorial Revision Engine: starting %s pass (%d chars)", article_type, len(body))

    paragraphs = split_paragraphs(body)
    if not paragraphs:
        log.warning("Revision Engine: draft has no body content — nothing to revise")
        return RevisionReport(original_body=body, revised_body=body, revised=False)

    client = _get_client()
    model = ANTHROPIC_MODEL

    # ── Stage 1: Critique ──────────────────────────────────────────────────────
    notes = critique_stage.run(
        paragraphs, brief, editorial_context, client, model, article_type=article_type,
    )

    # ── Stage 2: Plan (mechanical triage) ──────────────────────────────────────
    cap = paragraph_cap if paragraph_cap is not None else plan_stage.DEFAULT_PARAGRAPH_CAP
    selected = plan_stage.select_revisions(notes, paragraph_cap=cap)

    report = RevisionReport(
        notes=notes,
        plan=[n.id for n in selected],
        original_body=body,
        revised_body=body,
        revised=False,
    )

    if not selected:
        log.info("Editorial Revision Engine: no actionable edits — draft stands. %s", report.summary())
        return report

    # ── Stage 3: Targeted Rewrites ─────────────────────────────────────────────
    revised_map = rewrite_stage.run(paragraphs, selected, brief, editorial_context, client, model)
    if not revised_map:
        log.info("Editorial Revision Engine: plan produced no paragraph rewrites. %s", report.summary())
        return report

    report.revised_paragraphs = revised_map
    report.revised_body = apply_revisions(body, revised_map)
    report.revised = report.revised_body != body

    log.info("Editorial Revision Engine: complete. %s", report.summary())
    return report
