#!/usr/bin/env bash
# Run expand_diplomatic in Docker (Mac, Linux, Windows via WSL2).
# Usage: ./run-container.sh [--workspace DIR] [--build] [--platform PLAT] [--] [expand_diplomatic args...]
#   --workspace DIR   Mount DIR at /workspace (default: current directory)
#   --build           Build image for detected host before run (prefers native arch; Apple Silicon -> arm64)
#   --platform PLAT   Use image for PLAT (linux/amd64, linux/arm64). Default: detected host.
#   --                Remaining args passed to expand_diplomatic (paths relative to workspace)
#
# Examples:
#   export GEMINI_API_KEY=your-key
#   ./run-container.sh --build -- --file sample.xml --out sample_expanded.xml
#   ./run-container.sh --build -- --backend local --file sample.xml --out sample_expanded.xml
#   OLLAMA_UPDATE_MODEL=1 ./run-container.sh -- --backend local --file sample.xml --out out.xml

set -euo pipefail

if ! command -v docker &>/dev/null; then
  echo "Error: docker not found. Install Docker and ensure the daemon is running." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
IMAGE_NAME="expand-diplomatic"
WORKSPACE="$(pwd)"
DO_BUILD=""
PLATFORM=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace)
      WORKSPACE="$(cd "$2" && pwd)"
      shift 2
      ;;
    --build)
      DO_BUILD=1
      shift
      ;;
    --platform)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "Error: --platform requires a value (e.g. linux/amd64, linux/arm64)." >&2
        exit 1
      fi
      PLATFORM="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

if [[ -n "$DO_BUILD" ]] || ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
  if [[ -z "$PLATFORM" ]]; then
    case "$(uname -m 2>/dev/null)" in
      arm64|aarch64) PLATFORM="linux/arm64" ;;
      *)             PLATFORM="linux/amd64" ;;
    esac
    echo "Building for $PLATFORM..."
  fi
  opts=(-t "$IMAGE_NAME" -f "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR")
  [[ -n "$PLATFORM" ]] && opts+=(--platform "$PLATFORM")
  docker build "${opts[@]}"
fi

run_opts=(--rm -v "$WORKSPACE:/workspace" -w /workspace)
[[ -n "$PLATFORM" ]] && run_opts+=(--platform "$PLATFORM")
# Pass API keys: .env file (when in workspace) or host env
if [[ -f "$WORKSPACE/.env" ]]; then
  run_opts+=(--env-file "$WORKSPACE/.env")
fi
for ev in GEMINI_API_KEY GOOGLE_API_KEY GEMINI_MODEL OLLAMA_MODEL OLLAMA_UPDATE_MODEL; do
  [[ -n "${!ev:-}" ]] && run_opts+=(-e "$ev")
done
run_opts+=("$IMAGE_NAME")

docker run "${run_opts[@]}" "$@"
