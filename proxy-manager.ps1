<#
.SYNOPSIS
    VPN/Proxy Manager - clash-meta (Mihomo) direct launch
.EXAMPLE
    .\proxy-manager.ps1              # Show status
    .\proxy-manager.ps1 -Action on   # Start clash-meta + set proxies
    .\proxy-manager.ps1 -Action off  # Disable proxies
    .\proxy-manager.ps1 -Action dev  # Dev tools proxy only (git/npm)
    .\proxy-manager.ps1 -Action clean # Remove ALL proxy traces
    .\proxy-manager.ps1 -Action toggle
#>
param(
    [ValidateSet('status','on','off','dev','clean','toggle')]
    [string]$Action = 'status'
)

$BypassList = @(
    'localhost','127.0.0.1','192.168.*','10.*','172.16.*',
    '*.baidu.com','*.baidupcs.com','*.bdpan.com',
    '*.bilibili.com','*.bilivideo.com','*.hdslb.com','*.biliapi.net',
    '*.quark.cn','*.yunpan.cn',
    '*.chaoxing.com','*.zhihuishu.com',
    '*.taobao.com','*.tmall.com','*.alipay.com','*.alicdn.com','*.aliyuncs.com',
    '*.jd.com','*.qq.com','*.weixin.qq.com','*.wechat.com',
    '*.douyin.com','*.bytedance.com','*.toutiao.com',
    '*.xju.edu.cn','*.3chuang.net','*.sanxianjiyi.com',
    'aiotvr.xyz','*.aiotvr.xyz','hf-mirror.com','*.hf-mirror.com'
) -join ';'

$BaseDir = $PSScriptRoot
$ClashMeta = Join-Path $BaseDir 'clash-meta.exe'
$ClashConfig = Join-Path $BaseDir 'clash-config.yaml'
$MixedPort = 7890
$ApiPort = 9097
$HttpProxy = '127.0.0.1:7890'
$RegPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'

function WS { param($L,$V,$C='White'); Write-Host "  $L : " -NoNewline -ForegroundColor Gray; Write-Host $V -ForegroundColor $C }

function Test-Port { param([int]$P=$MixedPort)
    try { $t=New-Object System.Net.Sockets.TcpClient; $t.Connect('127.0.0.1',$P); $t.Close(); $true } catch { $false }
}

function Get-ClashProc {
    Get-Process -Name 'clash-meta' -ErrorAction SilentlyContinue
}

function Show-Status {
    Write-Host "`n===== VPN/Proxy Status =====" -ForegroundColor Cyan
    Write-Host "[clash-meta (Mihomo)]" -ForegroundColor Yellow
    $p = Get-ClashProc
    if($p){ WS "Process" "Running (PID: $(($p|%{$_.Id}) -join ','))" "Green" } else { WS "Process" "Not running" "Red" }
    $po = Test-Port
    WS "Port $MixedPort" $(if($po){"Listening"}else{"Closed"}) $(if($po){"Green"}else{"DarkGray"})
    $api = Test-Port -P $ApiPort
    WS "API $ApiPort" $(if($api){"Listening"}else{"Closed"}) $(if($api){"Green"}else{"DarkGray"})

    Write-Host "[System Proxy]" -ForegroundColor Yellow
    $r = Get-ItemProperty $RegPath -ErrorAction SilentlyContinue
    if($r.ProxyEnable -eq 1){ WS "Status" "ON -> $($r.ProxyServer)" "Green"
    } else {
        WS "Status" "OFF" "DarkGray"
        if($r.ProxyServer){ WS "Residual" $r.ProxyServer "DarkYellow" }
    }

    Write-Host "[Env Vars]" -ForegroundColor Yellow
    $any=$false
    foreach($v in 'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'){
        $val=[Environment]::GetEnvironmentVariable($v,'User')
        if($val){ WS $v $val "Green"; $any=$true }
    }
    if(-not $any){ WS "All" "(empty)" "DarkGray" }

    Write-Host "[Git]" -ForegroundColor Yellow
    $gh = git config --global --get http.proxy 2>$null
    $gs = git config --global --get https.proxy 2>$null
    if($gh -or $gs){ WS "http.proxy" $(if($gh){$gh}else{"(none)"}) $(if($gh){"Green"}else{"DarkGray"})
                     WS "https.proxy" $(if($gs){$gs}else{"(none)"}) $(if($gs){"Green"}else{"DarkGray"})
    } else { WS "Proxy" "(none)" "DarkGray" }

    Write-Host "[Current Process]" -ForegroundColor Yellow
    WS 'HTTP_PROXY' $(if($env:HTTP_PROXY){$env:HTTP_PROXY}else{"(empty)"}) $(if($env:HTTP_PROXY){"Green"}else{"DarkGray"})
    WS 'HTTPS_PROXY' $(if($env:HTTPS_PROXY){$env:HTTPS_PROXY}else{"(empty)"}) $(if($env:HTTPS_PROXY){"Green"}else{"DarkGray"})

    Write-Host "[Connectivity]" -ForegroundColor Yellow
    if($po){
        try{ $x=Invoke-WebRequest 'https://www.google.com' -Proxy "http://$HttpProxy" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop; WS "Google(proxy)" "OK ($($x.StatusCode))" "Green" }catch{ WS "Google(proxy)" "FAIL" "Red" }
    } else { WS "Google(proxy)" "proxy not running" "DarkGray" }
    try{ $x=Invoke-WebRequest 'https://www.baidu.com' -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop; WS "Baidu(direct)" "OK ($($x.StatusCode))" "Green" }catch{ WS "Baidu(direct)" "FAIL" "Red" }
    Write-Host ""
}

