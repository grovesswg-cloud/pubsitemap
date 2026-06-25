# Editorial Lessons

Each entry documents a production failure, a recurring editorial weakness, or a structural pattern observed across multiple articles. The bar is high — individual article feedback does not qualify. Entries represent patterns observed more than once, or a structural risk identified before it becomes a recurring problem.

---

## 2026-06-25

### Failure
After the first full classic review article (*The Miseducation of Lauryn Hill*), editorial review identified that the analytical frame "This album was misunderstood as X; it was actually about Y" had already become a recognizable structural template. No single article was wrong for using it — the risk is that readers begin to predict the structure before finishing the first paragraph.

### Root Cause
The writer prompt did not vary the central argumentative frame between reviews. A single successful structure was reused because it consistently produced strong-sounding criticism. No mechanism existed to detect or discourage structural repetition across articles.

### Resolution
No pipeline fix required. Writer prompt should be adjusted to vary the analytical frame across reviews. Structural diversity is a voice issue, not a pipeline issue.

### Permanent Rule
LORD should have a recognizable voice, not a recognizable template. The following structural habits are acceptable in a single article but must not become defaults across multiple consecutive reviews:

- "This album was always really about X, not Y" (reinterpretation frame)
- Opening with historical revisionism
- Closing with a sweeping cultural conclusion
- Framing every review around a single central reinterpretation

When the same frame appears in two or more consecutive reviews, vary the approach before publishing the next. The goal is a publication whose voice is consistent, but whose analytical approach is unpredictable.
