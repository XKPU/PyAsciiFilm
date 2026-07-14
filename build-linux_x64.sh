#!/usr/bin/env bash
VERSION="$(tr -d '[:space:]' < ./VERSION)"
VERSION="${VERSION:-0.0.0}"

.venv-linux/bin/python -m nuitka \
    --onefile \
    --standalone \
    --follow-imports \
    --enable-plugin=tk-inter \
    --include-package=textual \
    --include-package=rich._unicode_data \
    --include-package=imageio_ffmpeg \
    --include-module=miniaudio \
    --output-filename="PyAsciiFilm-v${VERSION}-linux_x64" \
    --output-dir="build/linux_x64" \
    --lto=yes \
    ./src/main.py