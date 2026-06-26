"""LORD Editorial — constitution, playbook, and critical listening loaders."""
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def load_constitution() -> str:
    return (_DIR / 'constitution.md').read_text(encoding='utf-8')


@lru_cache(maxsize=None)
def load_playbook() -> str:
    return (_DIR / 'playbook.md').read_text(encoding='utf-8')


@lru_cache(maxsize=None)
def load_listening_framework() -> str:
    return (_DIR / 'listening_framework.md').read_text(encoding='utf-8')


@lru_cache(maxsize=None)
def load_music_knowledge() -> str:
    return (_DIR / 'music_knowledge.md').read_text(encoding='utf-8')


@lru_cache(maxsize=None)
def load_criticism_framework() -> str:
    return (_DIR / 'criticism_framework.md').read_text(encoding='utf-8')


@lru_cache(maxsize=None)
def load_editorial() -> str:
    """Constitution + playbook — injected into all writer system prompts."""
    return (
        "LORD EDITORIAL CONSTITUTION\n\n"
        + load_constitution()
        + "\n\n---\n\n"
        + "LORD EDITORIAL PLAYBOOK\n\n"
        + load_playbook()
    )


@lru_cache(maxsize=None)
def load_criticism_context() -> str:
    """Full critical context — injected into review and feature system prompts only."""
    return (
        load_editorial()
        + "\n\n---\n\n"
        + "LORD CRITICAL LISTENING FRAMEWORK\n\n"
        + load_listening_framework()
        + "\n\n---\n\n"
        + "LORD MUSIC KNOWLEDGE REFERENCE\n\n"
        + load_music_knowledge()
        + "\n\n---\n\n"
        + "LORD CRITICISM FRAMEWORK\n\n"
        + load_criticism_framework()
    )
