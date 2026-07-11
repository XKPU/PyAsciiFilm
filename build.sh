#!/bin/bash

./.venv-linux/bin/python -m nuitka \
    --onefile \
    --enable-plugin=tk-inter \
    --include-package=textual \
    --include-module=sounddevice \
    --include-data-dir=./.venv-linux/lib/python3.12/site-packages/_sounddevice_data=_sounddevice_data \
    --include-package=imageio_ffmpeg \
    --include-package-data=imageio_ffmpeg \
    --output-filename=PyAsciiFilm \
    --output-dir=build/Linux_64 \
    --python-flag=-O \
    --lto=yes \
    ./src/main.py
