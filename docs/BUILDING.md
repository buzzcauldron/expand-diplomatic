# Building and Packaging

This document describes how to build distribution packages for Expand Diplomatic.

## Quick Start

```bash
# Build everything for your platform
./scripts/build-all.sh

# Or build specific formats
./scripts/build-all.sh --rpm --deb --app --msi --zip --docker --packages
```

## Package Formats

### Python Packages (Universal)

**Script:** `./scripts/build-packages.sh`

**Requires:** Python 3.10+, `pip install build wheel`

**Output:**
- `dist/expand_diplomatic-*.whl` (wheel, platform-independent)
- `dist/expand_diplomatic-*.tar.gz` (source distribution)

**Install:**
```bash
pip install dist/expand_diplomatic-*.whl
```

**Platforms:** All (Linux, macOS, Windows)

---

### RPM Packages (Red Hat Ecosystem)

**Script:** `./scripts/build-rpm.sh`

**Requires:**
- `rpm-build`
- `python3-devel`
- Linux system (RHEL, Fedora, CentOS, Rocky, Alma, etc.)

**Install requirements:**
```bash
# Fedora/RHEL 8+/Rocky/Alma
sudo dnf install rpm-build python3-devel

# CentOS 7
sudo yum install rpm-build python3-devel
```

**Output:**
- `rpmbuild/RPMS/noarch/expand-diplomatic-*.rpm` (binary RPM)
- `rpmbuild/SRPMS/expand-diplomatic-*.src.rpm` (source RPM)

**Install:**
```bash
# Method 1: rpm
sudo rpm -ivh rpmbuild/RPMS/noarch/expand-diplomatic-*.rpm

# Method 2: dnf (auto-resolves dependencies)
sudo dnf install rpmbuild/RPMS/noarch/expand-diplomatic-*.rpm

# Method 3: yum (CentOS 7)
sudo yum install rpmbuild/RPMS/noarch/expand-diplomatic-*.rpm
```

**Dependencies installed automatically:**
- python3
- python3-lxml
- python3-pillow
- python3-dotenv
- python3-tkinter

**Commands installed:**
- `/usr/bin/expand-diplomatic` (CLI)
- `/usr/bin/expand-diplomatic-gui` (GUI)

**Desktop entry:** Applications menu → Office → Expand Diplomatic

---

### Windows MSI Installer

**Script:** `./scripts/build-windows-msi.sh`

**Requires:**
- Python 3.10+ with `cx_Freeze`
- Windows or WSL2

**Install requirements:**
```bash
pip install cx_Freeze
```

**Output:**
- `dist/expand-diplomatic-*.msi`
- `dist/expand-diplomatic-portable.zip` (flat — extract puts files directly in folder, no subfolder)

**Install:**
```bash
# MSI: Interactive install (double-click) or: msiexec /i expand-diplomatic-*.msi /qn
# Portable ZIP: Extract to any folder; run expand-diplomatic-gui.exe
```

**Features:**
- GUI launcher: "Expand Diplomatic" in Start Menu
- CLI: `expand-diplomatic.exe` added to PATH
- Includes all dependencies (Python runtime, libraries, examples)
- Uninstall via Windows Settings → Apps

**Platforms:** Windows 10/11 (x64, arm64)

**WSL2:** Use Windows Python: `python.exe setup_msi.py bdist_msi` from the project dir. Or run the build on native Windows.

**MSI troubleshooting:** If install fails, run `msiexec -i file.msi -l*vx msi_log.txt` to capture a log. Common fixes: use Windows Python (not WSL Linux Python), ensure icon is .ico (script auto-converts .png).

**Portable ZIP only** (no MSI):
```bash
./scripts/build-windows-zip.sh
# Or: ./scripts/build-all.sh --zip
# Output: dist/expand-diplomatic-portable.zip — flat structure, no subfolder when extracted
```

---

### DEB Packages (Debian/Ubuntu)

**Script:** `./scripts/build-deb.sh`

**Requires:**
- `dpkg-dev`
- Linux system (Debian, Ubuntu, Mint, Pop!_OS, etc.)

**Install requirements:**
```bash
sudo apt-get install dpkg-dev
```

**Output:**
- `dist/expand-diplomatic_*_all.deb`

**Install:**
```bash
# Method 1: apt (recommended, auto-resolves dependencies)
sudo apt install ./dist/expand-diplomatic_*_all.deb

# Method 2: dpkg + apt-get
sudo dpkg -i dist/expand-diplomatic_*_all.deb
sudo apt-get install -f  # Install missing dependencies
```

**Dependencies installed automatically:**
- python3 (>= 3.10)
- python3-lxml
- python3-pil
- python3-dotenv
- python3-tk

**Commands installed:**
- `/usr/bin/expand-diplomatic` (CLI)
- `/usr/bin/expand-diplomatic-gui` (GUI)

**Desktop entry:** Applications menu → Office → Expand Diplomatic

---

### macOS Application Bundle

**Script:** `./scripts/build-macos-app.sh`

**Requires:**
- macOS system (Intel or Apple Silicon)
- Python 3.10+
- Optional: `py2app` (`pip install py2app`) for optimized bundle

**Output:**
- `dist/Expand-Diplomatic.app`

**Install:**
```bash
# Copy to Applications folder
cp -r dist/Expand-Diplomatic.app /Applications/

# Or open directly
open dist/Expand-Diplomatic.app
```

**First launch:**
1. Right-click → Open (if macOS Gatekeeper blocks unsigned apps)
2. Dependencies must be installed: `pip3 install -r requirements.txt`

