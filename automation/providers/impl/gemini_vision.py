"""VisionVerificationProvider — Gemini visual editorial review.

Answers four questions about every hero image before publication:
  1. Is this the correct person?
  2. Is this the correct event, era, or context?
  3. Is the image technically suitable? (resolution, crop, watermarks)
  4. Is this the strongest editorial choice for this article?

Swap this file to switch vision verification to a different AI provider.
All Gemini-specific details are contained entirely within this file.
"""
import base64
import json
import logging
import re

import google.generativeai as genai

from config import GEMINI_VISION_MODEL
from providers.base import VisionVerificationProvider, VisionVerificationResult

log = logging.getLogger('lord.vision_verification')

_STRIP_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.MULTILINE)
_VALID_EDITORIAL = {'strong', 'adequate', 'weak'}


def _strip_fences(text: str) -> str:
    return _STRIP_RE.sub('', text.strip()).strip()


class GeminiVisionProvider(VisionVerificationProvider):
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(GEMINI_VISION_MODEL)

    def verify_image(self, image_bytes: bytes, mime_type: str, article_data: dict) -> VisionVerificationResult:
        tags = article_data.get('tags') or []
        artist = (
            article_data.get('artistName')
            or (tags[0] if tags else '')
        ).strip()
        title        = (article_data.get('title') or '').strip()
        deck         = (article_data.get('deck') or '').strip()
        article_type = (article_data.get('type') or '').strip()
        album        = (article_data.get('albumName') or '').strip()

        prompt = self._build_prompt(artist, title, deck, article_type, album)

        try:
            image_part = {
                'mime_type': mime_type,
                'data': base64.b64encode(image_bytes).decode(),
            }
            response = self._model.generate_content(
                contents=[{'parts': [{'inline_data': image_part}, {'text': prompt}]}]
            )
            return self._parse_response(response.text)
        except Exception as exc:
            log.warning("Gemini vision verification error: %s", exc)
            return VisionVerificationResult(
                result='UNCERTAIN',
                confidence=0.0,
                errors=[f"Vision provider unavailable: {exc}"],
            )

    def _build_prompt(
        self, artist: str, title: str, deck: str, article_type: str, album: str
    ) -> str:
        album_line = f'\nAlbum: "{album}"' if album else ''
        return f"""\
You are a visual editorial reviewer for LORD, an independent music publication.
Evaluate this image for use as the hero image of the article described below.

Article: {title}
Type: {article_type}
Summary: {deck}{album_line}
Primary Artist: "{artist}"

Answer these four questions precisely:

1. PERSON MATCH — Is "{artist}" clearly visible and identifiable in this image?
   If the image contains no recognizable person, answer false.

2. CONTEXT MATCH — Does the image match the article's context?
   Consider: does the era, styling, event, or setting fit what the article is about?
   A 2010 photo for a 2026 album rollout is a mismatch. Note any discrepancy.

3. TECHNICAL QUALITY — Is the image technically suitable for publication?
   Check: adequate resolution (not blurry/pixelated), no visible watermarks,
   subject is well-framed and not awkwardly cropped, aspect ratio is usable.

4. EDITORIAL QUALITY — Beyond technical pass, is this a strong image for this article?
   Rate as exactly one of: "strong", "adequate", or "weak".
   - "strong": compelling, visually arresting, elevates the article
   - "adequate": acceptable, does the job, unremarkable
   - "weak": technically usable but editorially poor (unflattering, generic, low energy)

Return ONLY valid JSON — no markdown, no prose:
{{
  "person_match": true,
  "person_match_confidence": 0.95,
  "context_match": true,
  "context_match_note": "Contemporary photo consistent with article about 2026 tour",
  "technical_pass": true,
  "technical_notes": [],
  "editorial_quality": "strong",
  "editorial_note": "Striking performance shot with strong visual composition",
  "issues": [],
  "confidence": 0.92,
  "result": "PASS"
}}

Rules:
- result = "PASS"      if person_match=true AND context_match=true AND technical_pass=true
- result = "FAIL"      if person_match=false OR technical issues are blocking (watermark, etc.)
- result = "UNCERTAIN" if you cannot confidently identify the person in the image
- editorial_quality "weak" is a warning, not a failure — article can still publish
- issues: list any specific blocking problems; empty list if none
"""

    def _parse_response(self, text: str) -> VisionVerificationResult:
        try:
            data = json.loads(_strip_fences(text))

            result = data.get('result', 'UNCERTAIN')
            if result not in ('PASS', 'FAIL', 'UNCERTAIN'):
                result = 'UNCERTAIN'

            editorial = data.get('editorial_quality', 'adequate')
            if editorial not in _VALID_EDITORIAL:
                editorial = 'adequate'

            warnings: list[str] = []
            if editorial == 'weak':
                note = data.get('editorial_note', '')
                warnings.append(
                    f"Editorial quality is weak — consider replacing image. {note}".strip()
                )

            tech_notes = data.get('technical_notes', [])
            if isinstance(tech_notes, list):
                warnings.extend(tech_notes)

            return VisionVerificationResult(
                result=result,
                confidence=float(data.get('confidence', 0.5)),
                person_match=bool(data.get('person_match', False)),
                context_match=bool(data.get('context_match', False)),
                technical_pass=bool(data.get('technical_pass', False)),
                editorial_quality=editorial,
                editorial_note=str(data.get('editorial_note', '')),
                errors=data.get('issues', []),
                warnings=warnings,
            )

        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            log.warning("Failed to parse Gemini vision response: %s", exc)
            return VisionVerificationResult(
                result='UNCERTAIN',
                confidence=0.0,
                errors=['Failed to parse vision verification response'],
            )
