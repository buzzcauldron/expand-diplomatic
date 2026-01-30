# Speed & Efficiency Notes

## Implemented optimizations

- **ideasrule-style startup**: GUI uses `FALLBACK_MODELS` at import; Gemini model list fetched in background after window appears (avoids blocking on API/network).
- **Prompt prefix**: Built once per document, reused for all blocks (avoids per-block string concat).
- **Parallel expansion**: `ThreadPoolExecutor` for concurrent Gemini/Ollama calls (configurable via Parallel / `EXPANDER_MAX_CONCURRENT`).
- **Streaming throttle**: In parallel mode with many blocks (>8), `partial_result_callback` runs every 2nd block to reduce XML serialization cost.
- **Examples I/O**: Shared `_parse_pairs` helper; lean JSON load/save.
- **Local rules pre-sort**: Sorted pairs computed once per document when backend=local; passed to each block (avoids O(n log n) sort per block).
- **Block-ranges cache**: GUI caches `get_block_ranges` per panel content to avoid re-parsing on repeated clicks/syncs.
- **Shared helpers**: `_local_name` (expander), `_format_examples_for_prompt` (expander), `_get_block_at_click` (GUI) — reduce duplication.

## Bottlenecks (expected)

- **Gemini API**: Main cost; rate limits (429) suggest lowering Parallel.
- **Ollama**: Local; latency depends on model size and hardware.
- **XML parsing**: Per-call parsers (lxml not thread-safe for shared parser).
- **Auto-learn**: Runs in background; no user-facing impact.

## High-end GPU detection

When a high-end GPU is detected (NVIDIA or AMD with >= 8GB VRAM) **and on AC power** (not battery):

- **NVIDIA**: `nvidia-smi`
- **AMD**: `rocm-smi`, `amd-smi`, or Linux sysfs `/sys/class/drm/card*/device/mem_info_vram_total`

- **Local parallelism**: Default 12 instead of 6.
- **Ollama context**: `num_ctx=8192` for larger prompts (more examples).
- **GUI**: Layered Training default on; Parallel 12 when Backend=Local; spinbox to 16.
- **Auto-learn**: Cap 4000 learned pairs instead of 2000.

Override: `EXPANDER_AGGRESSIVE_LOCAL=0` to disable; `=1` to force on (even on battery).
`EXPANDER_AGGRESSIVE_ON_BATTERY=1` allows aggressive when on battery (if GPU ok).

## Tuning

- `EXPANDER_MAX_CONCURRENT`: Default 2 (Gemini), 6 (local), 12 (local + high-end GPU). Lower if hitting 429.
- `GEMINI_TIMEOUT`: Per-request timeout (default 120s). Pro models auto-use at least 300s.
- Pro model timeout: `_get_timeout_for_model` bumps timeout to 300s (or `GEMINI_TIMEOUT_PRO_MIN`) when model contains "pro".
- Timeout retry: one automatic retry on `TimeoutError` (transient).
- Batch with Pro: parallel capped at 2 to avoid overload.
- `OLLAMA_TIMEOUT`: For local backend (default 120s).
