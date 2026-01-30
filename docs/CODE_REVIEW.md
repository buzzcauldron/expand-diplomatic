# Code review

Review scope: `gui.py`, `run_gemini.py`, `expand_diplomatic` (expander, __main__, local_llm, examples_io), scripts, config.

---

## Summary

- **Structure:** Clear separation (GUI, CLI, expander, run_gemini, local_llm, examples_io). Lazy imports keep startup fast.
- **APIs:** Consistent use of `backend` (gemini | local), `modality`, `examples` JSON, env-based config.
- **Error handling:** Generally solid; a few gaps were fixed below.

---

## Changes made

1. **Removed dead code (GUI)**  
   `_api_key_error_message()` was never used; the GUI uses `_show_api_error_dialog` instead. Removed.

2. **Ollama `error` in JSON (local_llm)**  
   Ollama can return `{"error": "..."}`. We now check `out.get("error")` and raise `RuntimeError` with that message instead of returning empty text.

3. **Examples JSON loading (examples_io)**  
   - `load_examples` now raises `ValueError` with a clear message on `json.JSONDecodeError`.  
   - GUI: `_refresh_train_list`, `_run_expand_internal`, `_on_add_example` catch `ValueError` and show status/messagebox.  
   - CLI: `_run_train` and `_run_expand` catch `ValueError`, print to stderr, and exit 1.

4. **Ctrl+Return binding (GUI)**  
   Add-pair binding now returns `"break"` to avoid unintended event propagation.

5. **Graceful handling of invalid examples**  
   Malformed `examples.json` no longer crashes the GUI or produces opaque CLI tracebacks.

---

## Notes and suggestions

### Robustness

- **Local backend, Expand enabled:** With backend **local**, Expand stays enabled during expansion. Rapid repeated clicks can start overlapping runs; the last result wins. Acceptable given the “expand as option” requirement.
- **Gemini timeout:** Each `generate_content` call is limited by `GEMINI_TIMEOUT` (default 120s). The worker thread is not cancelled on timeout; it may still run until the HTTP layer finishes.
- **Batch CLI:** A single failing file (e.g. unreadable or invalid XML) aborts the whole batch. Consider per-file try/except and continuing with the next file if you want more resilience.

### Possible improvements

- **Duplicate pairs:** `save_examples` does not deduplicate. Adding the same diplomatic→full twice creates duplicates. Optional: normalize/deduplicate when saving or when loading.
- **Ollama base URL:** `run_local` uses `http://localhost:11434` only. Supporting `OLLAMA_BASE_URL` (or similar) would help Docker / remote Ollama setups.
- **Progress when `total == 0`:** If there are no blocks to expand, we never call `progress_callback`. The GUI keeps “Expanding…” until “Done.” Fine as-is; could add an explicit “0/0” or “No blocks” update if desired.

### Security and config

- **API keys:** Sourced from env / `.env` or session; not logged. `.env` is gitignored. Good.
- **Paths:** User-controlled paths (files, examples) are used as-is. No path traversal checks; usage is assumed trusted (local/user CLI and GUI).

### Tests

- No automated tests found. Consider `pytest` for `examples_io`, `local_llm` (e.g. rules, Ollama error handling), and `expander` (dry_run, block discovery) to guard regressions.

---

## File-level checklist

| File | Status |
|------|--------|
| `gui.py` | Dead code removed, examples errors handled, Ctrl+Return fixed |
| `run_gemini.py` | Timeout and `_do_run_gemini` structure look good |
| `expand_diplomatic/expander.py` | Progress callback, block collection, modalities look good |
| `expand_diplomatic/__main__.py` | Examples `ValueError` handled; train/expand CLI consistent |
| `expand_diplomatic/local_llm.py` | Ollama `error` handling added |
| `expand_diplomatic/examples_io.py` | `ValueError` on invalid JSON, GUI/CLI handle it |
| `scripts/expand_deeds_batch.sh` | Uses `--batch` + `--out-dir`, skips METS; robust |
