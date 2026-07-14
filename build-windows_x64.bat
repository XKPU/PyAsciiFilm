@echo off
set VERSION=
for /f "usebackq delims=" %%v in ("VERSION") do set "VERSION=%%v"
if not defined VERSION set VERSION=0.0.0

.venv-windows\Scripts\python.exe -m nuitka ^
    --onefile ^
    --standalone ^
    --follow-imports ^
    --enable-plugin=tk-inter ^
    --include-package=textual ^
    --include-package=rich._unicode_data ^
    --include-package=imageio_ffmpeg ^
    --include-module=miniaudio ^
    --output-filename=PyAsciiFilm-v%VERSION%-windows_x64.exe ^
    --output-dir=build\windows_x64 ^
    --lto=yes ^
    --windows-company-name=K_PU ^
    --windows-product-name=PyAsciiFilm ^
    --windows-file-version=%VERSION% ^
    --windows-product-version=%VERSION% ^
    .\src\main.py