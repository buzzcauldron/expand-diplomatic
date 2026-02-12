# Strategies for free API key speeds

Free-tier Gemini API keys have strict rate limits (requests per minute, tokens per minute). These strategies reduce 429s and make expansion feel faster and more reliable.

---

## 1. Fewer API calls

**Whole-document mode (Gemini only)**  
- **GUI**: Choose **Whole doc** instead of **Block-by-block**.  
- **CLI**: `--whole-doc` (with `--backend gemini`).  
- One request per file instead of one per block, so you stay under RPM limits and often finish sooner.

**Caveat**: Very large files or long documents can hit context/token limits or time out. Use block-by-block for those.

---

## 2. Lower parallelism

**Single request at a time**  
- **GUI**: Uncheck **Paid API key** (or leave unchecked for free tier). Single-file expand then uses **Parallel 1** (sequential blocks). Batch stays sequential.  
- **CLI / .env**: Set `EXPANDER_MAX_CONCURRENT=1` so only one block request is in flight.  
- Free tier often allows only 1–2 concurrent requests; sequential avoids 429 bursts.

---

## 3. Smaller prompts (faster + cheaper)

**Cap examples per request**  
- **GUI**: Set **Max ex** to a small number (e.g. 5–15).  
- **CLI**: `--max-examples 10`.  
- Fewer examples = smaller prompts = less latency and fewer tokens, with little loss in quality if your best pairs are selected (e.g. **Strategy: longest-first**).

---

## 4. Use a faster model

**Flash vs Pro**  
- Free tier usually includes **Gemini Flash** (e.g. `gemini-2.0-flash`). Use it by default.  
- Pro models are slower and have stricter limits; switch to Pro only when you need higher quality and can accept more 429s or slower runs.

---

## 5. Retries and backoff (already in place)

- **429**: The client retries up to 2 extra times with an 8-second backoff (`run_gemini.py`).  
- **Timeout**: One extra retry after a short pause.  
- If you still see 429s, lower concurrency (see above) and prefer whole-doc or smaller batches.

---

## 6. Rules-only where possible

**No API call**  
- **GUI**: **Backend: rules** (expand using only your example pairs, no Gemini).  
- **CLI**: `--backend rules`.  
- Instant and free; use for documents that are mostly covered by your training pairs, or for a first pass before a single Gemini pass.

---

## 7. Batch: sequential and small

- **GUI**: For batch, leave **Paid API key** unchecked so files are processed one at a time.  
- Process a small folder first; if you hit 429, wait a minute or reduce **Max ex** / use **Whole doc** for smaller requests.

---

## Quick checklist (free key)

| Goal              | Setting / action                          |
|-------------------|--------------------------------------------|
| Fewer 429s        | Parallel 1, or `EXPANDER_MAX_CONCURRENT=1` |
| Fewer calls       | **Whole doc** when file size allows        |
| Faster responses  | **Max ex** 5–15, Flash model               |
| No API use        | **Backend: rules** when examples suffice   |
| Retries           | Already on (429 + timeout); keep defaults  |
