#!/usr/bin/env bash
# Build Docker image for Mac, Linux, and Windows (via WSL2).
# Platforms: linux/amd64 (x64), linux/arm64 (Mac Silicon, ARM). Optional: linux/arm/v7.
#
# Usage: ./scripts/build-docker.sh [--push] [--load] [--platform PLAT[,PLAT...]]
#   --push            Push to registry after build.
#   --load            Load into local Docker (native arch only).
#   --platform LIST   Override platforms (default: linux/amd64,linux/arm64).
#
# Multi-arch build requires buildx with container driver.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-expand-diplomatic}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
PUSH=""
LOAD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) PUSH=1; shift ;;
    --load) LOAD=1; shift ;;
    --platform)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "Usage: $0 [--push] [--load] [--platform linux/amd64,linux/arm64,...]" >&2
        exit 1
      fi
      PLATFORMS="$2"; shift 2 ;;
    *) echo "Usage: $0 [--push] [--load] [--platform linux/amd64,linux/arm64,...]" >&2; exit 1 ;;
  esac
done

command -v docker &>/dev/null || { echo "Error: docker not found." >&2; exit 1; }
docker buildx version &>/dev/null || { echo "Error: docker buildx not found." >&2; exit 1; }

cd "$PROJECT_ROOT"
export DOCKER_BUILDKIT=1

if [[ -n "$LOAD" ]]; then
  echo "Building native-arch image and loading..."
  docker build -t "$IMAGE_NAME" -f Dockerfile "$PROJECT_ROOT"
  exit 0
fi

# Multi-arch: ensure a container driver builder exists
use_builder() {
  if docker buildx inspect "$1" &>/dev/null; then
    docker buildx use "$1"
    return 0
  fi
  return 1
}

if ! use_builder "expand-diplomatic-multiarche" 2>/dev/null; then
  docker buildx create --name "expand-diplomatic-multiarche" --use --driver docker-container 2>/dev/null || true
  use_builder "expand-diplomatic-multiarche" 2>/dev/null || true
fi

opts=(--platform "$PLATFORMS" -t "$IMAGE_NAME:latest" -f Dockerfile "$PROJECT_ROOT")
[[ -n "$PUSH" ]] && opts+=(--push)
echo "Building multi-arch image ($PLATFORMS)..."
docker buildx build "${opts[@]}"
[[ -z "$PUSH" ]] && echo "Done. Use --push to push to registry."
