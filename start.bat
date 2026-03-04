@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
chcp 65001 >nul 2>nul
title VPN Manager

echo ========================================
echo   VPN Manager - Clash Meta (Mihomo)
echo ========================================
echo.

:: Preferred: tray app (handles everything)
if exist "%~dp0vpn-app.pyw" (
    echo [..] Starting VPN Manager tray app...
    start "" pythonw "%~dp0vpn-app.pyw"
    echo [OK] Tray app launched (check system tray)
    echo.
    echo   Web UI:      http://127.0.0.1:9098
    echo   MetaCubeXD:  http://127.0.0.1:9097/ui/
    echo   Proxy:       127.0.0.1:7890
    echo.
    timeout /t 3 /nobreak >nul
    exit /b 0
)

:: Fallback: legacy mode (no tray)
echo [WARN] vpn-app.pyw not found, using legacy mode
echo.

:: Start clash-meta
netstat -ano 2>nul | findstr ":7890 " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] clash-meta already running
) else (
    echo [..] Starting clash-meta...
    start "clash-meta" /MIN "%~dp0clash-meta.exe" -d "%~dp0" -f "%~dp0clash-config.yaml"
    timeout /t 5 /nobreak >nul
    netstat -ano 2>nul | findstr ":7890 " | findstr "LISTENING" >nul 2>&1
    if %errorlevel%==0 ( echo [OK] clash-meta started ) else ( echo [WARN] clash-meta may need more time )
)

:: Start Web UI
netstat -ano 2>nul | findstr ":9098 " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Web UI already running
) else (
    echo [..] Starting Web UI...
    start "VPN-WebUI" /MIN python "%~dp0vpn-manager.py"
    timeout /t 3 /nobreak >nul
    echo [OK] Web UI started
)

echo.
echo   Web UI:  http://127.0.0.1:9098
echo   Proxy:   127.0.0.1:7890
echo.

start http://127.0.0.1:9098
echo Press any key to exit (services keep running)...
pause >nul
