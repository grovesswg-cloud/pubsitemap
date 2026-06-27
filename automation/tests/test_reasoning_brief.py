"""Tests for ReasoningBrief and EvidenceItem."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from reasoning.brief import ReasoningBrief, EvidenceItem, derive_thesis_confidence


def _sample_brief() -> ReasoningBrief:
    return ReasoningBrief(
        thesis="This record argues that grief is not linear but recursive.",
        rejected_theses=[
            "Album is Kendrick's most personal record.",
            "Album represents a return to classic hip-hop.",
        ],
        counterargument="A critic who values formal innovation over emotional immediacy would find the production choices too familiar.",
        observations=[
            "HIGH: The album opens with silence before any instrument enters.",
            "MEDIUM: Vocals remain compressed throughout, reducing dynamic range.",
            "LOW: The record appears to draw on Talk Talk's 'Spirit of Eden' in its use of space.",
        ],
        interpretations=[
            "Silence as an opening statement withholds the expected hook — demands attention before it rewards it.",
            "Compressed vocals create a sense of emotional distance from the material being described.",
            "If the Talk Talk influence is present, it positions this as an album about texture over melody.",
        ],
        synthesis="Every musical choice removes forward momentum — this is an album about the loss of agency.",
        perspective="The sequencing is the most important element: it forces the listener to re-experience rather than progress.",
        evidence=[
            EvidenceItem(
                observation="Silence as opening",
                evidence="Track 1 begins with 4.3 seconds of silence",
                supports="Thesis: grief is recursive — re-entry each time",
                confidence="high",
                id="E-001",
            ),
            EvidenceItem(
                observation="Compressed vocals",
                evidence="Tracks 2, 5, 8 — consistently narrow dynamic range",
                supports="Loss of agency thesis",
                confidence="medium",
                id="E-002",
            ),
        ],
        weaknesses=["The second half loses thematic coherence — tracks 7–9 feel like fragments rather than development."],
        positioning={'consensus': 'Critics are focusing on production choices.', 'underexplored': ''},
        publication_memory={
            'prior_coverage': ['2025-01-15 [BULLETIN] Artist announces new album'],
            'previous_ratings': [],
            'coverage_count': 1,
        },
        outline=[
            "Paragraph 1: Open with the silence — the record withholds before it gives.",
            "Paragraph 2: Move through the compression — the voice is present but held at distance.",
            "Paragraph 3: Address the sequencing argument — re-experience vs. progress.",
            "Paragraph 4: The counterargument — production familiarity as limitation.",
            "Paragraph 5: Return to thesis — grief is recursive; so is this record.",
        ],
        editor_notes=[
            "The Talk Talk influence claim is LOW confidence — hedge explicitly.",
            "Don't open with biography — open with the silence.",
        ],
        confidence="medium",
    )


def test_brief_serialisation_roundtrip():
    brief = _sample_brief()
    d = brief.to_dict()
    restored = ReasoningBrief.from_dict(d)
    assert restored.thesis == brief.thesis
    assert restored.confidence == brief.confidence
    assert len(restored.evidence) == len(brief.evidence)
    assert restored.evidence[0].observation == brief.evidence[0].observation
    assert restored.evidence[0].confidence == brief.evidence[0].confidence


def test_brief_json_roundtrip():
    brief = _sample_brief()
    json_str = brief.to_json()
    d = json.loads(json_str)
    restored = ReasoningBrief.from_dict(d)
    assert restored.thesis == brief.thesis
    assert len(restored.rejected_theses) == 2
    assert len(restored.evidence) == 2


def test_writer_context_contains_thesis():
    brief = _sample_brief()
    ctx = brief.to_writer_context()
    assert brief.thesis in ctx
    assert 'THESIS' in ctx


def test_writer_context_contains_weaknesses():
    brief = _sample_brief()
    ctx = brief.to_writer_context()
    assert 'WEAKNESSES' in ctx
    assert brief.weaknesses[0] in ctx


def test_writer_context_contains_outline():
    brief = _sample_brief()
    ctx = brief.to_writer_context()
    assert 'OUTLINE' in ctx
    assert 'Paragraph 1' in ctx


def test_writer_context_contains_editor_notes():
    brief = _sample_brief()
    ctx = brief.to_writer_context()
    assert 'EDITOR NOTES' in ctx
    assert 'Talk Talk' in ctx


def test_writer_context_contains_prior_coverage():
    brief = _sample_brief()
    ctx = brief.to_writer_context()
    assert 'PRIOR LORD COVERAGE' in ctx


def test_writer_context_contains_counterargument():
    brief = _sample_brief()
    ctx = brief.to_writer_context()
    assert 'COUNTERARGUMENT' in ctx
    assert 'formal innovation' in ctx


def test_evidence_item_confidence_values():
    for conf in ('high', 'medium', 'low'):
        e = EvidenceItem(observation='x', evidence='y', supports='z', confidence=conf)
        assert e.confidence == conf


def test_empty_brief_defaults():
    brief = ReasoningBrief()
    assert brief.thesis == ''
    assert brief.observations == []
    assert brief.evidence == []
    assert brief.confidence == 'medium'
    assert brief.editor_notes == []


def test_empty_brief_writer_context():
    brief = ReasoningBrief()
    ctx = brief.to_writer_context()
    assert 'THESIS' in ctx
    assert isinstance(ctx, str)


def test_from_dict_preserves_evidence_items():
    brief = _sample_brief()
    d = brief.to_dict()
    assert isinstance(d['evidence'][0], dict)
    restored = ReasoningBrief.from_dict(d)
    assert isinstance(restored.evidence[0], EvidenceItem)
    assert restored.evidence[1].supports == "Loss of agency thesis"


def test_evidence_id_roundtrips():
    brief = _sample_brief()
    restored = ReasoningBrief.from_dict(brief.to_dict())
    assert restored.evidence[0].id == "E-001"
    assert restored.evidence[1].id == "E-002"


def test_writer_context_shows_evidence_ids():
    brief = _sample_brief()
    ctx = brief.to_writer_context()
    assert "E-001" in ctx
    assert "E-002" in ctx


def test_thesis_confidence_field_present():
    brief = _sample_brief()
    restored = ReasoningBrief.from_dict(brief.to_dict())
    assert restored.thesis_confidence in ('high', 'medium', 'low')


def test_writer_context_shows_thesis_confidence():
    brief = ReasoningBrief(thesis="X", thesis_confidence="low")
    ctx = brief.to_writer_context()
    assert "confidence: low" in ctx


def test_derive_thesis_confidence_all_high():
    ev = [EvidenceItem('o', 'e', 's', 'high') for _ in range(3)]
    assert derive_thesis_confidence(ev) == 'high'


def test_derive_thesis_confidence_all_low():
    ev = [EvidenceItem('o', 'e', 's', 'low') for _ in range(3)]
    assert derive_thesis_confidence(ev) == 'low'


def test_derive_thesis_confidence_mixed_is_medium():
    ev = [
        EvidenceItem('o', 'e', 's', 'high'),
        EvidenceItem('o', 'e', 's', 'medium'),
        EvidenceItem('o', 'e', 's', 'low'),
    ]
    assert derive_thesis_confidence(ev) == 'medium'


def test_derive_thesis_confidence_empty_is_low():
    assert derive_thesis_confidence([]) == 'low'


def test_derive_thesis_confidence_mostly_low_drags_down():
    # A thesis resting mostly on low-confidence evidence is not high-confidence,
    # regardless of one strong supporting item.
    ev = [
        EvidenceItem('o', 'e', 's', 'high'),
        EvidenceItem('o', 'e', 's', 'low'),
        EvidenceItem('o', 'e', 's', 'low'),
    ]
    assert derive_thesis_confidence(ev) == 'low'
