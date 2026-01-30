#!/usr/bin/env bash
# Build RPM package for Red Hat/Fedora/CentOS/Rocky Linux
# Requires: rpmbuild, python3-devel
# Usage: ./scripts/build-rpm.sh
# Output: rpmbuild/RPMS/ and rpmbuild/SRPMS/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Check for rpmbuild
if ! command -v rpmbuild &> /dev/null; then
    echo "Error: rpmbuild not found. Install with:"
    echo "  Fedora/RHEL: sudo dnf install rpm-build python3-devel"
    echo "  CentOS: sudo yum install rpm-build python3-devel"
    exit 1
fi

# Read version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
NAME="expand-diplomatic"

echo "Building RPM for $NAME v$VERSION..."

# Create RPM build directories
mkdir -p "$PROJECT_ROOT/rpmbuild"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Build source tarball first
./scripts/build-packages.sh
TARBALL=$(ls -t "$PROJECT_ROOT/dist/${NAME}-${VERSION}.tar.gz" 2>/dev/null | head -1)

if [[ ! -f "$TARBALL" ]]; then
    echo "Error: Source tarball not found. Build failed."
    exit 1
fi

# Copy tarball to SOURCES
cp "$TARBALL" "$PROJECT_ROOT/rpmbuild/SOURCES/"

# Create RPM spec file
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
%autosetup -n %{name}-%{version}

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
%{python3_sitelib}/__pycache__/run_gemini*.pyc
%{python3_sitelib}/__pycache__/gui*.pyc
%{_bindir}/expand-diplomatic
%{_bindir}/expand-diplomatic-gui

%changelog
* $(date '+%a %b %d %Y') Builder <builder@localhost> - ${VERSION}-1
- Initial RPM release
EOF

echo "Building RPM package..."
rpmbuild --define "_topdir $PROJECT_ROOT/rpmbuild" \
         -ba "$PROJECT_ROOT/rpmbuild/SPECS/${NAME}.spec"

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
