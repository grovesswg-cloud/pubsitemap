"""Groves Engine — ReasoningBrief and supporting types.

The ReasoningBrief is the complete output of the Editorial Intelligence Engine.
It is the only thing the writer receives. The writer renders it into prose;
it does not reason, position, or generate theses.

The brief is JSON-serialisable by design. When the Editorial Notebook lands
(PR-010), these briefs are stored as the permanent record of every editorial
decision made about a published article.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict


_CONFIDENCE_WEIGHT = {'high': 3, 'medium': 2, 'low': 1}


@dataclass
class EvidenceItem:
    """A single piece of evidence mapping an observation to a thesis claim.

    The id (E-001, E-002, …) is stable within a brief and lets the Revision
    Engine (PR-006.3) reference a specific claim — "E-014 is weak" — rather
    than "the third bullet under paragraph six".
    """
    observation: str         # what was directly observed
    evidence: str            # specific moment (track, timestamp, lyric, production detail)
    supports: str            # which part of the thesis this evidence supports
    confidence: str          # 'high' | 'medium' | 'low'
    id: str = ''             # E-001 style; auto-assigned by the outline stage


def derive_thesis_confidence(evidence: list[EvidenceItem]) -> str:
    """Compute thesis confidence from the evidence that supports it.

    This is distinct from the brief's overall self-reported confidence. It is
    mechanical and auditable: a thesis resting mostly on HIGH-confidence
    evidence is itself high-confidence; one resting on LOW evidence is not,
    regardless of how assured the prose sounds. Confidence must survive the
    pipeline rather than being asserted at the end.
    """
    weights = [_CONFIDENCE_WEIGHT.get(e.confidence, 2) for e in evidence]
    if not weights:
        return 'low'
    avg = sum(weights) / len(weights)
    if avg >= 2.34:
        return 'high'
    if avg >= 1.67:
        return 'medium'
    return 'low'


@dataclass
class ReasoningBrief:
    """Complete editorial reasoning produced before any prose is written.

    Fields are populated by the reasoning stages in order:
      research     → publication_memory, positioning
      observation  → observations, interpretations
      thesis       → synthesis, perspective, thesis, rejected_theses, counterargument, weaknesses
      outline      → evidence, outline, editor_notes, confidence
    """
    # Core argument
    thesis: str = ''
    rejected_theses: list[str] = field(default_factory=list)
    counterargument: str = ''

    # Observation layer (what is known)
    observations: list[str] = field(default_factory=list)
    interpretations: list[str] = field(default_factory=list)

    # Synthesis and perspective (what it means; which truth is worth 1,500 words)
    synthesis: str = ''
    perspective: str = ''

    # Evidence (maps observations to thesis; basis for mandatory weaknesses)
    evidence: list[EvidenceItem] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)

    # Memory and positioning (from research stage)
    publication_memory: dict = field(default_factory=dict)
    positioning: dict = field(default_factory=dict)

    # Structure
    outline: list[str] = field(default_factory=list)

    # Internal — never published; seeds the future Editorial Notebook
    editor_notes: list[str] = field(default_factory=list)

    # Confidence — two distinct signals:
    #   confidence        — overall, self-reported by the outline stage (holistic)
    #   thesis_confidence — derived mechanically from the evidence map (auditable)
    confidence: str = 'medium'          # 'high' | 'medium' | 'low'
    thesis_confidence: str = 'medium'   # 'high' | 'medium' | 'low'

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> ReasoningBrief:
        evidence = [EvidenceItem(**e) for e in d.pop('evidence', [])]
        return cls(evidence=evidence, **d)

    # ── Writer context ─────────────────────────────────────────────────────────

    def to_writer_context(self) -> str:
        """Formats the brief as a structured context block for the writer prompt.

        The writer uses this to render the reasoning into prose.
        It does not deviate from the thesis or introduce new arguments.
        """
        lines = [
            'EDITORIAL REASONING BRIEF',
            '=' * 40,
            '',
            f'THESIS  (confidence: {self.thesis_confidence})\n{self.thesis}',
            '',
        ]

        if self.rejected_theses:
            lines += ['REJECTED THESES (do not use)']
            lines += [f'  • {t}' for t in self.rejected_theses]
            lines += ['']

        if self.counterargument:
            lines += [f'COUNTERARGUMENT CONSIDERED\n{self.counterargument}', '']

        if self.synthesis:
            lines += [f'SYNTHESIS\n{self.synthesis}', '']

        if self.perspective:
            lines += [f'EDITORIAL PERSPECTIVE\n{self.perspective}', '']

        if self.observations:
            lines += ['KEY OBSERVATIONS']
            lines += [f'  • {o}' for o in self.observations]
            lines += ['']

        if self.evidence:
            lines += ['EVIDENCE MAP']
            for e in self.evidence:
                id_tag = f'{e.id} ' if e.id else ''
                conf_tag = f'[{e.confidence.upper()}]'
                lines.append(f'  {id_tag}{conf_tag} {e.observation}')
                lines.append(f'       ↳ {e.evidence}')
                lines.append(f'       ↳ supports: {e.supports}')
            lines += ['']

        if self.weaknesses:
            lines += ['WEAKNESSES (must appear in article)']
            lines += [f'  • {w}' for w in self.weaknesses]
            lines += ['']

        if self.positioning.get('underexplored'):
            lines += [f'EDITORIAL ANGLE\n{self.positioning["underexplored"]}', '']

        if self.publication_memory.get('prior_coverage'):
            lines += ['PRIOR LORD COVERAGE (avoid repeating these positions)']
            for item in self.publication_memory['prior_coverage'][:3]:
                lines.append(f'  • {item}')
            lines += ['']

        if self.outline:
            lines += ['OUTLINE']
            for i, section in enumerate(self.outline, 1):
                lines.append(f'  {i}. {section}')
            lines += ['']

        if self.editor_notes:
            lines += ['EDITOR NOTES (internal — guide the prose, do not publish)']
            lines += [f'  • {n}' for n in self.editor_notes]

        return '\n'.join(lines)
