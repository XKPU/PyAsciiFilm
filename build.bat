.\.venv\Scripts\python.exe -m nuitka ^
    --standalone ^
    --enable-plugin=tk-inter ^
    --include-data-file=ffplay.exe=ffplay.exe ^
    --include-data-file=setting.json=setting.json ^
    --output-filename=PyAsciiFilm.exe ^
    --output-dir=build\Win_64 ^
    --python-flag=-O ^
    --lto=yes ^
    .\src\main.py
