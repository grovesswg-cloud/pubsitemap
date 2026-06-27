"""Groves Engine — Revision Engine stage LLM helper.

This mirrors reasoning/llm.py rather than importing from it. The two are kept
decoupled on purpose: the reasoning and revision engines are separate cognitive
profiles, and coupling them through a shared helper now — with only two
consumers and different temperature/caching policies — would couple their stage
vocabularies for no real gain. When a third profile appears (e.g. an
investigative pipeline), the genuinely shared shape will be obvious and the
abstraction can be extracted then. Until then, this small mirror is the cheaper,
clearer choice.

What it shares with reasoning/llm.py by design:
  PROMPT CACHING — editorial_context (~13K tokens) is identical across stages
    and articles, sent as a cache-controlled system block. ~90% reduction on the
    context portion of a multi-call revision pass.
  PER-STAGE TEMPERATURE — critique is faithful diagnosis (low); rewrite needs
    craft but must stay bound to the brief (moderate).
"""
from __future__ import annotations
import logging

import engine_telemetry

log = logging.getLogger('revision.llm')

# Critique should be reliable and close to repeatable — the same draft should
# surface the same weaknesses. Rewrite needs craft latitude but stays bound to
# the brief, so it sits well below the thesis stage's exploratory 0.9.
STAGE_TEMPERATURE = {
    'critique': 0.3,
    'rewrite':  0.6,
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
    """Run one revision stage and return the raw text response.

    editorial_context is the cache-controlled system block; stage_instructions
    are a second, uncached block. Temperature is selected by stage name.
    """
    temperature = STAGE_TEMPERATURE.get(stage, 0.4)

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
            "Revision stage '%s': input=%d output=%d cache_read=%d cache_write=%d stop=%s",
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
            "Revision stage '%s': response hit max_tokens=%d and was TRUNCATED — "
            "the JSON is incomplete and will not parse. Raise max_tokens or reduce the ask.",
            stage, max_tokens,
        )
