"""Groves Engine — paragraph addressability for the Revision Engine.

Targeted rewrites require that the editor can point at a specific section and
the rewriter can replace exactly that section, leaving the rest of the prose
untouched. The natural unit is the HTML paragraph the writers emit (<p>…</p>).

These helpers are deliberately small and pure so they can be unit-tested
without any model calls. They preserve any non-paragraph content (whitespace,
stray markup) between blocks by rebuilding from the original string rather than
naively re-joining a list.
"""
from __future__ import annotations
import re

_P_BLOCK = re.compile(r'<p\b[^>]*>.*?</p>', re.DOTALL | re.IGNORECASE)


def split_paragraphs(body: str) -> list[str]:
    """Return the <p>…</p> blocks of a body, in order.

    If the body contains no paragraph blocks (unexpected, but possible for a
    malformed draft), the whole body is returned as a single block so the
    Revision Engine degrades to whole-draft addressing rather than crashing.
    """
    blocks = _P_BLOCK.findall(body or '')
    if not blocks:
        stripped = (body or '').strip()
        return [stripped] if stripped else []
    return blocks


def apply_revisions(body: str, revised: dict) -> str:
    """Replace targeted paragraphs in `body` with their rewritten HTML.

    `revised` maps 1-based paragraph index → new HTML block. Indices not present
    are left exactly as they were. Content between paragraph blocks is preserved
    because replacement is done in place on the original string, not by re-join.

    Indices outside the valid range are ignored (defensive — a model could
    hallucinate a paragraph 99 that does not exist).
    """
    if not revised:
        return body

    counter = {'i': 0}

    def _replace(match: re.Match) -> str:
        counter['i'] += 1
        idx = counter['i']  # 1-based
        return revised.get(idx, match.group(0))

    new_body, n = _P_BLOCK.subn(_replace, body or '')
    if n == 0:
        # No paragraph blocks matched — body was treated as a single block by
        # split_paragraphs. Honour a rewrite of paragraph 1 if provided.
        if 1 in revised:
            return revised[1]
        return body
    return new_body
