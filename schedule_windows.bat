@echo off
chcp 65001 >nul
title WebEtu Daily Automation Scheduler
echo ========================================================
echo     WebEtu Automation - Windows Daily Scheduler
echo ========================================================
echo.
echo This script will schedule WebEtu to run automatically 
echo every day at 20:00 (8:00 PM) via Windows Task Scheduler.
echo.

set TASK_NAME=WebEtuMealReservation
set SCRIPT_DIR=%~dp0
set RUN_CMD=cmd.exe /c "cd /d "%SCRIPT_DIR%" && python webetu_client.py auto"

schtasks /create /tn "%TASK_NAME%" /tr "%RUN_CMD%" /sc daily /st 20:00 /f >nul 2>nul

if %errorlevel% equ 0 (
    echo [+] SUCCESS: Task '%TASK_NAME%' scheduled for 20:00 daily!
    echo     It will run in the background every day to reserve your meals.
    echo.
    echo To remove this task in the future, run:
    echo     schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo [!] Notice: Please right-click this file and select "Run as Administrator"
    echo     to allow Windows Task Scheduler to register the daily task.
)

echo.
pause
