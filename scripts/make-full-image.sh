#!/usr/bin/env bash
# scripts/make-full-image.sh <build-dir> <out-file>
#
# Turns the core's build output into an image that is safe to flash at 0x0.
#
# The ESP32 core writes <sketch>.ino.merged.bin padded out to the WHOLE flash
# chip. Flashing that blanks everything above the app. This cuts it right after
# the app (app starts at 0x10000, cut rounded up to a 4KB sector), and refuses
# to cut if any non-0xFF byte lies above the cut point, which would mean a
# future core version started putting real data there.

set -euo pipefail

BUILD_DIR="${1:?usage: make-full-image.sh <build-dir> <out-file>}"
OUT="${2:?usage: make-full-image.sh <build-dir> <out-file>}"
SKETCH="${SKETCH:-usb_mouse_jiggler}"

MERGED="${BUILD_DIR}/${SKETCH}.ino.merged.bin"
APP="${BUILD_DIR}/${SKETCH}.ino.bin"

if [ ! -f "$MERGED" ] || [ ! -f "$APP" ]; then
  echo "error: expected build output missing in ${BUILD_DIR}; run 'make build' first" >&2
  ls -la "$BUILD_DIR" 2>/dev/null || true
  exit 1
fi

size() { wc -c < "$1" | tr -d ' '; }

CUT=$(( (0x10000 + $(size "$APP") + 4095) / 4096 * 4096 ))

STRAY=$(tail -c "+$(( CUT + 1 ))" "$MERGED" | LC_ALL=C tr -d '\377' | wc -c | tr -d ' ')
if [ "$STRAY" -ne 0 ]; then
  echo "error: $STRAY non-0xFF bytes above offset $CUT in $MERGED; refusing to truncate" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
head -c "$CUT" "$MERGED" > "$OUT"
echo "Wrote $OUT ($(size "$OUT") bytes, trimmed from $(size "$MERGED"))"
