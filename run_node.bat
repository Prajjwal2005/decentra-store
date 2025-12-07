@echo off
:: DecentraStore Node Runner for Windows
:: Double-click this file to start your storage node!

title DecentraStore Storage Node
color 0A

:: IMPORTANT: Change to the directory where this batch file is located
cd /d "%~dp0"

echo.
echo  ╔═══════════════════════════════════════════════════════════╗
echo  ║           DecentraStore Storage Node Setup                ║
echo  ╚═══════════════════════════════════════════════════════════╝
echo.

:: Configuration - CHANGE THESE FOR YOUR SETUP
set DISCOVERY_URL=http://localhost:4000
set NODE_PORT=6001
set STORAGE_DIR=%USERPROFILE%\DecentraStore\chunks

:: Generate a unique node ID based on computer name
set NODE_ID=node-%COMPUTERNAME%

echo  Discovery Server: %DISCOVERY_URL%
echo  Node Port:        %NODE_PORT%
echo  Storage Location: %STORAGE_DIR%
echo  Node ID:          %NODE_ID%
echo.

:: Create storage directory
if not exist "%STORAGE_DIR%" (
    echo  Creating storage directory...
    mkdir "%STORAGE_DIR%"
)

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed or not in PATH!
    echo  Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check if requirements are installed
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo  Installing dependencies...
    pip install flask flask-cors requests cryptography pycryptodome -q
)

echo.
echo  ═══════════════════════════════════════════════════════════
echo  Starting Storage Node...
echo  Press Ctrl+C to stop
echo  ═══════════════════════════════════════════════════════════
echo.

:: Run the storage node
python -m node.storage_node ^
    --host 0.0.0.0 ^
    --port %NODE_PORT% ^
    --discovery %DISCOVERY_URL% ^
    --storage-dir "%STORAGE_DIR%" ^
    --node-id %NODE_ID%

pause
