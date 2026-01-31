#!/usr/bin/env bash
#
# Build Windows MSI installer for expand-diplomatic
# Requires: Python with cx_Freeze on Windows or WSL2
#
# Usage:
#   ./scripts/build-windows-msi.sh [--no-clean]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
DIST_DIR="$PROJECT_ROOT/dist"

echo "=== Building Windows MSI installer ==="
cd "$PROJECT_ROOT"

# Check platform
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        ON_WINDOWS=1
        ;;
    *)
        # Check if running in WSL2
        if grep -qi microsoft /proc/version 2>/dev/null; then
            echo "Detected WSL2 - checking for Windows Python..."
            ON_WINDOWS=0
            WSL_MODE=1
        else
            echo "Error: This script must run on Windows or WSL2"
            exit 1
        fi
        ;;
esac

# Clean previous builds unless --no-clean
if [[ "$1" != "--no-clean" ]]; then
    echo "Cleaning previous builds..."
    rm -rf "$BUILD_DIR" "$DIST_DIR"/*.msi
fi

# Ensure cx_Freeze is installed
if ! python -c "import cx_Freeze" 2>/dev/null; then
    echo "Installing cx_Freeze..."
    python -m pip install --upgrade cx_Freeze
fi

# Create .ico from .png if needed (Windows requires .ico for exe/installer)
ICON_ICO="$PROJECT_ROOT/stretch_armstrong_icon.ico"
if [[ ! -f "$ICON_ICO" ]] && [[ -f "$PROJECT_ROOT/stretch_armstrong_icon.png" ]]; then
    echo "Converting icon to .ico format..."
    python -c "
from pathlib import Path
from PIL import Image
png = Path('stretch_armstrong_icon.png')
ico = Path('stretch_armstrong_icon.ico')
img = Image.open(png)
if img.mode != 'RGBA':
    img = img.convert('RGBA')
img.save(ico, format='ICO')
print('Created', ico)
" 2>/dev/null || true
fi

# Create setup_msi.py for cx_Freeze
cat > "$PROJECT_ROOT/setup_msi.py" << 'SETUP_EOF'
"""
cx_Freeze setup for Windows MSI installer.
"""
import sys
from pathlib import Path
from cx_Freeze import setup, Executable

# Read version
version_file = Path(__file__).parent / "expand_diplomatic" / "_version.py"
version = "0.3.0"
for line in version_file.read_text().splitlines():
    if line.startswith("__version__"):
        version = line.split("=")[1].strip().strip('"').strip("'")
        break

# Read README for description
readme = Path(__file__).parent / "README.md"
long_description = readme.read_text(encoding="utf-8") if readme.exists() else ""

# Icon: Windows needs .ico; use converted file or skip
icon_ico = Path("stretch_armstrong_icon.ico")
icon_png = Path("stretch_armstrong_icon.png")
icon_path = str(icon_ico) if icon_ico.exists() else (str(icon_png) if icon_png.exists() else None)

# Build options
build_exe_options = {
    "packages": [
        "expand_diplomatic",
        "google.genai",
        "google.genai.types",
        "lxml",
        "dotenv",
        "requests",
        "PIL",
        "tkinter",
    ],
    "includes": [
        "tkinter",
        "tkinter.ttk",
        "tkinter.scrolledtext",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "run_gemini",
    ],
    "include_files": [
        ("examples.json", "examples.json"),
        (".env.example", ".env.example"),
        ("README.md", "README.md"),
        ("stretch_armstrong_icon.png", "stretch_armstrong_icon.png"),
    ],
    "excludes": [
        "test",
        "tests",
        "pytest",
        "numpy",
        "scipy",
        "matplotlib",
    ],
    "optimize": 2,
}

# MSI options
bdist_msi_options = {
    "add_to_path": True,
    "upgrade_code": "{8A5C3F1E-9B2D-4E7A-8F3C-1D6E9A4B7C2F}",
    "initial_target_dir": r"[ProgramFiles64Folder]Expand-Diplomatic",
}
if icon_path:
    bdist_msi_options["install_icon"] = icon_path

# Executables
executables = [
    Executable(
        script="gui.py",
        base="Win32GUI",
        target_name="expand-diplomatic-gui.exe",
        icon=icon_path,
    ),
    Executable(
        script="expand_diplomatic/__main__.py",
        base=None,
        target_name="expand-diplomatic.exe",
        icon=icon_path,
    ),
]

setup(
    name="expand-diplomatic",
    version=version,
    description="Expand diplomatic Latin transcriptions to full text using AI",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="halxiii",
    url="https://github.com/halxiii/expand-diplomatic",
    license="MIT",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=executables,
)
SETUP_EOF

echo "Building MSI installer..."
# On WSL2, use Windows Python (python.exe); on native Windows, python is fine
if [[ -n "${WSL_MODE:-}" ]] && command -v python.exe &>/dev/null; then
    python.exe setup_msi.py bdist_msi
else
    python setup_msi.py bdist_msi
fi

# Find generated MSI
MSI_FILE=$(find "$DIST_DIR" -name "*.msi" -type f | head -n 1)

if [[ -n "$MSI_FILE" ]]; then
    echo ""
    echo "✓ MSI installer created:"
    echo "  $MSI_FILE"
    echo ""
    echo "Installation:"
    echo "  1. Double-click the MSI file"
    echo "  2. Follow the installation wizard"
    echo "  3. Launch from Start Menu: 'Expand Diplomatic'"
    echo ""
    echo "Or install silently:"
    echo "  msiexec /i \"$(basename "$MSI_FILE")\" /qn"
else
    echo "Error: MSI file not found in $DIST_DIR"
    rm -f "$PROJECT_ROOT/setup_msi.py"
    exit 1
fi

# Also create flat portable ZIP (no subfolder when extracted)
EXE_DIR=$(find "$BUILD_DIR" -maxdepth 1 -type d -name "exe.win-*" 2>/dev/null | head -n 1)
if [[ -n "$EXE_DIR" && -d "$EXE_DIR" ]]; then
    mkdir -p "$DIST_DIR"
    ZIP_PATH="$DIST_DIR/expand-diplomatic-portable.zip"
    rm -f "$ZIP_PATH"
    (cd "$EXE_DIR" && zip -rq "$ZIP_PATH" . -x "*.pyc" -x "__pycache__/*" 2>/dev/null) || true
    if [[ -f "$ZIP_PATH" ]]; then
        echo ""
        echo "✓ Portable ZIP (flat, no subfolder):"
        echo "  $ZIP_PATH"
    fi
fi

# Cleanup
rm -f "$PROJECT_ROOT/setup_msi.py"
