"""
VPN Manager v4.0 — 系统托盘 (对标 CFW / Clash Verge / mihomo-party)

功能清单:
  1. 管理面板 / MetaCubeXD 面板 (双入口)
  2. 一键开启 / 一键关闭
  3. 代理模式切换 (Rule/Global/Direct) — 子菜单+单选
  4. 系统代理 / TUN模式 / 允许局域网 / 代理守护 — 开关
  5. 开发者工具子菜单 (Git/NPM代理 + 复制代理命令)
  6. 代理组子菜单 (动态加载节点, 点击切换)
  7. 更新订阅 / 重载配置 / 重启内核 / 网络测试 / 关闭所有连接
  8. 打开配置目录 / 开机自启 / 退出

图标: 🟢引擎+代理  🟡引擎无代理  🔴引擎停止  ⚪启动中
Tooltip: 模式 | 当前节点 | ↑速度 ↓速度 | 代理状态
"""

import os, sys, time, threading, subprocess, webbrowser, socket, winreg, ctypes
import pystray
from pystray import MenuItem, Menu
from PIL import Image, ImageDraw
import requests

# ==================== Constants ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MIXED_PORT = 7890
API_PORT = 9097
WEB_PORT = 9098
CLASH_META = os.path.join(BASE_DIR, 'clash-meta.exe')
CLASH_CONFIG = os.path.join(BASE_DIR, 'clash-config.yaml')
VPN_MANAGER = os.path.join(BASE_DIR, 'vpn-manager.py')
APP_NAME = 'VPN Manager v4.0'
STARTUP_REG_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
STARTUP_REG_NAME = 'VPNManager'
CREATE_NO_WINDOW = 0x08000000
POLL_INTERVAL = 4
LOCK_FILE = os.path.join(BASE_DIR, '.vpn-app.lock')
CLASH_API_SECRET = 'clash-agent-local'

PROXY_CMDS = {
    'Bash/Zsh':  'export http_proxy=http://127.0.0.1:7890 https_proxy=http://127.0.0.1:7890 all_proxy=socks5://127.0.0.1:7890',
    'PowerShell': '$env:http_proxy="http://127.0.0.1:7890"; $env:https_proxy="http://127.0.0.1:7890"; $env:all_proxy="socks5://127.0.0.1:7890"',
    'CMD':        'set http_proxy=http://127.0.0.1:7890 && set https_proxy=http://127.0.0.1:7890',
}


