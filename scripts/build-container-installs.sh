#!/usr/bin/env bash
# Build Docker container for detected host (macOS, Linux, Windows/WSL2).
# Prefers native hardware arch: on Apple Silicon (even with Rosetta 2), uses arm64 not emulated amd64.
#
# Usage: ./scripts/build-container-installs.sh [OPTIONS]
#   --native       Build for detected host only and load into Docker (default)
#   --all          Build for all platforms (linux/amd64, linux/arm64)
#   --push         Push to registry (with --all)
#   --skip-ollama  Skip Ollama model pull (faster build)
#
# Detected platforms:
#   macOS Apple Silicon  -> linux/arm64 (native, not emulated via Rosetta)
#   macOS Intel          -> linux/amd64
#   Linux arm64/aarch64  -> linux/arm64
#   Linux x86_64         -> linux/amd64
#   Windows (WSL2)       -> same as underlying Linux arch

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-expand-diplomatic}"
NATIVE_ONLY=1
ALL_PLATFORMS=""
PUSH=""
SKIP_OLLAMA=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --native) NATIVE_ONLY=1; shift ;;
    --all)    ALL_PLATFORMS=1; NATIVE_ONLY=0; shift ;;
    --push)   PUSH=1; shift ;;
    --skip-ollama) SKIP_OLLAMA=1; shift ;;
    *) echo "Usage: $0 [--native] [--all] [--push] [--skip-ollama]" >&2; exit 1 ;;
  esac
done

command -v docker &>/dev/null || { echo "Error: docker not found." >&2; exit 1; }

detect_platform() {
  local os arch platform
  os=$(uname -s 2>/dev/null)
  arch=$(uname -m 2>/dev/null)

  case "$arch" in
    arm64|aarch64)
      # Apple Silicon, ARM Linux: use native arm64 (not amd64 via Rosetta/QEMU)
      platform="linux/arm64"
      ;;
    x86_64|amd64)
      platform="linux/amd64"
      ;;
    armv7l|armv6l)
      echo "Warning: armv7/v6 not supported (Ollama lacks builds); defaulting to linux/amd64" >&2
      platform="linux/amd64"
      ;;
    *)
      echo "Warning: unknown arch $arch, defaulting to linux/amd64" >&2
      platform="linux/amd64"
      ;;
  esac

  case "$os" in
    Darwin)  echo "macOS ($arch) -> $platform" >&2 ;;
    Linux)   echo "Linux ($arch) -> $platform" >&2 ;;
    MINGW*|MSYS*|CYGWIN*) echo "Windows ($arch) -> $platform" >&2 ;;
    *)       echo "OS $os ($arch) -> $platform" >&2 ;;
  esac
  echo "$platform"
}

cd "$PROJECT_ROOT"
export DOCKER_BUILDKIT=1

if [[ -n "$ALL_PLATFORMS" ]]; then
  docker buildx version &>/dev/null || { echo "Error: docker buildx required for --all." >&2; exit 1; }
  PLATFORMS="linux/amd64,linux/arm64"
  echo "Building multi-arch ($PLATFORMS)..."
  if ! docker buildx inspect expand-diplomatic-multiarch &>/dev/null; then
    docker buildx create --name expand-diplomatic-multiarch --use --driver docker-container 2>/dev/null || true
  fi
  docker buildx use expand-diplomatic-multiarch 2>/dev/null || true
  opts=(--platform "$PLATFORMS" -t "$IMAGE_NAME:latest" -f Dockerfile "$PROJECT_ROOT")
  [[ -n "$SKIP_OLLAMA" ]] && opts+=(--build-arg SKIP_OLLAMA_PULL=1)
  [[ -n "$PUSH" ]] && opts+=(--push)
  docker buildx build "${opts[@]}"
  [[ -z "$PUSH" ]] && echo "Done. Use --push to push to registry."
else
  PLATFORM=$(detect_platform)
  echo "Building for $PLATFORM..."
  opts=(-t "$IMAGE_NAME" -f Dockerfile "$PROJECT_ROOT")
  [[ -n "$SKIP_OLLAMA" ]] && opts+=(--build-arg SKIP_OLLAMA_PULL=1)
  docker build "${opts[@]}"
  echo "Done. Image $IMAGE_NAME loaded for $PLATFORM."
fi
