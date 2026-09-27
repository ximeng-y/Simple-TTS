@echo off
cd /d "%~dp0"

rem Only use the project's own virtual environment: PySide6-Essentials is
rem installed in .venv; the system Python does not have it.
if not exist ".venv\Scripts\pythonw.exe" (
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

rem Launch with pythonw.exe so no console is allocated, detached via start so
rem this window closes immediately: double-clicking leaves only the app window.
rem Keep the file pure ASCII -- cmd parses it in the OEM codepage (GBK here),
rem where multi-byte text can swallow the character after it and break lines.
start "" /b ".venv\Scripts\pythonw.exe" main.py
if errorlevel 1 (
    echo.
    echo [Error] Failed to start the program, error code %errorlevel%
    pause
)
