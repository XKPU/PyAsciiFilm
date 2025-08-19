@echo off
set CURRENT_DIR=%~dp0
set CURRENT_DIR=%CURRENT_DIR:~0,-1%

echo home = %CURRENT_DIR%\python> .venv\pyvenv.cfg.tmp
echo include-system-site-packages = false>> .venv\pyvenv.cfg.tmp
echo version = 3.8.0>> .venv\pyvenv.cfg.tmp
move /y .venv\pyvenv.cfg.tmp .venv\pyvenv.cfg > nul

if not exist ".venv\Scripts\python.exe" (
    echo Error: .venv\Scripts\python.exe not found
    echo Please make sure virtual environment is set up correctly
    pause
    exit /b 1
)

if not exist "main.py" (
    echo Error: main.py main program file not found
    pause
    exit /b 1
)

.venv\Scripts\python.exe main.py

if %errorlevel% neq 0 (
    echo.
    echo Program exited abnormally, error code: %errorlevel%
    pause
)

pause