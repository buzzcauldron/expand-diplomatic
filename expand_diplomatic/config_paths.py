"""Per-user config directory and paths for learned pairs and review queue."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_config_dir() -> Path:
    """Return the per-user config directory for expand-diplomatic.
    Creates the directory if it does not exist.
    - Linux: $XDG_CONFIG_HOME/expand-diplomatic or ~/.config/expand-diplomatic
    - macOS: ~/Library/Application Support/expand-diplomatic
    - Windows: %APPDATA%\\expand-diplomatic
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        dir_path = Path(base) / "expand-diplomatic"
    elif sys.platform == "darwin":
        dir_path = Path.home() / "Library" / "Application Support" / "expand-diplomatic"
    else:
        base = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        dir_path = Path(base) / "expand-diplomatic"
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def get_personal_learned_path() -> Path:
    """Path to the user's personal learned examples file (in config dir)."""
    return get_config_dir() / "learned_examples.json"


def get_review_queue_path() -> Path:
    """Path to the persisted review queue (staged pairs awaiting accept/reject)."""
    return get_config_dir() / "review_queue.json"
