# Debug & Stability Review

## Speed & Stability Fixes

### Expander
- **Cancel support**: Added `cancel_check` callback and `ExpandCancelled` exception. Expansion stops when user cancels (GUI) or callback returns True.
- **Run ID**: GUI uses `expand_run_id` so a stale `on_done` from an older expansion cannot overwrite a newer result.
- **Docstring**: Corrected `max_concurrent` default (2 for Gemini, 6 for local).

### Local LLM
- **Configurable timeout**: `OLLAMA_TIMEOUT` env (seconds, default 120, min 10) for Ollama API calls.
- **Retries**: No retries added (Ollama is local; transient failures fall back to rules).

### GUI
- **Cancel flow**: User Cancel sets `cancel_requested`; expander checks it between blocks; `on_done` treats `ExpandCancelled` as “Cancelled” (no error dialog).
- **Run ID**: Prevents overwriting output when user starts a new expand while a previous one finishes.
- **Thread safety**: All UI updates still use `app.root.after(0, ...)`.

## Container Build

### Dockerfile
- ** pip cache**: `--mount=type=cache,target=/root/.cache/pip` for faster rebuilds.
- **Ollama pull skip**: `SKIP_OLLAMA_PULL=1` build arg to skip model pull (faster CI).
- **Ollama wait loop**: Uses `while` instead of `seq` for portability; up to 30 iterations (60s).

### build-docker.sh
- **Typo fix**: `expand-diplomatic-multiarche` → `expand-diplomatic-multiarch`.

### run-container.sh
- **Build logic**: Single build step when `--build` or image missing; uses `-f Dockerfile`.
- **Env handling**: Loads `.env` when present in workspace; only passes env vars that are set in the host.
