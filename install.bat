@echo off
chcp 65001 > nul
title Minecraft Simple Server (MSS) - Automated Installer

echo ===============================================================================
echo   ⛏️  MINECRAFT SIMPLE SERVER (MSS) — AUTOMATED 1-CLICK INSTALLER
echo ===============================================================================
echo.

:: 1. Check Python
echo [1/4] Checking Python environment...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in your system PATH!
    echo.
    echo Please install Python 3.10 or newer from:
    echo   https://www.python.org/downloads/
    echo.
    echo NOTE: Make sure to check the box "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set "PY_VER=%%i"
echo       Detected: %PY_VER%

:: 2. Check Java
echo.
echo [2/4] Checking Java runtime environment...
where java >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] Java was not found in your system PATH.
    echo           Minecraft server engines require Java:
    echo             - Minecraft 1.20.5+ : Java 21 LTS (recommended)
    echo             - Minecraft 1.18 - 1.20.4 : Java 17 LTS
    echo             - Minecraft 1.16.5 and older : Java 8 or 11
    echo           Download Eclipse Adoptium Temurin: https://adoptium.net/
    echo           (You can also specify custom java_path later in MSS web panel).
) else (
    for /f "tokens=*" %%i in ('java -version 2^>^&1') do (
        echo       Detected: %%i
        goto :java_checked
    )
)
:java_checked

:: 3. Setup Virtual Environment
echo.
echo [3/4] Preparing Python virtual environment (venv)...
if not exist "venv\Scripts\python.exe" (
    echo       Creating isolated virtual environment in .\venv ...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
) else (
    echo       Virtual environment already exists in .\venv.
)

echo       Installing dependencies from requirements.txt...
venv\Scripts\python.exe -m pip install --quiet --upgrade pip
venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies! Please check your network connection.
    pause
    exit /b 1
)
echo       Dependencies successfully installed.

:: 4. Download and cache Minecraft audio assets
echo.
echo [4/4] Verifying Minecraft UI audio sound assets...
venv\Scripts\python.exe scripts\download_mc_sounds.py
echo.

echo ===============================================================================
echo   ✨ INSTALLATION COMPLETED SUCCESSFULLY!
echo ===============================================================================
echo.
echo   MSS Web Panel is ready to launch.
echo   URL: http://127.0.0.1:8000
echo.
set /p "LAUNCH=Would you like to launch MSS right now? (Y/n): "
if /i "%LAUNCH%"=="n" (
    echo.
    echo You can start the server anytime by double-clicking 'run.bat'.
    pause
    exit /b 0
)

echo.
echo Launching MSS...
call run.bat
