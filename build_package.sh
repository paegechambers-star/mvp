#!/usr/bin/env bash
# Builds a distributable FraPP + G.O.D.A.I. package archive.
# Output: dist/frapp-<version>.tar.gz
#
# Usage:
#   bash build_package.sh
#   bash build_package.sh --version 1.0.0

set -e

VERSION="0.1.0"
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --version) VERSION="$2"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DIST_DIR="dist"
PKG_NAME="frapp-${VERSION}"
PKG_DIR="${DIST_DIR}/${PKG_NAME}"

echo ""
echo "  Building FraPP + G.O.D.A.I. package v${VERSION} ..."
echo ""

rm -rf "${PKG_DIR}"
mkdir -p "${PKG_DIR}"

# Copy source
cp -r src/           "${PKG_DIR}/src/"
cp -r godai/         "${PKG_DIR}/godai/"
cp -r contextos/     "${PKG_DIR}/contextos/"
cp -r alembic/       "${PKG_DIR}/alembic/"
cp -r installer/     "${PKG_DIR}/installer/"
cp -r scripts/       "${PKG_DIR}/scripts/"
cp -r tests/         "${PKG_DIR}/tests/"

# Copy config files
cp requirements.txt  "${PKG_DIR}/"
cp pyproject.toml    "${PKG_DIR}/"
cp alembic.ini       "${PKG_DIR}/"
cp .env.example      "${PKG_DIR}/" 2>/dev/null || true

# Entry point wrapper
cat > "${PKG_DIR}/install.sh" << 'EOF'
#!/usr/bin/env bash
# Entry point — run this to install FraPP + G.O.D.A.I.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
python installer/install.py "$@"
EOF
chmod +x "${PKG_DIR}/install.sh"

# Archive
tar -czf "${DIST_DIR}/${PKG_NAME}.tar.gz" -C "${DIST_DIR}" "${PKG_NAME}"
rm -rf "${PKG_DIR}"

echo "  Package ready: ${DIST_DIR}/${PKG_NAME}.tar.gz"
echo ""
echo "  Install:"
echo "    tar -xzf ${PKG_NAME}.tar.gz"
echo "    bash ${PKG_NAME}/install.sh"
echo ""
