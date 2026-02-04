#!/usr/bin/env bash
# Build RPM package for Red Hat/Fedora/CentOS/Rocky Linux
# Requires: rpmbuild, python3-devel
# Usage: ./scripts/build-rpm.sh [--install-deps]
#   --install-deps    Install build dependencies with dnf/yum (uses sudo)
# Output: rpmbuild/RPMS/ and rpmbuild/SRPMS/
#
# Supported (build and run): Fedora 35+, RHEL 9+, CentOS Stream 9+, Rocky 9+, Alma 9+
# Legacy (build with fallback spec): Fedora 30–42, RHEL 8 (no pyproject-rpm-macros)

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

# Optionally install build dependencies
if [[ $INSTALL_DEPS -eq 1 ]]; then
    if command -v dnf &> /dev/null; then
        echo "Installing build dependencies (dnf)..."
        sudo dnf install -y rpm-build python3-devel python3-setuptools python3-wheel
        if rpm -q pyproject-rpm-macros &> /dev/null; then
            : # already installed
        else
            sudo dnf install -y pyproject-rpm-macros 2>/dev/null || true
        fi
    elif command -v yum &> /dev/null; then
        echo "Installing build dependencies (yum)..."
        sudo yum install -y rpm-build python3-devel python3-setuptools python3-wheel
    else
        echo "Error: neither dnf nor yum found. Install dependencies manually." >&2
        exit 1
    fi
    echo "Build dependencies installed."
    echo ""
fi

# Check for rpmbuild
if ! command -v rpmbuild &> /dev/null; then
    echo "Error: rpmbuild not found. Install with:"
    echo "  Fedora/RHEL: sudo dnf install rpm-build python3-devel"
    echo "  CentOS: sudo yum install rpm-build python3-devel"
    exit 1
fi

# Check for python3-devel (required by spec BuildRequires)
if ! rpm -q python3-devel &> /dev/null; then
    echo "Error: python3-devel is not installed. It is required to build the RPM."
    echo "  Fedora/RHEL: sudo dnf install python3-devel"
    echo "  CentOS: sudo yum install python3-devel"
    exit 1
fi

# Read version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
NAME="expand-diplomatic"

# Prefer modern spec (Fedora 35+, RHEL 9+) when pyproject-rpm-macros is available
USE_PYPROJECT_SPEC=0
if rpm -q pyproject-rpm-macros &> /dev/null; then
    USE_PYPROJECT_SPEC=1
fi

echo "Building RPM for $NAME v$VERSION..."
[[ $USE_PYPROJECT_SPEC -eq 1 ]] && echo "Using modern pyproject spec (Fedora 35+/RHEL 9+)." || echo "Using legacy spec (older distros)."

# Modern spec needs python3-wheel and python3-setuptools; check before building
if [[ $USE_PYPROJECT_SPEC -eq 1 ]]; then
    MISSING=""
    rpm -q python3-wheel &> /dev/null || MISSING="python3-wheel"
    rpm -q python3-setuptools &> /dev/null || MISSING="${MISSING:+$MISSING }python3-setuptools"
    if [[ -n "$MISSING" ]]; then
        echo "Error: Modern spec requires: $MISSING"
        echo "  Install with: sudo dnf install $MISSING"
        echo "  Or re-run with: $0 --install-deps"
        exit 1
    fi
fi

# Create RPM build directories
mkdir -p "$PROJECT_ROOT/rpmbuild"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Build source tarball first (RPM needs sdist; skip wheel for speed)
./scripts/build-packages.sh --sdist-only
# setuptools sdist uses normalized name (underscore), e.g. expand_diplomatic-0.3.3.tar.gz
TARBALL=$(ls -t "$PROJECT_ROOT/dist/"*"-${VERSION}.tar.gz" 2>/dev/null | head -1)

if [[ ! -f "$TARBALL" ]]; then
    echo "Error: Source tarball not found at dist/*-${VERSION}.tar.gz"
    echo "  Ensure dist/ exists and build-packages.sh completed (pip install build wheel)."
    exit 1
fi

