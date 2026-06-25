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
