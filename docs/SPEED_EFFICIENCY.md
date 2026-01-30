# Speed & Efficiency Notes

## Implemented optimizations

- **Prompt prefix**: Built once per document, reused for all blocks (avoids per-block string concat).
- **Parallel expansion**: `ThreadPoolExecutor` for concurrent Gemini/Ollama calls (configurable via Parallel / `EXPANDER_MAX_CONCURRENT`).
- **Streaming throttle**: In parallel mode with many blocks (>8), `partial_result_callback` runs every 2nd block to reduce XML serialization cost.
- **Examples I/O**: Shared `_parse_pairs` helper; lean JSON load/save.

## Bottlenecks (expected)

- **Gemini API**: Main cost; rate limits (429) suggest lowering Parallel.
- **Ollama**: Local; latency depends on model size and hardware.
- **XML parsing**: Per-call parsers (lxml not thread-safe for shared parser).
- **Auto-learn**: Runs in background; no user-facing impact.

## Tuning

- `EXPANDER_MAX_CONCURRENT`: Default 2 (Gemini), 6 (local). Lower if hitting 429.
- `GEMINI_TIMEOUT`: Per-request timeout (default 120s).
- `OLLAMA_TIMEOUT`: For local backend (default 120s).
