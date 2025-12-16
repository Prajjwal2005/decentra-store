@echo off
REM DecentraStore Storage Node - Windows Automated Installer
REM This script automatically sets up and runs a storage node on Windows
REM
REM Usage:
REM   1. Download this file
REM   2. Double-click to run
REM   3. Follow the prompts

setlocal enabledelayedexpansion

echo ============================================================
echo DecentraStore Storage Node - Automated Installer
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8 or higher from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

echo [OK] Python is installed
python --version

REM Check if git is installed
git --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Git is not installed or not in PATH
    echo.
    echo Please install Git from:
    echo https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)

echo [OK] Git is installed

REM Set installation directory
set "INSTALL_DIR=%USERPROFILE%\DecentraStore"

echo.
echo Installation directory: %INSTALL_DIR%
echo.

REM Check if already installed
if exist "%INSTALL_DIR%" (
    echo DecentraStore is already installed at %INSTALL_DIR%
    echo.
    choice /C YN /M "Do you want to update and restart the node"
    if errorlevel 2 goto configure
    if errorlevel 1 goto update
) else (
    goto install
)

:install
echo.
echo ============================================================
echo Installing DecentraStore...
echo ============================================================
echo.

REM Clone repository
echo [1/3] Downloading DecentraStore...
git clone https://github.com/Prajjwal2005/decentra-store.git "%INSTALL_DIR%"
if errorlevel 1 (
    echo ERROR: Failed to download DecentraStore
    pause
    exit /b 1
)

cd /d "%INSTALL_DIR%"

REM Install dependencies
echo.
echo [2/3] Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [3/3] Installation complete!
goto configure

:update
echo.
echo ============================================================
echo Updating DecentraStore...
echo ============================================================
echo.

cd /d "%INSTALL_DIR%"

REM Pull latest changes
echo Downloading latest updates...
git pull origin main
if errorlevel 1 (
    echo WARNING: Failed to update. Continuing with current version...
)

REM Update dependencies
echo Updating dependencies...
pip install -r requirements.txt --upgrade
if errorlevel 1 (
    echo WARNING: Failed to update dependencies
)

echo.
echo Update complete!
goto configure

:configure
echo.
echo ============================================================
echo Node Configuration
echo ============================================================
echo.

REM Get configuration from user
set "SERVER_URL=https://web-production-dcddc.up.railway.app"
set "CAPACITY=50"

echo Server URL: %SERVER_URL%
echo Default storage capacity: %CAPACITY% GB
echo.

choice /C YN /M "Do you want to customize these settings"
if errorlevel 2 goto create_shortcut
if errorlevel 1 goto custom_config

:custom_config
echo.
set /p "SERVER_URL=Enter server URL (or press Enter for default): "
if "%SERVER_URL%"=="" set "SERVER_URL=https://web-production-dcddc.up.railway.app"

set /p "CAPACITY=Enter storage capacity in GB (or press Enter for default): "
if "%CAPACITY%"=="" set "CAPACITY=50"

:create_shortcut
echo.
echo ============================================================
echo Creating shortcuts...
echo ============================================================
echo.

REM Create batch file to run node
set "RUN_SCRIPT=%INSTALL_DIR%\run_node.bat"
(
echo @echo off
echo cd /d "%INSTALL_DIR%"
echo python node_package\websocket_node.py --server %SERVER_URL% --capacity %CAPACITY%
echo pause
) > "%RUN_SCRIPT%"

echo Created: %RUN_SCRIPT%

REM Create desktop shortcut
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\DecentraStore Node.lnk"

REM Use PowerShell to create shortcut
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%SHORTCUT%'); $SC.TargetPath = '%RUN_SCRIPT%'; $SC.WorkingDirectory = '%INSTALL_DIR%'; $SC.Description = 'Run DecentraStore Storage Node'; $SC.Save()"

if exist "%SHORTCUT%" (
    echo Created desktop shortcut: DecentraStore Node
) else (
    echo WARNING: Could not create desktop shortcut
)

REM Create startup shortcut (optional)
echo.
choice /C YN /M "Do you want the node to start automatically with Windows"
if errorlevel 2 goto run_node
if errorlevel 1 goto create_startup

:create_startup
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_SHORTCUT=%STARTUP%\DecentraStore Node.lnk"

powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%STARTUP_SHORTCUT%'); $SC.TargetPath = '%RUN_SCRIPT%'; $SC.WorkingDirectory = '%INSTALL_DIR%'; $SC.Description = 'Run DecentraStore Storage Node'; $SC.Save()"

if exist "%STARTUP_SHORTCUT%" (
    echo Created startup shortcut - Node will start automatically with Windows
) else (
    echo WARNING: Could not create startup shortcut
)

:run_node
echo.
echo ============================================================
echo Installation Complete!
echo ============================================================
echo.
echo Your DecentraStore storage node is ready!
echo.
echo You can start it by:
echo   1. Double-clicking the "DecentraStore Node" shortcut on your desktop
echo   2. Running: %RUN_SCRIPT%
echo.
echo Storage location: %INSTALL_DIR%\node_storage
echo Server: %SERVER_URL%
echo Capacity: %CAPACITY% GB
echo.
choice /C YN /M "Do you want to start the node now"
if errorlevel 2 goto end
if errorlevel 1 goto start

:start
echo.
echo Starting node...
cd /d "%INSTALL_DIR%"
python node_package\websocket_node.py --server %SERVER_URL% --capacity %CAPACITY%
goto end

:end
echo.
echo Thank you for joining the DecentraStore network!
pause
exit /b 0
