#!/usr/bin/env bash
# Test automatic expansion of one XML file (sample.xml).
# Requires GEMINI_API_KEY or GOOGLE_API_KEY (env or .env in project root).
# Usage: ./scripts/test_expand_one.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INPUT="${1:-$ROOT/sample.xml}"
OUTPUT="${2:-}"

if [[ ! -f "$INPUT" ]]; then
  echo "Error: input not found: $INPUT" >&2
  exit 1
fi

if [[ -z "${OUTPUT:-}" ]]; then
  OUTPUT="$(dirname "$INPUT")/$(basename "$INPUT" .xml)_expanded.xml"
fi

if [[ -z "${GEMINI_API_KEY:-}" && -z "${GOOGLE_API_KEY:-}" ]]; then
  echo "Error: set GEMINI_API_KEY or GOOGLE_API_KEY (or add to .env in project root)" >&2
  exit 1
fi

PYTHON="${ROOT}/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python"

echo "Expand: $INPUT -> $OUTPUT"
(cd "$ROOT" && "$PYTHON" -m expand_diplomatic --file "$INPUT" --out "$OUTPUT" --examples "$ROOT/examples.json")
echo "Done."
