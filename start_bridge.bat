@echo off
setlocal EnableDelayedExpansion

:: -------------------------------------------------------------
:: Nova OS — Windows AI Bridge Launcher & Firewall Helper
:: -------------------------------------------------------------

:: Test for administrative rights
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [Nova OS] Administrative permissions required to verify firewall rules.
    echo Requesting elevation...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

:: Running with administrative privileges
title Nova OS Bridge Launcher
cd /d "%~dp0"

echo ==============================================================
echo  NOVA OS — STARTING BRIDGE (ADMINISTRATOR)
echo ==============================================================

:: Step 1: Run Firewall Helper Script
set "FIREWALL_SCRIPT=%~dp0scripts\allow_firewall.ps1"
if exist "!FIREWALL_SCRIPT!" (
    echo [1/2] Configuring Windows Defender Firewall rules...
    powershell -NoProfile -ExecutionPolicy Bypass -File "!FIREWALL_SCRIPT!"
) else (
    echo [1/2] Warning: scripts\allow_firewall.ps1 not found, continuing...
)

:: Step 2: Locate Python
set "PYTHON_CMD=python"
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0venv\Scripts\python.exe"
)

echo [2/2] Launching Nova OS Bridge using "!PYTHON_CMD!"...
echo --------------------------------------------------------------

:: Step 3: Run run_bridge.py
if exist "%~dp0run_bridge.py" (
    "!PYTHON_CMD!" "%~dp0run_bridge.py"
) else (
    echo [Error] Could not find run_bridge.py!
    pause
    exit /b 1
)

pause
