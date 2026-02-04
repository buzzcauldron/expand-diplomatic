#!/usr/bin/env bash
# Build sdist and wheel for x64 and Mac Silicon (universal py3-none-any).
# Use on macOS (Intel or Apple Silicon) or Linux x64; output works on all.
#
# Usage: ./scripts/build-packages.sh [--no-sdist] [--sdist-only] [--install-deps]
#   --install-deps    Install build/wheel (pip) before building.
#   --sdist-only      Build only the source tarball (skip wheel).
# Output: dist/ with *.tar.gz and *.whl
# Requires: pip install build wheel (or pip install -e ".[dev]")

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

NO_SDIST=""
SDIST_ONLY=0
INSTALL_DEPS_ONLY=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-sdist) NO_SDIST=1; shift ;;
        --sdist-only) SDIST_ONLY=1; shift ;;
        --install-deps|-i) INSTALL_DEPS_ONLY=1; shift ;;
        *) echo "Unknown option: $1. Usage: $0 [--no-sdist] [--sdist-only] [--install-deps]" >&2; exit 1 ;;
    esac
done

if [[ -n "$NO_SDIST" && $SDIST_ONLY -eq 1 ]]; then
  echo "Error: --no-sdist and --sdist-only cannot be used together." >&2
  exit 1
fi

export PYTHONPATH=""
if [[ -d "$PROJECT_ROOT/.venv" ]]; then
  VENV_PY="${PROJECT_ROOT}/.venv/bin/python"
  VENV_PIP="${PROJECT_ROOT}/.venv/bin/pip"
else
  VENV_PY="${PYTHON:-python3}"
  VENV_PIP="${PIP:-pip}"
fi

if [[ $INSTALL_DEPS_ONLY -eq 1 ]]; then
  echo "Installing build dependencies (pip)..."
  "$VENV_PIP" install build wheel
  echo "Build dependencies installed."
  echo ""
fi

"$VENV_PIP" install -q build wheel 2>/dev/null || true

rm -rf "$PROJECT_ROOT/dist" "$PROJECT_ROOT/build"
mkdir -p "$PROJECT_ROOT/dist"

if [[ -z "$NO_SDIST" ]]; then
  echo "Building sdist..."
  "$VENV_PY" -m build --outdir "$PROJECT_ROOT/dist" --sdist
fi

if [[ $SDIST_ONLY -eq 0 ]]; then
  echo "Building wheel (universal py3-none-any)..."
  "$VENV_PY" -m build --outdir "$PROJECT_ROOT/dist" --wheel
fi

echo "Done. Artifacts in dist/:"
ls -la "$PROJECT_ROOT/dist"
