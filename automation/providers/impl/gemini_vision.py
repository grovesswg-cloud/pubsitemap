"""VisionVerificationProvider — Gemini visual editorial review.

Answers five questions about every hero image before publication:
  1. Is this the correct person?
  2. Is this the correct event, era, or context?
  3. Is the image technically suitable? (resolution, crop, watermarks)
  4. Is this the strongest editorial choice for this article?
  5. Is the entity depicted SPECIFICALLY the entity this article is about?
     (identity-level match, not name-level match)

Swap this file to switch vision verification to a different AI provider.
All Gemini-specific details are contained entirely within this file.
"""
import json
import logging
import re

from google import genai
from google.genai import types

from config import GEMINI_VISION_MODEL
from providers.base import VisionVerificationProvider, VisionVerificationResult

log = logging.getLogger('lord.vision_verification')

_STRIP_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.MULTILINE)
_VALID_EDITORIAL = {'strong', 'adequate', 'weak'}


def _strip_fences(text: str) -> str:
    return _STRIP_RE.sub('', text.strip()).strip()


class GeminiVisionProvider(VisionVerificationProvider):
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

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
        body_excerpt = (article_data.get('body') or '')[:500]

        prompt = self._build_prompt(artist, title, deck, article_type, album, body_excerpt)

        try:
            response = self._client.models.generate_content(
                model=GEMINI_VISION_MODEL,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    prompt,
                ],
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
        self, artist: str, title: str, deck: str, article_type: str, album: str,
        body_excerpt: str,
    ) -> str:
        album_line = f'\nAlbum: "{album}"' if album else ''
        body_line  = f'\nArticle excerpt: {body_excerpt}' if body_excerpt else ''
        return f"""\
You are a visual editorial reviewer for LORD, an independent music publication.
Evaluate this image for use as the hero image of the article described below.

Article: {title}
Type: {article_type}
Summary: {deck}{album_line}
Primary Artist: "{artist}"{body_line}

Answer these five questions precisely:

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

5. ENTITY IDENTITY — Is the entity shown in this image SPECIFICALLY the same entity
   this article is about? This is an identity check, not a name check.

   Step A: Use ALL article context (title, summary, excerpt, tags, type) to determine
   the precise real-world entity this article covers. Describe it specifically:
   e.g. "Camille (French singer, born 1978, known for albums Le Fil and Music Hole)"
   — NOT just "Camille".

   Step B: Examine the image and identify every recognizable entity depicted.
   Describe specifically what you see.

   Step C: Do the identities match at the entity level?

   CRITICAL — name similarity is NOT identity. Common failure modes:
   - Camille (French singer) ≠ Camille Claudel (French sculptor, 1864–1943)
   - Seal (musician) ≠ seal (marine animal)
   - Bush (band) ≠ George W. Bush or any politician
   - Journey (band) ≠ generic travel/road/journey imagery
   - America (band) ≠ the United States, American flag, or Americana imagery
   - Chicago (band) ≠ city of Chicago or Chicago skyline
   - Boston (band) ≠ city of Boston
   - Phoenix (band) ≠ Phoenix, Arizona or phoenix bird imagery
   - Queen (band) ≠ Queen Elizabeth II or royalty imagery
   - Eagles (band) ≠ bald eagle or any bird
   - Garbage (band) ≠ garbage, trash, or waste imagery
   - Kiss (band) ≠ people kissing or kiss imagery

   entity_match must be false if the image depicts anything other than the specific
   entity the article is about — even if names overlap.

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
  "entity_match": true,
  "expected_entity": "Camille (French singer, born 1978, known for Le Fil, Music Hole)",
  "detected_entity": "Camille (French singer)",
  "entity_confidence": 0.95,
  "mismatch_reason": "",
  "issues": [],
  "confidence": 0.92,
  "result": "PASS"
}}

Rules:
- result = "PASS"      if person_match=true AND context_match=true AND technical_pass=true AND entity_match=true
- result = "FAIL"      if person_match=false OR entity_match=false OR technical issues are blocking (watermark, etc.)
- result = "UNCERTAIN" if you cannot confidently identify the person or entity in the image
- editorial_quality "weak" is a warning, not a failure — article can still publish
- issues: list any specific blocking problems; empty list if none
- mismatch_reason: explain the identity mismatch in plain language; empty string if entity_match=true
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

            entity_match    = bool(data.get('entity_match', True))
            expected_entity = str(data.get('expected_entity', ''))
            detected_entity = str(data.get('detected_entity', ''))
            entity_confidence = float(data.get('entity_confidence', 0.0))
            mismatch_reason = str(data.get('mismatch_reason', ''))

            errors: list[str] = list(data.get('issues', []))

            # Entity mismatch is always a hard FAIL, regardless of what the model's
            # result field says. The model might say PASS while entity_match=false
            # if it gets confused — we enforce the rule here.
            if not entity_match:
                result = 'FAIL'
                errors.append(
                    f"Entity mismatch — Expected: {expected_entity} | "
                    f"Detected: {detected_entity} | Reason: {mismatch_reason}"
                )
                log.warning(
                    "VISION ENTITY MISMATCH: expected=%r detected=%r reason=%s",
                    expected_entity, detected_entity, mismatch_reason,
                )

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
                entity_match=entity_match,
                expected_entity=expected_entity,
                detected_entity=detected_entity,
                entity_confidence=entity_confidence,
                mismatch_reason=mismatch_reason,
                errors=errors,
                warnings=warnings,
            )

        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            log.warning("Failed to parse Gemini vision response: %s", exc)
            return VisionVerificationResult(
                result='UNCERTAIN',
                confidence=0.0,
                errors=['Failed to parse vision verification response'],
            )