# ==================== Icon Generation ====================
def make_icon(fill_color, size=64):
    scale = 4
    big = size * scale
    img = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = big
    shield = [
        (s*0.50, s*0.04), (s*0.90, s*0.22), (s*0.87, s*0.60),
        (s*0.50, s*0.96), (s*0.13, s*0.60), (s*0.10, s*0.22),
    ]
    d.polygon(shield, fill=fill_color)
    darker = {'#22c55e':'#16a34a', '#eab308':'#a16207', '#ef4444':'#b91c1c', '#94a3b8':'#64748b'}
    d.polygon(shield, outline=darker.get(fill_color, '#333'), width=max(4, s//32))
    lw = s // 10
    pts = [(s*0.27, s*0.48), (s*0.43, s*0.67), (s*0.73, s*0.30)]
    d.line(pts, fill='white', width=lw, joint='curve')
    for pt in pts:
        r = lw // 2
        d.ellipse([pt[0]-r, pt[1]-r, pt[0]+r, pt[1]+r], fill='white')
    return img.resize((size, size), Image.LANCZOS)


ICONS = {
    'green': make_icon('#22c55e'), 'yellow': make_icon('#eab308'),
    'red':   make_icon('#ef4444'), 'gray':   make_icon('#94a3b8'),
}


# ==================== Utilities ====================
def check_port(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(('127.0.0.1', port))
        s.close()
        return True
    except Exception:
        return False


def api(path, method='GET', data=None, timeout=5):
    try:
        url = f'http://127.0.0.1:{WEB_PORT}{path}'
        if method == 'POST':
            r = requests.post(url, json=data, timeout=timeout)
        else:
            r = requests.get(url, timeout=timeout)
        return r.json()
    except Exception:
        return None


def set_clipboard(text):
    try:
        ctypes.windll.user32.OpenClipboard(0)
        ctypes.windll.user32.EmptyClipboard()
        data = text.encode('utf-16-le') + b'\x00\x00'
        h = ctypes.windll.kernel32.GlobalAlloc(0x0042, len(data))
        p = ctypes.windll.kernel32.GlobalLock(h)
        ctypes.cdll.msvcrt.memcpy(ctypes.c_void_p(p), data, len(data))
        ctypes.windll.kernel32.GlobalUnlock(h)
        ctypes.windll.user32.SetClipboardData(13, h)
        ctypes.windll.user32.CloseClipboard()
    except Exception:
        pass


def fmt_speed(bps):
    if bps < 1024: return f'{bps}B/s'
    if bps < 1048576: return f'{bps/1024:.1f}K/s'
    if bps < 1073741824: return f'{bps/1048576:.1f}M/s'
    return f'{bps/1073741824:.2f}G/s'


# ==================== Process Management ====================
def start_clash_meta():
    if check_port(MIXED_PORT): return True
    if not os.path.isfile(CLASH_META) or not os.path.isfile(CLASH_CONFIG): return False
    subprocess.Popen([CLASH_META, '-d', BASE_DIR, '-f', CLASH_CONFIG], creationflags=CREATE_NO_WINDOW)
    for _ in range(15):
        time.sleep(1)
        if check_port(MIXED_PORT): return True
    return False


def start_flask_server():
    if check_port(WEB_PORT): return None
    if not os.path.isfile(VPN_MANAGER): return None
    python = sys.executable
    pythonw = os.path.join(os.path.dirname(python), 'pythonw.exe')
    if os.path.isfile(pythonw): python = pythonw
    proc = subprocess.Popen([python, VPN_MANAGER, '--no-auto'], cwd=BASE_DIR, creationflags=CREATE_NO_WINDOW)
    for _ in range(10):
        time.sleep(1)
        if check_port(WEB_PORT): return proc
    return proc


def restart_clash_core():
    try:
        subprocess.run(['taskkill', '/F', '/IM', 'clash-meta.exe'],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
        time.sleep(1)
        subprocess.Popen([CLASH_META, '-d', BASE_DIR, '-f', CLASH_CONFIG], creationflags=CREATE_NO_WINDOW)
        for _ in range(10):
            time.sleep(1)
            if check_port(MIXED_PORT): return True
        return False
    except Exception:
        return False


# ==================== Windows Startup ====================
def is_startup_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, STARTUP_REG_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def set_startup(enable):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            app_path = os.path.abspath(__file__)
            pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
            if not os.path.isfile(pythonw): pythonw = sys.executable
            winreg.SetValueEx(key, STARTUP_REG_NAME, 0, winreg.REG_SZ, f'"{pythonw}" "{app_path}"')
        else:
            try: winreg.DeleteValue(key, STARTUP_REG_NAME)
            except Exception: pass
        winreg.CloseKey(key)
    except Exception:
        pass


# ==================== Main Application ====================
class VPNTrayApp:
    def __init__(self):
        self.running = True
        self.status = {}
        self.flask_proc = None
        self.icon = None
        self._startup = is_startup_enabled()
        self._npm_on = False
        self._speed_up = 0
        self._speed_down = 0
        self._prev_ul = 0
        self._prev_dl = 0
        self._mode = 'rule'
        self._tun_on = False
        self._allow_lan = False
        self._guard_on = False
        self._groups = []
        self._current_node = ''

    # --- Status properties ---
    @property
    def engine_on(self):
        c = self.status.get('clash', {})
        return bool(c.get('proxy_port', False)) if isinstance(c, dict) else False

    @property
    def proxy_on(self):
        sp = self.status.get('system_proxy', {})
        return sp.get('enabled', False) if isinstance(sp, dict) else False

    @property
    def git_on(self):
        gp = self.status.get('git_proxy', {})
        return bool(gp.get('http')) if isinstance(gp, dict) else False

    # --- Icon / Tooltip ---
    def current_icon(self):
        if self.engine_on and self.proxy_on: return ICONS['green']
        if self.engine_on: return ICONS['yellow']
        return ICONS['red']

    def current_title(self):
        if not self.status:
            return f'{APP_NAME}\n启动中...'
        if not self.engine_on:
            return f'{APP_NAME}\n引擎: 停止'
        mode_zh = {'rule': '规则', 'global': '全局', 'direct': '直连'}.get(self._mode, self._mode)
        node = self._current_node[:20] if self._current_node else '-'
        line1 = APP_NAME
        line2 = f'{mode_zh} | {node}'
        parts = []
        if self._speed_up > 0 or self._speed_down > 0:
            parts.append(f'\u2191{fmt_speed(self._speed_up)} \u2193{fmt_speed(self._speed_down)}')
        flags = []
        if self.proxy_on: flags.append('代理')
        if self._tun_on: flags.append('TUN')
        if self._guard_on: flags.append('守护')
        if flags: parts.append(' '.join(flags))
        line3 = ' | '.join(parts) if parts else ('代理:开' if self.proxy_on else '代理:关')
        return f'{line1}\n{line2}\n{line3}'

    # --- Menu builder (called each time menu is shown) ---
    def create_menu(self):
        def _mode_action(m):
            def action(icon, item): self._set_mode(m)
            return action
        mode_menu = Menu(
            MenuItem('规则模式 (Rule)', _mode_action('rule'),
                     checked=lambda item: self._mode == 'rule'),
            MenuItem('全局代理 (Global)', _mode_action('global'),
                     checked=lambda item: self._mode == 'global'),
            MenuItem('直连模式 (Direct)', _mode_action('direct'),
                     checked=lambda item: self._mode == 'direct'),
        )
        copy_items = [MenuItem(f'复制 {k}', self._make_copy(v)) for k, v in PROXY_CMDS.items()]
        dev_menu = Menu(
            MenuItem('Git 代理', self._toggle_git, checked=lambda item: self.git_on),
            MenuItem('NPM 代理', self._toggle_npm, checked=lambda item: self._npm_on),
            Menu.SEPARATOR, *copy_items,
        )
        group_items = self._build_group_menu()
        groups_menu = Menu(*group_items) if group_items else Menu(
            MenuItem('(加载中...)', None, enabled=False))

        return Menu(
            MenuItem('管理面板', self.open_webui, default=True),
            MenuItem('MetaCubeXD', self.open_metacubexd),
            Menu.SEPARATOR,
            MenuItem('\u26a1 一键开启', self.quick_on),
            MenuItem('\u23f9 一键关闭', self.quick_off),
            Menu.SEPARATOR,
            MenuItem('代理模式', mode_menu),
            Menu.SEPARATOR,
            MenuItem('系统代理', self._toggle_sys_proxy, checked=lambda item: self.proxy_on),
            MenuItem('TUN 模式', self._toggle_tun, checked=lambda item: self._tun_on),
            MenuItem('允许局域网', self._toggle_lan, checked=lambda item: self._allow_lan),
            MenuItem('代理守护', self._toggle_guard, checked=lambda item: self._guard_on),
            Menu.SEPARATOR,
            MenuItem('开发者工具', dev_menu),
            MenuItem('代理组', groups_menu),
            Menu.SEPARATOR,
            MenuItem('更新订阅', self._update_sub),
            MenuItem('重载配置', self._reload_config),
            MenuItem('重启内核', self._restart_core),
            MenuItem('网络测试', self._test_net),
            MenuItem('关闭所有连接', self._close_all_conns),
            Menu.SEPARATOR,
            MenuItem('打开配置目录', self._open_dir),
            MenuItem('开机自启', self._toggle_startup, checked=lambda item: self._startup),
            MenuItem('退出', self.quit_app),
        )

    def _make_node_action(self, gn, nn):
        def action(icon, item):
            self._select_node(gn, nn)
        return action

    def _make_node_check(self, nn, gnow):
        def check(item):
            return nn == gnow
        return check

    def _build_group_menu(self):
        items = []
        for g in self._groups[:10]:
            gname = g.get('name', '?')
            gnow = g.get('now', '')
            nodes = g.get('nodes', [])
            if not nodes:
                items.append(MenuItem(f'{gname} (空)', None, enabled=False))
                continue
            node_items = []
            for n in nodes[:30]:
                nname = n.get('name', '?')
                delay = n.get('delay', 0)
                dl_str = f' ({delay}ms)' if delay and delay > 0 else ''
                node_items.append(MenuItem(
                    f'{nname}{dl_str}',
                    self._make_node_action(gname, nname),
                    checked=self._make_node_check(nname, gnow),
                ))
            if len(nodes) > 30:
                node_items.append(MenuItem(f'...还有 {len(nodes)-30} 个', None, enabled=False))
            label = f'{gname} [{g.get("type","")}] ({gnow or "-"})'
            items.append(MenuItem(label, Menu(*node_items)))
        return items

    # --- Actions ---
    def _bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _make_copy(self, text):
        def handler(icon=None, item=None):
            set_clipboard(text)
            self.notify('已复制到剪贴板')
        return handler

    def open_webui(self, icon=None, item=None):
        webbrowser.open(f'http://127.0.0.1:{WEB_PORT}')

    def open_metacubexd(self, icon=None, item=None):
        webbrowser.open(f'http://127.0.0.1:{API_PORT}/ui/')

    def quick_on(self, icon=None, item=None):
        def _do():
            self.notify('正在启动 VPN...')
            if not check_port(MIXED_PORT): start_clash_meta()
            time.sleep(1)
            api('/api/quick-on', 'POST', timeout=15)
            time.sleep(0.5)
            self._refresh()
            self.notify('VPN 已开启' if self.engine_on else '启动失败')
        self._bg(_do)

    def quick_off(self, icon=None, item=None):
        def _do():
            api('/api/quick-off', 'POST', timeout=10)
            time.sleep(0.5)
            self._refresh()
            self.notify('代理已关闭')
        self._bg(_do)

    def _set_mode(self, mode):
        def _do():
            api('/api/mode', 'POST', {'mode': mode}, timeout=5)
            time.sleep(0.3)
            self._refresh()
            self._update_menu()
        self._bg(_do)

    def _toggle_sys_proxy(self, icon=None, item=None):
        def _do():
            api('/api/proxy/system', 'POST', {'enable': not self.proxy_on}, timeout=10)
            time.sleep(0.5)
            self._refresh()
        self._bg(_do)

    def _toggle_tun(self, icon=None, item=None):
        def _do():
            api('/api/tun', 'POST', {'enable': not self._tun_on}, timeout=5)
            time.sleep(0.5)
            self._refresh()
            self._update_menu()
        self._bg(_do)

    def _toggle_lan(self, icon=None, item=None):
        def _do():
            try:
                import json, urllib.request
                payload = json.dumps({'allow-lan': not self._allow_lan}).encode()
                headers = {'Content-Type': 'application/json'}
                if CLASH_API_SECRET:
                    headers['Authorization'] = f'Bearer {CLASH_API_SECRET}'
                req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}/configs',
                    data=payload, method='PATCH', headers=headers)
                urllib.request.urlopen(req, timeout=5)
            except Exception: pass
            time.sleep(0.3)
            self._refresh()
            self._update_menu()
        self._bg(_do)

    def _toggle_guard(self, icon=None, item=None):
        def _do():
            api('/api/proxy/guard', 'POST', {'enable': not self._guard_on}, timeout=5)
            time.sleep(0.3)
            self._refresh()
            self._update_menu()
        self._bg(_do)

    def _toggle_git(self, icon=None, item=None):
        def _do():
            api('/api/proxy/git', 'POST', {'enable': not self.git_on}, timeout=10)
            time.sleep(0.5)
            self._refresh()
        self._bg(_do)

    def _toggle_npm(self, icon=None, item=None):
        def _do():
            api('/api/proxy/npm', 'POST', {'enable': not self._npm_on}, timeout=10)
            time.sleep(0.5)
            self._refresh()
        self._bg(_do)

    def _select_node(self, group, node):
        def _do():
            import urllib.parse
            api(f'/api/proxies/{urllib.parse.quote(group, safe="")}/select', 'POST', {'name': node}, timeout=5)
            time.sleep(0.3)
            self._refresh()
            self._update_menu()
            self.notify(f'{group}: {node}')
        self._bg(_do)

    def _update_sub(self, icon=None, item=None):
        def _do():
            self.notify('正在更新订阅...')
            r = api('/api/subscription/update', 'POST', timeout=60)
            self.notify(r.get('msg', '完成') if r and r.get('ok') else '订阅更新失败')
            self._refresh()
            self._update_menu()
        self._bg(_do)

    def _reload_config(self, icon=None, item=None):
        def _do():
            self.notify('正在重载配置...')
            r = api('/api/config/reload', 'POST', timeout=15)
            self.notify('配置已重载' if r and r.get('ok') else '重载失败')
            self._refresh()
            self._update_menu()
        self._bg(_do)

    def _restart_core(self, icon=None, item=None):
        def _do():
            self.notify('正在重启内核...')
            ok = restart_clash_core()
            self.notify('内核已重启' if ok else '重启失败')
            time.sleep(1)
            self._refresh()
            self._update_menu()
        self._bg(_do)

    def _test_net(self, icon=None, item=None):
        def _do():
            self.notify('正在测试网络...')
            r = api('/api/connectivity', 'POST', timeout=30)
            if r:
                ok = sum(1 for k in ('google', 'github', 'baidu') if r.get(k) is True)
                self.notify(f'网络测试: {ok}/3 通过')
            else:
                self.notify('网络测试失败')
        self._bg(_do)

    def _close_all_conns(self, icon=None, item=None):
        def _do():
            api('/api/connections/close-all', 'POST', timeout=5)
            self.notify('已关闭所有连接')
        self._bg(_do)

    def _open_dir(self, icon=None, item=None):
        os.startfile(BASE_DIR)

    def _toggle_startup(self, icon=None, item=None):
        self._startup = not self._startup
        set_startup(self._startup)

    def quit_app(self, icon=None, item=None):
        self.running = False
        try: api('/api/proxy/system', 'POST', {'enable': False}, timeout=3)
        except Exception: pass
        if self.flask_proc:
            try: self.flask_proc.terminate()
            except Exception: pass
        try: os.remove(LOCK_FILE)
        except Exception: pass
        if self.icon: self.icon.stop()

    def notify(self, msg):
        if self.icon:
            try: self.icon.notify(msg, APP_NAME)
            except Exception: pass

    # --- Status polling ---
    def _refresh(self):
        s = api('/api/status')
        if s:
            self.status = s
        else:
            self.status = {'clash': {'proxy_port': check_port(MIXED_PORT)}}
        # Mode + TUN + allow-lan from Clash API
        try:
            import json, urllib.request
            req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}/configs')
            if CLASH_API_SECRET:
                req.add_header('Authorization', f'Bearer {CLASH_API_SECRET}')
            cfg = json.loads(urllib.request.urlopen(req, timeout=3).read())
            self._mode = cfg.get('mode', 'rule')
            self._tun_on = cfg.get('tun', {}).get('enable', False)
            self._allow_lan = cfg.get('allow-lan', False)
        except Exception: pass
        # Guard
        try:
            g = api('/api/proxy/guard', timeout=2)
            self._guard_on = g.get('enabled', False) if g else False
        except Exception: pass
        # NPM
        try:
            r = api('/api/npm/status', timeout=2)
            self._npm_on = r.get('enabled', False) if r else False
        except Exception: pass
        # Traffic speed (delta)
        try:
            t = api('/api/traffic', timeout=2)
            if t and t.get('ok'):
                ul, dl = t.get('upload', 0), t.get('download', 0)
                if self._prev_ul > 0:
                    self._speed_up = max(0, ul - self._prev_ul) // POLL_INTERVAL
                    self._speed_down = max(0, dl - self._prev_dl) // POLL_INTERVAL
                self._prev_ul, self._prev_dl = ul, dl
        except Exception: pass
        # Proxy groups
        try:
            pg = api('/api/proxies', timeout=5)
            if pg and pg.get('groups'):
                self._groups = pg['groups']
                for g in self._groups:
                    if g.get('type') == 'Selector' and g.get('now'):
                        self._current_node = g['now']
                        break
        except Exception: pass
        # Update icon + tooltip
        if self.icon:
            self.icon.icon = self.current_icon()
            self.icon.title = self.current_title()

    def _update_menu(self):
        if self.icon:
            try: self.icon.menu = self.create_menu()
            except Exception: pass

    def _status_loop(self):
        while self.running:
            try:
                self._refresh()
                self._update_menu()
            except Exception: pass
            time.sleep(POLL_INTERVAL)

    # --- Main entry ---
    def run(self):
        engine_ok = start_clash_meta()
        self.flask_proc = start_flask_server()
        time.sleep(1)
        self._refresh()
        if not engine_ok:
            self.notify('clash-meta 启动失败')
        elif not check_port(WEB_PORT):
            self.notify('Web UI 启动失败')
        if check_port(WEB_PORT):
            webbrowser.open(f'http://127.0.0.1:{WEB_PORT}')
        threading.Thread(target=self._status_loop, daemon=True).start()
        self.icon = pystray.Icon('vpn-manager', self.current_icon(),
                                 self.current_title(), self.create_menu())
        self.icon.run()


# ==================== Lock + Entry ====================
def acquire_lock():
    if os.path.isfile(LOCK_FILE):
        try:
            pid = int(open(LOCK_FILE).read().strip())
            if pid == os.getpid():
                return True
            import subprocess as _sp
            out = _sp.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                          capture_output=True, text=True, creationflags=CREATE_NO_WINDOW).stdout
            if 'pythonw' in out.lower() or 'python' in out.lower():
                return False
        except (ValueError, OSError): pass
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True


if __name__ == '__main__':
    if not acquire_lock():
        webbrowser.open(f'http://127.0.0.1:{WEB_PORT}')
        sys.exit(0)
    try:
        VPNTrayApp().run()
    finally:
        try: os.remove(LOCK_FILE)
        except Exception: pass
