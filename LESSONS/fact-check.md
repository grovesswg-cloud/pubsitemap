# Fact-Check Lessons

Each entry: what failed, why, the fix, and the permanent rule.

---

## 2026-06-23 — Invented band name published to site

**Failure:** Feature writer generated an article about "Everyone Says Hi" — a band that does not exist. The article was published and reached the live site.

**Root Cause:** No fact verification gate existed. The feature writer hallucinated a band name under prompt pressure to produce novel content. The name passed no external check before publication.

**Solution:**
1. Article deleted from `site/articles/`, `site/api/articles.json`, and `site/sitemap.xml`.
2. Added ABSOLUTE RULE to all writer system prompts: "NEVER make up a band, artist, or project. Only report on what has been reliably reported on already."
3. Added `FactVerificationProvider` to the quality pipeline (PR-002) to verify every entity against external sources before publication.

**Permanent Rule:** Every artist, band, album, song, tour, label, and project mentioned in any article MUST be verified as real against at least one external source before the article is published. If the writer cannot confirm an entity exists, that entity must not appear in the article.
