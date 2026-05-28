@echo off
REM ============================================================
REM Mimir Launcher Build Script
REM Run this from the launcher\ directory.
REM Requires Python 3.11+ and a venv with requirements installed.
REM ============================================================

echo.
echo  MIMIR — Build Script
echo  =====================

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found on PATH.
    echo  Install Python 3.11+ and try again.
    pause
    exit /b 1
)

REM Create venv if it doesn't exist
if not exist "venv\" (
    echo  Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install/update dependencies
echo  Installing dependencies...
pip install -r requirements.txt --quiet

REM Clean previous build
if exist "dist\" (
    echo  Cleaning previous build...
    rmdir /s /q dist
)
if exist "build\" (
    rmdir /s /q build
)

REM Run PyInstaller
echo  Building Mimir.exe...
pyinstaller Mimir.spec

if errorlevel 1 (
    echo.
    echo  BUILD FAILED. Check output above for errors.
    pause
    exit /b 1
)

echo.
echo  Build complete.
echo  Output: dist\Mimir\Mimir.exe
echo.
echo  To deploy to the drive:
echo    1. Copy the entire dist\Mimir\ folder to {drive}\Mimir\launcher\
echo    2. Rename it so Mimir.exe is at {drive}\Mimir\launcher\Mimir.exe
echo    3. The config\ and assets\ folders are bundled inside _internal\
echo       but the live config\ in launcher\ takes precedence for user settings.
echo.
pause
