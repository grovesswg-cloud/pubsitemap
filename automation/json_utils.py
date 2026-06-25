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


def _repair_json_strings(text: str) -> str:
    """
    Single-pass repair of two Claude JSON generation bugs:

    1. Bare newlines/tabs inside string values (illegal per RFC 7159 §7).
       Claude occasionally writes a multi-line body field whose real newlines
       are inside the JSON string rather than escaped as \\n.

    2. Unescaped double quotes inside string values.
       HTML body content sometimes includes <a href="url"> attributes or
       prose like He called it "revolutionary" without escaping the inner
       quotes. When we see a `"` while already inside a string, we look ahead
       for the next non-whitespace character: if it is a valid JSON delimiter
       (`:`, `,`, `}`, `]`) we treat the `"` as the closing delimiter;
       otherwise we escape it as `\"`.
    """
    result = []
    in_string = False
    escape_next = False
    i = 0

    while i < len(text):
        ch = text[i]

        if escape_next:
            result.append(ch)
            escape_next = False
            i += 1
            continue

        if ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
            i += 1
            continue

        if ch == '"':
            if not in_string:
                result.append(ch)
                in_string = True
            else:
                # Determine whether this " closes the string or is stray content.
                # Skip whitespace (including newlines) to find the next structural
                # character. If it's a valid JSON delimiter the " is closing;
                # otherwise it's an unescaped quote inside the value.
                j = i + 1
                while j < len(text) and text[j] in ' \t\n\r':
                    j += 1
                next_ch = text[j] if j < len(text) else ''
                if next_ch in (':', ',', '}', ']', ''):
                    result.append(ch)
                    in_string = False
                else:
                    result.append('\\"')
            i += 1
            continue

        if in_string:
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                pass  # strip bare CR
            elif ch == '\t':
                result.append('\\t')
            else:
                result.append(ch)
        else:
            result.append(ch)

        i += 1

    return ''.join(result)


def parse_writer_json(raw: str) -> dict:
    """
    Strip fences, repair bare newlines/tabs and unescaped quotes in strings, then parse.
    Raises ValueError (not JSONDecodeError) on failure so callers get a clean message.
    """
    cleaned = strip_fences(raw)
    fixed = _repair_json_strings(cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Writer returned invalid JSON: {exc}") from exc
