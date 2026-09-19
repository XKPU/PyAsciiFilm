#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-standalone}"
SUFFIX="macos_arm64"

cd "$(dirname "$0")/.."

VERSION=$(cat version.txt | tr -d '[:space:]')
OUT_NAME="PyAsciiFilm-v${VERSION}-${SUFFIX}"

case "$MODE" in
  standalone) OUT_DIR="dist/standalone" ;;
  onefile)    OUT_DIR="dist/onefile" ;;
  *) echo "unknown mode: $MODE" >&2; exit 2 ;;
esac

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

if [ "$MODE" = "onefile" ]; then
  MODE_FLAG="--onefile"
else
  MODE_FLAG="--standalone"
fi

python -m nuitka \
  $MODE_FLAG \
  --follow-imports \
  --assume-yes-for-downloads \
  --enable-plugin=tk-inter \
  --include-package=textual \
  --include-package=rich._unicode_data \
  --include-package=imageio_ffmpeg \
  --include-module=miniaudio \
  --output-filename="$OUT_NAME" \
  --output-dir="$OUT_DIR" \
  --lto=yes \
  src/main.py

if [ "$MODE" = "standalone" ]; then
  distFolder=$(find "$OUT_DIR" -maxdepth 1 -type d -name '*.dist' | head -1)
  if [ -z "$distFolder" ]; then
    echo "build failed: no .dist directory in $OUT_DIR" >&2
    exit 1
  fi
  base=$(basename "$distFolder")
  zip -9 -r "$OUT_DIR/${base}.zip" "$base" >/dev/null
  echo "artifact: $OUT_DIR/${base}.zip"
else
  echo "artifact: $OUT_DIR/$OUT_NAME"
fi
