@echo off
chcp 65001 >nul
title WebEtu Meal Reservation
echo ========================================================
echo        🎓 WebEtu Meal Reservation Automation
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Error: Python is not installed or not added to PATH.
    echo.
    echo Please install Python 3 from https://www.python.org/downloads/
    echo IMPORTANT: During installation, make sure to check:
    echo   [x] "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

python -c "import requests" >nul 2>nul
if %errorlevel% neq 0 (
    echo [*] Installing required library (requests)...
    pip install -r requirements.txt
    echo.
)

python webetu_client.py auto %*
echo.
pause
