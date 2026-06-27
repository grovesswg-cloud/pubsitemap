# LORD Editorial Pipeline

Canonical reference for how each article type moves from source material to
published content. Each pipeline has a distinct responsibility at each stage.
Update this document when any stage is added, removed, or significantly changed.

---

## Guiding Principle

Each stage has a single, narrow responsibility. No stage should do the work of
another stage. Quality at each handoff is more valuable than minimizing the
number of stages or API calls.

---

## Pipeline 1 — Bulletin (Journalism)

Bulletins answer one question: **What happened?**

They do not produce theses. They do not evaluate. They do not apply the
listening framework. Their job is accurate, clear, contextualised news reporting.

```
RSS / News Sources
      ↓
  news_fetcher.py
  (fetch, deduplicate, filter)
      ↓
  scheduler.py
  (select story, check daily limits)
      ↓
  article_writer.py  ←── load_editorial()
  (write bulletin — 300–500 words)
      ↓
  quality pipeline
  (metadata validation → fact check → image validation → vision QA)
      ↓
  publisher.py
  (render HTML, update articles.json, sitemap)
      ↓
  Published
```

**Editorial context loaded:** Constitution + Playbook only (`load_editorial()`).
The listening framework, music knowledge, and criticism framework are not loaded
for bulletins. News reporting does not require criticism dimensions.

**Key constraints:**
- Must stay within reported facts — no speculation, no editorialisation
- Source URL always included
- 300–500 words; no headers inside body; `<p>` tags only

---

## Pipeline 2 — Review (Criticism)

Reviews answer: **What does this record achieve, and what does it mean?**

The Reasoning Engine (PR-006.2) runs a structured pre-writing phase before
the writer is invoked. The writer receives a `ReasoningBrief` — not raw input.

```
Album info (artist, album, context)
      ↓
  reasoning_engine.py  ←── load_criticism_context()
  ├── Stage 1: Research + Knowledge Load
  │   (Publication Intelligence: what has LORD said about this artist/subject?
  │    Editorial Positioning: what has broader criticism said? where is the gap?)
  ├── Stage 2: Listening Framework
  │   (Three-listen protocol → observations → confidence levels)
  ├── Stage 3: Thesis Generation
  │   (Generate 5 thesis candidates)
  ├── Stage 4: Challenge + Counterargument
  │   (Challenge the strongest thesis; ask why a reasonable critic would disagree)
  └── Stage 5: Select + Outline
      (Select thesis; produce structured outline)
      ↓
  ReasoningBrief {
    thesis, rejected_theses, evidence,
    observations, weaknesses, counterargument,
    outline, confidence
  }
      ↓
  review_writer.py  ←── load_criticism_context() + ReasoningBrief
  (write review — 800–1,200 words; rating assigned)
      ↓
  revision_engine.py  (PR-006.3)
  (draft → critique → weak sections → rewrite plan → targeted rewrites → QA)
      ↓
  quality pipeline
  (metadata → fact check → image validation → vision QA → editorial review)
      ↓
  publisher.py
      ↓
  Published
```

**Editorial context loaded:** Full criticism context (`load_criticism_context()`):
Constitution + Playbook + Listening Framework + Music Knowledge + Criticism Framework.

**Key constraints:**
- Rating must be earned by the argument in the body — they must agree
- Every claim traces back to a specific sonic observation
- Step 9 (Weaknesses) is mandatory — cannot be omitted
- Counterargument must be considered before thesis is finalised

---

## Pipeline 3 — Feature (Editorial)

Features answer: **What does this artist's work mean, and why does it matter now?**

