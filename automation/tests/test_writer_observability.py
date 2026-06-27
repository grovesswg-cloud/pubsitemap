"""Tests for writer-stage observability.

The writers (bulletin, feature, review, classic review) are the final stage of
the pipeline. Before writer_llm.write_article existed, a writer whose JSON failed
to parse logged only the first 500 characters of the raw response and re-raised —
the same 400-char-preview mystery the engine_debug evidence subsystem eliminated
for the reasoning and revision stages.

These pin the contract that closed that gap:

  • a writer parse failure writes a full evidence folder (raw response, repaired
    text, exact break position) and re-raises (fail-closed preserved);
  • the failing call's telemetry (stop_reason, token counts) is recorded and
    stamped into the evidence — so a truncation names itself instead of reading
    as a malformed-JSON bug (the lesson of the GNX/Kid A calibration incidents);
  • a valid response parses and writes nothing.
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

import engine_telemetry
import writer_llm


@pytest.fixture(autouse=True)
def _clean_telemetry():
    engine_telemetry.reset()
    yield
    engine_telemetry.reset()


# ─── fakes mirroring the Anthropic message shape write_article consumes ──────

class _Usage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class _Block:
    def __init__(self, text):
        self.text = text


class _Message:
    def __init__(self, text, stop_reason='end_turn', usage=None):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason
        self.usage = usage or _Usage(1000, 500)


class _FakeClient:
    """Returns a fixed message from messages.create, ignoring the request."""
    def __init__(self, message):
        self._message = message
        self.messages = self

    def create(self, **kwargs):
        return self._message


def _call(message, **overrides):
    kwargs = dict(
        client=_FakeClient(message),
        system='SYS', prompt='THE PROMPT', stage='writer-classic',
        subject='Radiohead — Kid A', article_type='classic-review',
        max_tokens=2500, log=None,
    )
    kwargs.update(overrides)
    import logging
    kwargs['log'] = logging.getLogger('test.writer')
    return writer_llm.write_article(**kwargs)


# ─── happy path ──────────────────────────────────────────────────────────────

def test_valid_response_parses_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_DEBUG_DIR', str(tmp_path))
    data = _call(_Message('{"title": "ok", "rating": "Eternal"}'))
    assert data == {'title': 'ok', 'rating': 'Eternal'}
    assert not any(tmp_path.iterdir())
    # The call was still recorded for budget telemetry.
    assert engine_telemetry.latest('writer-classic')['output_tokens'] == 500


# ─── failure produces evidence (the gap this closed) ─────────────────────────

def test_parse_failure_writes_full_evidence_and_reraises(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_DEBUG_DIR', str(tmp_path))
    raw = '{"title": "ok", "body": "<p>unterminated...'
    with pytest.raises(ValueError) as ei:
        _call(_Message(raw))
    assert 'evidence saved to' in str(ei.value)

    folder = next(tmp_path.iterdir())
    assert folder.name.endswith('--writer-classic')
    # The full raw response is preserved untouched — not a 500-char preview.
    assert (folder / 'raw_response.txt').read_text() == raw
    assert (folder / 'prompt.txt').read_text() == 'THE PROMPT'
    ctx = json.loads((folder / 'context.json').read_text())
    assert ctx['subject'] == 'Radiohead — Kid A'
    assert ctx['article_type'] == 'classic-review'
    assert ctx['stop_reason'] == 'end_turn'
    assert ctx['truncated'] is False


def test_truncated_writer_call_is_named_as_truncation(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_DEBUG_DIR', str(tmp_path))
    # A response cut off at max_tokens: the evidence must say so, not read as a bug.
    msg = _Message('{"title": "ok", "body": "<p>cut off here',
                   stop_reason='max_tokens', usage=_Usage(1000, 2500))
    with pytest.raises(ValueError):
        _call(msg)
    folder = next(tmp_path.iterdir())
    ctx = json.loads((folder / 'context.json').read_text())
    assert ctx['truncated'] is True
    assert ctx['stop_reason'] == 'max_tokens'
    assert (folder / 'error.txt').read_text().startswith('TRUNCATED')


def test_failure_evidence_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_DEBUG_DIR', 'off')
    with pytest.raises(ValueError):
        _call(_Message('{"title": "ok", "body": "<p>unterminated'))
    assert not any(tmp_path.iterdir())
