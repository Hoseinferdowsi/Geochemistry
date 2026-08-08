@echo off
echo Starting Geochemistry Analysis Server on port 80...
echo This requires administrator privileges...

:: Get the directory where the batch file is located
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running with administrator privileges...
    echo.
    echo Starting Python server...
    echo.
    python "%SCRIPT_DIR%server.py"
    if %errorLevel% neq 0 (
        echo.
        echo Error occurred while starting the server!
        echo Please check the error message above.
    )
) else (
    echo Please run this script as administrator!
    echo Right-click on this file and select "Run as administrator"
)

echo.
echo Press any key to exit...
pause > nul 