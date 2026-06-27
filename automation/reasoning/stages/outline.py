"""Groves Engine — Stages 7–8: Evidence Map + Outline

Evidence Map: structured mapping of observations to thesis claims.
Each item carries: observation / specific evidence / what it supports / confidence.
This is the layer the Revision Engine will use to challenge weak-confidence claims.

Outline: paragraph-by-paragraph plan derived from thesis, evidence, and counterargument.
The outline is what the writer executes. It does not leave room for the writer to
invent a new argument — it provides the structure into which the prose is poured.

Editor Notes: internal guidance for the writer. Never published. Seeds the
Editorial Notebook (PR-010).

Failure mode: fail-closed. An article without a structured evidence base and
an outline is an article that bypasses the reasoning the engine just did.
"""
from __future__ import annotations
import logging

from engine_debug import parse_stage_json
from reasoning.brief import EvidenceItem
from reasoning.llm import call_stage

log = logging.getLogger('engine.outline')

_INSTRUCTIONS = """\
You are performing the Evidence Mapping and Outline stages of the editorial
reasoning process.

You have a completed thesis, synthesis, observations, and counterargument.
Your task is to map evidence to the thesis and produce a paragraph outline.

EVIDENCE MAPPING:
For each significant observation, determine:
  — The specific evidence that supports it (track name, timestamp, lyric, production detail)
  — Which part of the thesis it supports
  — Its confidence level: high (verifiable fact), medium (interpretation), low (historical claim)

Map 6–10 pieces of evidence. Include at least one LOW confidence item to
acknowledge the limits of what can be claimed with certainty.

WEAKNESS IDENTIFICATION:
Identify 1–2 meaningful weaknesses in the record or the thesis.
A weakness is not invented to appear balanced — it is a real limitation.
This field is mandatory per the listening framework.

OUTLINE:
Generate a paragraph-by-paragraph outline for the article.
Each outline item is one sentence describing what that paragraph does.
The outline should:
  — Open with the emotional anchor (from observations, not biography)
  — Move through the evidence in a purposeful order
  — Address the counterargument before the conclusion (not to concede — to strengthen)
  — Close by returning to the thesis with the full weight of the evidence behind it

EDITOR NOTES:
Internal notes to guide the prose writer. Examples:
  — "The production claim in paragraph 3 rests on medium-confidence evidence — hedge"
  — "The opening image could be the moment the bass arrives"
  — "Don't mention the producer in paragraph 2 — it pulls focus from the record"
Never published. Seed for the Editorial Notebook.

Return ONLY a valid JSON object:
{{
  "evidence": [
    {{
      "observation": "What was observed",
      "evidence": "Specific supporting moment (track, lyric, production detail)",
      "supports": "Which part of the thesis this supports",
      "confidence": "high | medium | low"
    }}
  ],
  "weaknesses": [
    "One real weakness in this record or in the thesis."
  ],
  "outline": [
    "Paragraph 1: ...",
    "Paragraph 2: ...",
    "..."
  ],
  "editor_notes": [
    "Internal note 1.",
    "Internal note 2."
  ],
  "confidence": "high | medium | low"
}}
"""


def run(
    subject: dict,
    thesis: str,
    synthesis: str,
    counterargument: str,
    observations: list[str],
    interpretations: list[str],
    editorial_context: str,
    client,
    model: str,
) -> tuple[list[EvidenceItem], list[str], list[str], list[str], str]:
    """
    Returns:
        (evidence, weaknesses, outline, editor_notes, confidence)
    """
    artist = subject.get('artist', '') or subject.get('artistName', '')
    album = subject.get('album', '') or subject.get('albumName', '')
    article_type = subject.get('_article_type', 'review')

    word_target = '1,500–2,000' if article_type == 'feature' else '800–1,200'

    obs_block = '\n'.join(f'  {i+1}. {o}' for i, o in enumerate(observations))
    interp_block = '\n'.join(f'  {i+1}. {t}' for i, t in enumerate(interpretations))

    parts = [
        f'SUBJECT: {artist}{" — " + album if album else ""}',
        f'ARTICLE TYPE: {article_type} ({word_target} words)',
        '',
        f'SELECTED THESIS:\n{thesis}',
        '',
        f'SYNTHESIS:\n{synthesis}',
        '',
        f'COUNTERARGUMENT TO INTEGRATE:\n{counterargument}',
        '',
        'OBSERVATIONS:',
        obs_block,
        '',
        'INTERPRETATIONS:',
        interp_block,
        '',
        'Map evidence and produce a paragraph outline for this article.',
        'The outline must have a clear arc: opening → evidence → counterargument → thesis return.',
    ]

    user_prompt = '\n'.join(parts)
    raw = call_stage(
        client, model,
        editorial_context=editorial_context,
        stage_instructions=_INSTRUCTIONS,
        user_prompt=user_prompt,
        stage='outline',
        # The outline stage is the heaviest producer in the engine: it emits the
        # evidence map, weaknesses, the full paragraph outline, editor notes, and
        # confidence in a single response. A 2500-token budget truncated rich
        # subjects mid-output (see the GNX calibration incident); 4096 gives the
        # reasoning room to finish. Revisit from telemetry if runs approach it.
        max_tokens=4096,
    )
    data = parse_stage_json(raw, stage='outline', prompt=user_prompt, log=log,
                            extra={'subject': f'{artist} — {album}' if album else artist,
                                   'article_type': article_type, 'model': model})

    raw_evidence = data.get('evidence', [])
    evidence = []
    for idx, e in enumerate(raw_evidence, 1):
        try:
            evidence.append(EvidenceItem(
                observation=e.get('observation', ''),
                evidence=e.get('evidence', ''),
                supports=e.get('supports', ''),
                confidence=e.get('confidence', 'medium').lower(),
                id=f'E-{idx:03d}',
            ))
        except Exception as exc:
            log.warning("Outline stage: skipping malformed evidence item: %s", exc)

    weaknesses = data.get('weaknesses', [])
    if not weaknesses:
        log.warning("Outline stage: weaknesses is empty — mandatory field missing")
        weaknesses = ['No specific weakness identified.']

    outline = data.get('outline', [])
    editor_notes = data.get('editor_notes', [])
    confidence = data.get('confidence', 'medium').lower()

    if confidence not in ('high', 'medium', 'low'):
        confidence = 'medium'

    log.info(
        "Outline stage: %d evidence items, %d weaknesses, %d outline paragraphs, confidence=%s",
        len(evidence), len(weaknesses), len(outline), confidence,
    )
    return evidence, weaknesses, outline, editor_notes, confidence
