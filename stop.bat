@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
chcp 65001 >nul
title VPN Manager - Stop

echo Disabling system proxy...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul 2>&1

echo Stopping tray app...
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq vpn-app*" >nul 2>&1

echo Stopping clash-meta...
taskkill /F /IM clash-meta.exe >nul 2>&1

echo Stopping Web UI...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9098 " ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1

echo Clearing dev proxies...
git config --global --unset http.proxy >nul 2>&1
git config --global --unset https.proxy >nul 2>&1

echo.
echo [OK] All services stopped, proxy disabled.
timeout /t 2 >nul
