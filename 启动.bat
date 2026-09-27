@echo off
cd /d "%~dp0"
py -3.12 main.py 2>nul || python main.py
if errorlevel 1 (
    echo Failed to start: Python 3.12 not found. Please install it first (with Tkinter).
    pause
)
