"""Groves Engine — shared stage LLM call helper.

Every reasoning stage calls the model through call_stage(). Centralising this
gives us three things uniformly across the pipeline:

1. PROMPT CACHING.
   The editorial context (~13K tokens) is identical across every stage and
   every article. It is sent as a separate, cache-controlled system block so
   the API caches it once and reads it cheaply on subsequent stages. With a
   four-call pipeline this turns 4× full-context billing into 1× write + 3×
   cache-read — roughly a 90% reduction on the context portion. The 5-minute
   cache TTL comfortably covers one article's pipeline.

2. PER-STAGE TEMPERATURE.
   Determinism belongs in some stages and exploration in others:
     observation → low  (faithful, repeatable; facts should not vary)
     thesis      → high (genuine exploration; 5 divergent candidates)
     outline     → low  (faithful structuring of an already-decided thesis)
   This is the concrete answer to "deterministic vs controlled exploration":
   variation is scoped to the stage where it adds value, not global.

3. ONE MESSAGE STRUCTURE.
   Stage-specific instructions live in a second, uncached system block.
"""
from __future__ import annotations
import logging

import engine_telemetry

log = logging.getLogger('engine.llm')

# Per-stage temperature. Exploration is concentrated in the thesis stage;
# observation and outline are kept faithful and close to repeatable.
STAGE_TEMPERATURE = {
    'observation': 0.4,
    'thesis':      0.9,
    'outline':     0.4,
}


def call_stage(
    client,
    model: str,
    editorial_context: str,
    stage_instructions: str,
    user_prompt: str,
    *,
    stage: str,
    max_tokens: int,
) -> str:
    """Run one reasoning stage and return the raw text response.

    The editorial_context is sent as a cache-controlled system block; the
    stage_instructions are a second, uncached block. Temperature is selected
    from STAGE_TEMPERATURE by stage name.
    """
    temperature = STAGE_TEMPERATURE.get(stage, 0.7)

    system_blocks = [
        {
            'type': 'text',
            'text': editorial_context,
            'cache_control': {'type': 'ephemeral'},
        },
        {
            'type': 'text',
            'text': stage_instructions,
        },
    ]

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_blocks,
        messages=[{'role': 'user', 'content': user_prompt}],
    )

    _log_cache_usage(stage, message)
    _warn_if_truncated(stage, message, max_tokens)
    engine_telemetry.record(stage, message, max_tokens)
    return message.content[0].text


def _log_cache_usage(stage: str, message) -> None:
    """Surface cache hit/write counts so the savings are visible in CI logs."""
    try:
        u = message.usage
        cache_read = getattr(u, 'cache_read_input_tokens', 0) or 0
        cache_write = getattr(u, 'cache_creation_input_tokens', 0) or 0
        log.info(
            "Stage '%s': input=%d output=%d cache_read=%d cache_write=%d stop=%s",
            stage, u.input_tokens, u.output_tokens, cache_read, cache_write,
            getattr(message, 'stop_reason', None),
        )
    except Exception:
        pass


def _warn_if_truncated(stage: str, message, max_tokens: int) -> None:
    """A 'max_tokens' stop means the response was cut mid-stream — the JSON is
    therefore incomplete and WILL fail to parse. Name that cause loudly here so
    it is never mistaken for a malformed-quote bug. Fix by raising max_tokens for
    the stage or shortening what it is asked to produce.
    """
    if getattr(message, 'stop_reason', None) == 'max_tokens':
        log.warning(
            "Stage '%s': response hit max_tokens=%d and was TRUNCATED — the JSON "
            "is incomplete and will not parse. Raise max_tokens or reduce the ask.",
            stage, max_tokens,
        )
