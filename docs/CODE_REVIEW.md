# Code Review

Review date: 2026-01-29

## Overall assessment

**Strengths:** Clear structure, good separation of concerns, robust error handling, caching where it helps. The expander supports both whole-document and block-by-block flows cleanly.

**Areas to watch:** A few minor issues and possible improvements noted below.

---

## expand_diplomatic/expander.py

### ✓ Good
- `_local_name`, `_format_examples_for_prompt` shared to reduce duplication
- Block-by-block and whole-document paths are clearly separated
- Modality system is modular and easy to extend
- `ExpandCancelled` for clean cancel handling

### ✓ Fixed
1. ~~Unused parameter `input_file_path`~~ — Removed from `_expand_whole_document`.
2. ~~Whole-doc output validation~~ — Added `etree.fromstring` validation; raises `ValueError` with helpful message on parse failure.

### ✓ Robust
- `get_block_ranges` fallback for namespaced XML
- `etree.XMLParser` created per call (thread-safe)

---

## expand_diplomatic/examples_io.py

### ✓ Good
- mtime-based caching avoids redundant JSON reads
- Pro-model weighting in `add_learned_pairs`
- Cache eviction when `len(cache) >= 8`

### ⚠ Minor
1. **`load_examples` with missing path:** When `path` does not exist and `include_learned=True`, it loads only learned. That’s intentional but not obvious from the docstring; a short note would help.

### ✓ Robust
- `_parse_pairs` handles malformed items safely
- Cache cleared on write to avoid stale data

---

## expand_diplomatic/local_llm.py

### ✓ Good
- Ollama with rule-based fallback
- `sorted_pairs` avoids repeated sorting
- `high_end_gpu` for larger context

### ⚠ Minor
1. **Rule substitution order:** `run_local_rules` uses longest-match-first, which is good for overlaps. Replacing with `.replace(d, f)` can still create new overlaps; for most Latin abbreviation workloads this is acceptable.

---

## expand_diplomatic/gemini_models.py

### ✓ Good
- 24-hour cache reduces API usage
- Fallback list when the API fails
- Speed-based sort key

### ✓ Robust
- Import and network errors handled; fallback list used

---

## run_gemini.py

### ✓ Good
- 429 retry with backoff
- Clear error messages for common failures
- `max_output_tokens=40000` for whole-document use

### ✓ Fixed
1. ~~Timeout for large docs~~ — `.env.example` and README now note increasing `GEMINI_TIMEOUT` for very large documents.

---

## gui.py

### ✓ Good
- Threading for non-blocking expansion
- Queue for multiple files
- Block sync and companion file loading
- `expand_run_id` avoids stale callbacks

### ✓ Fixed
1. **`whole_document_var` guard** — Defensive fallback remains; var is always created.
2. ~~Progress with whole-document~~ — Status now shows "Expanding whole document…" when whole-doc mode is active.

### ✓ Robust
- `cancel_check` used in block-by-block path
- Hang detection with status update

---

## Security / robustness

- API keys from env / `.env`; `.env` in `.gitignore`
- No obvious path traversal issues
- User XML passed to the model; output is not sanitized, but it is only displayed/saved by the user

---

## Performance

- Examples cached by mtime
- Block-ranges cached in GUI
- Pre-sorted pairs for local rules
- Parallel block processing when `whole_document=False`

---

## Recommendations (implemented)

1. ✓ **expander:** Removed unused `input_file_path` from `_expand_whole_document`.
2. ✓ **expander:** Added XML validation; raises `ValueError` on parse failure.
3. ✓ **run_gemini:** `.env.example` and README note `GEMINI_TIMEOUT` for large documents.
4. ✓ **gui:** Status bar shows "Expanding whole document…" when whole-doc mode is active.
