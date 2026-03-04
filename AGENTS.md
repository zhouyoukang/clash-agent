# Clash Agent — Agent 操作手册

> 按应用智能路由的 VPN 管理器。整合 GitHub 全生态优质资源。

## 定位

自研 Flask Web UI + Mihomo 内核 + MetaCubeXD 官方面板 + Loyalsoldier 规则集 + PowerShell CLI。

## 端口分配（固定）

| 端口 | 用途 |
|------|------|
| 7890 | 混合代理 (HTTP+SOCKS5) |
| 9097 | Clash Meta API + MetaCubeXD 面板 |
| 9098 | 自研 VPN Manager Web UI |

## 文件结构

```text
clash-agent/
├── vpn-app.pyw             ← 系统托盘编排器（推荐入口）
├── vpn-manager.py          ← 核心: Flask 后端 + 嵌入式前端 (1892行)
├── clash-config.yaml       ← 配置 (rule-providers + PROCESS-NAME)
├── proxy-manager.ps1       ← PowerShell CLI 管理
├── gen_config.py            ← 订阅→配置生成器 (含远程规则集)
├── update-resources.ps1    ← 一键更新面板/地理数据/内核
├── start.bat / stop.bat    ← 一键启停
├── _pyi_hook.py            ← PyInstaller 运行时钩子
├── 资源总览.md              ← GitHub Clash 生态全景索引
├── ui/                     ← [gitignored] MetaCubeXD 官方面板 (108文件)
├── geodata/                ← [gitignored] GeoIP/GeoSite 增强数据
│   ├── geoip.dat           ← Loyalsoldier 增强版 (19MB)
│   ├── geosite.dat         ← Loyalsoldier 增强版 (10MB)
│   └── Country.mmdb        ← MetaCubeX MaxMind (8MB)
├── ruleset/                ← [gitignored] 远程规则集缓存 (引擎自动下载)
├── cache.db                ← [gitignored] 引擎缓存
└── clash-meta.exe          ← [gitignored] Mihomo v1.18.2
```

## 前置条件

- Python 3.10+ + `flask` + `pyyaml` + `requests` + `pystray` + `pillow`
- 首次使用运行 `.\update-resources.ps1` 下载面板/地理数据/内核

## 启动方式

```powershell
# 方式1: 托盘应用（推荐，自动编排所有组件）
pythonw vpn-app.pyw

# 方式2: 批处理一键启动
.\start.bat

# 方式3: 仅 Web UI（无托盘）
python vpn-manager.py

# 方式4: CLI
.\proxy-manager.ps1 -Action on
```

## 双面板

| 面板 | 地址 | 特色 |
|------|------|------|
| 自研 VPN Manager | `http://127.0.0.1:9098` | 按应用路由、未分类进程、一键翻墙 |
| MetaCubeXD 官方 | `http://127.0.0.1:9097/ui` | 连接详情、规则测试、代理延迟、日志 |

