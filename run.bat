@echo off
chcp 65001 > nul
title MSS (Minecraft Simple Server)

:: Check if virtual environment exists
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:: Validate Python dependencies
%PYTHON_EXE% -c "import fastapi, uvicorn, websockets, psutil, PIL, nbtlib" 2>nul
if %errorlevel% neq 0 (
    echo ========================================================
    echo   [MSS] Dependencies missing or incomplete!
    echo   Launching automated 1-click installer...
    echo ========================================================
    echo.
    call install.bat
    exit /b
)

echo ========================================================
echo   Starting MSS (Minecraft Simple Server)...
echo   Web Panel: http://127.0.0.1:8000
echo ========================================================
echo.

%PYTHON_EXE% run.py
pause
