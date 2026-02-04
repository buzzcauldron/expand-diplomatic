"""Review queue and personal learned pairs: staging, persistence, and promotion."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .config_paths import get_personal_learned_path, get_review_queue_path

# Minimum length for diplomatic/full to avoid junk
_MIN_DIP_LEN = 1
_MIN_FULL_LEN = 1
# Prompt leakage markers: skip if full text looks like model echoed the prompt
_LEAKAGE_PATTERNS = re.compile(
    r"(?i)(Diplomatic\s*:\s*|Full\s*:\s*|Output\s*:\s*|Here\s+is\s+the\s+expanded)"
)
# Mostly punctuation: reject if diplomatic or full is mostly non-letter
_PUNCT_RATIO_THRESHOLD = 0.8


def _punct_ratio(text: str) -> float:
    """Ratio of non-letter non-space characters to total non-space."""
    if not text or not text.strip():
        return 0.0
    no_ws = "".join(text.split())
    if not no_ws:
        return 0.0
    non_letter = sum(1 for c in no_ws if not c.isalpha())
    return non_letter / len(no_ws)


def filter_quality(pairs: list[dict[str, str]]) -> list[dict[str, str]]:
    """Filter out pairs that likely degrade data: empty, too short, leakage, mostly punctuation.
    Returns only pairs that pass. Dedup by appearance_key is left to the caller."""
    from .examples_io import appearance_key

    seen_keys: set[str] = set()
    out: list[dict[str, str]] = []
    for pair in pairs:
        diplomatic = (pair.get("diplomatic") or "").strip()
        full = (pair.get("full") or "").strip()
        if not diplomatic or not full or diplomatic == full:
            continue
        if len(diplomatic) < _MIN_DIP_LEN or len(full) < _MIN_FULL_LEN:
            continue
        if _punct_ratio(diplomatic) >= _PUNCT_RATIO_THRESHOLD or _punct_ratio(full) >= _PUNCT_RATIO_THRESHOLD:
            continue
        if _LEAKAGE_PATTERNS.search(full):
            continue
        key = appearance_key(diplomatic)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append({"diplomatic": diplomatic, "full": full})
    return out


def load_review_queue(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the review queue from disk. Returns a list of staged pairs.
    Each item: diplomatic, full, source (model), timestamp, path (optional).
    """
    p = path or get_review_queue_path()
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and "diplomatic" in item and "full" in item]


def save_review_queue(items: list[dict[str, Any]], path: Path | None = None) -> None:
    """Persist the review queue to disk."""
    p = path or get_review_queue_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def add_to_review_queue(
    pairs: list[dict[str, str]],
    *,
    source: str = "",
    path: Path | None = None,
    queue_path: Path | None = None,
) -> int:
    """Append new pairs to the review queue after quality gates. Each pair gets source and timestamp.
    Returns the number of items appended (after quality filter and dedup by appearance_key).
    """
    from .examples_io import appearance_key

    pairs = filter_quality(pairs)
    existing = load_review_queue(queue_path)
    existing_keys = {appearance_key((e.get("diplomatic") or "").strip()) for e in existing}
    added = 0
    for pair in pairs:
        diplomatic = (pair.get("diplomatic") or "").strip()
        full = (pair.get("full") or "").strip()
        if not diplomatic or not full or diplomatic == full:
            continue
        key = appearance_key(diplomatic)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        existing.append({
            "diplomatic": diplomatic,
            "full": full,
            "source": source,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "path": str(path) if path else None,
        })
        added += 1
    if added:
        save_review_queue(existing, queue_path)
    return added


def load_personal_learned(path: Path | None = None) -> list[dict[str, str]]:
    """Load personal learned pairs from config dir."""
    p = path or get_personal_learned_path()
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [
        {"diplomatic": str(item.get("diplomatic", "")), "full": str(item.get("full", ""))}
        for item in data
        if isinstance(item, dict) and item.get("diplomatic") is not None and item.get("full") is not None
    ]


def save_personal_learned(items: list[dict[str, str]], path: Path | None = None) -> None:
    """Save personal learned pairs to config dir."""
    p = path or get_personal_learned_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump([{"diplomatic": e["diplomatic"], "full": e["full"]} for e in items], f, indent=2, ensure_ascii=False)
