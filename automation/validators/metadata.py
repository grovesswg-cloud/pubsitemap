"""LORD Quality Pipeline — Metadata Validator (PR-001)
Fast, zero-cost gate: validates required fields before any AI or image calls.
Returns {"result": "PASS"|"FAIL", "errors": [...], "warnings": [...]}.
"""
import re
from datetime import datetime

VALID_TYPES = {'bulletin', 'review', 'feature', 'sermon', 'archive', 'interview', 'culture'}
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def validate_metadata(article_data: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    # title
    title = (article_data.get('title') or '').strip()
    if not title:
        errors.append("Missing required field: title")
    elif len(title) < 10:
        errors.append(f"Title too short ({len(title)} chars): '{title}'")
    elif len(title) > 200:
        warnings.append(f"Title very long ({len(title)} chars) — may truncate in previews")

    # type
    article_type = (article_data.get('type') or '').strip()
    if not article_type:
        errors.append("Missing required field: type")
    elif article_type not in VALID_TYPES:
        errors.append(
            f"Invalid type '{article_type}' — must be one of: {', '.join(sorted(VALID_TYPES))}"
        )

    # date
    date_str = (article_data.get('date') or '').strip()
    if not date_str:
        errors.append("Missing required field: date")
    elif not _DATE_RE.match(date_str):
        errors.append(f"Invalid date format '{date_str}' — expected YYYY-MM-DD")
    else:
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            errors.append(f"Invalid date value: '{date_str}'")

    # body
    body = (article_data.get('body') or '').strip()
    if not body:
        errors.append("Missing required field: body")
    elif len(body) < 200:
        errors.append(f"Body too short ({len(body)} chars) — minimum 200 characters")

    # tags
    tags = article_data.get('tags')
    if not isinstance(tags, list):
        errors.append("Field 'tags' must be a list")
    elif not tags:
        errors.append("Missing required field: tags — must include at least one artist/topic tag")
    elif not (tags[0] or '').strip():
        errors.append("First tag (artist name) must not be empty")

    # deck (recommended)
    deck = (article_data.get('deck') or '').strip()
    if not deck:
        warnings.append("Missing recommended field: deck (article subtitle)")
    elif len(deck) > 300:
        warnings.append(f"Deck very long ({len(deck)} chars) — consider shortening")

    # imageQuery (recommended)
    if not (article_data.get('imageQuery') or article_data.get('imageQueries')):
        warnings.append("Missing recommended field: imageQuery — image sourcing may fail")

    return {
        "result": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": warnings,
    }
