# Clash Agent · 按应用智能路由 VPN 管理器

## 身份
Flask Web UI (vpn-manager.py) + Mihomo 内核 + MetaCubeXD 面板 + 系统托盘 (vpn-app.pyw)。

## 边界
- ✅ 本目录 git 追踪的 11 个源码文件
- 🚫 运行实例 `D:\VPN\` 需手动同步

## 入口
| 方式 | 命令 | 端口 |
|------|------|------|
| 托盘(推荐) | `pythonw vpn-app.pyw` | — |
| Web UI | `python vpn-manager.py` | :9098 |
| CLI | `.\proxy-manager.ps1 -Action on/off/status` | — |
| 感知 | `python proxy_sense.py [--check/--env/--fix]` | — |
| 官方面板 | 引擎自带 | :9097/ui |

## 铁律
1. **停止引擎自动关闭系统代理**（P0 防断网）
2. 凭据在 `clash-config.yaml`，不进代码/git
3. 所有路径为相对路径，可任意位置运行

## API 速查

### 核心
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/quick-on` | 一键开启 |
| POST | `/api/quick-off` | 一键关闭 |
| GET | `/api/status` | 全量状态 JSON |
| POST | `/api/clash/start` | 启动引擎 |
| POST | `/api/clash/stop` | 停止引擎 |

### 代理
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/proxy/system` | 系统代理 `{enable:bool}` |
| POST | `/api/proxy/git` | Git 代理 |
| POST | `/api/proxy/npm` | NPM 代理 |
| GET/POST | `/api/proxy/guard` | 代理守护 |
| GET/POST | `/api/tun` | TUN 开关 |

### 应用路由
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/app/route` | 切换路由 `{process,route}` |
| POST | `/api/app/add` | 添加规则 |

### 工具
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/diagnose` | 一键诊断 (11 项) |
| POST | `/api/connectivity` | 连通性测试 |
| POST | `/api/dns/query` | DNS 查询 `{name,type}` |
| POST | `/api/config/reload` | 配置热重载 |

## 故障排查
| 现象 | 解决 |
|------|------|
| 托盘图标永红 | `start.bat` 重启 |
| 国内应用慢 | Web UI 应用页检查路由 |
| 关 VPN 断网 | `stop.bat` 或 `proxy-manager.ps1 -Action clean` |
| MetaCubeXD 打不开 | `update-resources.ps1 -Only ui` |
| 节点全超时 | 更新订阅 → `python gen_config.py` |

## 陷阱
- 代理守护线程自动恢复被其他软件关闭的系统代理
- `clash-config.yaml` 由 Web UI 动态修改，PROCESS-NAME 规则热重载
- 远程规则集 (8 个 rule-providers) 引擎每 24h 自动更新
