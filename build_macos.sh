#!/usr/bin/env bash
# Build AetherHE.app for macOS.
#
#   ./build_macos.sh              -> ad-hoc signed .app in dist/
#   ./build_macos.sh --zip        -> also dist/AetherHE-macos-<arch>.zip
#                                    (the in-app updater's payload)
#   ./build_macos.sh --dmg        -> also dist/AetherHE-macos-<arch>.dmg
#                                    (first install: drag to Applications)
#   ./build_macos.sh --release    -> both; this is what CI runs
#   CODESIGN_IDENTITY="Developer ID Application: ..." ./build_macos.sh
#                                 -> sign with a real identity (for distribution)
#
# WHY THE APP IS SIGNED (and what the signature does NOT buy):
# Apple Silicon refuses to run unsigned code at all, and the updater checks the
# bundle's seal (`codesign --verify --deep --strict`) before it swaps one in.
# The identifier (-i below) keeps the bundle id in the signature stable.
#
# It does NOT make privacy (TCC) grants survive a rebuild. macOS matches a
# grant such as Input Monitoring against the app's designated requirement, and
# for an AD-HOC signature that requirement is the cdhash - a hash of the code -
# not the identifier. Every build has a new cdhash, so an Input Monitoring
# grant MAY be reset by each update, and the user asked again. Only a real
# Developer ID identity (CODESIGN_IDENTITY) gives a requirement that outlives
# a rebuild.
# What has actually been verified: the Win60's vendor interface (usage page
# 0xFF1B) opens WITHOUT any grant (measured 2026-07-24), so that board is not
# affected. Nothing has been measured for a board that does need the grant.
set -euo pipefail
cd "$(dirname "$0")"

BUNDLE_ID="io.github.mrwhosnexus.AetherHE"
APP="dist/AetherHE.app"
PY="${PYTHON:-venv-web/bin/python}"

WANT_ZIP=0
WANT_DMG=0
for arg in "$@"; do
  case "$arg" in
    --zip)     WANT_ZIP=1 ;;
    --dmg)     WANT_DMG=1 ;;
    --release) WANT_ZIP=1; WANT_DMG=1 ;;
    *) echo "error: unknown option $arg (use --zip, --dmg or --release)" >&2; exit 2 ;;
  esac
done

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
# --deep --strict is exactly what updater.py runs on a staged update before it
# swaps it in, so a build that cannot pass it here could never be installed by
# the updater. Fail the build instead of shipping that.
codesign --verify --deep --strict --verbose=2 "$APP"
# shellcheck disable=SC2086  # VERIFY_ARGS is deliberately word-split
"$PY" tools/verify_macos_bundle.py "$APP" ${VERIFY_ARGS:-}

# The asset names carry the arch: updater._pick_asset_full matches on it so an
# Intel build is never offered to Apple Silicon (or the reverse).
ARCH="$(uname -m)"
ZIP="dist/AetherHE-macos-${ARCH}.zip"
DMG="dist/AetherHE-macos-${ARCH}.dmg"

if [ "$WANT_ZIP" = 1 ]; then
  echo "==> zip (updater payload)"
  rm -f "$ZIP"
  # ditto preserves the symlinks and extended attributes inside a .app; `zip`
  # does not, and a bundle that loses them no longer matches its signature.
  ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
  # Prove the round trip the updater performs: extract with ditto, then verify
  # the signature of what came out. A zip that fails this is not shippable.
  RT="$(mktemp -d "${TMPDIR:-/tmp}/aetherhe.XXXXXX")"
  ditto -x -k "$ZIP" "$RT"
  codesign --verify --deep --strict "$RT/AetherHE.app"
  rm -rf "$RT"
  echo "==> wrote $ZIP"
fi

if [ "$WANT_DMG" = 1 ]; then
  echo "==> dmg (first install)"
  rm -f "$DMG"
  STAGE="$(mktemp -d "${TMPDIR:-/tmp}/aetherhe.XXXXXX")"
  # ditto, not cp -R: same reason as the zip.
  ditto "$APP" "$STAGE/AetherHE.app"
  ln -s /Applications "$STAGE/Applications"
  hdiutil create -volname "AETHER HE" -srcfolder "$STAGE" -fs HFS+ \
    -format UDZO -ov "$DMG" >/dev/null
  rm -rf "$STAGE"
  hdiutil verify "$DMG" >/dev/null
  echo "==> wrote $DMG"
fi

echo "==> done: $APP"
