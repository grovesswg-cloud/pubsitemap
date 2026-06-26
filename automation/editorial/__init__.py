"""LORD Editorial — constitution and playbook loader."""
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
def load_editorial() -> str:
    """Combined editorial context for injection into writer system prompts."""
    return (
        "LORD EDITORIAL CONSTITUTION\n\n"
        + load_constitution()
        + "\n\n---\n\n"
        + "LORD EDITORIAL PLAYBOOK\n\n"
        + load_playbook()
    )
