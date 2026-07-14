#!/usr/bin/env bash
VERSION="3.0.2"

./venv/bin/python -m nuitka \
    --onefile \
    --standalone \
    --follow-imports \
    --enable-plugin=tk-inter \
    --include-package=textual \
    --include-package=rich._unicode_data \
    --include-package=imageio_ffmpeg \
    --include-module=miniaudio \
    --output-filename="PyAsciiFilm-${VERSION}-linux_x64" \
    --output-dir="build/linux_x64" \
    --lto=yes \
    ./src/main.py