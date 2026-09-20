#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-standalone}"
SUFFIX="linux_x64"

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
  distFolder=$(find "$OUT_DIR" -maxdepth 1 -type d -name '*.dist' -print -quit)
  if [ -z "$distFolder" ]; then
    echo "build failed: no .dist directory in $OUT_DIR" >&2
    exit 1
  fi
  base=$(basename "$distFolder")
  tar -czf "$OUT_DIR/${OUT_NAME}.tar.gz" -C "$distFolder" .

  LISTING=$(tar -tzf "$OUT_DIR/${OUT_NAME}.tar.gz")
  TOP=$(printf '%s\n' "$LISTING" | sed -n '1p')
  N=$(printf '%s\n' "$LISTING" | grep -cv '/$' || true)
  case "$TOP" in
    "./") ;;
    *) echo "verify failed: archive top level is not './': $TOP" >&2; exit 1 ;;
  esac
  if printf '%s\n' "$LISTING" | grep -q "^${base}/"; then
    echo "verify failed: archive must not contain a top-level ${base}/ directory" >&2
    exit 1
  fi
  if [ "$N" -lt 10 ]; then
    echo "verify failed: archive has only $N files" >&2
    exit 1
  fi
  echo "artifact: $OUT_DIR/${OUT_NAME}.tar.gz ($N files, no top-level directory)"
else
  echo "artifact: $OUT_DIR/$OUT_NAME"
fi

if [ "$MODE" = "standalone" ]; then
  distDir=$(find "$OUT_DIR" -maxdepth 1 -type d -name '*.dist' -print -quit)
  BIN="${distDir:-$OUT_DIR}/$OUT_NAME"
else
  BIN="$OUT_DIR/$OUT_NAME"
fi
if [ -f "$BIN" ] && command -v objdump >/dev/null 2>&1; then
  SYMS=$(objdump -T "$BIN" 2>/dev/null | grep -o 'GLIBC_2\.[0-9]*' | sed 's/^GLIBC_//' || true)
  MAX=$(printf '%s\n' "$SYMS" | sort -V -u | tail -1)
  echo "glibc requirement: ${MAX:-unknown}"
fi
