"""Groves Engine — RevisionReport and supporting types.

The RevisionReport is the complete output of the Editorial Revision Engine.
It records what the internal editor found (the critique), what it chose to act
on (the plan), and the paragraphs it actually rewrote — alongside the original
and revised bodies.

Like the ReasoningBrief, the report is JSON-serialisable by design. It is the
permanent record of the editorial revision pass and seeds the Editorial
Notebook (PR-010): the critique is *why* an article reads the way it does.

Two layers of critique are tracked deliberately:
  fidelity — did the prose deliver the ReasoningBrief? (thesis drift, dropped
             evidence, missing weaknesses, over-confident hedging, smuggled
             arguments). Checkable against the brief — the closest thing the
             editor has to an objective standard.
  craft    — prose-level weaknesses (transitions, pacing, endings, repetition,
             shallow analysis). Judgment, but informed judgment.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict


_IMPACT_RANK = {'high': 3, 'medium': 2, 'low': 1}

# The two critique layers. Kept as constants so stages and tests reference one
# source of truth rather than bare strings.
LAYER_FIDELITY = 'fidelity'
LAYER_CRAFT = 'craft'
_LAYERS = (LAYER_FIDELITY, LAYER_CRAFT)


@dataclass
class CritiqueNote:
    """A single editorial observation about the draft.

    paragraph is a 1-based index into the article body's paragraphs; 0 is
    reserved for whole-draft / structural notes that do not map to one
    paragraph (e.g. "the argument never addresses the counterargument").

    impact is the editor's judgment of how much fixing this matters. It is the
    LLM's call in the critique stage; the plan stage then triages mechanically
    on it — high-impact issues are fixed first, low-impact ones are tolerated
    rather than risk over-editing prose that already works.

    fix is the instruction for the rewrite — what the revised paragraph must
    accomplish — not the rewritten prose itself. The rewrite stage executes it.
    """
    paragraph: int          # 1-based paragraph index; 0 = whole-draft/structural
    layer: str              # 'fidelity' | 'craft'
    issue_type: str         # e.g. 'dropped_evidence', 'weak_transition', 'shallow_analysis'
    impact: str             # 'high' | 'medium' | 'low'
    description: str         # what is wrong
    fix: str                # what the rewrite must accomplish (an instruction)
    id: str = ''            # C-001 style; auto-assigned by the critique stage

    def impact_rank(self) -> int:
        return _IMPACT_RANK.get(self.impact, 2)


@dataclass
class RevisionReport:
    """Complete record of one editorial revision pass.

    notes              — full critique (every issue found, both layers)
    plan               — ids of the notes selected for rewrite (highest-impact subset)
    revised_paragraphs — {1-based paragraph index: rewritten HTML}
    original_body      — the writer's draft body, unchanged
    revised_body       — the body after targeted rewrites are stitched back in
    revised            — True iff at least one paragraph was rewritten
    """
    notes: list[CritiqueNote] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    revised_paragraphs: dict = field(default_factory=dict)
    original_body: str = ''
    revised_body: str = ''
    revised: bool = False

    # ── Convenience views ──────────────────────────────────────────────────────

    def fidelity_notes(self) -> list[CritiqueNote]:
        return [n for n in self.notes if n.layer == LAYER_FIDELITY]

    def craft_notes(self) -> list[CritiqueNote]:
        return [n for n in self.notes if n.layer == LAYER_CRAFT]

    def selected_notes(self) -> list[CritiqueNote]:
        chosen = set(self.plan)
        return [n for n in self.notes if n.id in chosen]

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> RevisionReport:
        d = dict(d)
        notes = [CritiqueNote(**n) for n in d.pop('notes', [])]
        # JSON object keys are strings — normalise revised_paragraphs keys to int.
        raw_rp = d.pop('revised_paragraphs', {}) or {}
        revised_paragraphs = {int(k): v for k, v in raw_rp.items()}
        return cls(notes=notes, revised_paragraphs=revised_paragraphs, **d)

    def summary(self) -> str:
        """One-line human summary for CI logs and the editor's record."""
        fid = len(self.fidelity_notes())
        craft = len(self.craft_notes())
        return (
            f"critique: {len(self.notes)} notes ({fid} fidelity, {craft} craft); "
            f"plan: {len(self.plan)} selected; "
            f"rewritten: {len(self.revised_paragraphs)} paragraph(s); "
            f"changed={self.revised}"
        )
