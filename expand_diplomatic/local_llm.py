"""Local backends: Ollama (optional) and rule-based fallback using training examples."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def _ollama_timeout() -> int:
    v = os.environ.get("OLLAMA_TIMEOUT", "").strip()
    if v:
        try:
            return max(10, int(v))
        except ValueError:
            pass
    return 120


def run_local_rules(
    text: str,
    examples: list[dict[str, str]] | None = None,
    *,
    sorted_pairs: list[tuple[str, str]] | None = None,
) -> str:
    """
    Expand using training examples only: replace each diplomatic→full in text.
    Longest matches first to avoid overlapping substitutions. No Ollama or API.
    Pass sorted_pairs to skip per-call sort when same examples used for many blocks.
    """
    if not text or not text.strip():
        return text
    if sorted_pairs is not None:
        pairs = sorted_pairs
    elif examples:
        pairs = sorted(
            [(ex["diplomatic"], ex["full"]) for ex in examples],
            key=lambda p: len(p[0]),
            reverse=True,
        )
    else:
        return text
    out = text
    for d, f in pairs:
        if not d:
            continue
        # Replace whole-word / standalone occurrences first; then any occurrence
        out = out.replace(d, f)
    return out


def run_ollama(
    prompt: str,
    model: str = "llama3.2",
    base_url: str = "http://localhost:11434",
    *,
    system: str | None = None,
    high_end_gpu: bool = False,
) -> str:
    """
    Send prompt to Ollama /api/generate and return the generated text.
    Raises RuntimeError if Ollama is unreachable or returns an error.
    high_end_gpu: when True, use larger context (num_ctx=8192) for more examples.
    """
    url = f"{base_url.rstrip('/')}/api/generate"
    body: dict = {"model": model, "prompt": prompt, "stream": False}
    if system is not None:
        body["system"] = system
    if high_end_gpu:
        body["options"] = {"num_ctx": 8192}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    timeout = _ollama_timeout()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(
            "Ollama not reachable. Start Ollama (e.g. ollama serve) and pull a model (e.g. ollama pull llama3.2)."
        ) from e
    except json.JSONDecodeError as e:
        raise RuntimeError("Ollama returned invalid JSON.") from e
    err = out.get("error")
    if err:
        raise RuntimeError(f"Ollama error: {err}")
    text = out.get("response") or ""
    return text.strip()


def run_local(
    text: str,
    examples: list[dict[str, str]],
    prompt: str,
    model: str = "llama3.2",
    base_url: str = "http://localhost:11434",
    *,
    sorted_pairs: list[tuple[str, str]] | None = None,
    high_end_gpu: bool = False,
) -> str:
    """
    Try Ollama first; if unreachable, fall back to rule-based expansion using examples.
    Training examples are always applied as a final pass so they override model guesses
    (any diplomatic form in the output is replaced by the canonical example).
    sorted_pairs: optional pre-sorted (dip, full) to avoid per-block sort.
    high_end_gpu: when True, use larger context for Ollama (aggressive local training).
    """
    try:
        raw = run_ollama(
            prompt, model=model, base_url=base_url,
            high_end_gpu=high_end_gpu,
        )
    except RuntimeError:
        return run_local_rules(text, examples=examples, sorted_pairs=sorted_pairs)
    # Apply training examples as correct overlay: override any diplomatic forms in model output
    return run_local_rules(raw, examples=examples, sorted_pairs=sorted_pairs)
