@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
chcp 65001 >nul 2>nul
title VPN Manager v4.0

echo.
echo   VPN Manager v4.0 - One Click Start
echo   ===================================
echo.

:: Check if already running
netstat -ano 2>nul | findstr ":9098 " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo   [OK] Already running
    start http://127.0.0.1:9098
    timeout /t 2 /nobreak >nul
    exit /b 0
)

:: Start vpn-manager.py (it auto-starts clash-meta)
echo   [..] Starting...
start "" pythonw "%~dp0vpn-manager.py"
timeout /t 4 /nobreak >nul

echo.
echo   Web UI:  http://127.0.0.1:9098
echo   Proxy:   127.0.0.1:7890
echo.
