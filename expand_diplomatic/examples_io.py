"""Lightweight load/save of example pairs (JSON). No run_gemini or lxml."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_MAX_LEARNED = 2000

# Simple cache for examples (path -> (mtime, examples))
_examples_cache: dict[str, tuple[float, list[dict]]] = {}
_learned_cache: dict[str, tuple[float, list[dict]]] = {}


def _get_cached(path: Path, cache: dict[str, tuple[float, list[dict]]]) -> list[dict] | None:
    """Return cached examples if file hasn't changed, else None."""
    key = str(path.resolve())
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if key in cache:
        cached_mtime, cached_data = cache[key]
        if cached_mtime == mtime:
            return cached_data
    return None


def _set_cache(path: Path, data: list[dict], cache: dict[str, tuple[float, list[dict]]]) -> None:
    """Store examples in cache."""
    key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
        # Limit cache size
        if len(cache) >= 8:
            cache.clear()
        cache[key] = (mtime, data)
    except OSError:
        pass


def clear_examples_cache() -> None:
    """Clear the examples cache (call after saving examples)."""
    _examples_cache.clear()
    _learned_cache.clear()


def get_learned_path(examples_path: str | Path) -> Path:
    """Path for learned examples file (alongside examples.json)."""
    p = Path(examples_path)
    return p.parent / "learned_examples.json"


def _parse_pairs(data: list) -> list[dict]:
    """Parse list of dicts into validated pairs."""
    out = []
    for item in data:
        if isinstance(item, dict) and "diplomatic" in item and "full" in item:
            p = {"diplomatic": str(item["diplomatic"]), "full": str(item["full"])}
            if item.get("pro"):
                p["pro"] = True
            out.append(p)
    return out


def _is_pro_model(model: str) -> bool:
    """True if model is a Pro variant (higher quality for training)."""
    return model is not None and "pro" in (model or "").lower()


def load_examples(path: str | Path, include_learned: bool = False) -> list[dict[str, str]]:
    """Load example pairs from JSON. Each item: {"diplomatic": "...", "full": "..."}. Cached by mtime."""
    p = Path(path)
    if not p.exists():
        return [] if not include_learned else load_learned(get_learned_path(p))
    # Check cache
    cached = _get_cached(p, _examples_cache)
    if cached is not None:
        out = list(cached)  # Copy to avoid mutation
    else:
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {p}: {e}") from e
        out = _parse_pairs(data if isinstance(data, list) else [])
        _set_cache(p, out, _examples_cache)
    if include_learned:
        out = out + load_learned(get_learned_path(p))
    return out


def load_learned(path: str | Path) -> list[dict[str, str]]:
    """Load learned example pairs from JSON. Cached by mtime. Pro-derived pairs first."""
    p = Path(path)
    if not p.exists():
        return []
    # Check cache
    cached = _get_cached(p, _learned_cache)
    if cached is not None:
        return list(cached)  # Copy to avoid mutation
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    pairs = _parse_pairs(data if isinstance(data, list) else [])
    pairs.sort(key=lambda x: (0 if x.get("pro") else 1))
    _set_cache(p, pairs, _learned_cache)
    return pairs


def add_learned_pairs(
    pairs: list[dict[str, str]],
    learned_path: str | Path,
    *,
    max_learned: int = DEFAULT_MAX_LEARNED,
    model: str | None = None,
) -> int:
    """
    Append new pairs to learned file. Dedupes by diplomatic text.
    Weights toward Pro model: pro-derived pairs overwrite flash; evict flash first.
    Caps total at max_learned. Returns count of newly added pairs.
    """
    p = Path(learned_path)
    raw = load_learned(p)
    # existing: diplomatic -> (full, pro)
    existing: dict[str, tuple[str, bool]] = {}
    for e in raw:
        d = (e.get("diplomatic") or "").strip()
        f = (e.get("full") or "").strip()
        if d:
            existing[d] = (f, bool(e.get("pro")))

    is_pro = _is_pro_model(model)
    added = 0
    for pair in pairs:
        d = (pair.get("diplomatic") or "").strip()
        f = (pair.get("full") or "").strip()
        if not d or d == f:
            continue
        if d not in existing:
            added += 1
            existing[d] = (f, is_pro)
        else:
            _, old_pro = existing[d]
            if is_pro and not old_pro:
                existing[d] = (f, True)
                added += 1
            elif not is_pro and old_pro:
                continue
            else:
                existing[d] = (f, is_pro)

    items = [
        {"diplomatic": k, "full": v, **({"pro": True} if pro else {})}
        for k, (v, pro) in existing.items()
    ]
    if len(items) > max_learned:
        pro_items = [x for x in items if x.get("pro")]
        flash_items = [x for x in items if not x.get("pro")]
        if len(pro_items) >= max_learned:
            items = pro_items[-max_learned:]
        else:
            keep_pro = len(pro_items)
            keep_flash = max_learned - keep_pro
            items = pro_items + flash_items[-keep_flash:]

    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    # Clear cache for this file
    key = str(p.resolve())
    _learned_cache.pop(key, None)
    return added


def save_examples(path: str | Path, examples: list[dict[str, str]]) -> None:
    """Write example pairs to JSON. Creates parent dirs if needed. Clears cache."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(
            [{"diplomatic": e["diplomatic"], "full": e["full"]} for e in examples],
            f,
            indent=2,
            ensure_ascii=False,
        )
    # Clear cache for this file
    key = str(p.resolve())
    _examples_cache.pop(key, None)