function Enable-Proxy {
    Write-Host "`n===== Enable VPN Proxy =====" -ForegroundColor Green
    if(-not (Get-ClashProc)){
        if(Test-Path $ClashMeta){
            if(-not (Test-Path $ClashConfig)){ Write-Host "  WARNING: $ClashConfig not found" -ForegroundColor Yellow; return }
            Write-Host "  Starting clash-meta..." -ForegroundColor Cyan
            Start-Process $ClashMeta -ArgumentList "-d `"$BaseDir`" -f `"$ClashConfig`"" -WindowStyle Hidden
            Start-Sleep 3
        } else { Write-Host "  WARNING: $ClashMeta not found" -ForegroundColor Yellow }
    } else { Write-Host "  clash-meta already running" -ForegroundColor Green }
    $retry=0; while(-not(Test-Port) -and $retry -lt 10){ Start-Sleep 1; $retry++ }
    if(Test-Port){ Write-Host "  Port $MixedPort ready" -ForegroundColor Green } else { Write-Host "  WARNING: Port $MixedPort not ready" -ForegroundColor Yellow }
    Set-ItemProperty $RegPath -Name ProxyEnable -Value 1
    Set-ItemProperty $RegPath -Name ProxyServer -Value $HttpProxy
    Set-ItemProperty $RegPath -Name ProxyOverride -Value $BypassList
    Write-Host "  System proxy -> $HttpProxy" -ForegroundColor Green
    Set-DevProxy -Silent
    Write-Host "  DONE" -ForegroundColor Green
}

function Disable-Proxy {
    Write-Host "`n===== Disable VPN Proxy =====" -ForegroundColor Red
    Set-ItemProperty $RegPath -Name ProxyEnable -Value 0
    Write-Host "  System proxy -> OFF" -ForegroundColor Yellow
    Clear-DevProxy -Silent
    Write-Host "  clash-meta kept running (use -Action clean to stop)" -ForegroundColor DarkGray
    Write-Host "  DONE" -ForegroundColor Green
}

function Set-DevProxy {
    param([switch]$Silent)
    if(-not $Silent){ Write-Host "`n===== Dev Mode: Git/NPM proxy =====" -ForegroundColor Magenta }
    $proxy = "http://$HttpProxy"
    git config --global http.proxy $proxy 2>$null
    git config --global https.proxy $proxy 2>$null
    if(-not $Silent){ Write-Host "  Git -> $proxy" -ForegroundColor Green }
    npm config set proxy $proxy 2>$null
    npm config set https-proxy $proxy 2>$null
    if(-not $Silent){ Write-Host "  NPM -> $proxy" -ForegroundColor Green }
    $env:HTTP_PROXY = $proxy; $env:HTTPS_PROXY = $proxy; $env:ALL_PROXY = "socks5://127.0.0.1:$MixedPort"
    if(-not $Silent){ Write-Host "  Env(session) -> $proxy" -ForegroundColor Green; Write-Host "  DONE" -ForegroundColor Green }
}

function Clear-DevProxy {
    param([switch]$Silent)
    git config --global --unset http.proxy 2>$null; git config --global --unset https.proxy 2>$null
    npm config delete proxy 2>$null; npm config delete https-proxy 2>$null
    $env:HTTP_PROXY=$null; $env:HTTPS_PROXY=$null; $env:ALL_PROXY=$null
    if(-not $Silent){ Write-Host "  Git/NPM/Env cleared" -ForegroundColor Yellow }
}

function Clean-All {
    Write-Host "`n===== Clean ALL proxy traces =====" -ForegroundColor Red
    Set-ItemProperty $RegPath -Name ProxyEnable -Value 0
    Remove-ItemProperty $RegPath -Name ProxyServer -ErrorAction SilentlyContinue
    Remove-ItemProperty $RegPath -Name ProxyOverride -ErrorAction SilentlyContinue
    Remove-ItemProperty $RegPath -Name AutoConfigURL -ErrorAction SilentlyContinue
    Write-Host "  System proxy -> cleaned" -ForegroundColor Yellow
    Clear-DevProxy -Silent; Write-Host "  Git/NPM -> cleaned" -ForegroundColor Yellow
    foreach($v in 'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy'){
        [Environment]::SetEnvironmentVariable($v,$null,'User')
    }
    Write-Host "  User env vars -> cleaned" -ForegroundColor Yellow
    $p = Get-ClashProc; if($p){ $p | Stop-Process -Force -ErrorAction SilentlyContinue; Write-Host "  clash-meta -> killed" -ForegroundColor Yellow }
    Write-Host "  DONE" -ForegroundColor Green
}

switch($Action){
    'status' { Show-Status }
    'on'     { Enable-Proxy; Show-Status }
    'off'    { Disable-Proxy; Show-Status }
    'dev'    { Set-DevProxy; Show-Status }
    'clean'  { Clean-All; Show-Status }
    'toggle' { $r=Get-ItemProperty $RegPath; if($r.ProxyEnable -eq 1 -or (Test-Port)){Disable-Proxy}else{Enable-Proxy}; Show-Status }
}
