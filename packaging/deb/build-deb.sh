#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PKG_DIR="${SCRIPT_DIR}/zine-imposer"
LIB_DIR="${PKG_DIR}/usr/lib/zine-imposer/src"
DIST_DIR="${SCRIPT_DIR}/dist"
CONTROL_FILE="${PKG_DIR}/DEBIAN/control"
ICON_SOURCE="${REPO_ROOT}/src/zine_imposer/assets/icon-256.png"
ICON_TARGET="${PKG_DIR}/usr/share/icons/hicolor/256x256/apps/zine-imposer.png"

VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "${REPO_ROOT}/pyproject.toml" | head -n 1)"
if [[ -z "${VERSION}" ]]; then
  echo "Unable to determine version from pyproject.toml" >&2
  exit 1
fi

rm -rf "${LIB_DIR}"
mkdir -p "${LIB_DIR}"
cp -R "${REPO_ROOT}/src/zine_imposer" "${LIB_DIR}/zine_imposer"
find "${LIB_DIR}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${LIB_DIR}" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete
mkdir -p "$(dirname "${ICON_TARGET}")"
cp "${ICON_SOURCE}" "${ICON_TARGET}"

python3 - <<PY
from pathlib import Path

control_path = Path("${CONTROL_FILE}")
lines = control_path.read_text().splitlines()
updated = []
for line in lines:
    if line.startswith("Version: "):
        updated.append(f"Version: ${VERSION}")
    else:
        updated.append(line)
control_path.write_text("\\n".join(updated) + "\\n")
PY

mkdir -p "${DIST_DIR}"
OUTPUT="${DIST_DIR}/zine-imposer_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "${PKG_DIR}" "${OUTPUT}"
echo "Built ${OUTPUT}"
