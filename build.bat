.\.venv\Scripts\python.exe -m nuitka ^
    --onefile ^
    --enable-plugin=tk-inter ^
    --include-package=textual ^
    --include-package=rich._unicode_data ^
    --include-module=sounddevice ^
    --include-data-dir=.\.venv\Lib\site-packages\_sounddevice_data=_sounddevice_data ^
    --include-package=imageio_ffmpeg ^
    --include-package-data=imageio_ffmpeg ^
    --output-filename=PyAsciiFilm.exe ^
    --output-dir=build\Win_64 ^
    --python-flag=-O ^
    --lto=yes ^
    --windows-company-name=K_PU ^
    --windows-product-name=PyAsciiFilm ^
    --windows-file-version=2.1 ^
    --windows-product-version=2.1 ^
    .\src\main.py
