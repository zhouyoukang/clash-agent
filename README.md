<div align="center">

# Clash Agent

**Per-App Intelligent Routing VPN Manager**

**按应用智能路由 VPN 管理器**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-3776ab.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078d4.svg)]()
[![Engine](https://img.shields.io/badge/Engine-Mihomo-orange.svg)](https://github.com/MetaCubeX/mihomo)

*Chrome goes through VPN. WeChat goes direct. One click. Zero friction.*

*Chrome 走 VPN，微信走直连。一键切换，无感守护。*

</div>

---

## Why Clash Agent? | 为什么？

> 苦谛：全局代理让国内应用卡顿。灭谛：每个应用走最适合它的路。

| Pain Point | Solution |
|------------|----------|
| Global proxy slows domestic apps | **Per-process routing** — each app chooses VPN or Direct |
| Proxy silently disabled by other software | **Proxy guard** — auto-detect and recover in background |
| Clash GUIs are heavy (Electron 200MB+) | **Single Python file** — no framework, lightweight, fast |
| Too many manual steps | **One-click** — System proxy + Git + NPM, all at once |

## Quick Start | 快速开始

> Three steps. That's it. 三步即可，大道至简。

```powershell
# 1. Clone & install
git clone https://github.com/zhouyoukang/clash-agent.git
cd clash-agent
pip install flask pyyaml requests pystray pillow

# 2. Download resources (engine + panel + geodata)
.\update-resources.ps1

# 3. Configure your proxy nodes
copy clash-config.example.yaml clash-config.yaml
# Edit clash-config.yaml → fill in your proxy server & password

# Launch!
pythonw vpn-app.pyw          # System tray app (recommended)
# or: python vpn-manager.py  # Web UI only
# or: .\start.bat            # One-click start
```

Open **http://127.0.0.1:9098** — done.

---

## Features | 功能

### ☷ Per-App Routing (Core)

- **Process-level control** — one button per process, click to toggle VPN↔Direct
- **6 app categories** — Browser/Dev→VPN · Domestic/Remote/System/Driver→Direct
- **Auto-discovery** — detects uncategorized processes, one-click to add rules

### ☰ One-Click Control

- **Quick On** — Engine + System proxy + Git + NPM proxy, all at once
- **Quick Off** — Disable all and clean up
- **Independent toggles** — System proxy (with bypass) / Git / NPM / TUN / Proxy Guard

### ☲ Real-Time Monitoring

- **Live connections** — Process, destination, proxy chain, traffic at a glance
- **Speed charts** — Upload/download dual charts, 60-point rolling history
- **Engine info** — Version / mode / memory / log level, live
- **WebSocket logs** — Real-time log stream (Info/Warning/Error/Debug)

### ☵ Protection & Guard

- **Proxy guard** — Background thread auto-recovers proxy if disabled by other apps
- **Safe shutdown** — Stopping engine auto-disables proxy (prevents internet loss)
- **Ad blocking** — Loyalsoldier reject ruleset blocks ad domains
- **XSS protection** — All dynamic content HTML-escaped

### ☳ Diagnostic Tools

- **One-click diagnosis** — 11 system checks (engine/API/config/geodata/connectivity)
- **Connectivity test** — Google / GitHub / Baidu parallel check
- **DNS query** — Built-in DNS lookup tool
- **Subscription update** — Regenerate config from subscription + hot reload
- **Provider management** — Proxy/rule providers list + individual/batch update

---

## Architecture | 架构

```text
vpn-app.pyw (System Tray Orchestrator — recommended entry point)
├── Launches clash-meta.exe ── Proxy Engine
├── Launches vpn-manager.py ── Flask Web UI + 39 API endpoints
├── System tray icon ── Dynamic status + right-click menu
├── Status polling (5s) ── Icon / tooltip auto-update
└── Exit cleanup ── Disable proxy + stop processes + release lock

vpn-manager.py (1900 lines — single file = everything)
├── Flask backend ── 39 API endpoints
├── Embedded frontend ── HTML/CSS/JS, 7-tab responsive UI
└── Proxy guard thread ── Auto-recover system proxy

clash-meta.exe (Mihomo Engine)
├── Mixed proxy ── :7890 (HTTP + SOCKS5)
├── RESTful API ── :9097
└── MetaCubeXD panel ── :9097/ui
```

## Files | 文件

| File | Purpose |
|------|---------|
| `vpn-app.pyw` | System tray orchestrator (recommended, auto-launches everything) |
| `vpn-manager.py` | Core: Flask backend + embedded frontend (1900 lines) |
| `proxy-manager.ps1` | PowerShell CLI proxy manager |
| `gen_config.py` | Subscription → config generator (preserves per-app rules) |
| `update-resources.ps1` | One-click update: panel + geodata + engine |
| `clash-config.example.yaml` | Configuration template with full comments |
| `start.bat` / `stop.bat` | One-click start / stop |

## Ports

| Port | Purpose |
|------|---------|
| 7890 | Mixed proxy (HTTP + SOCKS5) |
| 9097 | Clash API + MetaCubeXD panel |
| 9098 | VPN Manager Web UI |

## Dual Panels | 双面板

- **VPN Manager** `http://127.0.0.1:9098` — 7 tabs: Overview / Apps / Nodes / Rules / Connections / Logs / Tools
- **MetaCubeXD** `http://127.0.0.1:9097/ui` — Official panel: connection details, rule testing, proxy latency

## CLI | 命令行

```powershell
.\proxy-manager.ps1              # Status
.\proxy-manager.ps1 -Action on   # Enable all proxies
.\proxy-manager.ps1 -Action off  # Disable all proxies
.\proxy-manager.ps1 -Action dev  # Git + NPM proxy only (dev mode)
.\proxy-manager.ps1 -Action clean # Clean all proxy traces
```

## Resource Updates | 资源更新

```powershell
.\update-resources.ps1              # Update all (panel + geodata + engine)
.\update-resources.ps1 -Only ui     # MetaCubeXD panel only
.\update-resources.ps1 -Only geo    # GeoIP / GeoSite data only
.\update-resources.ps1 -Only core   # Mihomo engine only
python gen_config.py                # Regenerate config from subscription
```

## Build EXE | 打包

```powershell
python -m venv .venv
.venv\Scripts\pip install flask pyyaml pyinstaller
.venv\Scripts\pyinstaller --onefile --noconsole --name VPNManager --runtime-hook _pyi_hook.py --distpath . vpn-manager.py
```

---

## Built With | 构建于

| Project | Stars | Integration |
|---------|-------|-------------|
| [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo) | 27K+ | Proxy engine core |
| [MetaCubeX/metacubexd](https://github.com/MetaCubeX/metacubexd) | 3.2K+ | Official web panel |
| [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) | 25K+ | 8 remote rulesets |
| [Loyalsoldier/v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat) | 19K+ | Enhanced GeoIP + GeoSite |
| [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) | — | Country.mmdb GeoIP2 |

Full ecosystem index: [`资源总览.md`](资源总览.md)

---

## Philosophy | 道 · 哲学

> *道可道，非常道。* — 老子《道德经》
>
> *上善若水，水善利万物而不争。* — 老子《道德经》第八章

Every feature maps to a trigram. Yin and Yang in balance:

| Trigram | Symbol | Feature | Yang (Do) | Yin (Don't) |
|---------|--------|---------|-----------|-------------|
| ☰ Qian | Heaven | **One-click** | Start engine + all proxies at once | Don't require memorizing steps |
| ☷ Kun | Earth | **Per-app routing** | Each process chooses its own path | Don't force one-size-fits-all |
| ☵ Kan | Water | **Proxy guard** | Self-healing, auto-recover | Don't force user intervention |
| ☲ Li | Fire | **Monitoring** | Connections / speed / logs visible | Don't act blindly |
| ☳ Zhen | Thunder | **Diagnosis** | 11 checks, push through to the end | Don't give up halfway |
| ☴ Xun | Wind | **Hot reload** | Gradual change, no restart needed | Don't cause disruption |
| ☶ Gen | Mountain | **Safety** | Stop engine → auto-disable proxy | Don't over-intervene |
| ☱ Dui | Lake | **Dual panels** | Custom + MetaCubeXD complement | Don't reinvent the wheel |

### Core Principles

- **Wu Wei (无为)** — The proxy guard runs silently. You don't feel it, but it's always there.
- **Simplicity (大道至简)** — One Python file, one command, no heavy dependencies.
- **Know When to Stop (知止不殆)** — 11 diagnostics: observe first, then act.
- **Like Water (上善若水)** — VPN or Direct, flowing to where it's needed.

## Contributing

Issues and PRs are welcome. Please keep changes minimal and focused.

## License

[MIT](LICENSE)
