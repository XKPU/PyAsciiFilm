#!/bin/bash

./.venv/Scripts/python.exe -m nuitka \
    --onefile \
    --enable-plugin=tk-inter \
    --include-package=textual \
    --include-module=sounddevice \
    --include-data-dir=./.venv/Lib/site-packages/_sounddevice_data=_sounddevice_data \
    --include-package=imageio_ffmpeg \
    --include-package-data=imageio_ffmpeg \
    --output-filename=PyAsciiFilm \
    --output-dir=build/Win_64 \
    --python-flag=-O \
    --lto=yes \
    ./src/main.py
