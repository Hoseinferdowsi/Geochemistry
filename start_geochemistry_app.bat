@echo off
chcp 65001 >nul
title Geochemistry Analysis System

echo.
echo ============================================================
echo 🌍 Geochemistry Analysis System
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo Please install Python 3.7+ and try again
    pause
    exit /b 1
)

echo ✅ Python found
echo.

REM Check if required packages are installed
echo Checking required packages...
python -c "import flask, pandas, numpy, scipy" >nul 2>&1
if errorlevel 1 (
    echo ❌ Some required packages are missing
    echo Installing required packages...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ❌ Failed to install packages
        pause
        exit /b 1
    )
)

echo ✅ All required packages are installed
echo.

REM Create necessary directories
if not exist "uploads" mkdir uploads
if not exist "output" mkdir output
if not exist "templates" mkdir templates

echo 📁 Directories created/verified
echo.

echo 🚀 Starting Flask application...
echo 🌐 Web interface will be available at: http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo ============================================================
echo.

REM Start the application
python geochemistry_analysis_app.py

echo.
echo 🛑 Application stopped
pause 