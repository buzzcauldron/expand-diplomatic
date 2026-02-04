#!/usr/bin/env bash
# Build macOS .app bundle for Expand Diplomatic GUI
# Requires: py2app or creates standalone .app with bundled Python
# Usage: ./scripts/build-macos-app.sh [--install-deps]
#   --install-deps    Install Python deps and optional py2app (pip)
# Output: dist/Expand-Diplomatic.app
#
# Supported: macOS 11 (Big Sur) through current (Intel and Apple Silicon).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

INSTALL_DEPS=0
for arg in "$@"; do
    case "$arg" in
        --install-deps|-i) INSTALL_DEPS=1 ;;
        *) echo "Unknown option: $arg. Usage: $0 [--install-deps]" >&2; exit 1 ;;
    esac
done

if [[ $INSTALL_DEPS -eq 1 ]]; then
    echo "Installing build dependencies (pip)..."
    pip3 install -q -r "$PROJECT_ROOT/requirements.txt"
    pip3 install -q build wheel 2>/dev/null || true
    pip3 install -q py2app 2>/dev/null || true
    echo "Build dependencies installed."
    echo ""
fi

# Check if on macOS
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Error: This script must be run on macOS"
    exit 1
fi

# Check for python3 (required for py2app or manual .app launcher)
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Install Python 3.10+ (e.g. from python.org or Homebrew)."
    exit 1
fi

# Read version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
APP_NAME="Expand-Diplomatic"

echo "Building macOS .app bundle for v$VERSION..."

# Method 1: Try py2app if available
if python3 -c "import py2app" 2>/dev/null; then
    echo "Using py2app..."
    
    # Create setup.py for py2app
    cat > "$PROJECT_ROOT/setup_app.py" <<EOF
from setuptools import setup

APP = ['gui.py']
DATA_FILES = [
    ('', ['examples.json', '.env.example', 'README.md', 'stretch_armstrong_icon.png']),
]
OPTIONS = {
    'argv_emulation': False,
    'packages': ['expand_diplomatic', 'lxml', 'PIL', 'google', 'dotenv'],
    'iconfile': 'stretch_armstrong_icon.png',
    'plist': {
        'CFBundleName': 'Expand Diplomatic',
        'CFBundleDisplayName': 'Expand Diplomatic',
        'CFBundleIdentifier': 'com.github.halxiii.expand-diplomatic',
        'CFBundleVersion': '${VERSION}',
        'CFBundleShortVersionString': '${VERSION}',
        'NSHumanReadableCopyright': 'Copyright © 2024-2026',
    }
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
EOF
    
    # Clean previous builds
    rm -rf "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist/${APP_NAME}.app"
    
    # Build
    python3 setup_app.py py2app
    
    # Clean up
    rm -f "$PROJECT_ROOT/setup_app.py"
    
else
    # Method 2: Create standalone .app bundle manually
    echo "py2app not available, creating standalone .app bundle..."
    
    APP_DIR="$PROJECT_ROOT/dist/${APP_NAME}.app"
    CONTENTS="$APP_DIR/Contents"
    MACOS="$CONTENTS/MacOS"
    RESOURCES="$CONTENTS/Resources"
    
    # Clean and create structure
    rm -rf "$APP_DIR"
    mkdir -p "$MACOS" "$RESOURCES"
    
    # Copy application files
    cp -r "$PROJECT_ROOT/expand_diplomatic" "$RESOURCES/"
    cp "$PROJECT_ROOT/gui.py" "$RESOURCES/"
    cp "$PROJECT_ROOT/run_gemini.py" "$RESOURCES/"
    cp "$PROJECT_ROOT/examples.json" "$RESOURCES/"
    cp "$PROJECT_ROOT/.env.example" "$RESOURCES/"
    cp "$PROJECT_ROOT/README.md" "$RESOURCES/"
    
    # Copy icon if exists
    if [[ -f "$PROJECT_ROOT/stretch_armstrong_icon.png" ]]; then
        cp "$PROJECT_ROOT/stretch_armstrong_icon.png" "$RESOURCES/icon.png"
    fi
    
    # Create launcher script
    cat > "$MACOS/launcher.sh" <<'LAUNCHER'
#!/bin/bash
DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
cd "$DIR"
export PYTHONPATH="$DIR:$PYTHONPATH"
exec python3 -u gui.py "$@"
LAUNCHER
    chmod +x "$MACOS/launcher.sh"
    
    # Create Info.plist
    cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>Expand Diplomatic</string>
    <key>CFBundleIdentifier</key>
    <string>com.github.halxiii.expand-diplomatic</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleExecutable</key>
    <string>launcher.sh</string>
    <key>CFBundleIconFile</key>
    <string>icon.png</string>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2024-2026</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST
    
    # Create PkgInfo
    echo -n "APPL????" > "$CONTENTS/PkgInfo"
fi

echo ""
echo "✓ macOS .app bundle created!"
echo ""
echo "Location: dist/${APP_NAME}.app"
echo ""
echo "To install:"
echo "  1. Copy to Applications: cp -r dist/${APP_NAME}.app /Applications/"
echo "  2. Or open directly: open dist/${APP_NAME}.app"
echo ""
echo "Note: On first launch, you may need to:"
echo "  - Right-click → Open (if Gatekeeper blocks it)"
echo "  - Install dependencies: pip3 install -r requirements.txt"
