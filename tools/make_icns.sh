#!/usr/bin/env bash
# Build ui/assets/logo.icns from logo.png (macOS only; needs sips + iconutil).
#
# The .icns is a BUILD ARTIFACT, not a checked-in asset — it is generated from
# logo.png so the icon can never drift from the source image.
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="ui/assets/logo.png"
OUT="ui/assets/logo.icns"
SET="$(mktemp -d)/AetherHE.iconset"
mkdir -p "$SET"

# The source is 500x500, so the 512/1024 slots are upscaled. Generate them
# anyway: a missing slot makes macOS fall back to a blurry scale of the nearest
# size, which looks worse than an explicit upscale.
for size in 16 32 128 256 512; do
  sips -z $size $size      "$SRC" --out "$SET/icon_${size}x${size}.png"      >/dev/null
  sips -z $((size*2)) $((size*2)) "$SRC" --out "$SET/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$SET" -o "$OUT"
rm -rf "$(dirname "$SET")"
echo "wrote $OUT"
