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
All writer JSON responses must pass repair and validation before entering the editorial pipeline. `parse_writer_json` is the single entry point for all writer output; all repair logic belongs there. When a writer cycle fails silently with "No new content to commit," check the Python log output for `JSON parse failed` — this is the signal that the writer response was malformed, not that the pipeline ran cleanly and found nothing to publish.
