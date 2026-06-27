"""Groves Engine — Revision Stage 2: Rewrite Plan (mechanical triage)

The critique stage diagnoses every weakness. The plan stage decides which ones
are worth acting on. This is deliberately NOT an LLM call: the editorial
judgment — how much each issue matters — already happened when the critique
rated each note's impact. Selection is policy, and policy should be auditable,
deterministic, and testable, the same way derive_thesis_confidence() is.

The policy encodes GPT's directive — "highest-impact weaknesses, not endless
rewriting":

  1. Fix every HIGH-impact issue. These are the ones that, left alone, make the
     article worse than the brief deserved (thesis drift, dropped mandatory
     weakness, a claim asserted but never heard).
  2. Then fix MEDIUM-impact issues, highest first, until the paragraph cap is
     reached.
  3. Never act on LOW-impact issues. A slightly soft transition is not worth the
     risk of rewriting a paragraph that already works.
  4. Cap the number of paragraphs touched. Beyond a few targeted rewrites you are
     no longer editing — you are re-drafting, which discards prose the writer got
     right. The cap protects the good.

A note on paragraph 0 (whole-draft/structural) issues: they are selected by the
same impact rules but do not count against the paragraph cap, because they do
not map to a single paragraph the rewrite stage can replace. The rewrite stage
handles them as global guidance.
"""
from __future__ import annotations
import logging

from revision.report import CritiqueNote

log = logging.getLogger('revision.plan')

# The most paragraphs a single revision pass may rewrite. Past this we are
# re-drafting, not editing. Deliberately small.
DEFAULT_PARAGRAPH_CAP = 4


def select_revisions(
    notes: list[CritiqueNote],
    *,
    paragraph_cap: int = DEFAULT_PARAGRAPH_CAP,
) -> list[CritiqueNote]:
    """Triage critique notes into the set worth rewriting.

    Deterministic. Given the same notes, always returns the same selection.

    Returns the selected notes (a subset of `notes`), ordered by paragraph so
    the rewrite stage receives them in document order.
    """
    # Never act on low-impact issues.
    actionable = [n for n in notes if n.impact in ('high', 'medium')]

    # Structural (paragraph 0) notes are selected on impact alone — they do not
    # consume the paragraph budget because they have no single paragraph to fix.
    structural = [n for n in actionable if n.paragraph == 0]
    paragraph_notes = [n for n in actionable if n.paragraph > 0]

    # Order: HIGH before MEDIUM; within a tier, earlier paragraphs first so the
    # selection is stable and reads in document order.
    paragraph_notes.sort(key=lambda n: (-n.impact_rank(), n.paragraph))

    selected_paragraph_notes: list[CritiqueNote] = []
    touched: set[int] = set()
    for note in paragraph_notes:
        if note.paragraph in touched:
            # Another note already put this paragraph in the plan — fold it in
            # without spending more of the cap (one rewrite addresses both).
            selected_paragraph_notes.append(note)
            continue
        if len(touched) >= paragraph_cap:
            continue
        touched.add(note.paragraph)
        selected_paragraph_notes.append(note)

    selected = structural + selected_paragraph_notes
    # Return in document order (structural notes, paragraph 0, sort first).
    selected.sort(key=lambda n: n.paragraph)

    log.info(
        "Plan stage: %d/%d notes selected (%d paragraph(s) touched, cap=%d, %d structural)",
        len(selected), len(notes), len(touched), paragraph_cap, len(structural),
    )
    return selected
