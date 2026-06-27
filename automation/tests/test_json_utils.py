"""Tests for strip_fences — and specifically that it distinguishes a truncated
response from a malformed one.

The GNX calibration incident: a response was cut off at max_tokens mid-string in
a late field, so it had an opening ```json fence but no closing fence. The old
strip_fences rewound to the last '}' (an early evidence object's brace), silently
discarding the truncated tail and relocating the parse error to the middle of the
document — making a truncation look like a structural bug. These tests pin the
honest behaviour.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from json_utils import strip_fences, parse_writer_json, WriterJSONError


def test_both_fences_extracts_between():
    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_no_fences_extracts_outermost_braces():
    # Trailing prose after complete JSON, no fences.
    assert strip_fences('{"a": 1}\nThanks!') == '{"a": 1}'


def test_opening_fence_complete_json_no_close():
    # Complete JSON but the closing fence is missing — still parses.
    assert parse_writer_json('```json\n{"a": 1}') == {'a': 1}


def test_opening_fence_truncated_keeps_tail():
    # Truncation fingerprint: opening fence, no close, content ends mid-string in
    # a late field. strip_fences must NOT rewind to the earlier '}' — it must keep
    # the truncated tail so the parser fails at the true end.
    raw = (
        '```json\n'
        '{\n'
        '  "evidence": [\n'
        '    {"observation": "o1", "confidence": "high"},\n'
        '    {"observation": "o2", "confidence": "low"}\n'
        '  ],\n'
        '  "editor_notes": [\n'
        '    "note cut off right here and gesture at where it'
    )
    stripped = strip_fences(raw)
    assert 'gesture at where it' in stripped          # tail preserved
    assert stripped.rstrip()[-1] != '}'               # not rewound to a brace


def test_truncation_reports_unterminated_not_delimiter():
    # The honest error for a truncation is an unterminated string at the true end,
    # NOT "Expecting ',' delimiter" relocated to an earlier object.
    raw = (
        '```json\n'
        '{"evidence": [{"x": "1"}, {"x": "2"}],\n'
        ' "editor_notes": ["complete note", "truncated note that just stops here'
    )
    try:
        parse_writer_json(raw)
        assert False, 'expected a parse failure'
    except WriterJSONError as exc:
        msg = str(exc.decode_error)
        assert 'Unterminated string' in msg
        assert "Expecting ',' delimiter" not in msg
