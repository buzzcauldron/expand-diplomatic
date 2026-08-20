"""Groq backend for expand-diplomatic (OpenAI-compatible, text-only)."""

from __future__ import annotations

import os
from typing import Optional

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def _get_api_key(api_key: Optional[str]) -> str:
    key = (
        api_key
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("TRANSCRIBER_SHELL_GROQ_API_KEY")
        or ""
    ).strip()
    if not key:
        raise RuntimeError("Set GROQ_API_KEY (or pass api_key)")
    return key


def run_groq(
    contents: str,
    *,
    model: str | None = None,
    api_key: Optional[str] = None,
    system_instruction: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 16_000,
) -> str:
    """Return model text for a single user prompt."""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("OpenAI SDK not installed. pip install openai") from e

    key = _get_api_key(api_key)
    model_id = model or os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL
    timeout = float(os.environ.get("GROQ_TIMEOUT", "120") or 120)
    client = OpenAI(api_key=key, base_url=_GROQ_BASE_URL, timeout=timeout)
    messages: list[dict] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": contents})
    r = client.chat.completions.create(
        model=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=messages,
    )
    return (r.choices[0].message.content or "").strip()
