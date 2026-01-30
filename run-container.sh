#!/usr/bin/env bash
# Run expand_diplomatic in Docker (Mac, Linux, Windows via WSL2).
# Usage: ./run-container.sh [--workspace DIR] [--build] [--platform PLAT] [--] [expand_diplomatic args...]
#   --workspace DIR   Mount DIR at /workspace (default: current directory)
#   --build           Build image before run (native arch only; use scripts/build-docker.sh for multi-arch)
#   --platform PLAT   Use image for PLAT (linux/amd64, linux/arm64). Default: host.
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

if [[ -n "$DO_BUILD" ]]; then
  docker build -t "$IMAGE_NAME" "$SCRIPT_DIR"
fi

if ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
  docker build -t "$IMAGE_NAME" "$SCRIPT_DIR"
fi

run_opts=(--rm -v "$WORKSPACE:/workspace" -w /workspace)
[[ -n "$PLATFORM" ]] && run_opts+=(--platform "$PLATFORM")
run_opts+=(-e GEMINI_API_KEY -e GOOGLE_API_KEY -e GEMINI_MODEL -e OLLAMA_MODEL -e OLLAMA_UPDATE_MODEL "$IMAGE_NAME")

docker run "${run_opts[@]}" "$@"
