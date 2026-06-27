"""Groves Engine — Revision Stage 1: Structured Critique

The critique stage reads the writer's draft, paragraph by paragraph, and
produces a structured list of CritiqueNotes. It is the publication's internal
editor doing a markup pass — not assigning a score.

Two layers, deliberately:

  FIDELITY — measured against the ReasoningBrief, the closest thing to an
    objective standard the editor has:
      • thesis drift — the prose argues something other than the assigned thesis
      • dropped evidence — an evidence item from the brief never appears
      • over-confident hedging — a LOW-confidence claim is stated as fact
      • missing weakness — a mandatory weakness never makes it into the article
      • smuggled argument — a new argument not in the brief was introduced
      • counterargument skipped — the brief's counterargument is never addressed

  CRAFT — informed judgment about the prose itself:
      • shallow_analysis — a musical claim asserted but not heard/shown
      • weak_transition — paragraphs abut without connective logic
      • repetition — an idea or phrase recurs without development
      • weak_ending — the close introduces a new argument or trails off
      • pacing — a section drags or rushes relative to its weight
      • weak_opening — opens on biography/cliché instead of the record

Each note carries an impact rating (high/medium/low). That rating is the
editor's judgment; the plan stage triages on it mechanically. The critique
does NOT decide what gets fixed — it only diagnoses.

Failure mode: fail-closed. A draft we could not critique is a draft we cannot
stand behind during pre-launch.
"""
from __future__ import annotations
import logging

from json_utils import parse_writer_json
from revision.report import CritiqueNote, LAYER_FIDELITY, LAYER_CRAFT
from revision.llm import call_stage

log = logging.getLogger('revision.critique')

_VALID_IMPACT = ('high', 'medium', 'low')

_INSTRUCTIONS = """\
You are the internal editor of the publication, performing a structured
critique pass on a draft article. You are not scoring it. You are marking it
up the way an experienced editor marks up a draft: identifying specific,
fixable weaknesses and saying exactly what each fix must accomplish.

You are given the draft with each paragraph numbered, and — when available —
the EDITORIAL REASONING BRIEF the writer was asked to render. The brief is the
contract. Hold the prose to it.

Critique on TWO layers.

FIDELITY (check the prose against the brief — this is the objective layer):
  • thesis_drift        — the prose argues something other than the assigned thesis
  • dropped_evidence    — an evidence item (E-001 etc.) from the brief never appears
  • overconfident       — a LOW-confidence claim is stated as settled fact (must be hedged)
  • missing_weakness    — a weakness the brief requires never appears in the article
  • smuggled_argument   — a new argument not supported by the brief was introduced
  • counterargument_skipped — the brief's counterargument is never addressed

CRAFT (judge the prose itself):
  • shallow_analysis    — a musical claim asserted but never heard or shown
  • weak_transition     — paragraphs abut without connective logic
  • repetition          — an idea or phrase recurs without development
  • weak_ending         — the close introduces a new argument or trails off
  • pacing              — a section drags or rushes relative to its weight
  • weak_opening        — opens on biography or cliché instead of the record

RULES:
  • Be specific. "Paragraph 4 asserts the production is 'cavernous' but never
    points to a sound that makes it so" — not "could be deeper".
  • Assign each note a paragraph number. Use 0 only for whole-draft/structural
    issues that do not belong to a single paragraph.
  • Rate impact honestly. A dropped mandatory weakness or thesis drift is HIGH.
    A slightly soft transition is LOW. Most drafts have only one or two HIGH
    issues — do not inflate. Reserve HIGH for things that, left unfixed, make
    the article worse than the brief deserved.
  • For each note, the "fix" is an INSTRUCTION for the rewrite — what the
    revised paragraph must accomplish — NOT the rewritten prose.
  • If the draft is genuinely strong, return few notes. Do not invent weaknesses
    to look thorough. An empty or near-empty critique is a valid result.

Return ONLY a valid JSON object:
{{
  "notes": [
    {{
      "paragraph": 4,
      "layer": "fidelity | craft",
      "issue_type": "one of the types above",
      "impact": "high | medium | low",
      "description": "What is wrong, specifically.",
      "fix": "What the rewrite must accomplish (an instruction, not prose)."
    }}
  ]
}}
"""


def _number_paragraphs(paragraphs: list[str]) -> str:
    return '\n\n'.join(f'[{i}] {p}' for i, p in enumerate(paragraphs, 1))


def run(
    paragraphs: list[str],
    brief,
    editorial_context: str,
    client,
    model: str,
    *,
    article_type: str = 'review',
) -> list[CritiqueNote]:
    """Critique a draft. Returns a list of CritiqueNote (may be empty).

    brief may be None (legacy path / reasoning engine disabled). Without a brief
    the fidelity layer has no contract to check against, so the critique runs
    craft-only and says so in the prompt.
    """
    numbered = _number_paragraphs(paragraphs)

    parts = [f'ARTICLE TYPE: {article_type}', '']
    if brief is not None:
        parts += [brief.to_writer_context(), '', '─' * 40, '']
        parts += ['Critique on BOTH layers (fidelity against the brief above, and craft).']
    else:
        parts += [
            'No editorial brief is available for this draft.',
            'Critique the CRAFT layer only. Do not raise fidelity issues — there',
            'is no brief to check against.',
        ]
    parts += [
        '',
        'DRAFT (paragraphs numbered):',
        numbered,
        '',
        'Mark up this draft. Return your structured critique.',
    ]

    raw = call_stage(
        client, model,
        editorial_context=editorial_context,
        stage_instructions=_INSTRUCTIONS,
        user_prompt='\n'.join(parts),
        stage='critique',
        max_tokens=2000,
    )
    try:
        data = parse_writer_json(raw)
    except ValueError:
        log.error("Critique stage: JSON parse failed. Raw:\n%s", raw[:400])
        raise

    n_paragraphs = len(paragraphs)
    valid_layers = (LAYER_FIDELITY, LAYER_CRAFT)
    notes: list[CritiqueNote] = []
    for idx, n in enumerate(data.get('notes', []), 1):
        try:
            paragraph = int(n.get('paragraph', 0))
        except (TypeError, ValueError):
            paragraph = 0
        # Clamp out-of-range paragraph references to 0 (whole-draft) rather than
        # trusting a hallucinated index the rewrite stage would fail to find.
        if paragraph < 0 or paragraph > n_paragraphs:
            log.warning("Critique stage: note references paragraph %d (have %d) — treating as structural",
                        paragraph, n_paragraphs)
            paragraph = 0

        layer = str(n.get('layer', '')).lower().strip()
        if layer not in valid_layers:
            layer = LAYER_CRAFT

        impact = str(n.get('impact', 'medium')).lower().strip()
        if impact not in _VALID_IMPACT:
            impact = 'medium'

        # If there is no brief, downgrade any fidelity note to craft — there was
        # no contract to violate, so the model overstepped its instructions.
        if brief is None and layer == LAYER_FIDELITY:
            continue

        notes.append(CritiqueNote(
            paragraph=paragraph,
            layer=layer,
            issue_type=str(n.get('issue_type', '')).strip() or 'unspecified',
            impact=impact,
            description=str(n.get('description', '')).strip(),
            fix=str(n.get('fix', '')).strip(),
            id=f'C-{idx:03d}',
        ))

    n_fid = sum(1 for x in notes if x.layer == LAYER_FIDELITY)
    n_high = sum(1 for x in notes if x.impact == 'high')
    log.info("Critique stage: %d notes (%d fidelity, %d high-impact)", len(notes), n_fid, n_high)
    return notes