## API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/` | Web UI 主页 |
| GET | `/api/status` | 全量状态 |
| POST | `/api/quick-on` | 一键开启（引擎+系统代理+Git） |
| POST | `/api/quick-off` | 一键关闭 |
| POST | `/api/clash/start` | 启动引擎 |
| POST | `/api/clash/stop` | 停止引擎（自动关代理） |
| POST | `/api/proxy/system` | 切换系统代理 `{enable:bool}` |
| POST | `/api/proxy/git` | 切换 Git 代理 |
| POST | `/api/proxy/npm` | 切换 NPM 代理 |
| POST | `/api/proxy/clean` | 彻底清理所有代理 |
| POST | `/api/app/route` | 切换应用路由 `{process,route}` |
| POST | `/api/app/add` | 添加新规则 |
| GET | `/api/connections` | 活跃连接 |
| POST | `/api/connectivity` | 连通性测试 |
| GET | `/api/npm/status` | NPM 代理状态 |
| GET | `/api/proxies` | 代理组/节点列表 |
| POST | `/api/proxies/<group>/select` | 选择节点 `{name}` |
| POST | `/api/proxies/<group>/delay-all` | 全组测速 |
| POST | `/api/proxies/<name>/delay` | 单节点测速 |
| GET | `/api/rules` | 规则列表 |
| GET | `/api/tun` | TUN 状态 |
| POST | `/api/tun` | 切换 TUN `{enable:bool}` |
| GET | `/api/traffic` | 流量统计 |
| GET | `/api/engine/info` | 引擎运行信息 |
| GET | `/api/version` | 版本信息 |
| GET | `/api/config/view` | 查看配置文件 |
| POST | `/api/config/reload` | 热重载配置 |
| POST | `/api/diagnose` | 一键诊断 (11项) |
| POST | `/api/dns/query` | DNS 查询 `{name,type}` |
| POST | `/api/subscription/update` | 订阅更新 |
| GET/POST | `/api/proxy/guard` | 代理守护开关 |
| POST | `/api/connections/close` | 关闭单个连接 `{id}` |
| POST | `/api/connections/close-all` | 关闭全部连接 |
| GET | `/api/rules/providers` | 规则提供者 |
| GET | `/api/providers/proxies` | 代理提供者 |
| POST | `/api/providers/proxies/update` | 更新代理提供者 |
| POST | `/api/providers/rules/update` | 更新规则提供者 |
| GET | `/api/logs` | 日志（前端用WebSocket直连Clash） |

## 资源更新

```powershell
.\update-resources.ps1              # 更新全部（面板+地理数据+内核）
.\update-resources.ps1 -Only ui     # 仅更新 MetaCubeXD 面板
.\update-resources.ps1 -Only geo    # 仅更新 GeoIP/GeoSite 数据
.\update-resources.ps1 -Only core   # 仅更新 Mihomo 内核
python gen_config.py                # 重新生成配置（保留 PROCESS-NAME 规则）
```

## GitHub 资源来源

| 资源 | 仓库 | 星标 |
|------|------|------|
| 内核 | MetaCubeX/mihomo | 27K★ |
| 面板 | MetaCubeX/metacubexd | 3.2K★ |
| 规则集 | Loyalsoldier/clash-rules | 25K★ |
| 地理数据 | Loyalsoldier/v2ray-rules-dat | 19K★ |
| GeoIP2 | MetaCubeX/meta-rules-dat | — |

详见 `资源总览.md` 获取完整生态索引。

## 运行目录

- **源码 (git)**: `d:\道\道生一\一生二\clash-agent\`
- **运行实例**: `D:\VPN\` (从源码同步)

## 托盘应用 (vpn-app.pyw)

- **图标状态**: 🟢引擎+代理开 | 🟡引擎开代理关 | 🔴引擎停 | ⚪启动中
- **右键菜单**: 面板/MetaCubeXD/一键开关/代理切换/重载/测试/自启/退出
- **tooltip**: 实时显示引擎状态+代理状态+上下行速度
- **防重复**: PID锁文件 `.vpn-app.lock`
- **退出清理**: 自动关闭系统代理+停止Flask+释放锁
- **一键开启**: 系统代理+Git代理+NPM代理同时开启

## 构建 EXE

```powershell
python -m PyInstaller --onefile --noconsole --name VPNManager --runtime-hook _pyi_hook.py --distpath . vpn-manager.py
```

## 注意事项

- 所有路径为相对路径（`BASE_DIR` / `$PSScriptRoot` / `%~dp0`），可任意位置运行
- 停止引擎自动关闭系统代理（P0 安全机制，防断网）
- 退出托盘App自动关闭系统代理（防断网）
- `clash-config.yaml` 由 Web UI 动态修改（PROCESS-NAME 规则热重载）
- 远程规则集（8个 rule-providers）由引擎每 24 小时自动更新
- 代理守护线程自动检测并恢复被其他软件关闭的系统代理
- 凭据：代理节点密码在 `clash-config.yaml` 中（trojan password）
- WebSocket 日志流连接 `ws://127.0.0.1:9097/logs?level=info`
