"""
VPN Manager Desktop App — 系统托盘 + 进程编排 + 状态感知

架构:
  vpn-app.pyw (本文件, .pyw=无控制台窗口)
    ├── 启动 clash-meta.exe (代理引擎)
    ├── 启动 vpn-manager.py --no-auto (Flask Web UI)
    ├── 创建系统托盘图标 (pystray)
    ├── 每5秒轮询状态, 动态更新图标/tooltip
    ├── 右键菜单: 面板/开关/代理/测试/自启/退出
    └── 自动打开浏览器到管理面板

图标颜色:
  🟢 绿色 = 引擎运行 + 系统代理开启
  🟡 黄色 = 引擎运行 + 系统代理关闭
  🔴 红色 = 引擎未运行
  ⚪ 灰色 = 启动中/未知
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
APP_NAME = 'VPN Manager'
STARTUP_REG_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
STARTUP_REG_NAME = 'VPNManager'
CREATE_NO_WINDOW = 0x08000000
POLL_INTERVAL = 5
LOCK_FILE = os.path.join(BASE_DIR, '.vpn-app.lock')


# ==================== Icon Generation ====================
def make_icon(fill_color, size=64):
    """Generate anti-aliased shield icon with checkmark"""
    scale = 4
    big = size * scale
    img = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = big

    # Shield polygon
    shield = [
        (s * 0.50, s * 0.04),
        (s * 0.90, s * 0.22),
        (s * 0.87, s * 0.60),
        (s * 0.50, s * 0.96),
        (s * 0.13, s * 0.60),
        (s * 0.10, s * 0.22),
    ]
    d.polygon(shield, fill=fill_color)

    # Inner darker border
    darker = {
        '#22c55e': '#16a34a', '#eab308': '#a16207',
        '#ef4444': '#b91c1c', '#94a3b8': '#64748b',
    }
    border_color = darker.get(fill_color, '#333333')
    d.polygon(shield, outline=border_color, width=max(4, s // 32))

    # Checkmark (✓)
    lw = s // 10
    check = [(s * 0.27, s * 0.48), (s * 0.43, s * 0.67), (s * 0.73, s * 0.30)]
    d.line(check, fill='white', width=lw, joint='curve')
    # Round line caps
    for pt in check:
        r = lw // 2
        d.ellipse([pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r], fill='white')

    return img.resize((size, size), Image.LANCZOS)


ICONS = {
    'green':  make_icon('#22c55e'),
    'yellow': make_icon('#eab308'),
    'red':    make_icon('#ef4444'),
    'gray':   make_icon('#94a3b8'),
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


def api_call(path, method='GET', data=None, timeout=5):
    """Call VPN Manager Flask API"""
    try:
        url = f'http://127.0.0.1:{WEB_PORT}{path}'
        if method == 'POST':
            r = requests.post(url, json=data, timeout=timeout)
        else:
            r = requests.get(url, timeout=timeout)
        return r.json()
    except Exception:
        return None


# ==================== Process Management ====================
def start_clash_meta():
    """Start clash-meta engine if not already running"""
    if check_port(MIXED_PORT):
        return True
    if not os.path.isfile(CLASH_META) or not os.path.isfile(CLASH_CONFIG):
        return False
    subprocess.Popen(
        [CLASH_META, '-d', BASE_DIR, '-f', CLASH_CONFIG],
        creationflags=CREATE_NO_WINDOW
    )
    for _ in range(15):
        time.sleep(1)
        if check_port(MIXED_PORT):
            return True
    return False


def start_flask_server():
    """Start vpn-manager.py Flask server, return Popen handle"""
    if check_port(WEB_PORT):
        return None  # Already running (externally)
    if not os.path.isfile(VPN_MANAGER):
        return None
    # Use pythonw.exe if available (no console)
    python = sys.executable
    pythonw = os.path.join(os.path.dirname(python), 'pythonw.exe')
    if os.path.isfile(pythonw):
        python = pythonw
    proc = subprocess.Popen(
        [python, VPN_MANAGER, '--no-auto'],
        cwd=BASE_DIR,
        creationflags=CREATE_NO_WINDOW
    )
    for _ in range(10):
        time.sleep(1)
        if check_port(WEB_PORT):
            return proc
    return proc


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
            if not os.path.isfile(pythonw):
                pythonw = sys.executable
            winreg.SetValueEx(key, STARTUP_REG_NAME, 0, winreg.REG_SZ,
                              f'"{pythonw}" "{app_path}"')
        else:
            try:
                winreg.DeleteValue(key, STARTUP_REG_NAME)
            except Exception:
                pass
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
        self._traffic = {'up': 0, 'down': 0}

    # --- Status properties ---
    @property
    def engine_on(self):
        clash = self.status.get('clash', {})
        if isinstance(clash, dict):
            return bool(clash.get('proxy_port', False))
        return bool(self.status.get('clash_running', False))

    @property
    def proxy_on(self):
        sp = self.status.get('system_proxy', {})
        return sp.get('enabled', False) if isinstance(sp, dict) else False

    @property
    def git_on(self):
        gp = self.status.get('git_proxy', {})
        return bool(gp.get('http')) if isinstance(gp, dict) else False

    @property
    def npm_on(self):
        return self._npm_on

    # --- Icon / Tooltip ---
    def current_icon(self):
        if self.engine_on and self.proxy_on:
            return ICONS['green']
        elif self.engine_on:
            return ICONS['yellow']
        else:
            return ICONS['red']

    def current_title(self):
        if not self.status:
            return f'{APP_NAME} — 启动中...'
        parts = [APP_NAME]
        parts.append('引擎:运行' if self.engine_on else '引擎:停止')
        if self.engine_on:
            parts.append('代理:开' if self.proxy_on else '代理:关')
            up = self._traffic.get('up', 0)
            down = self._traffic.get('down', 0)
            if up > 0 or down > 0:
                parts.append(f'↑{_fmt_speed(up)} ↓{_fmt_speed(down)}')
        return ' | '.join(parts)

    # --- Menu ---
    def create_menu(self):
        return Menu(
            MenuItem('VPN 管理面板', self.open_webui, default=True),
            MenuItem('MetaCubeXD 面板', self.open_metacubexd),
            Menu.SEPARATOR,
            MenuItem('⚡ 一键开启', self.quick_on),
            MenuItem('⏹ 一键关闭', self.quick_off),
            Menu.SEPARATOR,
            MenuItem('系统代理', self.toggle_system_proxy,
                     checked=lambda item: self.proxy_on),
            MenuItem('Git 代理', self.toggle_git_proxy,
                     checked=lambda item: self.git_on),
            MenuItem('NPM 代理', self.toggle_npm_proxy,
                     checked=lambda item: self.npm_on),
            Menu.SEPARATOR,
            MenuItem('重载配置', self.reload_config),
            MenuItem('网络测试', self.test_connectivity),
            Menu.SEPARATOR,
            MenuItem('开机自启', self.toggle_startup,
                     checked=lambda item: self._startup),
            MenuItem('退出', self.quit_app),
        )

    # --- Actions (all run in background threads) ---
    def _async(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def open_webui(self, icon=None, item=None):
        webbrowser.open(f'http://127.0.0.1:{WEB_PORT}')

    def open_metacubexd(self, icon=None, item=None):
        webbrowser.open(f'http://127.0.0.1:{API_PORT}/ui/')

    def quick_on(self, icon=None, item=None):
        def _do():
            self.notify('正在启动 VPN...')
            if not check_port(MIXED_PORT):
                start_clash_meta()
            time.sleep(1)
            api_call('/api/proxy/system', 'POST', {'enable': True}, timeout=10)
            api_call('/api/proxy/git', 'POST', {'enable': True}, timeout=5)
            api_call('/api/proxy/npm', 'POST', {'enable': True}, timeout=5)
            time.sleep(0.5)
            self.refresh_status()
            self.notify('VPN 已开启 ✅' if self.engine_on else '启动失败')
        self._async(_do)

    def quick_off(self, icon=None, item=None):
        def _do():
            api_call('/api/proxy/system', 'POST', {'enable': False}, timeout=10)
            api_call('/api/proxy/git', 'POST', {'enable': False}, timeout=5)
            api_call('/api/proxy/npm', 'POST', {'enable': False}, timeout=5)
            time.sleep(0.5)
            self.refresh_status()
            self.notify('代理已关闭')
        self._async(_do)

    def toggle_system_proxy(self, icon=None, item=None):
        def _do():
            api_call('/api/proxy/system', 'POST', {'enable': not self.proxy_on}, timeout=10)
            time.sleep(0.5)
            self.refresh_status()
        self._async(_do)

    def toggle_git_proxy(self, icon=None, item=None):
        def _do():
            api_call('/api/proxy/git', 'POST', {'enable': not self.git_on}, timeout=10)
            time.sleep(0.5)
            self.refresh_status()
        self._async(_do)

    def toggle_npm_proxy(self, icon=None, item=None):
        def _do():
            on = self.npm_on
            api_call('/api/proxy/npm', 'POST', {'enable': not on}, timeout=10)
            time.sleep(0.5)
            self.refresh_status()
        self._async(_do)

    def reload_config(self, icon=None, item=None):
        def _do():
            self.notify('正在重载配置...')
            r = api_call('/api/config/reload', 'POST', timeout=15)
            self.notify('配置已重载' if r and r.get('ok') else '重载失败')
        self._async(_do)

    def test_connectivity(self, icon=None, item=None):
        def _do():
            self.notify('正在测试网络...')
            r = api_call('/api/connectivity', 'POST', timeout=30)
            if r:
                ok = sum(1 for k in ('google', 'github', 'baidu') if r.get(k) is True)
                self.notify(f'网络测试: {ok}/3 通过')
            else:
                self.notify('网络测试失败')
        self._async(_do)

    def toggle_startup(self, icon=None, item=None):
        self._startup = not self._startup
        set_startup(self._startup)

    def quit_app(self, icon=None, item=None):
        self.running = False
        # Disable system proxy on exit (prevent user losing internet)
        try:
            api_call('/api/proxy/system', 'POST', {'enable': False}, timeout=3)
        except Exception:
            pass
        # Terminate Flask subprocess if we started it
        if self.flask_proc:
            try:
                self.flask_proc.terminate()
            except Exception:
                pass
        # Remove lock file
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass
        if self.icon:
            self.icon.stop()

    def notify(self, msg):
        if self.icon:
            try:
                self.icon.notify(msg, APP_NAME)
            except Exception:
                pass

    # --- Status polling ---
    def refresh_status(self):
        s = api_call('/api/status')
        if s:
            self.status = s
        else:
            self.status = {'clash': {'proxy_port': check_port(MIXED_PORT)}}
        # Cache npm status (avoid blocking menu render)
        try:
            r = api_call('/api/npm/status', timeout=2)
            self._npm_on = r.get('enabled', False) if r else False
        except Exception:
            pass
        # Cache traffic
        try:
            t = api_call('/api/traffic', timeout=2)
            if t and t.get('ok'):
                self._traffic = {'up': t.get('upload', 0), 'down': t.get('download', 0)}
        except Exception:
            pass
        if self.icon:
            self.icon.icon = self.current_icon()
            self.icon.title = self.current_title()

    def status_loop(self):
        while self.running:
            try:
                self.refresh_status()
            except Exception:
                pass
            time.sleep(POLL_INTERVAL)

    # --- Main entry ---
    def run(self):
        # 1. Start clash-meta engine
        engine_ok = start_clash_meta()

        # 2. Start Flask web UI
        self.flask_proc = start_flask_server()
        time.sleep(1)

        # 3. Initial status
        self.refresh_status()

        # 3.5 Notify startup result
        if not engine_ok:
            self.notify('⚠ clash-meta 启动失败，请检查配置')
        elif not check_port(WEB_PORT):
            self.notify('⚠ Web UI 启动失败')

        # 4. Auto-open browser
        if check_port(WEB_PORT):
            webbrowser.open(f'http://127.0.0.1:{WEB_PORT}')

        # 5. Status polling thread
        threading.Thread(target=self.status_loop, daemon=True).start()

        # 6. System tray (blocks main thread)
        self.icon = pystray.Icon(
            'vpn-manager',
            self.current_icon(),
            self.current_title(),
            self.create_menu()
        )
        self.icon.run()


def _fmt_speed(bps):
    """Format bytes/s to human readable"""
    if bps < 1024:
        return f'{bps}B/s'
    elif bps < 1024 * 1024:
        return f'{bps/1024:.1f}KB/s'
    else:
        return f'{bps/1024/1024:.1f}MB/s'


def acquire_lock():
    """Prevent duplicate tray instances via lock file"""
    if os.path.isfile(LOCK_FILE):
        try:
            pid = int(open(LOCK_FILE).read().strip())
            # Check if PID is still running
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return False  # Process exists - already running
        except (ValueError, OSError):
            pass  # Stale lock
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True


# ==================== Entry Point ====================
if __name__ == '__main__':
    if not acquire_lock():
        # Already running, just open browser
        webbrowser.open(f'http://127.0.0.1:{WEB_PORT}')
        sys.exit(0)
    try:
        app = VPNTrayApp()
        app.run()
    finally:
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass
