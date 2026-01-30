#!/usr/bin/env bash
# Master build script - builds all package formats
# Usage: ./scripts/build-all.sh [--rpm] [--deb] [--app] [--msi] [--docker] [--packages]
#        ./scripts/build-all.sh  # Builds everything available on this platform

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

PLATFORM="$(uname -s)"
BUILD_RPM=0
BUILD_DEB=0
BUILD_APP=0
BUILD_MSI=0
BUILD_DOCKER=0
BUILD_PACKAGES=0

# Parse arguments
if [[ $# -eq 0 ]]; then
    # No args: build everything available for this platform
    BUILD_PACKAGES=1
    BUILD_DOCKER=1
    if [[ "$PLATFORM" == "Darwin" ]]; then
        BUILD_APP=1
    elif [[ "$PLATFORM" == "Linux" ]]; then
        # Check what's available
        command -v rpmbuild &> /dev/null && BUILD_RPM=1
        command -v dpkg-deb &> /dev/null && BUILD_DEB=1
        # Check for WSL2 for Windows MSI builds
        if grep -qi microsoft /proc/version 2>/dev/null; then
            BUILD_MSI=1
        fi
    elif [[ "$PLATFORM" =~ ^(MINGW|MSYS|CYGWIN) ]]; then
        BUILD_MSI=1
    fi
else
    # Parse specific build targets
    for arg in "$@"; do
        case "$arg" in
            --rpm) BUILD_RPM=1 ;;
            --deb) BUILD_DEB=1 ;;
            --app) BUILD_APP=1 ;;
            --msi) BUILD_MSI=1 ;;
            --docker) BUILD_DOCKER=1 ;;
            --packages) BUILD_PACKAGES=1 ;;
            *)
                echo "Unknown option: $arg"
                echo "Usage: $0 [--rpm] [--deb] [--app] [--msi] [--docker] [--packages]"
                exit 1
                ;;
        esac
    done
fi

echo "========================================"
echo "Expand Diplomatic - Build All Packages"
echo "========================================"
echo "Platform: $PLATFORM"
echo ""

# Track what we built
BUILT=()

# Build Python packages (wheel + sdist)
if [[ $BUILD_PACKAGES -eq 1 ]]; then
    echo "→ Building Python packages (wheel + sdist)..."
    ./scripts/build-packages.sh
    BUILT+=("Python packages (dist/*.whl, dist/*.tar.gz)")
    echo ""
fi

# Build RPM
if [[ $BUILD_RPM -eq 1 ]]; then
    if command -v rpmbuild &> /dev/null; then
        echo "→ Building RPM package..."
        ./scripts/build-rpm.sh
        BUILT+=("RPM (rpmbuild/RPMS/)")
        echo ""
    else
        echo "⚠ Skipping RPM: rpmbuild not found"
        echo ""
    fi
fi

# Build DEB
if [[ $BUILD_DEB -eq 1 ]]; then
    if command -v dpkg-deb &> /dev/null; then
        echo "→ Building DEB package..."
        ./scripts/build-deb.sh
        BUILT+=("DEB (dist/*.deb)")
        echo ""
    else
        echo "⚠ Skipping DEB: dpkg-deb not found"
        echo ""
    fi
fi

# Build macOS .app
if [[ $BUILD_APP -eq 1 ]]; then
    if [[ "$PLATFORM" == "Darwin" ]]; then
        echo "→ Building macOS .app bundle..."
        ./scripts/build-macos-app.sh
        BUILT+=("macOS App (dist/Expand-Diplomatic.app)")
        echo ""
    else
        echo "⚠ Skipping macOS .app: not on macOS"
        echo ""
    fi
fi

# Build Windows MSI
if [[ $BUILD_MSI -eq 1 ]]; then
    if [[ "$PLATFORM" =~ ^(MINGW|MSYS|CYGWIN) ]] || grep -qi microsoft /proc/version 2>/dev/null; then
        echo "→ Building Windows MSI installer..."
        ./scripts/build-windows-msi.sh
        BUILT+=("Windows MSI (dist/*.msi)")
        echo ""
    else
        echo "⚠ Skipping Windows MSI: not on Windows or WSL2"
        echo ""
    fi
fi

# Build Docker images
if [[ $BUILD_DOCKER -eq 1 ]]; then
    if command -v docker &> /dev/null; then
        echo "→ Building Docker images..."
        ./scripts/build-docker.sh
        BUILT+=("Docker images (expand-diplomatic:latest)")
        echo ""
    else
        echo "⚠ Skipping Docker: docker not found"
        echo ""
    fi
fi

echo "========================================"
echo "✓ Build Complete!"
echo "========================================"
if [[ ${#BUILT[@]} -gt 0 ]]; then
    echo "Built packages:"
    for item in "${BUILT[@]}"; do
        echo "  ✓ $item"
    done
else
    echo "No packages were built."
fi
echo ""
echo "Distribution files:"
[[ -d dist ]] && ls -lh dist/ || echo "  (none)"
echo ""
