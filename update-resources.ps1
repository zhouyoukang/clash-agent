<#
.SYNOPSIS
    一键更新 Clash Agent 全部资源（面板/地理数据/内核）
.EXAMPLE
    .\update-resources.ps1              # 更新全部
    .\update-resources.ps1 -Only ui     # 仅更新面板
    .\update-resources.ps1 -Only geo    # 仅更新地理数据
    .\update-resources.ps1 -Only core   # 仅更新内核
#>
param(
    [ValidateSet('all','ui','geo','core')]
    [string]$Only = 'all'
)

$BaseDir = $PSScriptRoot
$Proxy = 'http://127.0.0.1:7890'
$Headers = @{ 'Accept' = 'application/vnd.github.v3+json'; 'User-Agent' = 'ClashAgent/1.0' }

function Get-WithProxy {
    param([string]$Url, [string]$OutFile, [int]$Timeout = 120)
    try {
        Invoke-WebRequest -Uri $Url -Proxy $Proxy -OutFile $OutFile -TimeoutSec $Timeout -ErrorAction Stop
        return $true
    } catch {
        # 无代理重试（国内镜像等）
        try {
            Invoke-WebRequest -Uri $Url -OutFile $OutFile -TimeoutSec $Timeout -ErrorAction Stop
            return $true
        } catch {
            Write-Host "  下载失败: $_" -ForegroundColor Red
            return $false
        }
    }
}

# ===== MetaCubeXD 官方面板 =====
function Update-Dashboard {
    Write-Host "`n[面板] MetaCubeXD 官方面板" -ForegroundColor Cyan
    $uiDir = Join-Path $BaseDir 'ui'

    try {
        $rel = Invoke-RestMethod -Uri 'https://api.github.com/repos/MetaCubeX/metacubexd/releases/latest' -Proxy $Proxy -Headers $Headers -TimeoutSec 15
        Write-Host "  最新版本: $($rel.tag_name)" -ForegroundColor Green
    } catch {
        Write-Host "  获取版本失败: $_" -ForegroundColor Red; return
    }

    $tgz = Join-Path $BaseDir 'metacubexd.tgz'
    $asset = $rel.assets | Where-Object { $_.name -eq 'compressed-dist.tgz' } | Select-Object -First 1
    if (-not $asset) { Write-Host "  未找到 compressed-dist.tgz" -ForegroundColor Red; return }

    Write-Host "  下载 $($asset.name) ($([math]::Round($asset.size/1MB,1))MB)..."
    if (Get-WithProxy -Url $asset.browser_download_url -OutFile $tgz) {
        if (Test-Path $uiDir) { Remove-Item $uiDir -Recurse -Force }
        New-Item -ItemType Directory -Path $uiDir -Force | Out-Null
        Push-Location $uiDir
        tar -xzf $tgz 2>&1 | Out-Null
        Pop-Location
        Remove-Item $tgz -Force -ErrorAction SilentlyContinue
        $count = (Get-ChildItem $uiDir -Recurse -File).Count
        Write-Host "  已更新: $count 个文件 → $uiDir" -ForegroundColor Green
    }
}

# ===== GeoIP / GeoSite 地理数据 =====
function Update-GeoData {
    Write-Host "`n[地理数据] Loyalsoldier 增强版" -ForegroundColor Cyan
    $geoDir = Join-Path $BaseDir 'geodata'
    New-Item -ItemType Directory -Path $geoDir -Force | Out-Null

    $files = @(
        @{ Name = 'geoip.dat';   Url = 'https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat';   Desc = 'GeoIP 数据库' },
        @{ Name = 'geosite.dat'; Url = 'https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat'; Desc = 'GeoSite 域名库' },
        @{ Name = 'Country.mmdb'; Url = 'https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/country.mmdb';   Desc = 'MaxMind GeoIP2' }
    )

    foreach ($f in $files) {
        $out = Join-Path $geoDir $f.Name
        Write-Host "  下载 $($f.Desc) ($($f.Name))..."
        if (Get-WithProxy -Url $f.Url -OutFile $out) {
            $sz = [math]::Round((Get-Item $out).Length / 1MB, 1)
            Write-Host "  已更新: $sz MB" -ForegroundColor Green
        }
    }
}

# ===== Mihomo 内核 =====
function Update-Core {
    Write-Host "`n[内核] Mihomo (Clash Meta)" -ForegroundColor Cyan

    try {
        $rel = Invoke-RestMethod -Uri 'https://api.github.com/repos/MetaCubeX/mihomo/releases/latest' -Proxy $Proxy -Headers $Headers -TimeoutSec 15
        Write-Host "  最新版本: $($rel.tag_name)" -ForegroundColor Green
    } catch {
        Write-Host "  获取版本失败: $_" -ForegroundColor Red; return
    }

    # 检测架构
    $arch = if ([Environment]::Is64BitOperatingSystem) { 'amd64' } else { '386' }
    $pattern = "mihomo-windows-$arch-v"
    $asset = $rel.assets | Where-Object { $_.name -match $pattern -and $_.name -match '\.zip$' -and $_.name -notmatch 'compatible' } | Select-Object -First 1
    if (-not $asset) {
        $asset = $rel.assets | Where-Object { $_.name -match "mihomo-windows-$arch" -and $_.name -match '\.zip$' } | Select-Object -First 1
    }
    if (-not $asset) { Write-Host "  未找到匹配的安装包 (arch=$arch)" -ForegroundColor Red; return }

    Write-Host "  下载 $($asset.name) ($([math]::Round($asset.size/1MB,1))MB)..."
    $zip = Join-Path $BaseDir 'mihomo-update.zip'
    if (Get-WithProxy -Url $asset.browser_download_url -OutFile $zip) {
        # 停止运行中的实例
        $proc = Get-Process -Name 'clash-meta' -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "  停止运行中的 clash-meta..." -ForegroundColor Yellow
            $proc | Stop-Process -Force; Start-Sleep 2
        }

        # 备份旧版
        $exe = Join-Path $BaseDir 'clash-meta.exe'
        if (Test-Path $exe) {
            $bak = Join-Path $BaseDir 'clash-meta.exe.bak'
            Move-Item $exe $bak -Force
            Write-Host "  旧版已备份: clash-meta.exe.bak" -ForegroundColor DarkGray
        }

        # 解压
        Expand-Archive -Path $zip -DestinationPath $BaseDir -Force
        Remove-Item $zip -Force
        # 重命名 (mihomo-windows-amd64.exe → clash-meta.exe)
        $newExe = Get-ChildItem $BaseDir -Filter 'mihomo-windows-*.exe' | Select-Object -First 1
        if ($newExe) {
            Rename-Item $newExe.FullName 'clash-meta.exe' -Force
            $sz = [math]::Round((Get-Item $exe).Length / 1MB, 1)
            Write-Host "  已更新: $sz MB → clash-meta.exe" -ForegroundColor Green
        } else {
            Write-Host "  解压后未找到可执行文件" -ForegroundColor Red
            # 恢复备份
            if (Test-Path "$exe.bak") { Move-Item "$exe.bak" $exe -Force }
        }
    }
}

# ===== 主流程 =====
Write-Host "===== Clash Agent 资源更新 =====" -ForegroundColor Magenta
Write-Host "代理: $Proxy | 目标: $Only" -ForegroundColor DarkGray

switch ($Only) {
    'ui'   { Update-Dashboard }
    'geo'  { Update-GeoData }
    'core' { Update-Core }
    'all'  { Update-Dashboard; Update-GeoData; Update-Core }
}

Write-Host "`n===== 更新完成 =====" -ForegroundColor Green
