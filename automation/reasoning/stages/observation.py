"""Groves Engine — Stage 2: Observation + Interpretation

Observation answers: what is present in this record?
Interpretation answers: what does each observation mean?

These are two distinct cognitive operations kept in the same stage because each
interpretation is paired with its observation. Separating them into independent
Claude calls would lose the pairing.

The listening_framework.md document is one source of observations. The stage
is named 'observation' rather than 'listening' because the framework applies
to any subject where evidence can be gathered — music, film, text, performance.
The listening framework is music-specific guidance for how to observe.

Observations carry confidence levels per the Confidence Levels section of the
listening framework: high (directly verifiable), medium (interpretive), low
(historical/influence claims).

Failure mode: fail-closed. The subsequent stages cannot produce a meaningful
thesis without observations.
"""
from __future__ import annotations
import json
import logging

from engine_debug import parse_stage_json
from reasoning.llm import call_stage

log = logging.getLogger('engine.observation')

_INSTRUCTIONS = """\
You are performing the Observation and Interpretation stages of the editorial reasoning process.

Your task is NOT to write an article. You are gathering structured observations
and interpreting each one, following the Observation stage protocol.

OBSERVATION STAGE:
Document what is known about this subject. Observations may come from:
  — Knowledge of the record (tracks, production, lyrics, structure)
  — Critical reception and reported context
  — The artist's prior work and evolution
  — Technical and compositional choices

Be honest about confidence. Do not state as fact what is inference.
Use the Confidence Levels from the listening framework:
  high     — directly verifiable (a track exists, an instrument is present)
  medium   — interpretive (the arrangement suggests withdrawal)
  low      — historical/influence claim (appears to draw on...)

INTERPRETATION STAGE:
For each observation, state what it means — one sentence of interpretation.
Interpretation explains function, not just presence.

Return ONLY a valid JSON object:
{{
  "observations": [
    "HIGH: [what is directly known]",
    "MEDIUM: [what the evidence suggests]",
    "LOW: [historical or influence claim, qualified appropriately]"
  ],
  "interpretations": [
    "Interpretation of observation 1.",
    "Interpretation of observation 2."
  ],
  "weaknesses_observed": [
    "One weakness identified during observation (mandatory — if none, state why with evidence)"
  ]
}}

Produce 8–12 observations. Each observation must have a paired interpretation.
weaknesses_observed must contain at least one entry.
"""


def run(subject: dict, editorial_context: str, client, model: str) -> tuple[list[str], list[str], list[str]]:
    """
    Args:
        subject:           Article subject dict (artist, album, context, title, summary).
        editorial_context: The publication's full criticism context (load_criticism_context()).
        client:            Anthropic client instance.
        model:             Model ID string.

    Returns:
        (observations, interpretations, weaknesses_observed) — all list[str].
    """
    artist = subject.get('artist', '') or subject.get('artistName', '')
    album = subject.get('album', '') or subject.get('albumName', '')
    context = subject.get('context', '') or subject.get('summary', '')
    title = subject.get('title', '')
    year = subject.get('year', '')

    prompt_parts = ['Gather structured observations about this subject.', '']
    if artist:
        prompt_parts.append(f'ARTIST: {artist}')
    if album:
        prompt_parts.append(f'ALBUM: {album}')
    if year:
        prompt_parts.append(f'YEAR: {year}')
    if title:
        prompt_parts.append(f'NEWS HEADLINE: {title}')
    if context:
        prompt_parts.append(f'CONTEXT: {context[:800]}')

    prompt_parts += [
        '',
        'Follow the three-pass observation protocol from the listening framework.',
        'Observation 1 (instinct): what is the immediate impression?',
        'Observation 2 (technical): what specific elements are present?',
        'Observation 3 (interpretive): what do these elements collectively suggest?',
        '',
        'Be specific. Name tracks, production choices, lyric moments where known.',
        'Carry confidence levels (HIGH/MEDIUM/LOW) in each observation.',
    ]

    user_prompt = '\n'.join(prompt_parts)
    raw = call_stage(
        client, model,
        editorial_context=editorial_context,
        stage_instructions=_INSTRUCTIONS,
        user_prompt=user_prompt,
        stage='observation',
        max_tokens=2000,
    )
    data = parse_stage_json(raw, stage='observation', prompt=user_prompt, log=log,
                            extra={'subject': f'{artist} — {album}' if album else artist,
                                   'model': model})

    observations = data.get('observations', [])
    interpretations = data.get('interpretations', [])
    weaknesses = data.get('weaknesses_observed', [])

    if len(observations) != len(interpretations):
        log.warning(
            "Observation/interpretation count mismatch: %d obs, %d interp — truncating to shorter",
            len(observations), len(interpretations),
        )
        n = min(len(observations), len(interpretations))
        observations, interpretations = observations[:n], interpretations[:n]

    if not weaknesses:
        log.warning("Observation stage: weaknesses_observed is empty — mandatory field missing")
        weaknesses = ['No specific weakness identified during observation.']

    log.info("Observation stage: %d observations, %d interpretations, %d weaknesses",
             len(observations), len(interpretations), len(weaknesses))
    return observations, interpretations, weaknesses
