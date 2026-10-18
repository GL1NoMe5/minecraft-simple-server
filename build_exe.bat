@echo off
chcp 65001 > nul
cd /d "%~dp0"
title MSS (Minecraft Simple Server) - Standalone Executable Builder

echo ===============================================================================
echo   ⛏️  MINECRAFT SIMPLE SERVER (MSS) — STANDALONE EXE BUILDER
echo ===============================================================================
echo.

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        where py >nul 2>nul
        if %errorlevel% equ 0 (
            set "PYTHON_EXE=py -3"
        ) else (
            set "PYTHON_EXE=python"
        )
    )
)

%PYTHON_EXE% scripts\build_exe.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Standalone executable build failed!
    pause
    exit /b 1
)

echo.
pause
