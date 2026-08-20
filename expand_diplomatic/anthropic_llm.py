"""Anthropic backend for expand-diplomatic (text-only messages)."""

from __future__ import annotations

import os
from typing import Optional

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _get_api_key(api_key: Optional[str]) -> str:
    key = (
        api_key
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("TRANSCRIBER_SHELL_ANTHROPIC_API_KEY")
        or ""
    ).strip()
    if not key:
        raise RuntimeError("Set ANTHROPIC_API_KEY (or pass api_key)")
    return key


def run_anthropic(
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
        import anthropic
    except ImportError as e:
        raise RuntimeError("Anthropic SDK not installed. pip install anthropic") from e

    key = _get_api_key(api_key)
    model_id = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
    timeout = float(os.environ.get("ANTHROPIC_TIMEOUT", "120") or 120)
    client = anthropic.Anthropic(api_key=key, timeout=timeout)
    kwargs: dict = {
        "model": model_id,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": contents}],
    }
    if system_instruction:
        kwargs["system"] = system_instruction
    msg = client.messages.create(**kwargs)
    parts: list[str] = []
    for block in msg.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip()
