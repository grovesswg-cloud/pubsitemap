"""EditorialReviewProvider — Claude editorial analysis.

Evaluates each article as a senior magazine editor would:
  - clarity, structure, flow, pacing, coherence
  - transitions, repetition, readability
  - tone consistency against LORD's editorial voice
  - unsupported assertions, logical contradictions
  - excessive hedging, awkward phrasing
  - paragraph balance, conclusion strength

Issues are classified by severity:
  FAIL — prevents publication
  WARN — logged, allows publication
  INFO — minor observation, no impact

Swap this file to switch editorial review to a different AI provider.
All Claude/Anthropic-specific details are contained within this file.
"""
import json
import logging
import re

import anthropic

from providers.base import EditorialReviewProvider, EditorialReviewResult, EditorialIssue, EditorialStandard

log = logging.getLogger('lord.editorial_review')

_STRIP_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.MULTILINE)
_VALID_SEVERITY = {'INFO', 'WARN', 'FAIL'}
_VALID_RESULT   = {'PASS', 'FAIL', 'UNCERTAIN'}


def _strip_fences(text: str) -> str:
    return _STRIP_RE.sub('', text.strip()).strip()


class ClaudeEditorialProvider(EditorialReviewProvider):
    def __init__(self, api_key: str, model: str, editorial_standard: EditorialStandard):
        self._client   = anthropic.Anthropic(api_key=api_key)
        self._model    = model
        self._standard = editorial_standard

    def review(self, article_data: dict) -> EditorialReviewResult:
        title        = (article_data.get('title')      or '').strip()
        deck         = (article_data.get('deck')       or '').strip()
        body         = (article_data.get('body')       or '').strip()
        article_type = (article_data.get('type')       or '').strip()
        album        = (article_data.get('albumName')  or '').strip()
        tags         = article_data.get('tags') or []
        artist       = (article_data.get('artistName') or (tags[0] if tags else '')).strip()

        if not body:
            return EditorialReviewResult(
                result='FAIL',
                confidence=1.0,
                summary='Article body is empty — nothing to review.',
                issues=[EditorialIssue(
                    severity='FAIL',
                    category='structure',
                    description='Article body is empty.',
                )],
            )

        prompt = self._build_prompt(title, deck, body, article_type, artist, album)

        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{'role': 'user', 'content': prompt}],
            )
            return self._parse_response(message.content[0].text)
        except Exception as exc:
            log.warning("Claude editorial review error: %s", exc)
            return EditorialReviewResult(
                result='UNCERTAIN',
                confidence=0.0,
                summary=f"Editorial provider unavailable: {exc}",
            )

    def _build_prompt(
        self,
        title: str,
        deck: str,
        body: str,
        article_type: str,
        artist: str,
        album: str,
    ) -> str:
        album_line = f'\nAlbum: "{album}"' if album else ''
        pub        = self._standard.publication_name
        voice      = self._standard.voice_prompt
        return f"""\
{voice}

You are a senior editor at {pub}, an independent music publication with the editorial voice described above.

An article has been submitted for editorial review before publication.
Facts have already been verified by a separate system — do not question factual accuracy.
Your role is editorial judgment only.

Article Title: {title}
Type: {article_type}
Deck (subtitle): {deck}
Primary Artist: {artist}{album_line}

Article Body:
---
{body}
---

Review this article as a professional editor evaluating it for publication in LORD.

Evaluate these editorial dimensions:

STRUCTURE
- Does the lede earn the reader's attention?
- Is there a clear opening, developed middle, and purposeful close?
- Does the piece end with authority, or does it trail off?

FLOW AND PACING
- Does the piece move well? Are there sections that drag or feel rushed?
- Do paragraphs connect logically? Are transitions present and earned?
- Are paragraphs balanced, or does one section dominate without purpose?

VOICE AND TONE
- Does the piece maintain LORD's voice throughout?
- Authoritative but not arrogant. Literary but not inaccessible. Critical but not cruel.
- Does the piece slip into hype ("masterpiece", "you need to hear this"), vague praise, or apology writing?
- Does it assert opinion as fact without editorial grounding?

CLARITY AND PRECISION
- Is each sentence clear? Does the reader need to re-read to understand?
- Is the piece weakened by excessive hedging ("might", "could be argued", "some would say")?
- Are there logical contradictions that undermine the argument?
- Are key points repeated without purpose?
- Is there filler that adds length but not meaning?

Classify each issue you find by severity:
- FAIL: Fundamental editorial problem that prevents publication.
  Examples: lede so weak the reader has no reason to continue; no discernible structure;
  contradictory argument; conclusion entirely absent; piece is incoherent throughout.
- WARN: Meaningful editorial weakness that should ideally be fixed but does not block publication.
  Examples: tone slip, excessive hedging, repetition, pacing issue, weak transition, underwhelming close.
- INFO: Minor observation or optional improvement with no publication impact.
  Examples: small phrasing suggestion, stylistic note, optional tightening.

CRITICAL RULES:
- Do NOT rewrite any part of the article.
- Do NOT suggest factual changes.
- Do NOT replace the author's voice — identify weaknesses, do not fix them.
- Do NOT generate new content.

Return ONLY valid JSON — no markdown, no prose:
{{
  "overall_result": "PASS",
  "confidence": 0.85,
  "summary": "Solid piece with a commanding lede and clear structure. Pacing slows briefly in the third paragraph but recovers well.",
  "issues": [
    {{
      "severity": "WARN",
      "category": "pacing",
      "description": "Third paragraph lingers on biographical background without advancing the editorial argument.",
      "quote": "Born in Detroit in 1982, he grew up listening to..."
    }}
  ],
  "recommendations": [
    "Compress the biographical paragraph to one sentence — the lede has already established authority."
  ],
  "notes": [
    "Lede is commanding and earns the reader.",
    "Conclusion lands with authority."
  ]
}}

Rules:
- overall_result = "PASS"      if no FAIL-severity issues found
- overall_result = "FAIL"      if any FAIL-severity issue is found
- overall_result = "UNCERTAIN" only if the article is too short or fragmented to evaluate
- issues: empty list if the article is ready to publish as-is
- WARN or INFO issues do not prevent publication
- quote: include the specific text excerpt that illustrates the issue; omit field or use "" if not applicable
"""

    def _parse_response(self, text: str) -> EditorialReviewResult:
        try:
            data = json.loads(_strip_fences(text))

            result = data.get('overall_result', 'UNCERTAIN')
            if result not in _VALID_RESULT:
                result = 'UNCERTAIN'

            issues: list[EditorialIssue] = []
            for item in data.get('issues', []):
                if not isinstance(item, dict):
                    continue
                severity = str(item.get('severity', 'INFO')).upper()
                if severity not in _VALID_SEVERITY:
                    severity = 'INFO'
                issues.append(EditorialIssue(
                    severity=severity,
                    category=str(item.get('category', '')),
                    description=str(item.get('description', '')),
                    quote=str(item.get('quote', '')),
                ))

            # Enforce: any FAIL-severity issue → overall_result = FAIL,
            # regardless of what the model's result field says.
            if any(i.severity == 'FAIL' for i in issues):
                result = 'FAIL'

            return EditorialReviewResult(
                result=result,
                confidence=float(data.get('confidence', 0.5)),
                summary=str(data.get('summary', '')),
                issues=issues,
                recommendations=list(data.get('recommendations', [])),
                notes=list(data.get('notes', [])),
            )

        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            log.warning("Failed to parse Claude editorial response: %s", exc)
            return EditorialReviewResult(
                result='UNCERTAIN',
                confidence=0.0,
                summary='Failed to parse editorial review response',
            )
