#!/usr/bin/env bash
# Build Docker image for Mac, Linux, and Windows (via WSL2).
# Platforms: linux/amd64 (x64), linux/arm64 (Mac Silicon, ARM). Optional: linux/arm/v7.
#
# Usage: ./scripts/build-docker.sh [--push] [--load] [--platform PLAT[,PLAT...]] [--skip-ollama]
#   --push            Push to registry after build.
#   --load            Build for detected host and load (native arch; prefers hardware over emulator).
#   --platform LIST   Override platforms (default: linux/amd64,linux/arm64).
#   --skip-ollama     Skip Ollama model pull (faster build).
#
# With --load: on Apple Silicon, builds linux/arm64 (native) not amd64 (emulated via Rosetta).
# Multi-arch build requires buildx with container driver.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-expand-diplomatic}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
PUSH=""
LOAD=""
SKIP_OLLAMA=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) PUSH=1; shift ;;
    --load) LOAD=1; shift ;;
    --skip-ollama) SKIP_OLLAMA=1; shift ;;
    --platform)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "Usage: $0 [--push] [--load] [--skip-ollama] [--platform linux/amd64,linux/arm64,...]" >&2
        exit 1
      fi
      PLATFORMS="$2"; shift 2 ;;
    *) echo "Usage: $0 [--push] [--load] [--skip-ollama] [--platform linux/amd64,linux/arm64,...]" >&2; exit 1 ;;
  esac
done

command -v docker &>/dev/null || { echo "Error: docker not found." >&2; exit 1; }

_detect_platform() {
  case "$(uname -m 2>/dev/null)" in
    arm64|aarch64) echo "linux/arm64" ;;
    x86_64|amd64)  echo "linux/amd64" ;;
    armv7l|armv6l) echo "linux/amd64" ;;  # armv7: Ollama has no build; use amd64 (emulated)
    *)             echo "linux/amd64" ;;
  esac
}

cd "$PROJECT_ROOT"
export DOCKER_BUILDKIT=1

if [[ -n "$LOAD" ]]; then
  PLAT=$(_detect_platform)
  echo "Building for detected host ($PLAT)..."
  opts=(-t "$IMAGE_NAME" -f Dockerfile "$PROJECT_ROOT")
  [[ -n "$SKIP_OLLAMA" ]] && opts+=(--build-arg SKIP_OLLAMA_PULL=1)
  docker build --platform "$PLAT" "${opts[@]}"
  exit 0
fi

docker buildx version &>/dev/null || { echo "Error: docker buildx not found." >&2; exit 1; }

# Multi-arch: ensure a container driver builder exists
use_builder() {
  if docker buildx inspect "$1" &>/dev/null; then
    docker buildx use "$1"
    return 0
  fi
  return 1
}

if ! use_builder "expand-diplomatic-multiarch" 2>/dev/null; then
  docker buildx create --name "expand-diplomatic-multiarch" --use --driver docker-container 2>/dev/null || true
  use_builder "expand-diplomatic-multiarch" 2>/dev/null || true
fi

opts=(--platform "$PLATFORMS" -t "$IMAGE_NAME:latest" -f Dockerfile "$PROJECT_ROOT")
[[ -n "$PUSH" ]] && opts+=(--push)
[[ -n "$SKIP_OLLAMA" ]] && opts+=(--build-arg SKIP_OLLAMA_PULL=1)
echo "Building multi-arch image ($PLATFORMS)..."
docker buildx build "${opts[@]}"
[[ -z "$PUSH" ]] && echo "Done. Use --push to push to registry."
