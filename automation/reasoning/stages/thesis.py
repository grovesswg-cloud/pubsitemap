"""Groves Engine — Stages 3–6: Synthesis + Perspective + Thesis + Counterargument

Four distinct operations in one stage file because they form a single reasoning arc:
what emerges → which truth matters → what the argument is → what challenges it.

Synthesis:      If all observations are simultaneously true, what larger argument emerges?
Perspective:    Which of these true ideas is worth 1,500 words?
Thesis:         Generate 5 candidates, challenge the strongest, select one.
Counterargument:Why would a reasonable critic who heard the same record disagree?

One Claude call covers all four. The prompt is structured to enforce the sequence:
Synthesis must precede Perspective; Perspective must precede Thesis generation.
This order is the core of the Synthesis stage's value — it prevents the AI from
jumping to a thesis before understanding what the observations collectively argue.

Failure mode: fail-closed. No thesis = no article.
"""
from __future__ import annotations
import logging

from json_utils import parse_writer_json

log = logging.getLogger('engine.thesis')

_SYSTEM = """\
You are performing the Synthesis, Perspective, Thesis, and Counterargument stages
of the editorial reasoning process.

{editorial_context}

You have already gathered observations and interpretations about the subject.
Now you will move through four reasoning stages in strict sequence.

SYNTHESIS STAGE:
If all of the observations and interpretations are simultaneously true, what
larger argument emerges? This is not a summary of the observations — it is the
argument that becomes visible only when you hold all of them at once.
The synthesis should be surprising. If it is obvious, look again.

PERSPECTIVE STAGE:
Of all the true things you have observed and synthesised, which single idea
is worth spending 1,500 words on? Editorial perspective is the decision about
which truth has the most to say. Not the most obvious truth — the most generative.

THESIS GENERATION:
Generate exactly 5 thesis candidates. Each must:
  — Propose a specific argument about this record's meaning or achievement
  — Be supportable by the observations
  — Be distinct from the other four candidates
  — Be falsifiable (a reasonable critic could disagree)

THESIS CHALLENGE:
Challenge the strongest candidate. What evidence contradicts it?
What does it miss? What would need to be true for it to fail?

THESIS SELECTION:
Select one thesis. It does not have to be the one that survived the challenge
without damage — sometimes the challenged thesis, now refined, is the strongest.
State the selected thesis as a single declarative sentence.

COUNTERARGUMENT:
Ask: why would a reasonable critic who encountered the same evidence disagree
with the selected thesis? One clear sentence. This is not a hedge — it is an
honest acknowledgment that the thesis is a position, not a fact.

Return ONLY a valid JSON object:
{{
  "synthesis": "The larger argument that emerges when all observations are held at once.",
  "perspective": "Which truth is worth 1,500 words, and why.",
  "thesis_candidates": [
    "Candidate 1: ...",
    "Candidate 2: ...",
    "Candidate 3: ...",
    "Candidate 4: ...",
    "Candidate 5: ..."
  ],
  "thesis_challenge": "The strongest candidate is X. The challenge is: ...",
  "thesis": "Selected thesis — one declarative sentence.",
  "rejected_theses": ["Candidate 2 rejected because...", "..."],
  "counterargument": "A reasonable critic would disagree because..."
}}
"""


def run(
    subject: dict,
    observations: list[str],
    interpretations: list[str],
    publication_memory: dict,
    positioning: dict,
    editorial_context: str,
    client,
    model: str,
) -> tuple[str, str, str, list[str], str]:
    """
    Returns:
        (synthesis, perspective, thesis, rejected_theses, counterargument)
    """
    system = _SYSTEM.format(editorial_context=editorial_context)

    artist = subject.get('artist', '') or subject.get('artistName', '')
    album = subject.get('album', '') or subject.get('albumName', '')

    prior = publication_memory.get('prior_coverage', [])
    consensus = positioning.get('consensus', '')

    obs_block = '\n'.join(f'  {i+1}. {o}' for i, o in enumerate(observations))
    interp_block = '\n'.join(f'  {i+1}. {t}' for i, t in enumerate(interpretations))

    parts = [
        f'SUBJECT: {artist}{" — " + album if album else ""}',
        '',
        'OBSERVATIONS:',
        obs_block,
        '',
        'INTERPRETATIONS:',
        interp_block,
    ]

    if consensus:
        parts += ['', f'INCOMING CRITICAL ANGLE (what the news is emphasising):\n{consensus[:400]}']

    if prior:
        parts += [
            '',
            'PRIOR LORD COVERAGE (positions to avoid repeating):',
            '\n'.join(f'  • {p}' for p in prior[:5]),
        ]

    parts += [
        '',
        'Move through Synthesis → Perspective → Thesis → Counterargument in that order.',
        'Do not skip directly to thesis generation.',
    ]

    message = client.messages.create(
        model=model,
        max_tokens=2500,
        system=system,
        messages=[{'role': 'user', 'content': '\n'.join(parts)}],
    )

    raw = message.content[0].text
    try:
        data = parse_writer_json(raw)
    except ValueError:
        log.error("Thesis stage: JSON parse failed. Raw:\n%s", raw[:400])
        raise

    synthesis = data.get('synthesis', '')
    perspective = data.get('perspective', '')
    thesis = data.get('thesis', '')
    rejected = data.get('rejected_theses', [])
    counterargument = data.get('counterargument', '')

    if not thesis:
        raise ValueError("Thesis stage: 'thesis' field is empty — cannot proceed")

    log.info("Thesis stage: thesis selected (%d chars), %d rejected, counterargument present=%s",
             len(thesis), len(rejected), bool(counterargument))
    return synthesis, perspective, thesis, rejected, counterargument
