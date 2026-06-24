"""Shared JSON helpers for LORD writer modules."""
import json
import re


def strip_fences(text: str) -> str:
    """Remove markdown code fences Claude may have wrapped the JSON in.
    Handles preamble prose appearing before the opening fence.
    """
    text = text.strip()
    # Extract content between fences regardless of leading prose
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    # No fences at all — find first { and last } and extract that range
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def _fix_string_newlines(text: str) -> str:
    """
    Walk the JSON character-by-character and replace bare newlines inside
    string values with the two-character sequence \\n.

    Claude occasionally writes a 1500-word body field that spans multiple
    real lines inside the JSON string. json.loads rejects those because JSON
    strings must not contain unescaped control characters (RFC 7159 §7).
    """
    result = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif ch == '\n' and in_string:
            result.append('\\n')
        elif ch == '\r' and in_string:
            pass  # strip bare CR
        else:
            result.append(ch)
    return ''.join(result)


def parse_writer_json(raw: str) -> dict:
    """
    Strip fences, fix bare newlines in strings, then parse.
    Raises ValueError (not JSONDecodeError) on failure so callers get a clean message.
    """
    cleaned = strip_fences(raw)
    fixed = _fix_string_newlines(cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Writer returned invalid JSON: {exc}") from exc
