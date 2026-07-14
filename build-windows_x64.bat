@echo off
set VERSION=3.0.2

.\.venv\Scripts\python.exe -m nuitka ^
    --onefile ^
    --standalone ^
    --follow-imports ^
    --enable-plugin=tk-inter ^
    --include-package=textual ^
    --include-package=rich._unicode_data ^
    --include-package=imageio_ffmpeg ^
    --include-module=miniaudio ^
    --output-filename=PyAsciiFilm-%VERSION%-windows_x64.exe ^
    --output-dir=build\windows_x64 ^
    --lto=yes ^
    --windows-company-name=K_PU ^
    --windows-product-name=PyAsciiFilm ^
    --windows-file-version=%VERSION% ^
    --windows-product-version=%VERSION% ^
    .\src\main.py