# Image QA Lessons

Each entry documents a production failure, a recurring image quality problem, or a pattern identified across multiple articles. Entries must represent a real failure or a class of risk confirmed in production.

---

## 2026-06-23

### Failure
An article about Swavay was published with a photo of Metro Boomin as the hero image. The incorrect artist's photo was live on the site.

### Root Cause
The image sourcer was using Unsplash/Pexels stock search, which returned a photo from a related search query (Metro Boomin appeared in the article context). No check verified that the photo subject matched the primary artist.

### Resolution
1. Article deleted from `site/articles/`, `site/api/articles.json`, and `site/sitemap.xml`.
2. Removed all stock photo fallback from `image_sourcer.py`. Editorial sources (Wikimedia Commons) only.
3. Added IMAGE RULE to all writer system prompts: imageQuery MUST name the primary artist. First tag MUST be artist name.
4. Added publication gate: if no editorial image is sourced, the article is not published.
5. `VisionVerificationProvider` added to the quality pipeline (PR-003) to verify the photo subject matches the article's primary artist.

### Permanent Rule
Every hero image and inline image MUST depict the article's primary artist. No exceptions. Stock photos, concert crowd shots, and instrument-only photos are not acceptable as hero images for artist profiles or reviews. The VisionVerificationProvider must confirm artist identity before publication clears the image gate.

---

## 2026-06-25

### Failure
An article about Camille (the French singer, born 1978) was published with an inline image of Camille Claudel (the French sculptor, 1864–1943). Both are real, prominent people named Camille. The vision pipeline cleared the image because it correctly identified a real person — it did not verify that the person was the specific entity the article was about.

### Root Cause
The original vision prompt asked "Is [artist name] visible and identifiable?" — a name-level check. Two entirely different people can satisfy a name-level check. The system lacked identity-level verification.

### Resolution
1. Added a fifth editorial question to `GeminiVisionProvider._build_prompt`: ENTITY IDENTITY — requires the model to resolve the specific real-world entity the article covers (not just the name), identify the specific entity shown in the image, and confirm they match at the identity level.
2. Extended `VisionVerificationResult` with `entity_match`, `expected_entity`, `detected_entity`, `entity_confidence`, and `mismatch_reason` fields.
3. `_parse_response` enforces `entity_match=false → result=FAIL` regardless of the model's result field.
4. Added regression test suite (`automation/tests/test_vision_entity.py`) covering 12 known ambiguous entity pairs including this exact failure.

### Permanent Rule
Vision verification must operate at the identity level, not the name level. A shared name is not a shared identity. The system must resolve the specific real-world entity the article covers and confirm the image depicts that precise entity — not merely something with the same or similar name. Every new editorial failure of this class must be added to the regression suite immediately.

---

## 2026-06-25

### Failure
A feature article about Linea Personal (Argentine new wave group) was published with two incorrect photos: one of Manny Carlton and one of Alejandra Ávalos. Neither person has any connection to the article's subject.

### Root Cause
Three compounding failures:
1. `QUALITY_IMAGE_VALIDATION` defaulted to `false` in `config.py` and was never set to `true` in any of the three production workflow files. The vision gate was built, reviewed, and merged — but never activated. Every article since PR-003 was published without any image verification.
2. Even when the gate was enabled, only `images[0]` (the hero) was passed to `_run_vision_verification`. Inline images in index positions 1+ were never verified. A feature article sourcing three images (one per `imageQueries` query) would have its hero checked and its two inline images pass through unchecked.
3. The image sourcer used keyword search with no identity resolution step. `imageQueries` entries like "Linea Personal performing" could match unrelated people if the search API returned weakly-ranked results.

### Resolution
1. Set `QUALITY_IMAGE_VALIDATION: 'true'` in all three production workflow files (`publish-articles.yml`, `publish-features.yml`, `publish-reviews.yml`).
2. Changed `_run_vision_verification` signature from `(image: dict, ...) -> bool` to `(images: list, ...) -> list`. Hero failure blocks publication (returns `[]`); inline failure drops that image only.
3. Updated all four cycle call sites to use the new list-returning signature.
4. Enhanced `_check_one_image` logs to include image index, expected entity, detected entity, entity confidence, and mismatch reason on every FAIL.

### Permanent Rule
A quality gate that is built but not enabled in production provides zero protection. Every time a quality-gate PR is merged, the merge checklist must include: (1) code merged, (2) feature flag enabled in all applicable workflows, (3) end-to-end production verification completed. Vision verification must run on every published image — hero and inline — not only the first image in the list.
