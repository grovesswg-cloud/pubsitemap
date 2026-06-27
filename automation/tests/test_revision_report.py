"""Tests for RevisionReport and CritiqueNote."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from revision.report import (
    RevisionReport, CritiqueNote, LAYER_FIDELITY, LAYER_CRAFT,
)


def _sample_report() -> RevisionReport:
    notes = [
        CritiqueNote(
            paragraph=2, layer=LAYER_FIDELITY, issue_type='dropped_evidence',
            impact='high', description='E-003 (the silence) never appears.',
            fix='Open the paragraph on the 4.3s of silence.', id='C-001',
        ),
        CritiqueNote(
            paragraph=5, layer=LAYER_CRAFT, issue_type='weak_transition',
            impact='medium', description='Abuts paragraph 4 without a bridge.',
            fix='Carry the compression image into the sequencing point.', id='C-002',
        ),
        CritiqueNote(
            paragraph=0, layer=LAYER_CRAFT, issue_type='weak_ending',
            impact='low', description='Close trails off.',
            fix='Return to the thesis.', id='C-003',
        ),
    ]
    return RevisionReport(
        notes=notes,
        plan=['C-001', 'C-002'],
        revised_paragraphs={2: '<p>Rewritten two.</p>', 5: '<p>Rewritten five.</p>'},
        original_body='<p>one</p><p>two</p>',
        revised_body='<p>one</p><p>Rewritten two.</p>',
        revised=True,
    )


def test_report_roundtrip():
    report = _sample_report()
    restored = RevisionReport.from_dict(report.to_dict())
    assert len(restored.notes) == 3
    assert restored.notes[0].id == 'C-001'
    assert restored.plan == ['C-001', 'C-002']
    assert restored.revised is True


def test_report_json_roundtrip():
    report = _sample_report()
    restored = RevisionReport.from_dict(json.loads(report.to_json()))
    assert restored.original_body == report.original_body
    assert restored.revised_body == report.revised_body


def test_revised_paragraphs_keys_normalise_to_int():
    # JSON object keys are strings; from_dict must restore int paragraph indices.
    report = _sample_report()
    d = report.to_dict()
    # asdict keeps int keys, but simulate a JSON round-trip which stringifies them
    d_json = json.loads(json.dumps(d))
    restored = RevisionReport.from_dict(d_json)
    assert 2 in restored.revised_paragraphs
    assert 5 in restored.revised_paragraphs
    assert restored.revised_paragraphs[2] == '<p>Rewritten two.</p>'


def test_fidelity_and_craft_views():
    report = _sample_report()
    assert len(report.fidelity_notes()) == 1
    assert len(report.craft_notes()) == 2
    assert report.fidelity_notes()[0].id == 'C-001'


def test_selected_notes_matches_plan():
    report = _sample_report()
    selected = report.selected_notes()
    assert {n.id for n in selected} == {'C-001', 'C-002'}


def test_impact_rank_ordering():
    high = CritiqueNote(1, LAYER_CRAFT, 'x', 'high', 'd', 'f')
    med = CritiqueNote(1, LAYER_CRAFT, 'x', 'medium', 'd', 'f')
    low = CritiqueNote(1, LAYER_CRAFT, 'x', 'low', 'd', 'f')
    assert high.impact_rank() > med.impact_rank() > low.impact_rank()


def test_empty_report_defaults():
    report = RevisionReport()
    assert report.notes == []
    assert report.plan == []
    assert report.revised is False
    assert report.revised_paragraphs == {}


def test_summary_is_a_string():
    report = _sample_report()
    s = report.summary()
    assert isinstance(s, str)
    assert 'fidelity' in s
    assert 'changed=True' in s