Features sit between journalism and criticism. Some are primarily critical
(a deep dive into an artist's catalogue); others are primarily contextual
(a cultural moment, an industry story, a movement). The feature pipeline
routes based on this distinction.

```
News item (used as launching point, not subject)
      ↓
  scheduler.py
  (determine: criticism-oriented or context-oriented?)
      ↓
  ┌─────────────────────────────────────────────────┐
  │ Criticism-oriented feature                      │
  │ (artist catalogue, reassessment, body of work)  │
  │         ↓                                       │
  │   reasoning_engine.py                           │
  │   (same pipeline as Review, adapted for         │
  │    a body of work rather than single record)    │
  │         ↓                                       │
  │   ReasoningBrief                                │
  └─────────────────────────────────────────────────┘
        ↓
  ┌─────────────────────────────────────────────────┐
  │ Context-oriented feature                        │
  │ (cultural moment, industry story, movement)     │
  │         ↓                                       │
  │   feature_reasoning.py  (future)                │
  │   (research → positioning → thesis → outline)  │
  └─────────────────────────────────────────────────┘
        ↓
  feature_writer.py  ←── load_criticism_context() + ReasoningBrief (if criticism)
  (write feature — 1,500–2,000 words; thesis-driven)
      ↓
  revision_engine.py  (PR-006.3)
      ↓
  quality pipeline
      ↓
  publisher.py
      ↓
  Published
```

**Editorial context loaded:** Full criticism context for criticism-oriented features.
Context-oriented features: Constitution + Playbook + (future) context reasoning documents.

---

## Supporting Systems

### Publication Intelligence (PR-006.2)
Dynamic institutional memory. Answers: **What has LORD already said?**

Sources: `site/api/articles.json` — scans published articles for:
- Prior coverage of this artist or album
- Repeated metaphors, phrases, comparisons
- Previous ratings and positions on this subject
- Vocabulary patterns across recent articles

Output fed into Stage 1 of the Reasoning Engine.
Prevents repetition. Identifies where LORD has already staked positions.

### Editorial Positioning (PR-006.2)
External discourse analysis. Answers: **What has broader criticism said, and where is there room to contribute?**

Sources: RSS feeds, news summaries, known critical positions.
Identifies: dominant critical angles, underexplored dimensions, consensus vs. contested ground.

Output fed into Stage 1 of the Reasoning Engine alongside Publication Intelligence.
Positioning is not about disagreeing with consensus — it is about finding where
a contribution is still possible.

### Revision Engine (PR-006.3)
The publication's internal editor. Runs after the writer and before the quality
gates. Input: the draft article + its ReasoningBrief. A single disciplined pass —
not a loop. Publication-agnostic: the caller supplies the editorial context.

```
Draft + ReasoningBrief
  ↓
Stage 1 — Critique  (fail-closed; low temperature)
  Two layers, each note rated high/medium/low impact:
    FIDELITY — checked against the brief (the objective layer):
      thesis_drift · dropped_evidence · overconfident (low-conf claim stated as fact)
      · missing_weakness · smuggled_argument · counterargument_skipped
    CRAFT — judgment about the prose:
      shallow_analysis · weak_transition · repetition · weak_ending
      · pacing · weak_opening
  ↓
Stage 2 — Plan  (mechanical, deterministic — no LLM call)
  Triage policy that encodes "highest-impact, not endless rewriting":
    fix every HIGH issue → then MEDIUM by rank → never LOW
    → cap the number of paragraphs touched (default 4)
  ↓
Stage 3 — Targeted Rewrites  (fail-closed; moderate temperature)
  Rewrite ONLY the selected paragraphs. Bound to the brief (no new arguments).
  Sees the whole draft read-only so transitions into/out of each edit survive.
  ↓
RevisionReport { notes, plan, revised_paragraphs, revised_body }
  ↓
Revised body → existing quality pipeline (Final QA is the existing gates,
  not a new subsystem: metadata → fact → vision → editorial review → search)
```

**Brief-grounded:** the critique's fidelity layer is what makes this an editor
rather than a prose polisher — it can check, objectively, whether the prose
delivered the assigned argument. On the legacy path (no brief) the critique runs
craft-only.

**Fail-fast (pre-launch):** a fail-closed stage error aborts the article rather
than publishing an un-revised draft. Toggle with `REVISION_ENGINE=false`.

### Editorial Notebook (future — PR-010 or later)
Persistent per-article reasoning record. Stores:
- Final observations and evidence
- Rejected theses
- Final ReasoningBrief

Never published. Used for institutional memory, debugging editorial decisions,
and eventually feeding Publication Intelligence with richer historical data.

Storage: `engine/notebooks/{artist}/{slug}.json` (engine directory, not site directory —
reusable across publications).

---

## What Each Stage Is Responsible For

| Stage | Responsibility | Must NOT do |
|---|---|---|
| News fetcher | Fetch, deduplicate, filter | Evaluate or rank stories |
| Scheduler | Select, route, enforce limits | Write content |
| Reasoning Engine | Structured pre-writing reasoning | Write prose |
| Writer | Turn ReasoningBrief into excellent prose | Reason from scratch |
| Revision Engine | Critique and targeted rewriting | Rewrite everything |
| Quality pipeline | Validate metadata, facts, images | Create content |
| Publisher | Render and commit | Make editorial decisions |

---

## Build Order

| PR | Component | Status |
|---|---|---|
| PR-038 | Canonical album deduplication | ✅ Merged |
| PR-006.1 | Editorial Constitution + Playbook | ✅ Merged |
| PR-008 | Critical Listening System | ✅ Merged |
| PR-006.2 | Reasoning Engine | ✅ Merged |
| PR-006.3 | Revision Engine | 🔨 This PR |
| PR-006.5 | Editorial Intelligence (Publication Intelligence) | Pending |
| PR-006.6 | Editorial Positioning Engine | Pending |
| PR-009 | Multi-layer Knowledge Base | Pending |
| PR-010 | Editorial Notebook | Future |
| PR-011 | Editorial Analytics | Future |