**Note:** The standalone bundle uses the system Python. For a fully self-contained app with bundled Python, install `py2app` before building.

---

### Docker Images

**Script:** `./scripts/build-docker.sh`

**Requires:**
- Docker installed and running

**Output:**
- `expand-diplomatic:latest` (Docker image)

**Build:**
```bash
# Native architecture only
./scripts/build-docker.sh --load

# Multi-architecture (amd64 + arm64)
./scripts/build-container-installs.sh --all
```

**Run:**
```bash
export GEMINI_API_KEY="your-key"
./run-container.sh --build -- --file input.xml --out output.xml
```

See main README for full Docker documentation.

---

## Build All Formats

**Script:** `./scripts/build-all.sh`

Builds all available package formats for your platform.

**Usage:**
```bash
# Auto-detect and build everything
./scripts/build-all.sh

# Build specific formats
./scripts/build-all.sh --packages --rpm --deb --app --docker
```

**Options:**
- `--packages` — Python wheel + sdist
- `--rpm` — RPM package (Linux only, requires rpmbuild)
- `--deb` — DEB package (Linux only, requires dpkg-deb)
- `--app` — macOS .app bundle (macOS only)
- `--docker` — Docker images

**Output locations:**
- Python packages: `dist/*.whl`, `dist/*.tar.gz`
- RPM: `rpmbuild/RPMS/noarch/*.rpm`, `rpmbuild/SRPMS/*.src.rpm`
- DEB: `dist/*.deb`
- macOS app: `dist/Expand-Diplomatic.app`
- Docker: `expand-diplomatic:latest` image

---

## Version Management

Version is managed in `pyproject.toml` and `expand_diplomatic/_version.py`.

To bump version:
1. Update `version = "x.y.z"` in `pyproject.toml`
2. Update `__version__ = "x.y.z"` in `expand_diplomatic/_version.py`
3. Update `CHANGELOG.md` with release notes
4. Commit changes
5. Tag release: `git tag v x.y.z && git push --tags`

All build scripts read the version automatically from `pyproject.toml`.

---

## Platform-Specific Notes

### ARM Support (Apple Silicon, ARM64 Linux)

- **Docker:** `linux/arm64` supported. On Apple Silicon, `run-container.sh --build` and `build-docker.sh --load` use native arm64 (not emulated amd64).
- **macOS .app:** Built natively on Apple Silicon; no special flags needed.
- **Python packages:** Pure Python (py3-none-any); runs on all architectures.
- **CI:** GitHub Actions runs packages on `macos-14` (Apple Silicon) and `ubuntu-latest`.
- **armv7/armv6:** Not supported (Ollama has no Linux build); scripts default to amd64.

### Linux (RPM/DEB)
- Packages install to system Python directories (`/usr/lib/python3/dist-packages`)
- Desktop entry appears in applications menu
- Icons installed to `/usr/share/pixmaps/`
- Example files in `/usr/share/doc/expand-diplomatic/`

### macOS (.app)
- Standalone bundle uses system Python
- For self-contained app, install `py2app` first
- Unsigned apps require: Right-click → Open (first time)
- Can be distributed as DMG: `hdiutil create -volname "Expand Diplomatic" -srcfolder dist/Expand-Diplomatic.app -ov -format UDZO dist/Expand-Diplomatic.dmg`

### Windows
- Use Python wheel: `pip install dist/expand_diplomatic-*.whl`
- Or run from source: `python gui.py`
- For exe distribution, use PyInstaller (not included, but compatible)

---

## Testing Packages

### RPM
```bash
# Install in clean container
docker run -it --rm -v "$PWD:/src" fedora:latest bash
cd /src
dnf install -y rpmbuild/RPMS/noarch/expand-diplomatic-*.rpm
expand-diplomatic --help
expand-diplomatic-gui  # (requires X11 forwarding)
```

### DEB
```bash
# Install in clean container
docker run -it --rm -v "$PWD:/src" ubuntu:latest bash
cd /src
apt update && apt install -y ./dist/expand-diplomatic_*_all.deb
expand-diplomatic --help
```

### macOS App
```bash
# Test direct launch
open dist/Expand-Diplomatic.app

# Test installed version
cp -r dist/Expand-Diplomatic.app /Applications/
open /Applications/Expand-Diplomatic.app
```

---

## Troubleshooting

### "rpmbuild: command not found"
```bash
sudo dnf install rpm-build python3-devel
```

### "dpkg-deb: command not found"
```bash
sudo apt-get install dpkg-dev
```

### macOS app won't open
- Right-click → Open (bypasses Gatekeeper)
- Check system Python: `which python3`
- Install dependencies: `pip3 install -r requirements.txt`

### Missing dependencies in packages
- RPM: Edit `Requires:` in `scripts/build-rpm.sh`
- DEB: Edit `Depends:` in `scripts/build-deb.sh`

---

## Distribution

After building:

1. **GitHub Releases:**
   ```bash
   gh release create v0.2.0 \
     dist/*.whl \
     dist/*.tar.gz \
     dist/*.deb \
     rpmbuild/RPMS/noarch/*.rpm \
     dist/Expand-Diplomatic.dmg
   ```

2. **PyPI:**
   ```bash
   pip install twine
   twine upload dist/*.whl dist/*.tar.gz
   ```

3. **Package Repositories:**
   - RPM: Submit to COPR, Fedora, EPEL
   - DEB: Submit to Debian, Ubuntu PPA
   - Homebrew: Create formula for macOS

4. **Docker Hub:**
   ```bash
   docker tag expand-diplomatic:latest username/expand-diplomatic:0.2.0
   docker push username/expand-diplomatic:0.2.0
   ```
