# Clash Agent v3.5

**按应用智能路由 VPN 管理器 | Per-App Intelligent Routing VPN Manager**

> 道可道，非常道。道生一，一生二，二生三，三生万物。
>
> *The Way that can be told is not the eternal Way.*
> *The Way gives birth to One, One gives birth to Two,*
> *Two gives birth to Three, and Three gives birth to all things.*

一个单文件 Flask 应用，赋予你**进程级精确控制**——哪些应用走 VPN，哪些直连。基于 [Mihomo](https://github.com/MetaCubeX/mihomo)（Clash Meta）内核。

---

## 道 · 哲学 | Philosophy

> *上善若水，水善利万物而不争。* —— 老子《道德经》第八章

### 伏羲八卦 × 功能映射

本工具的每个功能都对应一卦，阴阳辩证，动静相生：

| 卦 | 象 | 功能 | 阳（做） | 阴（不做） |
|----|-----|------|---------|-----------|
| ☰ 乾 | 天 | **一键翻墙** | 一键启动引擎+代理+Git | 不需要记忆多个步骤 |
| ☷ 坤 | 地 | **按应用路由** | 每个进程独立路径选择 | 不做全局一刀切 |
| ☵ 坎 | 水 | **代理守护** | 如水自愈，被关闭自动恢复 | 不强制干预用户操作 |
| ☲ 离 | 火 | **实时监控** | 连接/速率/日志全景可见 | 不盲目行动 |
| ☳ 震 | 雷 | **一键诊断** | 11项检测一次推到底 | 不半途而废 |
| ☴ 巽 | 风 | **热重载** | 渐进修改，不重启不断网 | 不大起大落 |
| ☶ 艮 | 山 | **安全机制** | 停引擎自动关代理防断网 | 不过度干预稳定系统 |
| ☱ 兑 | 泽 | **双面板** | 自研+MetaCubeXD互补 | 不重复造轮子 |

### 释迦 · 四圣谛映射

| 圣谛 | 网络之苦 | 本工具之解 |
|------|---------|-----------|
| **苦谛** | 全局代理太慢/微信打不开/GitHub连不上 | 识别问题的存在 |
| **集谛** | 根因：所有流量走同一条路 | 诊断为什么痛苦 |
| **灭谛** | 每个应用走最适合它的路 | 解决方案的愿景 |
| **道谛** | PROCESS-NAME规则 + 一键切换 | 实现解脱的路径 |

### 老子 · 核心原则

- **无为而无不为** — 代理守护线程静默运行，你感觉不到它，但它始终在守护
- **大道至简** — 一个Python文件，一个命令启动，无需安装复杂依赖
- **知止不殆** — 11项诊断先观察再行动，不盲改配置
- **上善若水** — 如水适形，VPN/直连按需切换，不强制统一

---

## 快速开始 | Quick Start

> 三步即可，大道至简。

```powershell
# 第一步：下载资源（面板 + 地理数据 + 内核）
.\update-resources.ps1

# 第二步：安装依赖
pip install flask pyyaml

# 第三步：配置你的代理节点
copy clash-config.example.yaml clash-config.yaml
# 编辑 clash-config.yaml → 填入你的代理服务器和密码

# 启动（自动打开浏览器）
python vpn-manager.py
```

打开 `http://127.0.0.1:9098` — 即刻开始。

---

## 功能 | Features

### ☷ 坤 · 按应用路由（核心）

- **进程级控制** — 每个进程旁一个按钮，点击切换 VPN↔直连
- **6类应用预设** — 浏览器/开发工具→VPN · 国内/远程/系统/驱动→直连
- **未分类检测** — 自动发现新进程，一键添加路由规则

### ☰ 乾 · 一键操控

- **一键翻墙** — 引擎 + 系统代理 + Git 代理一键全开
- **一键关闭** — 一键全部关闭并清理
- **Toggle开关** — 系统代理(含bypass)、Git代理、NPM代理独立开关

### ☲ 离 · 实时监控

- **实时连接** — 进程名、目标地址、代理链、流量一目了然
- **速率图表** — 上传/下载双图表，60点滚动历史
- **引擎信息** — 内核版本/模式/内存/日志级别实时显示
- **WebSocket日志** — 实时日志流（Info/Warning/Error/Debug）

### ☵ 坎 · 守护与防护

- **代理守护** — 后台线程自动检测并恢复被其他软件关闭的系统代理
- **安全停机** — 停止引擎自动关闭代理（防断网，P0安全）
- **广告拦截** — Loyalsoldier reject规则集自动屏蔽广告域名
- **XSS防护** — 所有用户输入HTML转义

### ☳ 震 · 诊断工具

- **一键诊断** — 11项系统检测（引擎/API/配置/地理数据/连通性）
- **连通性测试** — Google/GitHub/Baidu并行检测
- **DNS查询** — 内置DNS查询工具
- **订阅更新** — 从订阅源重新生成配置并热加载
- **提供者管理** — 代理/规则提供者列表 + 单个/全部更新

---

## 架构 | Architecture

```text
vpn-manager.py（1892行，单文件即全部）
├── Flask 后端 ─── 38个 API 端点
├── 嵌入式前端 ─── HTML/CSS/JS 7标签页响应式UI
└── 代理守护线程 ─── 自动恢复系统代理

clash-meta.exe（Mihomo 内核）
├── 混合代理 ─── :7890（HTTP+SOCKS5）
├── RESTful API ─── :9097
└── MetaCubeXD面板 ─── :9097/ui

自研Web UI ─── :9098
```

## 文件结构 | Files

| 文件 | 用途 |
|------|------|
| `vpn-manager.py` | 核心：Flask后端 + 嵌入式前端（1892行） |
| `clash-config.example.yaml` | 配置模板（复制为 `clash-config.yaml` 后使用） |
| `proxy-manager.ps1` | PowerShell 命令行管理脚本 |
| `gen_config.py` | 订阅→配置生成器（保留按应用路由规则） |
| `update-resources.ps1` | 一键更新面板/地理数据/内核 |
| `start.bat` / `stop.bat` | 一键启停 |
| `_pyi_hook.py` | PyInstaller 运行时钩子 |
| `资源总览.md` | GitHub Clash 生态全景索引 |

## 端口 | Ports

| 端口 | 用途 |
|------|------|
| 7890 | 混合代理（HTTP+SOCKS5） |
| 9097 | Clash API + MetaCubeXD 面板 |
| 9098 | VPN Manager 自研面板 |

## ☱ 兑 · 双面板

- **自研面板** `http://127.0.0.1:9098` — 7标签页：概览/应用/节点/规则/连接/日志/工具
- **MetaCubeXD** `http://127.0.0.1:9097/ui` — 官方面板：连接详情、规则测试、代理延迟

## 命令行 | CLI

```powershell
.\proxy-manager.ps1              # 查看状态
.\proxy-manager.ps1 -Action on   # 开启代理
.\proxy-manager.ps1 -Action off  # 关闭代理
.\proxy-manager.ps1 -Action dev  # 仅 Git/NPM 代理（开发模式）
.\proxy-manager.ps1 -Action clean # 彻底清理所有代理痕迹
```

## 资源更新 | Updates

```powershell
.\update-resources.ps1              # 更新全部（面板+地理数据+内核）
.\update-resources.ps1 -Only ui     # 仅更新 MetaCubeXD 面板
.\update-resources.ps1 -Only geo    # 仅更新 GeoIP/GeoSite 数据
.\update-resources.ps1 -Only core   # 仅更新 Mihomo 内核
python gen_config.py                # 从订阅重新生成配置
```

## 构建于 | Built With

| 项目 | 星标 | 整合内容 |
|------|------|----------|
| [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo) | 27K★ | 代理引擎内核 |
| [MetaCubeX/metacubexd](https://github.com/MetaCubeX/metacubexd) | 3.2K★ | 官方Web管理面板 |
| [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) | 25K★ | 8个远程规则集 |
| [Loyalsoldier/v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat) | 19K★ | 增强版GeoIP+GeoSite |
| [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) | — | Country.mmdb GeoIP2 |

完整生态索引见 `资源总览.md`。

## 打包EXE | Build

```powershell
python -m venv .venv
.venv\Scripts\pip install flask pyyaml pyinstaller
.venv\Scripts\pyinstaller --onefile --noconsole --name VPNManager --runtime-hook _pyi_hook.py --distpath . vpn-manager.py
```

## 许可 | License

MIT
