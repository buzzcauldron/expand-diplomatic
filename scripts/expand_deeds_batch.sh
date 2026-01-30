#!/usr/bin/env bash
# Expand XMLs from "Deeds test material" (Downloads). Writes to .../expanded/ per subdir.
# Excludes METS.xml and files under expanded/.
#
# Usage: ./scripts/expand_deeds_batch.sh [BASE_DIR]
#   BASE_DIR default: "$HOME/Downloads/Deeds test material"
#
# Env: BACKEND (gemini|local), MODALITY (full|conservative|normalize|aggressive),
#      EXAMPLES (path to examples.json). For gemini, set GEMINI_API_KEY or GOOGLE_API_KEY.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE="${1:-$HOME/Downloads/Deeds test material}"
EXAMPLES="${EXAMPLES:-$ROOT/examples.json}"
BACKEND="${BACKEND:-local}"
MODALITY="${MODALITY:-full}"

if [[ ! -d "$BASE" ]]; then
  echo "Error: base dir not found: $BASE" >&2
  exit 1
fi

if [[ "$BACKEND" == "gemini" ]] && [[ -z "${GEMINI_API_KEY:-}" && -z "${GOOGLE_API_KEY:-}" ]]; then
  echo "Error: set GEMINI_API_KEY or GOOGLE_API_KEY for backend gemini" >&2
  exit 1
fi

PYTHON="${ROOT}/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python"

for sub in "york registers new" "phillipps collection of english charters" "fenestella"; do
  dir="$BASE/$sub"
  out="$dir/expanded"
  if [[ ! -d "$dir" ]]; then continue; fi

  files=()
  while IFS= read -r -d '' f; do
    files+=("$f")
  done < <(find "$dir" -maxdepth 1 -name "*.xml" ! -name "METS.xml" -print0 2>/dev/null) || true

  if [[ ${#files[@]} -eq 0 ]]; then
    echo "Skip $sub (no XMLs)"
    continue
  fi

  echo "Expand $sub -> $out (${#files[@]} files, backend=$BACKEND, modality=$MODALITY)"
  mkdir -p "$out"
  (cd "$ROOT" && "$PYTHON" -m expand_diplomatic \
    --backend "$BACKEND" \
    --modality "$MODALITY" \
    --batch "${files[@]}" \
    --out-dir "$out" \
    --examples "$EXAMPLES") || true
done

echo "Done. Outputs under */expanded/."
