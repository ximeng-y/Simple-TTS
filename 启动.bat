@echo off
cd /d "%~dp0"

rem Only use the project's own virtual environment: PySide6-Essentials is
rem installed in .venv; the system Python does not have it.
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [Error] Virtual environment not found: .venv
    echo.
    echo Create it first, from the project root:
    echo     py -3.12 -m venv .venv
    echo     .venv\Scripts\pip install -r requirements-dev.txt
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo [Error] Program exited abnormally, error code %errorlevel%
    pause
)
