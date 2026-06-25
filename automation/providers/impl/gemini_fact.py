"""FactVerificationProvider — Gemini with Google Search grounding.

Verifies the primary artist, album, and ALL named entities in the article.
Captures full source provenance (name + URL) from grounding metadata.
Swap this file to switch fact verification to a different AI provider.
All Gemini-specific details (grounding, model config, response parsing)
are contained entirely within this file.
"""
import json
import logging
import re

import google.generativeai as genai

from config import GEMINI_FACT_MODEL
from providers.base import FactVerificationProvider, FactVerificationResult, VerificationSource

log = logging.getLogger('lord.fact_verification')

_STRIP_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _STRIP_RE.sub('', text.strip()).strip()


class GeminiFactProvider(FactVerificationProvider):
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            GEMINI_FACT_MODEL,
            tools='google_search_retrieval',
        )

    def verify(self, article_data: dict) -> FactVerificationResult:
        tags = article_data.get('tags') or []
        artist = (
            article_data.get('artistName')
            or (tags[0] if tags else '')
        ).strip()
        album        = (article_data.get('albumName') or '').strip()
        title        = (article_data.get('title') or '').strip()
        article_type = (article_data.get('type') or '').strip()
        body         = (article_data.get('body') or '')

        if not artist:
            return FactVerificationResult(
                result='FAIL',
                confidence=0.0,
                errors=['Cannot verify: no artist name found in article data'],
            )

        prompt = self._build_prompt(artist, album, title, article_type, body)

        try:
            response = self._model.generate_content(prompt)
            grounding_sources = self._extract_grounding_sources(response)
            return self._parse_response(response.text, grounding_sources)
        except Exception as exc:
            log.warning("Gemini fact verification error: %s", exc)
            return FactVerificationResult(
                result='UNCERTAIN',
                confidence=0.0,
                errors=[f"Verification provider unavailable: {exc}"],
            )

    def _build_prompt(self, artist: str, album: str, title: str, article_type: str, body: str) -> str:
        album_line = f'\nAlbum/Project: "{album}"' if album else ''
        return f"""\
You are a senior fact-checker for LORD, an independent music publication.
Use Google Search to verify every named entity in this article.

Article Title: {title}
Article Type: {article_type}
Primary Artist: "{artist}"{album_line}

For the article excerpt below, search for and verify ALL of the following:
- Primary artist/band (confirm real, publicly documented)
- Featured artists and collaborators
- Producers and engineers named
- Record labels named
- Album, song, and EP titles
- Release years (confirm they match actual release dates)
- Venue names and cities
- Tour names
- Award names and nominating/granting organizations
- Chart positions (confirm accurate if specific numbers cited)
- Any people directly quoted
- Factual dates and event chronology
- Any other named entities that could be fabricated

Article excerpt (first 1000 chars):
{body[:1000]}

Return ONLY valid JSON — no markdown fences, no prose before or after:
{{
  "result": "PASS",
  "confidence": 0.95,
  "entities_checked": ["Drake", "21 Savage", "OVO Sound"],
  "issues": [],
  "sources": [
    {{"name": "Rolling Stone", "url": "https://rollingstone.com/...", "claim": "Primary artist confirmed"}}
  ]
}}

Rules:
- result = "PASS"      if primary artist is real and no invented entities detected
- result = "FAIL"      if artist does not exist OR invented/fabricated entities confirmed
- result = "UNCERTAIN" if Google Search returns insufficient results to verify confidently
- issues: list each specific fabricated or unverifiable claim (empty list if none)
- sources: list sources used, each with name, url (if known), and what claim it verified
- entities_checked: flat list of every entity name you searched for
"""

    def _extract_grounding_sources(self, response) -> list[VerificationSource]:
        """Pull name + URL from Gemini's grounding metadata chunks."""
        sources: list[VerificationSource] = []
        try:
            candidates = getattr(response, 'candidates', [])
            if candidates:
                gm = getattr(candidates[0], 'grounding_metadata', None)
                if gm:
                    for chunk in getattr(gm, 'grounding_chunks', []):
                        web = getattr(chunk, 'web', None)
                        if web:
                            name = getattr(web, 'title', '') or ''
                            url  = getattr(web, 'uri', '') or ''
                            if name or url:
                                sources.append(VerificationSource(
                                    name=name or url,
                                    url=url,
                                    claim='grounding search result',
                                ))
        except Exception:
            pass
        return sources[:8]

    def _parse_response(
        self,
        text: str,
        grounding_sources: list[VerificationSource],
    ) -> FactVerificationResult:
        try:
            data = json.loads(_strip_fences(text))

            result = data.get('result', 'UNCERTAIN')
            if result not in ('PASS', 'FAIL', 'UNCERTAIN'):
                result = 'UNCERTAIN'

            # Build typed sources from model's JSON, then merge grounding sources
            model_sources: list[VerificationSource] = []
            for s in data.get('sources', []):
                if isinstance(s, dict):
                    model_sources.append(VerificationSource(
                        name=str(s.get('name', '')),
                        url=str(s.get('url', '')),
                        claim=str(s.get('claim', '')),
                    ))
                elif isinstance(s, str):
                    model_sources.append(VerificationSource(name=s))

            # Deduplicate by URL then by name; grounding sources carry real URLs
            seen_urls: set[str] = set()
            seen_names: set[str] = set()
            merged: list[VerificationSource] = []
            for src in grounding_sources + model_sources:
                key = src.url or src.name
                if src.url and src.url in seen_urls:
                    continue
                if not src.url and src.name in seen_names:
                    continue
                seen_urls.add(src.url)
                seen_names.add(src.name)
                merged.append(src)

            return FactVerificationResult(
                result=result,
                confidence=float(data.get('confidence', 0.5)),
                sources=merged[:10],
                errors=data.get('issues', []),
            )

        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            log.warning("Failed to parse Gemini fact response: %s", exc)
            return FactVerificationResult(
                result='UNCERTAIN',
                confidence=0.0,
                sources=grounding_sources,
                errors=['Failed to parse verification response'],
            )
