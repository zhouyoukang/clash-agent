# Clash Agent · 按应用智能路由 VPN 管理器

## 身份
Flask Web UI (vpn-manager.py) + Mihomo 内核 + MetaCubeXD 面板 + 系统托盘 (vpn-app.pyw)。

## 边界
- ✅ 本目录 git 追踪的 11 个源码文件
- 🚫 运行实例 `D:\VPN\` 需手动同步

## 入口
- 托盘(推荐): `pythonw vpn-app.pyw`
- Web UI: `python vpn-manager.py` (:9098)
- CLI: `.\proxy-manager.ps1 -Action on/off/status`
- API自发现: `GET /api/status` 返回全量状态+所有端点

## 铁律
1. **停止引擎自动关闭系统代理**（P0 防断网）
2. 凭据在 `clash-config.yaml`，不进代码/git
3. 所有路径为相对路径，可任意位置运行
4. 关VPN前必须clean系统代理 — 否则断网

## 关联
| 方向 | 项目 | 说明 |
|---|---|---|
| 全局 | 所有网络项目 | 代理开关影响GitHub/npm/pip等 |

## 陷阱
- 代理守护线程自动恢复被其他软件关闭的系统代理
- `clash-config.yaml` 由 Web UI 动态修改，PROCESS-NAME 规则热重载
- 关VPN断网 → `proxy-manager.ps1 -Action clean` 是唯一解
