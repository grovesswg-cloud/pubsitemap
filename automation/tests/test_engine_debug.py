"""Tests for engine observability — capturing stage JSON failures.

These pin two things:

1. json_utils now raises a WriterJSONError carrying the evidence (raw response,
   the repaired text actually handed to json.loads, and the JSONDecodeError with
   its exact break position).

2. engine_debug.parse_stage_json writes that evidence to ENGINE_DEBUG_DIR and
   re-raises (fail-closed preserved), and is disabled by ENGINE_DEBUG_DIR=off.

They also DOCUMENT the failure modes reproduced while diagnosing the calibration
sprint's first engine bug — so we never re-confuse them:

  • A missing structural comma between array objects -> "Expecting ',' delimiter".
    The repair pass does NOT touch structural commas, so this surfaces unchanged.
  • A truncation (stop_reason=max_tokens) was the ACTUAL cause of the GNX failure.
    It originally read as "Expecting ',' delimiter" near an early object only
    because strip_fences rewound to the last '}' (see test_json_utils.py). With
    that fixed, truncation reads as "Unterminated string" at the true end, and the
    evidence folder stamps stop_reason=max_tokens. Truncation and malformed-JSON
    are now distinct incidents.
  • Unescaped inner quotes are handled by the repair pass and do NOT raise; in
    pathological cases they corrupt silently rather than erroring.
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from json_utils import parse_writer_json, repair_json, WriterJSONError
import engine_debug
import engine_telemetry


@pytest.fixture(autouse=True)
def _clean_telemetry():
    # parse_stage_json reads engine_telemetry.latest() to stamp the evidence;
    # isolate each test from records left by another.
    engine_telemetry.reset()
    yield
    engine_telemetry.reset()


# ─── json_utils enrichment ──────────────────────────────────────────────────

def test_valid_json_parses():
    assert parse_writer_json('{"a": 1, "b": "two"}') == {'a': 1, 'b': 'two'}


def test_repair_json_exposes_parser_input():
    # repair_json must equal exactly what parse_writer_json feeds json.loads.
    raw = '```json\n{"body": "line one\nline two"}\n```'
    repaired = repair_json(raw)
    assert json.loads(repaired) == {'body': 'line one\nline two'}


def test_writer_json_error_carries_evidence():
    raw = '{"a": "unterminated'
    with pytest.raises(WriterJSONError) as ei:
        parse_writer_json(raw)
    exc = ei.value
    assert isinstance(exc, ValueError)          # backward compatible
    assert exc.raw == raw
    assert isinstance(exc.repaired, str)
    assert isinstance(exc.decode_error, json.JSONDecodeError)


def test_missing_structural_comma_reproduces_reported_error():
    # The exact failure class from the calibration sprint: two objects in an
    # array with no comma between them. The repair pass leaves it untouched.
    raw = (
        '{"evidence": [\n'
        '  {"observation": "a", "confidence": "high"}\n'
        '  {"observation": "b", "confidence": "low"}\n'
        ']}'
    )
    with pytest.raises(WriterJSONError) as ei:
        parse_writer_json(raw)
    assert "Expecting ',' delimiter" in str(ei.value.decode_error)


def test_truncation_is_a_distinct_error():
    # A cut-off response is "Unterminated string", NOT "Expecting ',' delimiter".
    raw = '{"outline": ["Paragraph one does the work'
    with pytest.raises(WriterJSONError) as ei:
        parse_writer_json(raw)
    msg = str(ei.value.decode_error)
    assert 'Unterminated string' in msg
    assert "Expecting ',' delimiter" not in msg


# ─── engine_debug.parse_stage_json ──────────────────────────────────────────

def test_parse_stage_json_passthrough_on_valid(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_DEBUG_DIR', str(tmp_path))
    data = engine_debug.parse_stage_json(
        '{"ok": true}', stage='outline', prompt='PROMPT')
    assert data == {'ok': True}
    # No failure -> nothing written.
    assert not any(tmp_path.iterdir())


def test_parse_stage_json_dumps_evidence_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_DEBUG_DIR', str(tmp_path))
    raw = (
        '{"evidence": [\n'
        '  {"observation": "a"}\n'
        '  {"observation": "b"}\n'
        ']}'
    )
    with pytest.raises(ValueError) as ei:
        engine_debug.parse_stage_json(raw, stage='outline', prompt='THE PROMPT')

    # The re-raised error points at the evidence folder.
    assert 'evidence saved to' in str(ei.value)

    folders = list(tmp_path.iterdir())
    assert len(folders) == 1
    folder = folders[0]
    assert folder.name.endswith('--outline')

    assert (folder / 'raw_response.txt').read_text() == raw
    assert (folder / 'prompt.txt').read_text() == 'THE PROMPT'
    assert (folder / 'stage.txt').read_text().strip() == 'outline'
    # repaired.txt is exactly what json.loads choked on.
    assert (folder / 'repaired.txt').exists()
    # error.txt names the parse error and the break position.
    error_text = (folder / 'error.txt').read_text()
    assert "Expecting ',' delimiter" in error_text
    assert 'char ' in error_text


def test_parse_stage_json_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_DEBUG_DIR', 'off')
    with pytest.raises(ValueError):
        engine_debug.parse_stage_json('{"a":', stage='thesis', prompt='p')
    # Nothing written anywhere under tmp_path (the default dir is not used).
    assert not any(tmp_path.iterdir())


def test_parse_stage_json_includes_extra_context(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_DEBUG_DIR', str(tmp_path))
    with pytest.raises(ValueError):
        engine_debug.parse_stage_json(
            '{"a":', stage='critique', prompt='p',
            extra={'subject': 'Massive Attack — Mezzanine'})
    folder = next(tmp_path.iterdir())
    ctx = json.loads((folder / 'context.json').read_text())
    assert ctx['subject'] == 'Massive Attack — Mezzanine'


# ─── telemetry stamped into the evidence ────────────────────────────────────

class _Usage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class _Message:
    def __init__(self, stop_reason, usage):
        self.stop_reason = stop_reason
        self.usage = usage


def test_evidence_stamps_stop_reason_from_telemetry(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_DEBUG_DIR', str(tmp_path))
    # Simulate the failing call's telemetry having been recorded by call_stage.
    engine_telemetry.record('outline', _Message('end_turn', _Usage(1200, 800)), 4096)
    with pytest.raises(ValueError):
        engine_debug.parse_stage_json('{"a":', stage='outline', prompt='p')
    ctx = json.loads((next(tmp_path.iterdir()) / 'context.json').read_text())
    assert ctx['stop_reason'] == 'end_turn'
    assert ctx['max_tokens'] == 4096
    assert ctx['truncated'] is False


def test_truncated_call_gets_banner_and_flag(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_DEBUG_DIR', str(tmp_path))
    engine_telemetry.record('outline', _Message('max_tokens', _Usage(1200, 4096)), 4096)
    with pytest.raises(ValueError):
        engine_debug.parse_stage_json('{"evidence": [{"x": 1}', stage='outline', prompt='p')
    folder = next(tmp_path.iterdir())
    ctx = json.loads((folder / 'context.json').read_text())
    assert ctx['truncated'] is True
    assert ctx['stop_reason'] == 'max_tokens'
    # error.txt leads with the TRUNCATED banner so it is not mistaken for a bug.
    assert (folder / 'error.txt').read_text().startswith('TRUNCATED')
