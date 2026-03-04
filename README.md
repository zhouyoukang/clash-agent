# Clash Agent v3.5

**Per-App Intelligent Routing VPN Manager | 按应用智能路由 VPN 管理器**

> 道可道，非常道。道生一，一生二，二生三，三生万物。
>
> *The Way that can be told is not the eternal Way. The Way gives birth to One, One gives birth to Two, Two gives birth to Three, and Three gives birth to all things.*

A single-file Flask web application that gives you **process-level control** over which apps use VPN and which connect directly — powered by the [Mihomo](https://github.com/MetaCubeX/mihomo) (Clash Meta) kernel.

## Philosophy | 哲学

Like water (上善若水), this tool adapts to your workflow:

- **Per-app routing as the Dao** — Each process gets exactly the path it needs. Browsers → VPN. WeChat → Direct. No blanket rules.
- **Minimal intervention (无为)** — One click to enable, one click to disable. The proxy guard silently restores what other software breaks.
- **Observe, then act (知止)** — 11-point diagnostics, real-time connections, speed charts — full visibility before any change.

## Quick Start | 快速开始

```powershell
# 1. Download resources (panel + geodata + engine)
.\update-resources.ps1

# 2. Install Python dependencies
pip install flask pyyaml

# 3. Copy and edit config with your proxy credentials
copy clash-config.example.yaml clash-config.yaml
# Edit clash-config.yaml → add your proxy server/password

# 4. Launch (auto-opens browser)
python vpn-manager.py
```

Open `http://127.0.0.1:9098` — you're in.

## Features | 功能

### Core | 核心

- **Per-app routing** — Toggle VPN↔Direct per process with one click
- **6 app categories** — Browsers/Dev→VPN · Chinese apps/Remote/System/Drivers→Direct
- **Uncategorized detection** — Auto-detect new processes, add rules instantly
- **One-click VPN** — Engine + system proxy + Git proxy toggled together

### Monitoring | 监控

- **Real-time connections** — Process name, destination, proxy chain, traffic per connection
- **Speed charts** — Upload/download dual charts, 60-point rolling history
- **Engine info** — Kernel version, mode, memory, log level — live
- **WebSocket logs** — Real-time log stream (Info/Warning/Error/Debug)
- **Connectivity test** — Google/GitHub/Baidu parallel detection

### Protection | 防护

- **Proxy guard** — Background thread auto-restores system proxy if disabled by other software
- **Safe shutdown** — Stopping engine auto-disables proxy (prevents network loss)
- **Ad blocking** — Loyalsoldier reject ruleset blocks ad domains
- **XSS protection** — All user input HTML-escaped

### Tools | 工具

- **11-point diagnostics** — Engine, API, config, geodata, connectivity checks
- **DNS query** — Built-in DNS lookup tool
- **Subscription update** — Regenerate config from subscription YAML
- **Provider management** — Proxy/rule provider list + individual/bulk update
- **Config hot-reload** — Apply changes without restart

## Architecture | 架构

```text
vpn-manager.py (1892 lines)
├── Flask backend ─── 38 API endpoints
├── Embedded HTML/CSS/JS ─── 7-tab responsive UI
└── Proxy guard thread ─── Auto-restore system proxy

clash-meta.exe (Mihomo kernel)
├── Mixed proxy ─── :7890 (HTTP+SOCKS5)
├── RESTful API ─── :9097
└── MetaCubeXD UI ─── :9097/ui

vpn-manager.py Web UI ─── :9098
```

## File Structure | 文件结构

| File | Purpose |
|------|---------|
| `vpn-manager.py` | Core: Flask backend + embedded frontend (1892 lines) |
| `clash-config.example.yaml` | Config template (copy to `clash-config.yaml`) |
| `proxy-manager.ps1` | PowerShell CLI management |
| `gen_config.py` | Subscription → config generator (preserves per-app rules) |
| `update-resources.ps1` | One-click update: panel / geodata / engine |
| `start.bat` / `stop.bat` | One-click start/stop |
| `_pyi_hook.py` | PyInstaller runtime hook |

## Ports | 端口

| Port | Purpose |
|------|---------|
| 7890 | Mixed proxy (HTTP+SOCKS5) |
| 9097 | Clash API + MetaCubeXD panel |
| 9098 | VPN Manager Web UI |

## Dual Panel | 双面板

- **VPN Manager** `http://127.0.0.1:9098` — 7 tabs: Overview / Apps / Nodes / Rules / Connections / Logs / Tools
- **MetaCubeXD** `http://127.0.0.1:9097/ui` — Official panel: connection details, rule testing, proxy latency

## CLI

```powershell
.\proxy-manager.ps1              # Status
.\proxy-manager.ps1 -Action on   # Enable proxy
.\proxy-manager.ps1 -Action off  # Disable proxy
.\proxy-manager.ps1 -Action dev  # Git/NPM proxy only
.\proxy-manager.ps1 -Action clean # Clean all proxy traces
```

## Resource Update | 资源更新

```powershell
.\update-resources.ps1              # Update all
.\update-resources.ps1 -Only ui     # MetaCubeXD panel only
.\update-resources.ps1 -Only geo    # GeoIP/GeoSite data only
.\update-resources.ps1 -Only core   # Mihomo engine only
python gen_config.py                # Regenerate config from subscription
```

## Built With | 构建于

| Project | Stars | Integration |
|---------|-------|-------------|
| [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo) | 27K★ | Proxy engine kernel |
| [MetaCubeX/metacubexd](https://github.com/MetaCubeX/metacubexd) | 3.2K★ | Official web panel |
| [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) | 25K★ | 8 remote rule-providers |
| [Loyalsoldier/v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat) | 19K★ | Enhanced GeoIP + GeoSite |
| [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) | — | Country.mmdb GeoIP2 |

Full ecosystem index: `资源总览.md`

## Build EXE | 打包

```powershell
python -m venv .venv
.venv\Scripts\pip install flask pyyaml pyinstaller
.venv\Scripts\pyinstaller --onefile --noconsole --name VPNManager --runtime-hook _pyi_hook.py --distpath . vpn-manager.py
```

## License

MIT
