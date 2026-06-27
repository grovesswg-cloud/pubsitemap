"""Tests for paragraph addressability (split + targeted apply)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from revision.paragraphs import split_paragraphs, apply_revisions


_BODY = (
    '<p>First paragraph opens on the record.</p>'
    '<p>Second paragraph develops the argument.</p>'
    '<p>Third paragraph addresses the counterargument.</p>'
)


def test_split_basic():
    paras = split_paragraphs(_BODY)
    assert len(paras) == 3
    assert paras[0] == '<p>First paragraph opens on the record.</p>'
    assert paras[2].startswith('<p>Third')


def test_split_preserves_inline_markup():
    body = '<p>A line with <em>emphasis</em> inside.</p><p>Plain second.</p>'
    paras = split_paragraphs(body)
    assert len(paras) == 2
    assert '<em>emphasis</em>' in paras[0]


def test_split_handles_attributes_and_newlines():
    body = '<p class="lead">\n  Lead paragraph.\n</p>\n<p>Second.</p>'
    paras = split_paragraphs(body)
    assert len(paras) == 2
    assert 'Lead paragraph' in paras[0]


def test_split_no_paragraphs_returns_single_block():
    paras = split_paragraphs('Just some text with no tags.')
    assert paras == ['Just some text with no tags.']


def test_split_empty():
    assert split_paragraphs('') == []
    assert split_paragraphs('   ') == []


def test_apply_replaces_only_targeted():
    revised = {2: '<p>Rewritten second paragraph.</p>'}
    out = apply_revisions(_BODY, revised)
    assert '<p>Rewritten second paragraph.</p>' in out
    assert '<p>First paragraph opens on the record.</p>' in out
    assert '<p>Third paragraph addresses the counterargument.</p>' in out
    assert 'Second paragraph develops' not in out


def test_apply_multiple():
    revised = {
        1: '<p>New first.</p>',
        3: '<p>New third.</p>',
    }
    out = apply_revisions(_BODY, revised)
    assert out == (
        '<p>New first.</p>'
        '<p>Second paragraph develops the argument.</p>'
        '<p>New third.</p>'
    )


def test_apply_empty_revision_is_noop():
    assert apply_revisions(_BODY, {}) == _BODY


def test_apply_ignores_out_of_range_index():
    # A hallucinated paragraph 99 must not corrupt the body.
    out = apply_revisions(_BODY, {99: '<p>nope</p>'})
    assert out == _BODY
    assert 'nope' not in out


def test_apply_roundtrip_count_stable():
    # Applying a rewrite must not change the number of paragraphs.
    revised = {2: '<p>Replacement two.</p>'}
    out = apply_revisions(_BODY, revised)
    assert len(split_paragraphs(out)) == 3
