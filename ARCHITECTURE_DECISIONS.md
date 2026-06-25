# Architecture Decision Records — LORD

Each entry documents a significant architectural decision: what was chosen, what was considered, and why. When context is lost, this file restores it.

---

## ADR-001: Provider abstraction for all AI services

**Status:** Accepted  
**Date:** 2026-06-25

**Decision:** All AI provider calls are wrapped behind interfaces (`FactVerificationProvider`, `VisionVerificationProvider`, `EditorialReviewProvider`). Concrete implementations live in `automation/providers/impl/`. The Editorial Board never references Gemini, Claude, or any specific model directly.

**Context:** The pipeline currently uses Claude for writing and Gemini for verification. Model quality shifts constantly. Locking provider names into orchestration logic requires codebase-wide surgery when switching vendors.

**Alternatives considered:**
- Hard-code Gemini throughout — rejected because one API pricing change triggers a wide refactor.
- Use LangChain/LiteLLM abstraction layer — rejected because it adds a heavy dependency for a problem we can solve with simple ABC classes.

**Consequences:** Swapping any AI provider requires editing one file in `automation/providers/impl/`. The Editorial Board, scheduler, and quality gates remain untouched.

---

## ADR-002: Pass/Fail quality gates, not numeric scores

**Status:** Accepted  
**Date:** 2026-06-25

**Decision:** Every quality gate returns an explicit `PASS` or `FAIL` per dimension (facts, images, metadata, seo, editorial). The publishing gate outputs `READY` or `BLOCKED`. No numeric scores are used as gates.

**Context:** A score of 87/100 is ambiguous — is 87 acceptable? Who decides the threshold? Every threshold becomes a maintenance burden and a source of debate. Objective PASS/FAIL per dimension is unambiguous and auditable.

**Alternatives considered:**
- Numeric quality score (0–100) — rejected because the threshold is inherently subjective and drifts over time.
- Weighted composite score — rejected as even harder to interpret and defend to a human reviewer.

**Consequences:** Gate decisions are explicit. Confidence values (0.0–1.0) are stored separately for analytics, but they never gate publication directly.

---

## ADR-003: Pipeline order — objective checks before editorial polish

**Status:** Accepted  
**Date:** 2026-06-25

**Decision:** The publication pipeline runs in this order: Writer → Metadata → Facts → Images → Editorial → SEO → Publisher. Editorial review runs only after all objective checks pass.

**Context:** Editorial review is expensive (AI tokens, time). Running it on an article that will fail fact verification or image QA wastes those resources and creates false confidence in content that cannot be published.

**Alternatives considered:**
- Editorial first, then validation — rejected because it polishes content that will be discarded.
- Parallel validation — rejected because image QA requires facts to be confirmed first (need to know the correct artist to validate the photo).

**Consequences:** Articles that fail objective checks never reach editorial review. This means fewer "polished but blocked" situations and lower operational cost.

---

## ADR-004: Evidence package stored outside the repository

**Status:** Accepted  
**Date:** 2026-06-25

**Decision:** Every published article generates an evidence package at `evidence/YYYY/MM/article-slug/` containing quality-report.json, fact-report.json, image-report.json, editorial-report.json, sources.json, and logs.txt. This directory is gitignored.

**Context:** If an article is challenged after publication, every decision made during the pipeline must be immediately retrievable — which sources verified the facts, what the image QA result was, what the editorial review said. Committing this to the repository would bloat git history rapidly.

**Alternatives considered:**
- Store evidence in git — rejected because at 12 articles/day, this creates thousands of large JSON files in the repository within months.
- No evidence storage — rejected because auditability is a core editorial requirement.
- External S3/blob storage — possible future path, but local filesystem is sufficient for now and avoids cloud dependencies.

**Consequences:** Evidence packages must be backed up separately from the repository. The `evidence/` directory is gitignored. On GitHub Actions, evidence is available during the run but is not persisted.

---

## ADR-005: Editorial Review Queue, not Human Review Queue

**Status:** Accepted  
**Date:** 2026-06-25

