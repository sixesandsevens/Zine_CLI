#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 path/to/package.deb" >&2
  exit 2
fi

DEB_PATH="$1"
if [[ ! -f "${DEB_PATH}" ]]; then
  echo "error: .deb file not found: ${DEB_PATH}" >&2
  exit 1
fi

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local message="$3"
  if ! grep -Fq "${needle}" <<<"${haystack}"; then
    echo "error: ${message}" >&2
    exit 1
  fi
}

CONTENTS="$(dpkg-deb -c "${DEB_PATH}")"
INFO="$(dpkg-deb -I "${DEB_PATH}")"

assert_contains "${CONTENTS}" "./usr/bin/zine-imposer" "missing wrapper at /usr/bin/zine-imposer"
assert_contains "${CONTENTS}" "./usr/share/applications/zine-imposer.desktop" "missing desktop launcher"
assert_contains "${CONTENTS}" "./usr/share/icons/hicolor/256x256/apps/zine-imposer.png" "missing packaged icon"
assert_contains "${CONTENTS}" "./usr/lib/zine-imposer/src/zine_imposer/cli.py" "missing bundled Python package"
assert_contains "${INFO}" "python3-fitz" "control metadata is missing python3-fitz dependency"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT
dpkg-deb -x "${DEB_PATH}" "${TMP_DIR}"

DESKTOP_FILE="${TMP_DIR}/usr/share/applications/zine-imposer.desktop"
if [[ ! -f "${DESKTOP_FILE}" ]]; then
  echo "error: desktop file was not extracted from the package" >&2
  exit 1
fi

DESKTOP_CONTENTS="$(cat "${DESKTOP_FILE}")"
assert_contains "${DESKTOP_CONTENTS}" "Exec=zine-imposer ui" "desktop file Exec is incorrect"
assert_contains "${DESKTOP_CONTENTS}" "Icon=zine-imposer" "desktop file Icon is incorrect"

echo "OK: ${DEB_PATH}"
echo "Verified launcher, icon, wrapper, Python payload, and control metadata."
