"""
Fetch and cache available Gemini models from the API.

This module queries the Gemini API to discover currently available models,
caching results to minimize API calls. Falls back to a hardcoded list if
the API is unreachable.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

_CACHE_FILE = Path.home() / ".cache" / "expand_diplomatic" / "gemini_models.txt"
_CACHE_TTL_SECONDS = 86400  # 24 hours

# Fallback models (ordered by speed: fastest to slowest)
_FALLBACK_MODELS = (
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3-pro-preview",
)

# Default model (Gemini 3 Flash)
DEFAULT_MODEL = "gemini-3-flash-preview"


def _is_cache_valid() -> bool:
    """Check if cached model list exists and is not expired."""
    if not _CACHE_FILE.exists():
        return False
    age = time.time() - _CACHE_FILE.stat().st_mtime
    return age < _CACHE_TTL_SECONDS


def _read_cache() -> list[str]:
    """Read cached model list."""
    try:
        return [line.strip() for line in _CACHE_FILE.read_text().splitlines() if line.strip()]
    except Exception:
        return []


def _write_cache(models: list[str]) -> None:
    """Write model list to cache."""
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text("\n".join(models) + "\n")
    except Exception:
        pass  # Cache write failure is non-critical


def _fetch_from_api(api_key: Optional[str] = None) -> list[str]:
    """
    Fetch available Gemini models from the API.
    Returns empty list on failure.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return []

    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return []

    try:
        # Create client with short timeout
        client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=10_000),  # 10 seconds
        )
        
        # List models
        response = client.models.list()
        models = []
        
        for model in response:
            # Filter for generateContent-capable models
            if hasattr(model, "supported_generation_methods"):
                if "generateContent" in model.supported_generation_methods:
                    # Extract model name (e.g., "models/gemini-2.5-flash" -> "gemini-2.5-flash")
                    name = model.name.split("/")[-1] if "/" in model.name else model.name
                    if name.startswith("gemini-"):
                        models.append(name)
        
        return sorted(models, key=_speed_sort_key)
    except Exception:
        return []


def _speed_sort_key(model_name: str) -> tuple[int, str]:
    """
    Sort key for ordering models by speed (fastest first).
    Returns (priority, name) where lower priority = faster.
    """
    name_lower = model_name.lower()
    
    # Priority order (lower = faster)
    if "flash-lite" in name_lower:
        return (0, model_name)
    elif "flash" in name_lower and "3" in name_lower:
        return (1, model_name)
    elif "flash" in name_lower and "2.0" in name_lower:
        return (2, model_name)
    elif "flash" in name_lower and "2.5" in name_lower:
        return (3, model_name)
    elif "pro" in name_lower and "2.5" in name_lower:
        return (4, model_name)
    elif "pro" in name_lower and "3" in name_lower:
        return (5, model_name)
    else:
        # Unknown models go to end
        return (99, model_name)


def get_available_models(api_key: Optional[str] = None, force_refresh: bool = False) -> tuple[str, ...]:
    """
    Get list of available Gemini models, ordered by speed (fastest first).
    
    Args:
        api_key: Optional API key for Gemini. If None, uses GEMINI_API_KEY env var.
        force_refresh: If True, bypass cache and fetch from API.
    
    Returns:
        Tuple of model names, ordered by speed. Falls back to hardcoded list on failure.
    """
    # Check cache first (unless force_refresh)
    if not force_refresh and _is_cache_valid():
        cached = _read_cache()
        if cached:
            return tuple(cached)
    
    # Fetch from API
    models = _fetch_from_api(api_key)
    
    if models:
        # Success - cache and return
        _write_cache(models)
        return tuple(models)
    
    # Fallback to hardcoded list
    return _FALLBACK_MODELS


def clear_cache() -> None:
    """Clear the cached model list, forcing a refresh on next call."""
    try:
        if _CACHE_FILE.exists():
            _CACHE_FILE.unlink()
    except Exception:
        pass