# Copy to SOURCES with name the spec expects (Source0: %{name}-%{version}.tar.gz)
cp "$TARBALL" "$PROJECT_ROOT/rpmbuild/SOURCES/${NAME}-${VERSION}.tar.gz"
echo "Using source tarball: $(basename "$TARBALL")"

if [[ $USE_PYPROJECT_SPEC -eq 1 ]]; then
# Modern spec: %pyproject_* macros (Fedora 35+, RHEL 9+); no deprecation warnings.
# Explicit BuildRequires so a single "rpmbuild -ba" produces the RPM (no two-phase generate_buildrequires).
cat > "$PROJECT_ROOT/rpmbuild/SPECS/${NAME}.spec" <<EOF
Name:           ${NAME}
Version:        ${VERSION}
Release:        1%{?dist}
Summary:        Expand diplomatic transcriptions to full form via Gemini API

License:        MIT
URL:            https://github.com/halxiii/expand-diplomatic
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel

%description
A tool to expand diplomatic transcriptions of medieval manuscripts to full,
readable form using Google's Gemini API. Supports TEI and PAGE XML formats.

%prep
# setuptools sdist unpacks to expand_diplomatic-%{version}, not %{name}-%{version}
%autosetup -n expand_diplomatic-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l expand_diplomatic run_gemini gui

%files -f %{pyproject_files}
%doc README.md CHANGELOG.md
%{_bindir}/expand-diplomatic
%{_bindir}/expand-diplomatic-gui

%changelog
* $(date '+%a %b %d %Y') Builder <builder@localhost> - ${VERSION}-1
- RPM release (pyproject spec)
EOF
else
# Legacy spec: %py3_build/%py3_install for older Fedora/RHEL 8
cat > "$PROJECT_ROOT/rpmbuild/SPECS/${NAME}.spec" <<EOF
Name:           ${NAME}
Version:        ${VERSION}
Release:        1%{?dist}
Summary:        Expand diplomatic transcriptions to full form via Gemini API

License:        MIT
URL:            https://github.com/halxiii/expand-diplomatic
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-pip
Requires:       python3
Requires:       python3-lxml
Requires:       python3-pillow
Requires:       python3-dotenv
Requires:       python3-tkinter

%description
A tool to expand diplomatic transcriptions of medieval manuscripts to full,
readable form using Google's Gemini API. Supports TEI and PAGE XML formats.

%prep
# setuptools sdist unpacks to expand_diplomatic-%{version}, not %{name}-%{version}
%autosetup -n expand_diplomatic-%{version}

%build
%py3_build

%install
%py3_install

%files
%doc README.md CHANGELOG.md
%{python3_sitelib}/%{name}-*.egg-info/
%{python3_sitelib}/expand_diplomatic/
%{python3_sitelib}/run_gemini.py
%{python3_sitelib}/gui.py
%{_bindir}/expand-diplomatic
%{_bindir}/expand-diplomatic-gui

%changelog
* $(date '+%a %b %d %Y') Builder <builder@localhost> - ${VERSION}-1
- Initial RPM release
EOF
fi

echo "Building RPM package..."
rpmbuild --define "_topdir $PROJECT_ROOT/rpmbuild" \
         -ba "$PROJECT_ROOT/rpmbuild/SPECS/${NAME}.spec"

RPM_COUNT=$(find "$PROJECT_ROOT/rpmbuild/RPMS" -name "*.rpm" -type f 2>/dev/null | wc -l)
if [[ "${RPM_COUNT:-0}" -eq 0 ]]; then
    echo "Error: No RPMs were produced. Check rpmbuild output above for errors."
    exit 1
fi

echo ""
echo "✓ RPM build complete!"
echo ""
echo "Binary RPMs:"
find "$PROJECT_ROOT/rpmbuild/RPMS" -name "*.rpm" -type f
echo ""
echo "Source RPMs:"
find "$PROJECT_ROOT/rpmbuild/SRPMS" -name "*.rpm" -type f
echo ""
echo "Install with: sudo rpm -ivh rpmbuild/RPMS/noarch/${NAME}-${VERSION}-1.*.rpm"
echo "Or: sudo dnf install rpmbuild/RPMS/noarch/${NAME}-${VERSION}-1.*.rpm"
