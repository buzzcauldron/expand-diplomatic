"""Lightweight load/save of example pairs (JSON). No run_gemini or lxml."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_MAX_LEARNED = 2000


def get_learned_path(examples_path: str | Path) -> Path:
    """Path for learned examples file (alongside examples.json)."""
    p = Path(examples_path)
    return p.parent / "learned_examples.json"


def _parse_pairs(data: list) -> list[dict[str, str]]:
    """Parse list of dicts into validated pairs."""
    out = []
    for item in data:
        if isinstance(item, dict) and "diplomatic" in item and "full" in item:
            out.append({"diplomatic": str(item["diplomatic"]), "full": str(item["full"])})
    return out


def load_examples(path: str | Path, include_learned: bool = False) -> list[dict[str, str]]:
    """Load example pairs from JSON. Each item: {"diplomatic": "...", "full": "..."}."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {p}: {e}") from e
    out = _parse_pairs(data if isinstance(data, list) else [])
    if include_learned:
        out = out + load_learned(get_learned_path(p))
    return out


def load_learned(path: str | Path) -> list[dict[str, str]]:
    """Load learned example pairs from JSON."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return _parse_pairs(data if isinstance(data, list) else [])


def add_learned_pairs(
    pairs: list[dict[str, str]],
    learned_path: str | Path,
    *,
    max_learned: int = DEFAULT_MAX_LEARNED,
) -> int:
    """
    Append new pairs to learned file. Dedupes by diplomatic text (keep last).
    Caps total at max_learned (FIFO evict). Returns count of newly added pairs.
    """
    p = Path(learned_path)
    existing = {e["diplomatic"]: e["full"] for e in load_learned(p)}
    added = 0
    for pair in pairs:
        d = (pair.get("diplomatic") or "").strip()
        f = (pair.get("full") or "").strip()
        if not d or d == f:
            continue
        if d not in existing:
            added += 1
        existing[d] = f
    # Enforce cap: keep most recent (last N)
    items = [{"diplomatic": k, "full": v} for k, v in existing.items()]
    if len(items) > max_learned:
        items = items[-max_learned:]
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    return added


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
