"""Lightweight load/save of example pairs (JSON). No run_gemini or lxml."""

from __future__ import annotations

import json
from pathlib import Path


def load_examples(path: str | Path) -> list[dict[str, str]]:
    """Load example pairs from JSON. Each item: {"diplomatic": "...", "full": "..."}."""
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, dict) and "diplomatic" in item and "full" in item:
            out.append({"diplomatic": str(item["diplomatic"]), "full": str(item["full"])})
    return out


def save_examples(path: str | Path, examples: list[dict[str, str]]) -> None:
    """Write example pairs to JSON. Creates parent dirs if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(
            [{"diplomatic": e["diplomatic"], "full": e["full"]} for e in examples],
            f,
            indent=2,
            ensure_ascii=False,
        )
