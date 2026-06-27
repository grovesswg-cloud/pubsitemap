"""Groves Engine — per-stage token telemetry.

Records token usage and stop_reason for every reasoning and revision stage call,
success or failure. Two purposes, both about replacing intuition with data:

  1. Sizing budgets. After N calibration runs you can see that the outline stage
     averages ~3600 output tokens while observation averages ~1200, and set each
     stage's max_tokens from measured behaviour rather than a guess. (The GNX
     truncation happened because outline's 2500-token budget was set blind.)

  2. Naming truncation. A stop_reason of 'max_tokens' means the response was cut
     off mid-stream — the single most useful fact when a stage's JSON fails to
     parse. The failure-evidence layer (engine_debug) reads the latest record to
     stamp stop_reason directly into the evidence folder.

The collector is process-global and append-only. A caller resets() at the start
of a run and snapshot()s at the end (the calibration tool writes telemetry.json).
The engine itself stays publication-agnostic and unaware of telemetry —
call_stage records; the caller decides what to persist.
"""
from __future__ import annotations

_records: list[dict] = []


def record(stage: str, message, max_tokens: int) -> dict:
    """Capture one stage call's usage from an Anthropic message. Returns the
    record (also appended to the process-global collector)."""
    usage = getattr(message, 'usage', None)
    stop_reason = getattr(message, 'stop_reason', None)
    rec = {
        'stage': stage,
        'input_tokens': getattr(usage, 'input_tokens', None),
        'output_tokens': getattr(usage, 'output_tokens', None),
        'cache_read_tokens': getattr(usage, 'cache_read_input_tokens', 0) or 0,
        'cache_write_tokens': getattr(usage, 'cache_creation_input_tokens', 0) or 0,
        'max_tokens': max_tokens,
        'stop_reason': stop_reason,
        'truncated': stop_reason == 'max_tokens',
    }
    _records.append(rec)
    return rec


def reset() -> None:
    """Clear the collector. Called at the start of a run."""
    _records.clear()


def snapshot() -> list[dict]:
    """Return a copy of all records collected since the last reset()."""
    return list(_records)


def latest(stage: str | None = None) -> dict | None:
    """Most recent record overall, or the most recent for a given stage."""
    for rec in reversed(_records):
        if stage is None or rec['stage'] == stage:
            return rec
    return None
