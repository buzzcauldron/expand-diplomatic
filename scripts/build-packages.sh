#!/usr/bin/env bash
# Build sdist and wheel for x64 and Mac Silicon (universal py3-none-any).
# Use on macOS (Intel or Apple Silicon) or Linux x64; output works on all.
#
# Usage: ./scripts/build-packages.sh [--no-sdist]
# Output: dist/ with *.tar.gz and *.whl
# Requires: pip install build wheel (or pip install -e ".[dev]")

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

NO_SDIST=""
[[ "${1:-}" == "--no-sdist" ]] && { NO_SDIST=1; shift; }

export PYTHONPATH=""
if [[ -d "$PROJECT_ROOT/.venv" ]]; then
  VENV_PY="${PROJECT_ROOT}/.venv/bin/python"
  VENV_PIP="${PROJECT_ROOT}/.venv/bin/pip"
else
  VENV_PY="${PYTHON:-python3}"
  VENV_PIP="${PIP:-pip}"
fi

"$VENV_PIP" install -q build wheel 2>/dev/null || true

rm -rf "$PROJECT_ROOT/dist" "$PROJECT_ROOT/build"
mkdir -p "$PROJECT_ROOT/dist"

if [[ -z "$NO_SDIST" ]]; then
  echo "Building sdist..."
  "$VENV_PY" -m build --outdir "$PROJECT_ROOT/dist" --sdist
fi

echo "Building wheel (universal py3-none-any)..."
"$VENV_PY" -m build --outdir "$PROJECT_ROOT/dist" --wheel

echo "Done. Artifacts in dist/:"
ls -la "$PROJECT_ROOT/dist"
