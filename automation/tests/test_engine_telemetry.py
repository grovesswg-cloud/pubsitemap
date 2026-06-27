"""Tests for per-stage token telemetry."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

import engine_telemetry


class _Usage:
    def __init__(self, input_tokens, output_tokens, cache_read=0, cache_write=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read
        self.cache_creation_input_tokens = cache_write


class _Message:
    def __init__(self, stop_reason, usage):
        self.stop_reason = stop_reason
        self.usage = usage


@pytest.fixture(autouse=True)
def _clean_telemetry():
    engine_telemetry.reset()
    yield
    engine_telemetry.reset()


def test_record_captures_usage_and_stop_reason():
    rec = engine_telemetry.record('outline', _Message('end_turn', _Usage(1200, 3600, 13000, 0)), 4096)
    assert rec['stage'] == 'outline'
    assert rec['input_tokens'] == 1200
    assert rec['output_tokens'] == 3600
    assert rec['cache_read_tokens'] == 13000
    assert rec['max_tokens'] == 4096
    assert rec['stop_reason'] == 'end_turn'
    assert rec['truncated'] is False


def test_truncated_flag_set_on_max_tokens():
    rec = engine_telemetry.record('outline', _Message('max_tokens', _Usage(1200, 2500)), 2500)
    assert rec['truncated'] is True


def test_reset_clears_records():
    engine_telemetry.record('thesis', _Message('end_turn', _Usage(1, 2)), 100)
    assert engine_telemetry.snapshot()
    engine_telemetry.reset()
    assert engine_telemetry.snapshot() == []


def test_snapshot_is_a_copy():
    engine_telemetry.record('thesis', _Message('end_turn', _Usage(1, 2)), 100)
    snap = engine_telemetry.snapshot()
    snap.append({'stage': 'injected'})
    assert len(engine_telemetry.snapshot()) == 1


def test_latest_overall_and_by_stage():
    engine_telemetry.record('observation', _Message('end_turn', _Usage(1, 2)), 2000)
    engine_telemetry.record('thesis', _Message('end_turn', _Usage(3, 4)), 2500)
    engine_telemetry.record('observation', _Message('max_tokens', _Usage(5, 6)), 2000)

    assert engine_telemetry.latest()['stage'] == 'observation'
    assert engine_telemetry.latest()['output_tokens'] == 6
    assert engine_telemetry.latest('thesis')['output_tokens'] == 4
    # Most recent observation, not the first one.
    assert engine_telemetry.latest('observation')['truncated'] is True


def test_latest_missing_stage_returns_none():
    assert engine_telemetry.latest('rewrite') is None


def test_record_tolerates_missing_usage():
    # A message without usage should not raise.
    class Bare:
        stop_reason = 'end_turn'
    rec = engine_telemetry.record('critique', Bare(), 2000)
    assert rec['input_tokens'] is None
    assert rec['output_tokens'] is None
    assert rec['truncated'] is False
