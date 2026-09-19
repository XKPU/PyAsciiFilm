#!/usr/bin/env bash
set -euo pipefail

export PATH=/opt/python/cp310-cp310/bin:$PATH

if [ -f /opt/_internal/static-libs-for-embedding-only.tar.xz ]; then
  cd /opt/_internal
  tar xf static-libs-for-embedding-only.tar.xz
fi

if [ -n "${GITHUB_PATH:-}" ]; then
  echo "/opt/python/cp310-cp310/bin" >> "$GITHUB_PATH"
fi
