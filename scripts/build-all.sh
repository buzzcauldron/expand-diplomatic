#!/usr/bin/env bash
# Master build script - builds all package formats
# Usage: ./scripts/build-all.sh [--rpm] [--deb] [--app] [--msi] [--zip] [--docker] [--packages] [--install-deps]
#        ./scripts/build-all.sh  # Builds everything available on this platform
#        --install-deps         Install build deps (sudo/pip) for each format before building

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

PLATFORM="$(uname -s)"
BUILD_RPM=0
BUILD_DEB=0
BUILD_APP=0
BUILD_MSI=0
BUILD_ZIP=0
BUILD_DOCKER=0
BUILD_PACKAGES=0
INSTALL_DEPS=0

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
            --zip) BUILD_ZIP=1 ;;
            --docker) BUILD_DOCKER=1 ;;
            --packages) BUILD_PACKAGES=1 ;;
            --install-deps|-i) INSTALL_DEPS=1 ;;
            *)
                echo "Unknown option: $arg"
                echo "Usage: $0 [--rpm] [--deb] [--app] [--msi] [--zip] [--docker] [--packages] [--install-deps]"
                exit 1
                ;;
        esac
    done
fi

DEPS_OPT=""
[[ $INSTALL_DEPS -eq 1 ]] && DEPS_OPT="--install-deps"

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
    ./scripts/build-packages.sh $DEPS_OPT
    BUILT+=("Python packages (dist/*.whl, dist/*.tar.gz)")
    echo ""
fi

# Build RPM
if [[ $BUILD_RPM -eq 1 ]]; then
    if command -v rpmbuild &> /dev/null; then
        echo "→ Building RPM package..."
        ./scripts/build-rpm.sh $DEPS_OPT
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
        ./scripts/build-deb.sh $DEPS_OPT
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
        ./scripts/build-macos-app.sh $DEPS_OPT
        BUILT+=("macOS App (dist/Expand-Diplomatic.app)")
        echo ""
    else
        echo "⚠ Skipping macOS .app: not on macOS"
        echo ""
    fi
fi

# Build Windows MSI (also produces portable ZIP)
if [[ $BUILD_MSI -eq 1 ]]; then
    if [[ "$PLATFORM" =~ ^(MINGW|MSYS|CYGWIN) ]] || grep -qi microsoft /proc/version 2>/dev/null; then
        echo "→ Building Windows MSI installer..."
        ./scripts/build-windows-msi.sh $DEPS_OPT
        BUILT+=("Windows MSI + portable ZIP (dist/*.msi, dist/*.zip)")
        echo ""
    else
        echo "⚠ Skipping Windows MSI: not on Windows or WSL2"
        echo ""
    fi
fi

# Build Windows portable ZIP only (no MSI)
if [[ $BUILD_ZIP -eq 1 ]]; then
    if [[ "$PLATFORM" =~ ^(MINGW|MSYS|CYGWIN) ]] || grep -qi microsoft /proc/version 2>/dev/null; then
        echo "→ Building Windows portable ZIP..."
        ./scripts/build-windows-zip.sh $DEPS_OPT
        BUILT+=("Windows portable ZIP (dist/*.zip)")
        echo ""
    else
        echo "⚠ Skipping Windows ZIP: not on Windows or WSL2"
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
