#!/bin/bash

# Linux 打包脚本 for PyAsciiFilm

./.venv-linux/bin/python -m nuitka \
    --standalone \
    --enable-plugin=tk-inter \
    --include-data-file=ffplay=ffplay \
    --include-data-file=setting.json=setting.json \
    --output-filename=PyAsciiFilm \
    --output-dir=build/Linux_64 \
    --python-flag=-O \
    --lto=yes \
    ./src/main.py
