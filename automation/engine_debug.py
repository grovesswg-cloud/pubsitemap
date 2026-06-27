"""Groves Engine — stage observability.

Every reasoning and revision stage asks the model for structured JSON. When the
model returns something that is not valid JSON, the stage fails closed (correct —
we never publish an article built on a broken reasoning step). But a stack trace
with a 400-character preview is not enough to understand WHY the JSON was
malformed: the break is often thousands of characters into the response.

This module is a permanent part of the Groves Engine. The principle it encodes:
failures produce evidence, not mysteries. If a reasoning or revision stage fails
in production six months from now, the system must leave behind enough to
understand exactly what happened without reproducing the failure.

Each failure writes a self-contained evidence folder:

    <evidence-dir>/<timestamp>--<stage>/
        stage.txt          the stage name
        error.txt          the parse error + the snippet around the break point
        prompt.txt         the exact user prompt sent to the model
        raw_response.txt   the model's raw output, untouched
        repaired.txt       the output after fence-stripping + quote/newline repair
                           — i.e. the exact bytes json.loads() choked on
        context.json       article subject, model, article_type (when provided)

Where the folder lands is controlled by the ENGINE_DEBUG_DIR environment
variable:
    unset            -> <repo-root>/evidence/failures  (gitignored; survives deploys)
    a path           -> that directory
    off|false|0|none -> disabled (nothing written)

The calibration tool (generate.py) points ENGINE_DEBUG_DIR at each run's own
failures/ subfolder, so a failed generation leaves its evidence beside its other
artifacts. The scheduler uses the default (evidence/failures/) so production
failures land in the same gitignored operational-artifact tree as other evidence.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from json_utils import parse_writer_json, WriterJSONError

_ROOT_DIR = Path(__file__).parent.parent
_DISABLED = ('off', 'false', '0', 'none')


def _resolve_debug_dir() -> Path | None:
    """Resolve the debug directory from ENGINE_DEBUG_DIR, or None if disabled."""
    raw = os.getenv('ENGINE_DEBUG_DIR', '').strip()
    if raw.lower() in _DISABLED:
        return None
    if raw:
        return Path(raw)
    return _ROOT_DIR / 'evidence' / 'failures'


def _error_context(repaired: str | None, decode_error: json.JSONDecodeError | None) -> str:
    """Human-readable view of the parse break: the error and the text around it."""
    if not isinstance(decode_error, json.JSONDecodeError):
        return ''
    lines = [
        str(decode_error),
        f'position: char {decode_error.pos}, line {decode_error.lineno}, column {decode_error.colno}',
    ]
    if repaired is not None:
        pos = decode_error.pos
        start = max(0, pos - 120)
        end = min(len(repaired), pos + 120)
        window = repaired[start:end]
        lines += [
            '',
            f'--- repaired[{start}:{end}] — the break is at char {pos} (marked >><<) ---',
            repaired[start:pos] + '>><<' + repaired[pos:end]
            if 0 <= pos <= len(repaired) else window,
        ]
    return '\n'.join(lines) + '\n'


def dump_stage_failure(
    stage: str,
    prompt: str,
    raw: str,
    error: Exception,
    *,
    repaired: str | None = None,
    decode_error: json.JSONDecodeError | None = None,
    extra: dict | None = None,
) -> Path | None:
    """Write the full evidence for a stage failure. Returns the folder, or None
    if debugging is disabled (ENGINE_DEBUG_DIR=off) or writing fails.
    """
    base = _resolve_debug_dir()
    if base is None:
        return None
    try:
        ts = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d-%H%M%S')
        safe_stage = re.sub(r'[^a-z0-9_-]+', '-', stage.lower()) or 'stage'
        folder = base / f'{ts}--{safe_stage}'
        folder.mkdir(parents=True, exist_ok=True)

        (folder / 'stage.txt').write_text(stage + '\n', encoding='utf-8')
        (folder / 'prompt.txt').write_text(prompt or '', encoding='utf-8')
        (folder / 'raw_response.txt').write_text(raw or '', encoding='utf-8')
        if repaired is not None:
            (folder / 'repaired.txt').write_text(repaired, encoding='utf-8')

        error_text = _error_context(repaired, decode_error) or f'{type(error).__name__}: {error}\n'
        (folder / 'error.txt').write_text(error_text, encoding='utf-8')

        if extra:
            try:
                (folder / 'context.json').write_text(
                    json.dumps(extra, indent=2, ensure_ascii=False, default=str),
                    encoding='utf-8')
            except Exception:
                pass
        return folder
    except Exception:
        # Observability must never mask the real failure. If we cannot write the
        # evidence, swallow it and let the original error propagate unchanged.
        return None


def parse_stage_json(
    raw: str,
    *,
    stage: str,
    prompt: str,
    log: logging.Logger | None = None,
    extra: dict | None = None,
) -> dict:
    """Parse a stage's JSON response, capturing full evidence on failure.

    On a parse failure this writes the raw response, the repaired text, the
    prompt, and the exact break position to the debug directory, then re-raises
    a ValueError whose message points at the evidence folder. Fail-closed
    behaviour is preserved — the article still stops.
    """
    try:
        return parse_writer_json(raw)
    except WriterJSONError as exc:
        folder = dump_stage_failure(
            stage, prompt, raw, exc,
            repaired=exc.repaired, decode_error=exc.decode_error, extra=extra,
        )
        if log is not None:
            if folder is not None:
                log.error("%s stage: JSON parse failed (%s). Evidence saved to %s",
                          stage, exc.decode_error, folder)
            else:
                log.error("%s stage: JSON parse failed (%s)", stage, exc.decode_error)
        if folder is not None:
            raise ValueError(f"{exc} — evidence saved to {folder}") from exc
        raise
