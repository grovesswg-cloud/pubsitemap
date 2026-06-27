"""Tests for the mechanical triage policy (plan stage).

This is the deterministic core of the Revision Engine: the policy that encodes
"highest-impact weaknesses, not endless rewriting". These tests pin that policy.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from revision.report import CritiqueNote, LAYER_CRAFT, LAYER_FIDELITY
from revision.stages.plan import select_revisions, DEFAULT_PARAGRAPH_CAP


def _note(paragraph, impact, *, id='', layer=LAYER_CRAFT, issue='x'):
    return CritiqueNote(
        paragraph=paragraph, layer=layer, issue_type=issue,
        impact=impact, description='d', fix='f', id=id or f'C-{paragraph}{impact[0]}',
    )


def test_low_impact_never_selected():
    notes = [_note(1, 'low'), _note(2, 'low')]
    assert select_revisions(notes) == []


def test_all_high_selected_within_cap():
    notes = [_note(i, 'high') for i in range(1, 4)]
    selected = select_revisions(notes)
    assert len(selected) == 3


def test_high_beats_medium_under_cap_pressure():
    # 5 issues, cap of 2: the two HIGH paragraphs win, mediums are dropped.
    notes = [
        _note(1, 'medium'),
        _note(2, 'high'),
        _note(3, 'medium'),
        _note(4, 'high'),
        _note(5, 'medium'),
    ]
    selected = select_revisions(notes, paragraph_cap=2)
    chosen_paragraphs = {n.paragraph for n in selected}
    assert chosen_paragraphs == {2, 4}


def test_paragraph_cap_limits_touched_paragraphs():
    notes = [_note(i, 'high') for i in range(1, 10)]
    selected = select_revisions(notes, paragraph_cap=DEFAULT_PARAGRAPH_CAP)
    touched = {n.paragraph for n in selected}
    assert len(touched) == DEFAULT_PARAGRAPH_CAP


def test_multiple_notes_same_paragraph_count_once_against_cap():
    # Two notes on paragraph 1 and one each on 2 and 3, cap of 2.
    # Paragraph 1 (with two notes) and paragraph 2 fit; paragraph 3 is dropped.
    notes = [
        _note(1, 'high', id='C-1a'),
        _note(1, 'high', id='C-1b'),
        _note(2, 'high', id='C-2'),
        _note(3, 'high', id='C-3'),
    ]
    selected = select_revisions(notes, paragraph_cap=2)
    touched = {n.paragraph for n in selected}
    assert touched == {1, 2}
    # both notes on paragraph 1 are folded in
    assert sum(1 for n in selected if n.paragraph == 1) == 2


def test_structural_notes_do_not_consume_cap():
    # A paragraph-0 structural note plus cap-worth of paragraph notes:
    # the structural note is selected on top, not instead of, a paragraph fix.
    notes = [
        _note(0, 'high', layer=LAYER_FIDELITY, id='C-struct'),
        _note(1, 'high', id='C-1'),
        _note(2, 'high', id='C-2'),
    ]
    selected = select_revisions(notes, paragraph_cap=2)
    ids = {n.id for n in selected}
    assert 'C-struct' in ids
    assert {'C-1', 'C-2'} <= ids


def test_selection_is_deterministic():
    notes = [
        _note(3, 'medium'),
        _note(1, 'high'),
        _note(2, 'medium'),
        _note(5, 'high'),
        _note(4, 'low'),
    ]
    first = [n.id for n in select_revisions(notes, paragraph_cap=3)]
    second = [n.id for n in select_revisions(notes, paragraph_cap=3)]
    assert first == second


def test_selected_returned_in_document_order():
    notes = [
        _note(5, 'high'),
        _note(1, 'high'),
        _note(3, 'high'),
    ]
    selected = select_revisions(notes, paragraph_cap=4)
    paragraphs = [n.paragraph for n in selected]
    assert paragraphs == sorted(paragraphs)


def test_empty_notes_empty_plan():
    assert select_revisions([]) == []
