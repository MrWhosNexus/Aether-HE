#!/usr/bin/env bash
# Build AetherHE.app for macOS.
#
#   ./build_macos.sh              -> ad-hoc signed .app in dist/
#   ./build_macos.sh --zip        -> also produce dist/AetherHE-macos-<arch>.zip
#   CODESIGN_IDENTITY="Developer ID Application: ..." ./build_macos.sh
#                                 -> sign with a real identity (for distribution)
#
# WHY THE SIGNATURE MATTERS HERE (it is not ceremony):
# macOS keys an Input Monitoring (TCC) grant to the app's code-signing identity.
# An UNSIGNED bundle is identified by a hash of its contents, so every rebuild
# looks like a different app and the user has to re-approve it — and stale
# entries pile up in System Settings. Ad-hoc signing with a STABLE identifier
# (-i below) keeps one identity across rebuilds, so the grant sticks.
set -euo pipefail
cd "$(dirname "$0")"

BUNDLE_ID="io.github.mrwhosnexus.AetherHE"
APP="dist/AetherHE.app"
PY="${PYTHON:-venv-web/bin/python}"

if [ ! -x "$PY" ]; then
  echo "error: no interpreter at $PY. Create one first:" >&2
  echo "  python3 -m venv venv-web && venv-web/bin/pip install -r requirements.txt pyinstaller" >&2
  exit 1
fi

echo "==> icon"
./tools/make_icns.sh

echo "==> pyinstaller"
"$PY" -m PyInstaller --clean --noconfirm AetherHE-macos.spec

echo "==> codesign"
# --deep is deprecated and unreliable for signing, so sign inner Mach-O files
# first (bottom-up), then the bundle itself. Unsigned nested binaries make
# Gatekeeper reject the whole app.
find "$APP/Contents" -type f \( -name "*.so" -o -name "*.dylib" \) -print0 |
  while IFS= read -r -d '' f; do
    codesign --force --timestamp=none -s "${CODESIGN_IDENTITY:--}" -i "$BUNDLE_ID" "$f" 2>/dev/null || true
  done
codesign --force --timestamp=none -s "${CODESIGN_IDENTITY:--}" -i "$BUNDLE_ID" "$APP"

echo "==> verify"
codesign --verify --strict --verbose=2 "$APP"
"$PY" tools/verify_macos_bundle.py "$APP"

if [ "${1:-}" = "--zip" ]; then
  ARCH="$(uname -m)"
  ZIP="dist/AetherHE-macos-${ARCH}.zip"
  rm -f "$ZIP"
  # ditto preserves the symlinks and resource forks inside a .app; `zip` does not.
  ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
  echo "==> wrote $ZIP"
fi

echo "==> done: $APP"
