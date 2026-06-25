# Image QA Lessons

Each entry: what failed, why, the fix, and the permanent rule.

---

## 2026-06-23 — Wrong artist photo used as article hero image

**Failure:** An article about Swavay used a photo of Metro Boomin as the hero image. The article was published with the incorrect artist's photo.

**Root Cause:** The image sourcer was using Unsplash/Pexels stock search, which returned a photo from a related search query (Metro Boomin was mentioned in the article context). No check verified that the photo subject matched the primary artist.

**Solution:**
1. Article deleted from `site/articles/`, `site/api/articles.json`, and `site/sitemap.xml`.
2. Removed all stock photo fallback from `image_sourcer.py`. Editorial sources (Wikimedia Commons) only.
3. Added IMAGE RULE to all writer system prompts: "imageQuery MUST name the primary artist. First tag MUST be artist name."
4. Added publication gate: if no editorial image is sourced, the article is not published.
5. `VisionVerificationProvider` added to the quality pipeline (PR-003) to verify the photo subject matches the article's primary artist.

**Permanent Rule:** Every hero image and inline image MUST depict the article's primary artist. No exceptions. Stock photos, concert crowd shots, and instrument-only photos are not acceptable as hero images for artist profiles or reviews. The VisionVerificationProvider must confirm artist identity before publication clears the image gate.

---

## 2026-06-25 — Wrong entity image passed vision check (Camille/Camille Claudel)

**Failure:** An article about Camille (the French singer, born 1978) was published with an inline image of Camille Claudel (the French sculptor, 1864–1943). Both are real, prominent people named Camille. The vision pipeline cleared the image because it correctly identified a real person — it did not verify that the person was the *specific* entity the article was about.

**Root Cause:** The original vision prompt asked "Is [artist name] visible and identifiable?" — a name-level check. Two entirely different people can satisfy a name-level check. The system lacked identity-level verification.

**Solution:**
1. Added a fifth editorial question to `GeminiVisionProvider._build_prompt`: **ENTITY IDENTITY** — requires the model to resolve the specific real-world entity the article covers (not just the name), identify the specific entity shown in the image, and confirm they match at the identity level.
2. Extended `VisionVerificationResult` with `entity_match`, `expected_entity`, `detected_entity`, `entity_confidence`, and `mismatch_reason` fields.
3. `_parse_response` enforces `entity_match=false → result=FAIL` regardless of the model's result field.
4. Added regression test suite (`automation/tests/test_vision_entity.py`) covering 12 known ambiguous entity pairs including this exact failure.

**Permanent Rule:** Vision verification must operate at the identity level, not the name level. A shared name is not a shared identity. The system must resolve the specific real-world entity the article covers and confirm the image depicts that precise entity — not merely something with the same or similar name. Every new editorial failure of this class must be added to the regression suite immediately.
