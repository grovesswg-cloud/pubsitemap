"""Groves Engine — Revision Stage 3: Targeted Rewrites

The rewrite stage executes the plan. It rewrites ONLY the selected paragraphs,
leaving the rest of the prose exactly as the writer left it — because the
writer's good prose is worth protecting, and because re-drafting everything is
how revision engines quietly destroy voice.

Three constraints make this an edit rather than a re-draft:

  1. BOUND TO THE BRIEF. The rewrite may not introduce arguments the brief does
     not contain. It is fixing the rendering of the assigned argument, not
     re-reasoning. Same ARGUMENT/PROSE separation the writer works under.

  2. FLOW IS PRESERVED. The model sees the WHOLE draft (read-only) so it can
     keep transitions into and out of each rewritten paragraph intact. It sees
     the neighbours; it changes only the target.

  3. ONE CALL, ALL TARGETS. All targeted paragraphs are rewritten together in a
     single call so the model can keep them consistent with each other, rather
     than rewriting paragraph 4 in ignorance of what it just did to paragraph 3.

Failure mode: fail-closed. If the plan said a paragraph needed fixing and we
could not produce the fix, we do not silently publish the unfixed draft during
pre-launch.
"""
from __future__ import annotations
import logging

from json_utils import parse_writer_json
from revision.report import CritiqueNote
from revision.llm import call_stage

log = logging.getLogger('revision.rewrite')

_INSTRUCTIONS = """\
You are the internal editor executing a set of targeted edits on a draft. The
editorial markup has already been done; the specific paragraphs to fix and what
each fix must accomplish are given to you. Your job is to rewrite ONLY those
paragraphs.

HARD RULES:
  • Rewrite ONLY the paragraphs listed under EDITS. Do not touch any other
    paragraph. Do not renumber, merge, split, add, or delete paragraphs.
  • Stay bound to the editorial brief. Do NOT introduce any argument, claim, or
    fact that is not already supported by the brief or the existing draft. You
    are improving the rendering of the argument, not changing the argument.
  • Preserve flow. You can see the full draft. Keep each rewritten paragraph
    reading smoothly out of the paragraph before it and into the paragraph after
    it — those neighbours are NOT changing, so your edit must fit them.
  • Keep the publication's voice. Match the register and rhythm of the
    surrounding prose. An edited paragraph should be indistinguishable in voice
    from the paragraphs around it.
  • Each rewritten paragraph must remain a single <p>…</p> block. You may use
    <em> sparingly, as the draft does. No headers.
  • Address the fix. Each edit names what it must accomplish — accomplish it.

Return ONLY a valid JSON object mapping each edited paragraph number (as a
string key) to its rewritten HTML:
{{
  "revised": {{
    "4": "<p>Rewritten paragraph 4…</p>",
    "7": "<p>Rewritten paragraph 7…</p>"
  }}
}}
Include a key for every paragraph listed under EDITS, and no others.
"""


def _number_paragraphs(paragraphs: list[str]) -> str:
    return '\n\n'.join(f'[{i}] {p}' for i, p in enumerate(paragraphs, 1))


def _format_edits(selected: list[CritiqueNote]) -> str:
    """Group the selected notes by paragraph into an instruction block."""
    by_paragraph: dict[int, list[CritiqueNote]] = {}
    structural: list[CritiqueNote] = []
    for note in selected:
        if note.paragraph == 0:
            structural.append(note)
        else:
            by_paragraph.setdefault(note.paragraph, []).append(note)

    lines: list[str] = []
    for paragraph in sorted(by_paragraph):
        lines.append(f'Paragraph {paragraph}:')
        for note in by_paragraph[paragraph]:
            lines.append(f'  • [{note.impact.upper()} · {note.issue_type}] {note.description}')
            lines.append(f'    fix: {note.fix}')
    if structural:
        lines.append('')
        lines.append('Whole-draft guidance (apply while editing the paragraphs above):')
        for note in structural:
            lines.append(f'  • [{note.impact.upper()} · {note.issue_type}] {note.description}')
            lines.append(f'    fix: {note.fix}')
    return '\n'.join(lines)


def run(
    paragraphs: list[str],
    selected: list[CritiqueNote],
    brief,
    editorial_context: str,
    client,
    model: str,
) -> dict:
    """Execute the rewrite plan. Returns {1-based paragraph index: new HTML}.

    Only paragraphs that map to a selected note (paragraph > 0) are rewritten.
    Structural (paragraph 0) notes inform the edits but produce no standalone
    rewrite of their own.
    """
    target_indices = sorted({n.paragraph for n in selected if n.paragraph > 0})
    if not target_indices:
        log.info("Rewrite stage: no paragraph-level edits to make")
        return {}

    parts = []
    if brief is not None:
        parts += [brief.to_writer_context(), '', '─' * 40, '']
    parts += [
        'FULL DRAFT (read-only context — paragraphs numbered):',
        _number_paragraphs(paragraphs),
        '',
        'EDITS (rewrite exactly these paragraphs):',
        _format_edits(selected),
        '',
        f'Rewrite paragraph(s): {", ".join(str(i) for i in target_indices)}.',
        'Return the JSON map of rewritten paragraphs.',
    ]

    raw = call_stage(
        client, model,
        editorial_context=editorial_context,
        stage_instructions=_INSTRUCTIONS,
        user_prompt='\n'.join(parts),
        stage='rewrite',
        max_tokens=2500,
    )
    try:
        data = parse_writer_json(raw)
    except ValueError:
        log.error("Rewrite stage: JSON parse failed. Raw:\n%s", raw[:400])
        raise

    raw_revised = data.get('revised', {}) or {}
    n_paragraphs = len(paragraphs)
    revised: dict = {}
    for key, html in raw_revised.items():
        try:
            idx = int(key)
        except (TypeError, ValueError):
            log.warning("Rewrite stage: non-integer paragraph key %r — skipping", key)
            continue
        if idx not in target_indices:
            log.warning("Rewrite stage: model rewrote unrequested paragraph %d — ignoring", idx)
            continue
        html = (html or '').strip()
        if not html:
            log.warning("Rewrite stage: empty rewrite for paragraph %d — keeping original", idx)
            continue
        # Defensive: ensure it is a paragraph block. Wrap if the model dropped tags.
        if not html.lower().startswith('<p'):
            html = f'<p>{html}</p>'
        revised[idx] = html

    missing = [i for i in target_indices if i not in revised]
    if missing:
        # Fail-closed: the plan said these needed fixing and we did not get them.
        raise ValueError(
            f"Rewrite stage: requested paragraphs {missing} were not returned by the model"
        )

    log.info("Rewrite stage: rewrote %d paragraph(s): %s", len(revised), sorted(revised))
    return revised
