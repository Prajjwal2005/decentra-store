@echo off
:: ============================================================
:: DecentraStore Storage Node Launcher
:: ============================================================
:: Just double-click to run! A setup window will appear.
:: ============================================================

title DecentraStore Node
color 0A

:: Change to script directory
cd /d "%~dp0"

echo.
echo  ============================================================
echo       DecentraStore Storage Node
echo  ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed!
    echo.
    echo  Please download Python from:
    echo  https://www.python.org/downloads/
    echo.
    echo  Make sure to check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)

:: Run the launcher (GUI or CLI)
python launcher.py

pause
