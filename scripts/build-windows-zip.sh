#!/usr/bin/env bash
#
# Build Windows portable ZIP for expand-diplomatic (recommended: no MSI).
# Single command: installs deps then builds a ZIP you can extract and run on Windows.
# Contents are at ZIP root so extracting does NOT create a subfolder.
#
# Usage: ./scripts/build-windows-zip.sh [--no-clean]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
DIST_DIR="$PROJECT_ROOT/dist"

echo "=== Building Windows portable ZIP (no MSI — extract and run) ==="
cd "$PROJECT_ROOT"

# Check platform
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        ;;
    *)
        if ! grep -qi microsoft /proc/version 2>/dev/null; then
            echo "Error: This script must run on Windows or WSL2"
            exit 1
        fi
        ;;
esac

# Install build dependencies (single-command: deps + build)
echo "Installing build dependencies..."
python -m pip install --upgrade pip -q
python -m pip install -r "$PROJECT_ROOT/requirements.txt" -q
python -c "import cx_Freeze" 2>/dev/null || { python -m pip install -q cx_Freeze; }
echo "Dependencies OK."

# Clean unless --no-clean
if [[ "$1" != "--no-clean" ]]; then
    rm -rf "$BUILD_DIR" "$DIST_DIR"/*.zip
fi

# Create .ico from .png if needed (Windows prefers .ico for exe icon)
ICON_ICO="$PROJECT_ROOT/stretch_armstrong_icon.ico"
if [[ ! -f "$ICON_ICO" ]] && [[ -f "$PROJECT_ROOT/stretch_armstrong_icon.png" ]]; then
    echo "Converting icon to .ico..."
    python -c "
from pathlib import Path
from PIL import Image
png = Path('stretch_armstrong_icon.png')
ico = Path('stretch_armstrong_icon.ico')
img = Image.open(png)
if img.mode != 'RGBA':
    img = img.convert('RGBA')
img.save(ico, format='ICO')
" 2>/dev/null || true
fi

# Build exe only (no MSI) - create setup and run build_exe
cat > "$PROJECT_ROOT/setup_zip.py" << 'SETUP_EOF'
from pathlib import Path
from cx_Freeze import setup, Executable

version = "0.3.0"
vfile = Path("expand_diplomatic/_version.py")
if vfile.exists():
    for line in vfile.read_text().splitlines():
        if line.startswith("__version__"):
            version = line.split("=")[1].strip().strip('"').strip("'")
            break

build_opts = {
    "packages": ["expand_diplomatic", "google.genai", "google.genai.types", "lxml", "dotenv", "requests", "PIL", "tkinter"],
    "includes": ["tkinter", "tkinter.ttk", "tkinter.scrolledtext", "tkinter.filedialog", "tkinter.messagebox", "run_gemini"],
    "include_files": [
        ("examples.json", "examples.json"),
        (".env.example", ".env.example"),
        ("README.md", "README.md"),
        ("stretch_armstrong_icon.png", "stretch_armstrong_icon.png"),
    ],
    "excludes": ["test", "tests", "pytest", "numpy", "scipy", "matplotlib"],
    "optimize": 2,
}

setup(
    name="expand-diplomatic",
    version=version,
    options={"build_exe": build_opts},
    executables=[
        Executable("gui.py", base="Win32GUI", target_name="expand-diplomatic-gui.exe",
                   icon="stretch_armstrong_icon.ico" if Path("stretch_armstrong_icon.ico").exists() else
                   ("stretch_armstrong_icon.png" if Path("stretch_armstrong_icon.png").exists() else None)),
        Executable("expand_diplomatic/__main__.py", base=None, target_name="expand-diplomatic.exe",
                   icon="stretch_armstrong_icon.ico" if Path("stretch_armstrong_icon.ico").exists() else
                   ("stretch_armstrong_icon.png" if Path("stretch_armstrong_icon.png").exists() else None)),
    ],
)
SETUP_EOF

# On WSL2, use Windows Python if available
if grep -qi microsoft /proc/version 2>/dev/null && command -v python.exe &>/dev/null; then
    python.exe setup_zip.py build_exe
else
    python setup_zip.py build_exe
fi
rm -f "$PROJECT_ROOT/setup_zip.py"

# Find the exe output dir (e.g. build/exe.win-amd64-3.12)
EXE_DIR=$(find "$BUILD_DIR" -maxdepth 1 -type d -name "exe.win-*" 2>/dev/null | head -n 1)
if [[ -z "$EXE_DIR" || ! -d "$EXE_DIR" ]]; then
    echo "Error: build exe directory not found"
    exit 1
fi

# Create ZIP with contents at root (no wrapper folder)
# cd into exe dir so zip contains files directly
mkdir -p "$DIST_DIR"
ZIP_NAME="expand-diplomatic-portable.zip"
ZIP_PATH="$DIST_DIR/$ZIP_NAME"
rm -f "$ZIP_PATH"

echo "Creating flat ZIP (extract = no subfolder)..."
(cd "$EXE_DIR" && zip -r "$ZIP_PATH" . -x "*.pyc" -x "__pycache__/*")

if [[ -f "$ZIP_PATH" ]]; then
    echo ""
    echo "✓ Portable ZIP created:"
    echo "  $ZIP_PATH"
    echo ""
    echo "Extract to any folder — files go directly there (no subfolder)."
    echo "Run: expand-diplomatic-gui.exe"
else
    echo "Error: ZIP was not created"
    exit 1
fi
