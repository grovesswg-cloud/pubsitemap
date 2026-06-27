"""Groves Engine — shared writer-stage LLM call.

The reasoning and revision stages all run through one helper (call_stage) so that
prompt caching, telemetry, and truncation handling are uniform. The writers —
bulletin, feature, review, classic review — are the final stage of the same
pipeline and deserve the same treatment. Before this helper existed each writer
called the model directly and, on a JSON parse failure, logged only the first
500 characters of the raw response: the exact 400-char-preview mystery that the
engine_debug evidence subsystem was built to eliminate everywhere else.

write_article() makes every writer a first-class citizen of that subsystem:

  1. TELEMETRY. Records the call's token usage and stop_reason via
     engine_telemetry, so a parse failure's evidence folder can name a
     truncation instead of leaving stop_reason a mystery.

  2. TRUNCATION WARNING. A 'max_tokens' stop means the JSON is incomplete and
     WILL fail to parse — surfaced loudly so it is never mistaken for a
     malformed-quote bug.

  3. FULL FAILURE EVIDENCE. The parse goes through engine_debug.parse_stage_json,
     which writes a self-contained evidence folder (raw response, repaired text,
     exact break position, stop_reason, token counts) and re-raises — fail-closed
     preserved. A writer failure is now debuggable to the same standard as the
     Editorial Intelligence Engine.

Writers keep their own system prompts, token budgets, and post-processing; only
the call-and-parse spine is shared here.
"""
from __future__ import annotations

import logging

from config import ANTHROPIC_MODEL
from engine_debug import parse_stage_json
import engine_telemetry


def write_article(
    *,
    client,
    system: str,
    prompt: str,
    stage: str,
    subject: str,
    article_type: str,
    max_tokens: int,
    log: logging.Logger,
) -> dict:
    """Run one writer call and parse its JSON, with full failure observability.

    Records telemetry BEFORE parsing (so the evidence is complete even when the
    parse fails), warns on truncation, and routes the parse through
    engine_debug.parse_stage_json. Returns the parsed article dict; raises a
    ValueError pointing at the evidence folder on failure (fail-closed).
    """
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{'role': 'user', 'content': prompt}],
    )

    engine_telemetry.record(stage, message, max_tokens)
    if getattr(message, 'stop_reason', None) == 'max_tokens':
        log.warning(
            "Writer stage '%s': response hit max_tokens=%d and was TRUNCATED — "
            "the JSON is incomplete and will not parse. Raise max_tokens.",
            stage, max_tokens,
        )

    raw = message.content[0].text
    return parse_stage_json(
        raw, stage=stage, prompt=prompt, log=log,
        extra={'subject': subject, 'article_type': article_type, 'model': ANTHROPIC_MODEL},
    )
