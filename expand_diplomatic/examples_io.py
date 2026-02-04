"""Lightweight load/save of example pairs (JSON). No run_gemini or lxml."""

from __future__ import annotations

import heapq
import json
import re
import unicodedata
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


def select_examples_for_prompt(
    examples: list[dict[str, str]],
    max_examples: int | None = None,
    strategy: str = "longest-first",
) -> list[dict[str, str]]:
    """Select a subset of examples for injection into the prompt (Gemini/Ollama).
    - max_examples: cap (None = use all).
    - strategy: 'longest-first' (prefer longer diplomatic forms) or 'most-recent' (last N in list).
    """
    if not examples:
        return []
    if max_examples is None or max_examples >= len(examples):
        return list(examples)
    if strategy == "most-recent":
        return list(examples[-max_examples:])
    # longest-first: nlargest avoids full sort when len(examples) >> max_examples
    key_fn = lambda e: len((e.get("diplomatic") or "").strip())
    return heapq.nlargest(max_examples, examples, key=key_fn)


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


_WS_RE = re.compile(r"\s+")
_ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\ufeff"}
_DASHES = {
    "\u2010",  # hyphen
    "\u2011",  # non-breaking hyphen
    "\u2012",  # figure dash
    "\u2013",  # en dash
    "\u2014",  # em dash
    "\u2212",  # minus sign
}
_SINGLE_QUOTES = {"\u2018", "\u2019", "\u201b", "\u2032"}
_DOUBLE_QUOTES = {"\u201c", "\u201d", "\u201f", "\u2033"}

# One-shot translation for appearance_key (dashes, quotes, spaces)
_APPEARANCE_KEY_TRANS = str.maketrans(
    {ch: "-" for ch in _DASHES}
    | {ch: "'" for ch in _SINGLE_QUOTES}
    | {ch: '"' for ch in _DOUBLE_QUOTES}
    | {"\u00a0": " ", "\u202f": " ", "\u2009": " "}
)


def appearance_key(text: str) -> str:
    """Normalize text for "looks the same" matching (not strict Unicode equality).

    Used to dedupe/attach training pairs even when the source text uses different
    Unicode forms (e.g. decomposed accents, NBSP vs space, curly quotes, dash variants).
    """
    if text is None:
        return ""
    normalized = str(text)
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = "".join(ch for ch in normalized if ch not in _ZERO_WIDTH)
    normalized = normalized.translate(_APPEARANCE_KEY_TRANS)
    normalized = _WS_RE.sub(" ", normalized).strip()
    return normalized


def load_examples(
    path: str | Path,
    include_learned: bool = False,
    include_personal_learned: bool = True,
) -> list[dict[str, str]]:
    """Load example pairs with deterministic layering: project examples, then project learned, then personal learned.
    Each item: {"diplomatic": "...", "full": "..."}. First occurrence of an appearance_key wins (project overrides later).
    If path does not exist and include_learned=True, returns only learned (and optionally personal) pairs."""
    seen: set[str] = set()
    out: list[dict[str, str]] = []

    def add_layer(pairs: list[dict]) -> None:
        for e in pairs:
            d = (e.get("diplomatic") or "").strip()
            if not d:
                continue
            key = appearance_key(d)
            if key in seen:
                continue
            seen.add(key)
            out.append({"diplomatic": d, "full": str(e.get("full", "")).strip()})

    p = Path(path)
    if p.exists():
        cached = _get_cached(p, _examples_cache)
        if cached is not None:
            add_layer(list(cached))
        else:
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in {p}: {e}") from e
            project = _parse_pairs(data if isinstance(data, list) else [])
            _set_cache(p, project, _examples_cache)
            add_layer(project)
    if include_learned:
        add_layer(load_learned(get_learned_path(p)))
    if include_personal_learned:
        try:
            from .learning import load_personal_learned
            add_layer(load_personal_learned())
        except Exception:
            pass
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
    local_diplomatic: set[str] | None = None,
) -> int:
    """
    Append new pairs to learned file. Dedupes by diplomatic text.
    Weights toward Pro model: pro-derived pairs overwrite flash; evict flash first.
    If local_diplomatic is provided (diplomatic forms from main examples.json),
    those pairs have huge weight: never overwrite them with new (e.g. Gemini) guesses.
    Caps total at max_learned. Returns count of newly added pairs.
    """
    p = Path(learned_path)
    raw = load_learned(p)
    # existing: appearance_key(diplomatic) -> (original_d, full, pro)
    existing: dict[str, tuple[str, str, bool]] = {}
    for e in raw:
        existing_diplomatic = (e.get("diplomatic") or "").strip()
        existing_full = (e.get("full") or "").strip()
        if existing_diplomatic:
            existing[appearance_key(existing_diplomatic)] = (existing_diplomatic, existing_full, bool(e.get("pro")))

    local = {appearance_key(x) for x in (local_diplomatic or set()) if str(x).strip()}
    is_pro = _is_pro_model(model)
    added = 0
    for pair in pairs:
        diplomatic_text = (pair.get("diplomatic") or "").strip()
        full_text = (pair.get("full") or "").strip()
        if not diplomatic_text or diplomatic_text == full_text:
            continue
        diplomatic_key = appearance_key(diplomatic_text)
        # Huge weight on local pairs: never overwrite main examples with Gemini guesses
        if diplomatic_key in local:
            continue
        if diplomatic_key not in existing:
            added += 1
            existing[diplomatic_key] = (diplomatic_text, full_text, is_pro)
        else:
            _, _, old_pro = existing[diplomatic_key]
            if is_pro and not old_pro:
                existing[diplomatic_key] = (diplomatic_text, full_text, True)
                added += 1
            elif not is_pro and old_pro:
                continue
            else:
                existing[diplomatic_key] = (diplomatic_text, full_text, is_pro)

    items = [
        {"diplomatic": d, "full": f, **({"pro": True} if pro else {})}
        for _, (d, f, pro) in existing.items()
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