**Decision:** When an article fails validation after 3 retry attempts, it is written to `review/pending/` as a JSON file with reason, logs, and associated file paths. The queue is named "Editorial Review Queue," not "Human Review Queue."

**Context:** "Human" unnecessarily constrains the architecture. Future iterations may involve AI agents performing queue review. "Editorial" reflects the function, not the actor.

**Alternatives considered:**
- Silent discard on failure — rejected because losing content silently makes it impossible to improve the pipeline.
- Human Review Queue — rejected as unnecessarily constraining (see above).

**Consequences:** Nothing is silently discarded. The `review/` directory is gitignored. Operators must periodically inspect `review/pending/` and move items to `review/approved/`, `review/rejected/`, or `review/fixed/`.

---

## ADR-006: Feature flags in config.py, not a separate YAML file

**Status:** Accepted  
**Date:** 2026-06-25

**Decision:** Quality pipeline feature flags are environment variables read in `config.py` alongside all other configuration. No separate YAML or JSON config file exists for flags.

**Context:** A separate config file adds a new parsing surface, a new file to keep in sync, and a new failure mode (file not found, bad YAML). Since all other config is already in `config.py` via `os.getenv()`, adding flags there keeps configuration in one place.

**Alternatives considered:**
- Separate `quality_config.yaml` — rejected because it creates two config systems for no gain.
- Feature flag service (LaunchDarkly, etc.) — rejected as overengineered for a site of this scale.

**Consequences:** Feature flags are togglable via GitHub Actions secrets/environment variables. Default state: metadata validation on, all others off (not yet implemented).

---

## ADR-007: LESSONS/ directory, not LESSONS.md

**Status:** Accepted  
**Date:** 2026-06-25

**Decision:** Pipeline failure lessons are stored in `LESSONS/` as category-specific files: `fact-check.md`, `images.md`, `metadata.md`, `seo.md`, `editorial.md`.

**Context:** A single `LESSONS.md` file grows unbounded. After years of operation it becomes too large to scan. Category files stay focused and are easier to include selectively in AI context windows.

**Alternatives considered:**
- Single LESSONS.md — rejected because of unbounded growth.
- Year-based files (2026.md, 2027.md) — considered, but category-based files are more useful when debugging a specific type of failure.

**Consequences:** When the pipeline encounters a new failure type, the relevant category file is updated. Each AI session can be primed with only the relevant category file rather than the entire lessons corpus.

---

## ADR-008: MusicBrainz replaced by Gemini for entity verification

**Status:** Accepted  
**Date:** 2026-06-25

**Decision:** Artist and album entity verification uses the Gemini API with Google Search grounding rather than the MusicBrainz API.

**Context:** MusicBrainz has poor coverage of emerging artists, non-Western music, and recent releases. Gemini with search grounding can verify entities that exist anywhere on the web, making it far more suitable for a music publication that covers current releases.

**Alternatives considered:**
- MusicBrainz API — rejected due to coverage gaps on emerging artists (the exact artists most likely to generate hallucinations).
- Wikidata/Wikipedia API — considered as supplement; can be added to the Gemini implementation as a cross-reference source without changing the provider interface.

**Consequences:** Fact verification requires a Gemini API key (GOOGLE_GEMINI_API_KEY). The `FactVerificationProvider` interface allows a fallback implementation using any alternative source.

---

## ADR-009: Image QA checks both person identity and contextual relevance

**Status:** Accepted  
**Date:** 2026-06-25

**Decision:** Image QA has two checks: (1) the correct person appears in the image, and (2) the image context matches the article (era, event, project). Both must pass.

**Context:** A 2012 photo of an artist is technically "correct person" but wrong for an article about their 2026 tour. Without context matching, correct-person-wrong-era images slip through.

**Alternatives considered:**
- Person match only — rejected because era/context mismatches undermine editorial credibility.
- Manual review of all images — rejected as unscalable; AI vision QA allows automated review at publication speed.

**Consequences:** Image QA is more expensive per article (two vision calls instead of one). The added accuracy justifies the cost for a publication with strict editorial standards.
