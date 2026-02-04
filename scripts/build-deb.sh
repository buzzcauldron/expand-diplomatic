#!/usr/bin/env bash
# Build DEB package for Debian/Ubuntu
# Requires: dpkg-deb, fakeroot (optional)
# Usage: ./scripts/build-deb.sh [--install-deps]
#   --install-deps    Install build dependencies with apt (uses sudo)
# Output: dist/*.deb
#
# Supported (Python 3.10+): Debian 12+ (Bookworm), Ubuntu 22.04+ (Jammy), and derivatives
# (Mint, Pop!_OS, etc.). Older Debian/Ubuntu lack python3.10 in default repos.

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
    echo "Installing build dependencies (apt)..."
    sudo apt-get update -qq
    sudo apt-get install -y dpkg-dev
    echo "Build dependencies installed."
    echo ""
fi

# Check for dpkg-deb
if ! command -v dpkg-deb &> /dev/null; then
    echo "Error: dpkg-deb not found. Install with:"
    echo "  sudo apt-get install dpkg-dev"
    exit 1
fi

# Read version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
NAME="expand-diplomatic"
ARCH="all"  # Python is architecture-independent

echo "Building DEB package for $NAME v$VERSION..."

# Create package directory structure
DEB_DIR="$PROJECT_ROOT/dist/${NAME}_${VERSION}_${ARCH}"
rm -rf "$DEB_DIR"
mkdir -p "$DEB_DIR/DEBIAN"
mkdir -p "$DEB_DIR/usr/lib/python3/dist-packages"
mkdir -p "$DEB_DIR/usr/bin"
mkdir -p "$DEB_DIR/usr/share/doc/${NAME}"
mkdir -p "$DEB_DIR/usr/share/applications"
mkdir -p "$DEB_DIR/usr/share/pixmaps"

# Copy Python package
cp -r "$PROJECT_ROOT/expand_diplomatic" "$DEB_DIR/usr/lib/python3/dist-packages/"
cp "$PROJECT_ROOT/gui.py" "$DEB_DIR/usr/lib/python3/dist-packages/"
cp "$PROJECT_ROOT/run_gemini.py" "$DEB_DIR/usr/lib/python3/dist-packages/"

# Copy examples and documentation
cp "$PROJECT_ROOT/examples.json" "$DEB_DIR/usr/share/doc/${NAME}/"
cp "$PROJECT_ROOT/.env.example" "$DEB_DIR/usr/share/doc/${NAME}/"
cp "$PROJECT_ROOT/README.md" "$DEB_DIR/usr/share/doc/${NAME}/"
[[ -f "$PROJECT_ROOT/CHANGELOG.md" ]] && cp "$PROJECT_ROOT/CHANGELOG.md" "$DEB_DIR/usr/share/doc/${NAME}/"

# Copy icon
if [[ -f "$PROJECT_ROOT/stretch_armstrong_icon.png" ]]; then
    cp "$PROJECT_ROOT/stretch_armstrong_icon.png" "$DEB_DIR/usr/share/pixmaps/${NAME}.png"
fi

# Create executable wrapper scripts
cat > "$DEB_DIR/usr/bin/expand-diplomatic" <<'EOF'
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/lib/python3/dist-packages')
from expand_diplomatic.__main__ import main
if __name__ == '__main__':
    main()
EOF
chmod +x "$DEB_DIR/usr/bin/expand-diplomatic"

cat > "$DEB_DIR/usr/bin/expand-diplomatic-gui" <<'EOF'
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/lib/python3/dist-packages')
from gui import main
if __name__ == '__main__':
    main()
EOF
chmod +x "$DEB_DIR/usr/bin/expand-diplomatic-gui"

# Create desktop entry
cat > "$DEB_DIR/usr/share/applications/${NAME}.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Expand Diplomatic
Comment=Expand diplomatic transcriptions to full form
Exec=/usr/bin/expand-diplomatic-gui
Icon=/usr/share/pixmaps/${NAME}.png
Terminal=false
Categories=Office;Education;Utility;
Keywords=transcription;manuscript;latin;xml;
EOF

# Calculate installed size (in KB)
INSTALLED_SIZE=$(du -sk "$DEB_DIR" | cut -f1)

# Create control file
cat > "$DEB_DIR/DEBIAN/control" <<EOF
Package: ${NAME}
Version: ${VERSION}
Section: text
Priority: optional
Architecture: ${ARCH}
Maintainer: Package Maintainer <maintainer@example.com>
Depends: python3 (>= 3.10), python3-lxml, python3-pil, python3-dotenv, python3-tk
Installed-Size: ${INSTALLED_SIZE}
Homepage: https://github.com/halxiii/expand-diplomatic
Description: Expand diplomatic transcriptions to full form
 A tool to expand diplomatic transcriptions of medieval manuscripts to full,
 readable form using Google's Gemini API. Supports TEI and PAGE XML formats.
 .
 Features:
  - Supports TEI and PAGE XML formats
  - Batch processing of multiple files
  - Local model fallback with Ollama
  - Auto-learning from successful expansions
  - GUI and command-line interfaces
EOF

# Create postinst script (optional)
cat > "$DEB_DIR/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e
# Update desktop database if available
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database -q /usr/share/applications
fi
exit 0
EOF
chmod +x "$DEB_DIR/DEBIAN/postinst"

# Create postrm script (optional)
cat > "$DEB_DIR/DEBIAN/postrm" <<'EOF'
#!/bin/bash
set -e
# Update desktop database if available
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database -q /usr/share/applications
fi
exit 0
EOF
chmod +x "$DEB_DIR/DEBIAN/postrm"

# Build the package
echo "Building DEB package..."
dpkg-deb --build "$DEB_DIR"

# Move to dist/
mkdir -p "$PROJECT_ROOT/dist"
mv "${DEB_DIR}.deb" "$PROJECT_ROOT/dist/"

# Clean up build directory
rm -rf "$DEB_DIR"

echo ""
echo "✓ DEB package created!"
echo ""
echo "Package: dist/${NAME}_${VERSION}_${ARCH}.deb"
echo ""
echo "Install with:"
echo "  sudo dpkg -i dist/${NAME}_${VERSION}_${ARCH}.deb"
echo "  sudo apt-get install -f  # Install missing dependencies"
echo ""
echo "Or:"
echo "  sudo apt install ./dist/${NAME}_${VERSION}_${ARCH}.deb"
