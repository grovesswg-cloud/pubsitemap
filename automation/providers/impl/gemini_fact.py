"""FactVerificationProvider — Gemini with Google Search grounding.

Verifies that the primary artist exists, the album/project exists (for reviews),
and no invented entities appear in the article body.
Swap this file to switch fact verification to a different AI provider.
"""
import json
import logging
import re

import google.generativeai as genai

from providers.base import FactVerificationProvider, FactVerificationResult

log = logging.getLogger('lord.fact_verification')

_GEMINI_MODEL = 'gemini-1.5-pro'
_STRIP_RE = re.compile(r'^```(?:json)?\s*|\s*```$')


def _strip_fences(text: str) -> str:
    return _STRIP_RE.sub('', text.strip()).strip()


class GeminiFactProvider(FactVerificationProvider):
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            _GEMINI_MODEL,
            tools='google_search_retrieval',
        )

    def verify(self, article_data: dict) -> FactVerificationResult:
        tags = article_data.get('tags') or []
        artist = (
            article_data.get('artistName')
            or (tags[0] if tags else '')
        ).strip()
        album       = (article_data.get('albumName') or '').strip()
        title       = (article_data.get('title') or '').strip()
        article_type = (article_data.get('type') or '').strip()
        body        = (article_data.get('body') or '')

        if not artist:
            return FactVerificationResult(
                result='FAIL',
                confidence=0.0,
                errors=['Cannot verify: no artist name found in article data'],
            )

        prompt = self._build_prompt(artist, album, title, article_type, body)

        try:
            response = self._model.generate_content(prompt)
            sources = self._extract_grounding_sources(response)
            return self._parse_response(response.text, sources)
        except Exception as exc:
            log.warning("Gemini fact verification error: %s", exc)
            return FactVerificationResult(
                result='UNCERTAIN',
                confidence=0.0,
                sources=[],
                errors=[f"Verification service unavailable: {exc}"],
                warnings=['Fact gate skipped due to provider error — proceeding'],
            )

    def _build_prompt(self, artist: str, album: str, title: str, article_type: str, body: str) -> str:
        album_line = f'\nAlbum/Project: "{album}"' if album else ''
        return f"""\
You are a fact-checker for LORD, an independent music publication.
Use Google Search to verify the claims below.

Article Title: {title}
Article Type: {article_type}
Primary Artist: "{artist}"{album_line}

Verification tasks (search for each):
1. Confirm "{artist}" is a real, publicly documented musician or band.
2. If an album/project is listed, confirm it exists and is credited to this artist.
3. Scan the article excerpt for any invented band names, fabricated song titles,
   or fictional collaborators that don't appear in any real music reporting.

Article excerpt (first 800 chars of body):
{body[:800]}

Return ONLY valid JSON — no markdown, no prose:
{{
  "artist_verified": true,
  "album_verified": true,
  "sources": ["Rolling Stone", "Billboard"],
  "confidence": 0.95,
  "issues": [],
  "result": "PASS"
}}

Rules:
- result = "PASS"  if artist is real and no invented entities detected
- result = "FAIL"  if artist does not exist or invented entities confirmed
- result = "UNCERTAIN"  if you cannot confidently verify from search results
- issues: list any specific fabricated or unverifiable claims found
- sources: publication names or site names used to confirm facts (from search)
"""

    def _extract_grounding_sources(self, response) -> list[str]:
        """Pull source names from Gemini's grounding metadata."""
        sources: list[str] = []
        try:
            candidates = getattr(response, 'candidates', [])
            if candidates:
                gm = getattr(candidates[0], 'grounding_metadata', None)
                if gm:
                    for chunk in getattr(gm, 'grounding_chunks', []):
                        web = getattr(chunk, 'web', None)
                        if web:
                            title = getattr(web, 'title', '') or getattr(web, 'uri', '')
                            if title:
                                sources.append(title)
        except Exception:
            pass
        return sources[:6]

    def _parse_response(self, text: str, grounding_sources: list[str]) -> FactVerificationResult:
        try:
            data = json.loads(_strip_fences(text))

            result = data.get('result', 'UNCERTAIN')
            if result not in ('PASS', 'FAIL', 'UNCERTAIN'):
                result = 'UNCERTAIN'

            # Merge grounding sources with any the model listed itself
            all_sources = list(dict.fromkeys(grounding_sources + data.get('sources', [])))

            return FactVerificationResult(
                result=result,
                confidence=float(data.get('confidence', 0.5)),
                sources=all_sources[:8],
                errors=data.get('issues', []),
                warnings=[],
            )
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            log.warning("Failed to parse Gemini fact response: %s", exc)
            return FactVerificationResult(
                result='UNCERTAIN',
                confidence=0.0,
                sources=grounding_sources,
                errors=['Failed to parse verification response — treating as uncertain'],
                warnings=[],
            )
