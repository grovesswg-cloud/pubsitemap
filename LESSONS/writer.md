# Writer Lessons

Each entry documents a production failure or recurring problem in the article writing stage. Entries must represent a real failure or a class of risk confirmed in production or during Golden Article validation.

---

## 2026-06-25

### Failure
Classic review cycle for Solange — *A Seat at the Table* failed to produce an article. The pipeline exited silently with "No new content to commit."

### Root Cause
Claude's writer response contained a `body` field with unescaped double quotes — either from HTML attributes (`<a href="url">`) or from quoted prose (`He called it "revolutionary"`). The existing `json_utils._fix_string_newlines` only repaired bare newlines inside JSON strings; it had no handling for unescaped `"` characters. `json.loads` raised `JSONDecodeError: Expecting ',' delimiter: line 4 column 1200` and the cycle aborted.

Discovered during the Golden Article validation run immediately following the PR-005.7 Gemini SDK migration.

### Resolution
PR-005.8 (`fix(json_utils)`): replaced `_fix_string_newlines` with `_repair_json_strings`, a single-pass function that repairs both bare newlines and unescaped quotes in a single walk. When a `"` is encountered inside a string value, the function looks ahead past whitespace for the next structural character: if it is a JSON delimiter (`:`, `,`, `}`, `]`) the quote is a valid closing delimiter; otherwise it is escaped as `\"`.

### Permanent Rule
All writer JSON responses must pass repair and validation before entering the editorial pipeline. `parse_writer_json` is the underlying parser; all repair logic belongs there. When a writer cycle fails silently with "No new content to commit," it means the writer response was malformed, not that the pipeline ran cleanly and found nothing to publish.

---

## 2026-06-27

### Failure
A classic-review calibration run (Radiohead — *Kid A*) failed inside `write_classic_review()` *after* the Editorial Intelligence Engine had succeeded. The error was `Writer returned invalid JSON: Unterminated string starting at: line 4 column 11 (char 300)`. Unlike the GNX outline failure (a late truncation ~char 5,700), this broke almost immediately (~char 300), implicating the writer's prompt/output rather than a token budget — but we could not confirm, because the writer threw away its evidence.

### Root Cause
The writers (`write_bulletin`, `write_feature`, `write_review`, `write_classic_review`) were never wired into the observability subsystem built for the reasoning and revision stages. Each called `client.messages.create` directly — no `engine_telemetry.record` (so no `stop_reason`, no token counts) — and on a parse failure logged only `raw[:500]` and re-raised. That is the exact 400-char-preview mystery `engine_debug` was built to eliminate. The writer's raw response and `stop_reason` were unrecoverable, so the actual cause of the char-300 break could not be diagnosed from the failure alone.

### Resolution
Introduced `writer_llm.write_article` — the writer analog of the engine's `call_stage`. All four writers now route through it: it records telemetry, warns loudly on `max_tokens` truncation, and parses via `engine_debug.parse_stage_json`, which writes a self-contained evidence folder (`raw_response.txt`, `repaired.txt`, `error.txt` with the exact break marked, `context.json` with `stop_reason` + token counts) and re-raises (fail-closed preserved). Three divergent local `_strip_fences` copies were deleted; the truncation-aware `json_utils.strip_fences` is the only fence handler.

### Permanent Rule
The writer is a first-class stage of the engine and must be debuggable to the same standard. A writer failure must leave behind an evidence folder, never a 400-char log preview. When a writer fails, read the latest folder under the run's `failures/` directory (or `evidence/failures/`): `error.txt` names the break or leads with a `TRUNCATED` banner, and `context.json` carries the `stop_reason`. Do not blind-patch the JSON repair heuristic from an error message alone — read the captured raw response first.
