.\.venv\Scripts\python.exe -m nuitka ^
    --onefile ^
    --standalone ^
    --follow-imports ^
    --enable-plugin=tk-inter ^
    --include-package=textual ^
    --include-package=rich._unicode_data ^
    --include-module=sounddevice ^
    --include-package=imageio_ffmpeg ^
    --output-filename=PyAsciiFilm.exe ^
    --output-dir=build ^
    --lto=yes ^
    --windows-company-name=K_PU ^
    --windows-product-name=PyAsciiFilm ^
    --windows-file-version=2.1 ^
    --windows-product-version=2.1 ^
    .\src\main.py
