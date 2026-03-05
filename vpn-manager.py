"""VPN Manager v2 - Per-App Proxy Control for Mihomo (Clash Meta)"""
import json, subprocess, socket, os, re, time, yaml, sys, webbrowser, threading
import urllib.request, urllib.error, urllib.parse
from pathlib import Path
from flask import Flask, jsonify, request

app = Flask(__name__)

# Auto-detect base directory (works for both .py and PyInstaller .exe)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CLASH_META = os.path.join(BASE_DIR, 'clash-meta.exe')
CLASH_CONFIG = os.path.join(BASE_DIR, 'clash-config.yaml')
MIXED_PORT = 7890
API_PORT = 9097
API_BASE = f'http://127.0.0.1:{API_PORT}'
REG_PATH = r'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'

# Comprehensive proxy bypass list (sites that should NEVER go through proxy)
BYPASS_LIST = ';'.join([
    'localhost', '127.*', '10.*', '192.168.*',
    '172.16.*','172.17.*','172.18.*','172.19.*','172.20.*',
    '172.21.*','172.22.*','172.23.*','172.24.*','172.25.*',
    '172.26.*','172.27.*','172.28.*','172.29.*','172.30.*','172.31.*',
    '<local>',
    '*.baidu.com','*.baidupcs.com','*.bdpan.com',
    '*.bilibili.com','*.bilivideo.com','*.hdslb.com','*.biliapi.net',
    '*.quark.cn','*.yunpan.cn',
    '*.chaoxing.com','*.zhihuishu.com',
    '*.taobao.com','*.tmall.com','*.alipay.com','*.alicdn.com','*.aliyuncs.com',
    '*.jd.com','*.qq.com','*.weixin.qq.com','*.wechat.com',
    '*.douyin.com','*.bytedance.com','*.toutiao.com',
    '*.xju.edu.cn','*.3chuang.net','*.sanxianjiyi.com',
    'aiotvr.xyz','*.aiotvr.xyz','hf-mirror.com','*.hf-mirror.com',
])

# App categories: name -> {need_vpn, reason, process_names}
APP_CATEGORIES = {
    "browsers": {
        "label": "浏览器",
        "icon": "🌐",
        "need_vpn": True,
        "reason": "访问Google/GitHub/YouTube等被墙网站",
        "apps": {
            "chrome.exe": "Google Chrome",
            "msedge.exe": "Microsoft Edge",
            "firefox.exe": "Firefox",
            "brave.exe": "Brave",
        }
    },
    "dev_tools": {
        "label": "开发工具",
        "icon": "💻",
        "need_vpn": True,
        "reason": "GitHub/npm/Docker/pip包下载",
        "apps": {
            "Windsurf.exe": "Windsurf IDE",
            "Code.exe": "VS Code",
            "git.exe": "Git",
            "node.exe": "Node.js/npm",
            "docker.exe": "Docker",
            "python.exe": "Python/pip",
            "pythonw.exe": "Python (bg)",
            "pwsh.exe": "PowerShell",
            "ollama.exe": "Ollama (AI模型)",
            "ollama app.exe": "Ollama App",
        }
    },
    "chinese_apps": {
        "label": "国内应用",
        "icon": "🏠",
        "need_vpn": False,
        "reason": "国内服务直连更快",
        "apps": {
            "QQ.exe": "QQ",
            "Weixin.exe": "微信",
            "WeChatAppEx.exe": "微信小程序",
            "JianyingPro.exe": "剪映专业版",
            "SogouCloud.exe": "搜狗输入法",
            "SGTool.exe": "搜狗工具",
        }
    },
    "remote_desktop": {
        "label": "远程控制",
        "icon": "🖥️",
        "need_vpn": False,
        "reason": "局域网/内网直连",
        "apps": {
            "mstsc.exe": "远程桌面",
            "ToDesk.exe": "ToDesk",
            "sunshine.exe": "Sunshine",
            "spacedeskService.exe": "SpaceDesk",
        }
    },
    "utilities": {
        "label": "系统工具",
        "icon": "🔧",
        "need_vpn": False,
        "reason": "本地工具无需网络",
        "apps": {
            "PixPin.exe": "PixPin截图",
            "OpenHardwareMonitor.exe": "硬件监控",
            "syncthing.exe": "Syncthing同步",
            "OpenRGB.exe": "OpenRGB灯光",
        }
    },
    "hardware": {
        "label": "硬件驱动",
        "icon": "🎮",
        "need_vpn": False,
        "reason": "驱动/固件本地运行",
        "apps": {
            "NVIDIA Overlay.exe": "NVIDIA Overlay",
            "RzSDKServer.exe": "Razer SDK",
            "OVRServer_x64.exe": "Oculus VR",
        }
    },
}

def get_app_rules():
    """Read PROCESS-NAME rules from clash config"""
    rules = {}
    try:
        with open(CLASH_CONFIG, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        for rule in cfg.get('rules', []):
            if rule.startswith('PROCESS-NAME,'):
                parts = rule.split(',')
                if len(parts) == 3:
                    rules[parts[1]] = parts[2]
    except Exception:
        pass
    return rules

def _sanitize_process_name(name):
    """Sanitize process name to prevent YAML injection"""
    if not name or not isinstance(name, str):
        return None
    import re as _re
    name = name.strip()
    if not _re.match(r'^[\w.-]+\.exe$', name, _re.IGNORECASE):
        return None
    if len(name) > 100:
        return None
    return name

def set_app_rule(process_name, route):
    """Set PROCESS-NAME rule for an app and reload Clash config"""
    process_name = _sanitize_process_name(process_name)
    if not process_name:
        return False
    if route not in ('DIRECT', 'PROXY', 'REJECT'):
        return False
    try:
        with open(CLASH_CONFIG, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        rules = cfg.get('rules', [])
        new_rule = f'PROCESS-NAME,{process_name},{route}'
        found = False
        for i, rule in enumerate(rules):
            if rule.startswith(f'PROCESS-NAME,{process_name},'):
                rules[i] = new_rule
                found = True
                break
        if not found:
            insert_idx = len(rules)
            for i, rule in enumerate(rules):
                if any(rule.startswith(p) for p in ['GEOSITE,', 'GEOIP,', 'MATCH,']):
                    insert_idx = i
                    break
            rules.insert(insert_idx, new_rule)
        cfg['rules'] = rules
        with open(CLASH_CONFIG, 'w', encoding='utf-8') as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        reload_clash_config()
        return True
    except Exception as e:
        print(f"Error setting app rule: {e}")
        return False

CLASH_API_SECRET = 'clash-agent-local'

def _clash_headers():
    h = {'Content-Type': 'application/json'}
    if CLASH_API_SECRET:
        h['Authorization'] = f'Bearer {CLASH_API_SECRET}'
    return h

def reload_clash_config():
    """Tell Clash to reload config file"""
    try:
        data = json.dumps({"path": CLASH_CONFIG}).encode()
        req = urllib.request.Request(
            f'{API_BASE}/configs?force=true',
            data=data, method='PUT',
            headers=_clash_headers()
        )
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception:
        return False

def clash_api(path, method='GET', data=None):
    """Generic Clash REST API caller"""
    try:
        url = f'{API_BASE}{path}'
        headers = _clash_headers()
        if data:
            body = json.dumps(data).encode()
            req = urllib.request.Request(url, data=body, method=method, headers=headers)
        else:
            req = urllib.request.Request(url, method=method, headers=headers)
        resp = urllib.request.urlopen(req, timeout=8)
        return json.loads(resp.read())
    except Exception:
        return None

def get_clash_connections():
    """Get active connections from Clash API"""
    return clash_api('/connections')

def check_port(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(('127.0.0.1', port))
        s.close()
        return True
    except Exception:
        return False

def run_ps(cmd, timeout=10):
    try:
        full_cmd = '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; ' + cmd
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command', full_cmd],
            capture_output=True, text=True, timeout=timeout, encoding='utf-8', errors='replace',
            creationflags=0x08000000
        )
        return r.stdout.strip()
    except Exception:
        return ''

# Windows system/driver processes to exclude from uncategorized list
SYSTEM_EXCLUDE = {
    'explorer.exe', 'SearchHost.exe', 'ShellExperienceHost.exe',
    'StartMenuExperienceHost.exe', 'TextInputHost.exe', 'TabTip.exe',
    'SystemSettings.exe', 'WidgetService.exe', 'Widgets.exe',
    'Copilot.exe', 'AppActions.exe', 'crashpad_handler.exe',
    'RuntimeBroker.exe', 'ApplicationFrameHost.exe', 'dwm.exe',
    'taskhostw.exe', 'sihost.exe', 'fontdrvhost.exe',
    'clash-meta.exe',  # VPN engine itself
}

def get_running_processes():
    """Get all user processes with windows or known names"""
    cmd = """Get-Process | Where-Object { $_.Path -and $_.Path -notmatch 'C:\\\\Windows\\\\System32' } | Select-Object ProcessName, Id, @{N='Window';E={$_.MainWindowTitle}}, @{N='ExePath';E={$_.Path}} | ConvertTo-Json -Depth 2"""
    out = run_ps(cmd, timeout=15)
    if not out:
        return []
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return data
    except:
        return []

def get_system_proxy():
    enable = run_ps(f'(Get-ItemProperty "{REG_PATH}").ProxyEnable')
    server = run_ps(f'(Get-ItemProperty "{REG_PATH}").ProxyServer')
    return {'enabled': enable == '1', 'server': server}

def get_git_proxy():
    http_p = run_ps('git config --global --get http.proxy')
    https_p = run_ps('git config --global --get https.proxy')
    return {'http': http_p, 'https': https_p}

def get_env_proxy():
    return {
        'HTTP_PROXY': os.environ.get('HTTP_PROXY', ''),
        'HTTPS_PROXY': os.environ.get('HTTPS_PROXY', ''),
        'ALL_PROXY': os.environ.get('ALL_PROXY', ''),
    }

@app.route('/')
def index():
    return HTML_PAGE

@app.route('/api/status')
def api_status():
    clash_running = check_port(MIXED_PORT)
    api_running = check_port(API_PORT)
    sys_proxy = get_system_proxy()
    git_proxy = get_git_proxy()
    env_proxy = get_env_proxy()
    
    # Get running processes
    procs = get_running_processes()
    proc_names = set()
    proc_map = {}
    for p in procs:
        name = p.get('ProcessName', '') + '.exe'
        proc_names.add(name)
        if name not in proc_map:
            proc_map[name] = {'name': name, 'pids': [], 'window': p.get('Window', '')}
        proc_map[name]['pids'].append(p.get('Id', 0))
    
    # Per-app routing rules from config
    app_rules = get_app_rules()
    
    # Categorize
    categories = []
    uncategorized = set(proc_names)
    for cat_id, cat in APP_CATEGORIES.items():
        apps = []
        for proc_name, display_name in cat['apps'].items():
            running = proc_name in proc_names
            if running:
                uncategorized.discard(proc_name)
            route = app_rules.get(proc_name, 'PROXY' if cat['need_vpn'] else 'DIRECT')
            apps.append({
                'process': proc_name,
                'display': display_name,
                'running': running,
                'route': route,
                'pids': proc_map.get(proc_name, {}).get('pids', []),
                'window': proc_map.get(proc_name, {}).get('window', ''),
            })
        categories.append({
            'id': cat_id,
            'label': cat['label'],
            'icon': cat['icon'],
            'need_vpn': cat['need_vpn'],
            'reason': cat['reason'],
            'apps': apps,
        })
    
    # Uncategorized running processes (with details, filtered)
    uncat_list = []
    for pname in sorted(uncategorized):
        if pname in proc_map and pname not in SYSTEM_EXCLUDE:
            route = app_rules.get(pname, '')
            uncat_list.append({
                'process': pname,
                'pids': proc_map[pname]['pids'],
                'window': proc_map[pname].get('window', ''),
                'route': route,
                'in_config': bool(route),
            })

    return jsonify({
        'clash': {'proxy_port': clash_running, 'api_port': api_running},
        'system_proxy': sys_proxy,
        'git_proxy': git_proxy,
        'env_proxy': env_proxy,
        'categories': categories,
        'uncategorized': uncat_list,
        'uncategorized_count': len(uncat_list),
    })

@app.route('/api/app/route', methods=['POST'])
def api_app_route():
    """Toggle per-app routing: PROXY or DIRECT"""
    data = request.json
    process = data.get('process')
    route = data.get('route', 'PROXY')
    if not process:
        return jsonify({'ok': False, 'msg': '缺少进程名'})
    ok = set_app_rule(process, route)
    return jsonify({'ok': ok, 'msg': f'{process} → {route}' if ok else '更新规则失败'})

@app.route('/api/app/add', methods=['POST'])
def api_app_add():
    """Add a new process rule to clash config"""
    data = request.json
    process = data.get('process')
    route = data.get('route', 'DIRECT')
    if not process:
        return jsonify({'ok': False, 'msg': '缺少进程名'})
    ok = set_app_rule(process, route)
    return jsonify({'ok': ok, 'msg': f'已添加 {process} → {route}' if ok else '添加失败'})

@app.route('/api/connections')
def api_connections():
    """Get active connections from Clash API"""
    data = get_clash_connections()
    if data is None:
        return jsonify({'connections': [], 'upload': 0, 'download': 0})
    conns = []
    for c in (data.get('connections') or [])[:100]:
        meta = c.get('metadata', {})
        proc_path = meta.get('processPath', '')
        proc_name = proc_path.split('\\')[-1].split('/')[-1] if proc_path else meta.get('process', '')
        conns.append({
            'id': c.get('id', ''),
            'host': meta.get('host') or meta.get('destinationIP', ''),
            'port': meta.get('destinationPort', ''),
            'process': proc_name,
            'chain': ' → '.join(c.get('chains', [])),
            'rule': c.get('rule', ''),
            'dl': c.get('download', 0),
            'ul': c.get('upload', 0),
        })
    return jsonify({
        'connections': conns,
        'upload': data.get('uploadTotal', 0),
        'download': data.get('downloadTotal', 0),
    })

@app.route('/api/clash/start', methods=['POST'])
def api_clash_start():
    if check_port(MIXED_PORT):
        return jsonify({'ok': True, 'msg': 'Already running'})
    subprocess.Popen([CLASH_META, '-d', BASE_DIR, '-f', CLASH_CONFIG], creationflags=0x08000000)
    time.sleep(4)
    ok = check_port(MIXED_PORT)
    return jsonify({'ok': ok, 'msg': '启动成功' if ok else '启动失败'})

@app.route('/api/clash/stop', methods=['POST'])
def api_clash_stop():
    # P0: Auto-disable system proxy to prevent internet loss
    run_ps(f'Set-ItemProperty "{REG_PATH}" -Name ProxyEnable -Value 0')
    run_ps("Get-Process -Name 'clash-meta' -ErrorAction SilentlyContinue | Stop-Process -Force")
    time.sleep(1)
    return jsonify({'ok': True, 'msg': 'Stopped + system proxy disabled'})

@app.route('/api/proxy/system', methods=['POST'])
def api_proxy_system():
    data = request.json
    enable = data.get('enable', False)
    if enable:
        run_ps(f'Set-ItemProperty "{REG_PATH}" -Name ProxyEnable -Value 1')
        run_ps(f'Set-ItemProperty "{REG_PATH}" -Name ProxyServer -Value "127.0.0.1:{MIXED_PORT}"')
        run_ps(f'Set-ItemProperty "{REG_PATH}" -Name ProxyOverride -Value "{BYPASS_LIST}"')
    else:
        run_ps(f'Set-ItemProperty "{REG_PATH}" -Name ProxyEnable -Value 0')
    return jsonify({'ok': True})

@app.route('/api/proxy/git', methods=['POST'])
def api_proxy_git():
    data = request.json
    enable = data.get('enable', False)
    proxy = f'http://127.0.0.1:{MIXED_PORT}'
    if enable:
        run_ps(f'git config --global http.proxy {proxy}')
        run_ps(f'git config --global https.proxy {proxy}')
    else:
        run_ps('git config --global --unset http.proxy')
        run_ps('git config --global --unset https.proxy')
    return jsonify({'ok': True})

@app.route('/api/proxy/npm', methods=['POST'])
def api_proxy_npm():
    data = request.json
    enable = data.get('enable', False)
    proxy = f'http://127.0.0.1:{MIXED_PORT}'
    if enable:
        run_ps(f'npm config set proxy {proxy}')
        run_ps(f'npm config set https-proxy {proxy}')
    else:
        run_ps('npm config delete proxy')
        run_ps('npm config delete https-proxy')
    return jsonify({'ok': True})

@app.route('/api/proxy/clean', methods=['POST'])
def api_proxy_clean():
    run_ps(f'Set-ItemProperty "{REG_PATH}" -Name ProxyEnable -Value 0')
    run_ps(f'Remove-ItemProperty "{REG_PATH}" -Name ProxyServer -ErrorAction SilentlyContinue')
    run_ps('git config --global --unset http.proxy')
    run_ps('git config --global --unset https.proxy')
    run_ps('npm config delete proxy 2>$null')
    run_ps('npm config delete https-proxy 2>$null')
    for v in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY']:
        run_ps(f'[Environment]::SetEnvironmentVariable("{v}",$null,"User")')
    return jsonify({'ok': True, 'msg': 'All proxy traces cleaned'})

@app.route('/api/quick-on', methods=['POST'])
def api_quick_on():
    """One-click VPN: start clash + enable system proxy + git proxy"""
    msgs = []
    if not check_port(MIXED_PORT):
        subprocess.Popen([CLASH_META, '-d', BASE_DIR, '-f', CLASH_CONFIG], creationflags=0x08000000)
        time.sleep(4)
        msgs.append('clash-meta started' if check_port(MIXED_PORT) else 'clash-meta FAILED')
    else:
        msgs.append('clash-meta already running')
    run_ps(f'Set-ItemProperty "{REG_PATH}" -Name ProxyEnable -Value 1')
    run_ps(f'Set-ItemProperty "{REG_PATH}" -Name ProxyServer -Value "127.0.0.1:{MIXED_PORT}"')
    run_ps(f'Set-ItemProperty "{REG_PATH}" -Name ProxyOverride -Value "{BYPASS_LIST}"')
    proxy = f'http://127.0.0.1:{MIXED_PORT}'
    run_ps(f'git config --global http.proxy {proxy}')
    run_ps(f'git config --global https.proxy {proxy}')
    run_ps(f'npm config set proxy {proxy}')
    run_ps(f'npm config set https-proxy {proxy}')
    msgs.append('system+git+npm proxy enabled')
    return jsonify({'ok': check_port(MIXED_PORT), 'msg': '; '.join(msgs)})

@app.route('/api/quick-off', methods=['POST'])
def api_quick_off():
    """One-click VPN off: disable proxies but keep clash running"""
    run_ps(f'Set-ItemProperty "{REG_PATH}" -Name ProxyEnable -Value 0')
    run_ps('git config --global --unset http.proxy')
    run_ps('git config --global --unset https.proxy')
    run_ps('npm config delete proxy 2>$null')
    run_ps('npm config delete https-proxy 2>$null')
    return jsonify({'ok': True, 'msg': 'All proxies disabled, clash-meta still running'})

@app.route('/api/npm/status')
def api_npm_status():
    proxy = run_ps('npm config get proxy 2>$null')
    on = bool(proxy) and proxy != 'null' and proxy != 'undefined'
    return jsonify({'enabled': on, 'proxy': proxy if on else ''})

@app.route('/api/connectivity', methods=['POST'])
def api_connectivity():
    import concurrent.futures
    results = {}
    proxy_up = check_port(MIXED_PORT)
    def test_google():
        if not proxy_up: return None
        out = run_ps(f"try {{ $r = Invoke-WebRequest 'https://www.google.com' -Proxy 'http://127.0.0.1:{MIXED_PORT}' -TimeoutSec 6 -UseBasicParsing -ErrorAction Stop; $r.StatusCode }} catch {{ 'FAIL' }}", timeout=12)
        return out == '200'
    def test_github():
        if not proxy_up: return None
        out = run_ps(f"try {{ $r = Invoke-WebRequest 'https://api.github.com' -Proxy 'http://127.0.0.1:{MIXED_PORT}' -TimeoutSec 6 -UseBasicParsing -ErrorAction Stop; $r.StatusCode }} catch {{ 'FAIL' }}", timeout=12)
        return out == '200'
    def test_baidu():
        out = run_ps("try { $r = Invoke-WebRequest 'https://www.baidu.com' -TimeoutSec 4 -UseBasicParsing -ErrorAction Stop; $r.StatusCode } catch { 'FAIL' }", timeout=8)
        return out == '200'
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        fg, fgh, fb = ex.submit(test_google), ex.submit(test_github), ex.submit(test_baidu)
        results['google'] = fg.result()
        results['github'] = fgh.result()
        results['baidu'] = fb.result()
    return jsonify(results)

# ===== New Clash API Endpoints (v3) =====

@app.route('/api/proxies')
def api_proxies():
    data = clash_api('/proxies')
    if not data:
        return jsonify({'groups': []})
    groups = []
    proxies_raw = data.get('proxies', {})
    for name, info in proxies_raw.items():
        ptype = info.get('type', '')
        if ptype in ('Selector', 'URLTest', 'Fallback', 'LoadBalance'):
            nodes = []
            for n in info.get('all', []):
                ni = proxies_raw.get(n, {})
                delay = 0
                hist = ni.get('history', [])
                if hist:
                    delay = hist[-1].get('delay', 0)
                nodes.append({'name': n, 'type': ni.get('type', '?'), 'delay': delay, 'udp': ni.get('udp', False), 'tfo': ni.get('tfo', False)})
            groups.append({'name': name, 'type': ptype, 'now': info.get('now', ''), 'nodes': nodes})
    groups.sort(key=lambda g: g['name'])
    return jsonify({'groups': groups})

@app.route('/api/proxies/<path:name>/delay', methods=['POST'])
def api_proxy_delay(name):
    encoded = urllib.parse.quote(name, safe='')
    result = clash_api(f'/proxies/{encoded}/delay?timeout=5000&url=http://www.gstatic.com/generate_204')
    if result and 'delay' in result:
        return jsonify({'ok': True, 'delay': result['delay'], 'name': name})
    return jsonify({'ok': False, 'delay': -1, 'name': name})

@app.route('/api/proxies/<path:group>/select', methods=['POST'])
def api_proxy_select(group):
    req_data = request.json
    proxy_name = req_data.get('name')
    if not proxy_name:
        return jsonify({'ok': False})
    encoded = urllib.parse.quote(group, safe='')
    try:
        body = json.dumps({'name': proxy_name}).encode()
        req = urllib.request.Request(f'{API_BASE}/proxies/{encoded}', data=body, method='PUT',
                                    headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
        return jsonify({'ok': True, 'msg': f'{group} → {proxy_name}'})
    except:
        return jsonify({'ok': False})

@app.route('/api/proxies/<path:group>/delay-all', methods=['POST'])
def api_proxy_delay_all(group):
    encoded = urllib.parse.quote(group, safe='')
    result = clash_api(f'/group/{encoded}/delay?url=http://www.gstatic.com/generate_204&timeout=5000')
    if result:
        return jsonify({'ok': True, 'delays': result})
    return jsonify({'ok': False, 'delays': {}})

@app.route('/api/rules')
def api_rules_list():
    data = clash_api('/rules')
    if not data:
        return jsonify({'rules': []})
    return jsonify({'rules': data.get('rules', [])})

@app.route('/api/dns/query', methods=['POST'])
def api_dns_query():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'ok': False, 'msg': '请输入域名'})
    result = clash_api(f'/dns/query?name={urllib.parse.quote(name)}&type={data.get("type","A")}')
    if result:
        return jsonify({'ok': True, 'result': result})
    return jsonify({'ok': False, 'msg': 'DNS查询失败'})

@app.route('/api/config/view')
def api_config_view():
    try:
        with open(CLASH_CONFIG, 'r', encoding='utf-8') as f:
            return jsonify({'ok': True, 'content': f.read(), 'path': CLASH_CONFIG})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/diagnose', methods=['POST'])
def api_diagnose():
    import concurrent.futures
    results = []
    engine_ok = check_port(MIXED_PORT)
    results.append({'name': '代理引擎 (:7890)', 'ok': engine_ok, 'detail': '运行中' if engine_ok else '未运行'})
    api_ok = check_port(API_PORT)
    results.append({'name': 'API (:9097)', 'ok': api_ok, 'detail': '正常' if api_ok else '未响应'})
    results.append({'name': '配置文件', 'ok': os.path.isfile(CLASH_CONFIG), 'detail': os.path.basename(CLASH_CONFIG)})
    results.append({'name': '引擎二进制', 'ok': os.path.isfile(CLASH_META), 'detail': os.path.basename(CLASH_META)})
    ui_dir = os.path.join(BASE_DIR, 'ui')
    ui_count = len(os.listdir(ui_dir)) if os.path.isdir(ui_dir) else 0
    results.append({'name': 'MetaCubeXD', 'ok': ui_count > 5, 'detail': f'{ui_count}文件' if ui_count else '未安装'})
    geo_dir = os.path.join(BASE_DIR, 'geodata')
    geo_found = sum(1 for f in ['geoip.dat','geosite.dat','Country.mmdb'] if os.path.isfile(os.path.join(geo_dir, f)))
    results.append({'name': '地理数据', 'ok': geo_found == 3, 'detail': f'{geo_found}/3'})
    v = clash_api('/version') if api_ok else None
    if v:
        results.append({'name': '引擎版本', 'ok': True, 'detail': v.get('version', '?')})
    sp = get_system_proxy()
    results.append({'name': '系统代理', 'ok': True, 'detail': f"{'启用' if sp['enabled'] else '关闭'} {sp.get('server','')}"})
    def _test(url, proxy=None, t=6):
        try:
            cmd = f"try {{ $r = Invoke-WebRequest '{url}'"
            if proxy: cmd += f" -Proxy '{proxy}'"
            cmd += f" -TimeoutSec {t} -UseBasicParsing -ErrorAction Stop; $r.StatusCode }} catch {{ 'FAIL' }}"
            return run_ps(cmd, timeout=t+4) == '200'
        except: return False
    purl = f'http://127.0.0.1:{MIXED_PORT}' if engine_ok else None
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        fb = ex.submit(_test, 'https://www.baidu.com', None, 4)
        fg = ex.submit(_test, 'https://www.google.com', purl) if engine_ok else None
        fgh = ex.submit(_test, 'https://api.github.com', purl) if engine_ok else None
        fb_ok = fb.result()
        results.append({'name': 'Baidu直连', 'ok': fb_ok, 'detail': '通' if fb_ok else '不通'})
        gok = fg.result() if fg else None
        ghok = fgh.result() if fgh else None
        results.append({'name': 'Google代理', 'ok': gok, 'detail': '通' if gok else ('未测' if gok is None else '不通')})
        results.append({'name': 'GitHub代理', 'ok': ghok, 'detail': '通' if ghok else ('未测' if ghok is None else '不通')})
    passed = sum(1 for r in results if r['ok'] is True)
    return jsonify({'results': results, 'passed': passed, 'total': len(results)})

@app.route('/api/subscription/update', methods=['POST'])
def api_sub_update():
    gen_script = os.path.join(BASE_DIR, 'gen_config.py')
    if not os.path.isfile(gen_script):
        return jsonify({'ok': False, 'msg': 'gen_config.py 不存在'})
    msgs = []
    # Step 1: Try to download fresh subscription
    sub_url, sub_dest = _find_sub_url()
    if sub_url and sub_dest:
        try:
            curl_cmd = ['curl.exe', '-s', '-m', '30', '--ssl-no-revoke', '-A', 'clash-verge/v1.5.11',
                        '--noproxy', '*', sub_url, '-o', sub_dest]
            dl = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=35, creationflags=0x08000000)
            if dl.returncode == 0 and os.path.getsize(sub_dest) > 1000:
                msgs.append(f'\u8ba2\u9605\u4e0b\u8f7d\u6210\u529f ({os.path.getsize(sub_dest)//1024}KB)')
            else:
                msgs.append('\u8ba2\u9605\u4e0b\u8f7d\u5931\u8d25\uff0c\u4f7f\u7528\u672c\u5730\u7f13\u5b58')
        except Exception:
            msgs.append('\u8ba2\u9605\u4e0b\u8f7d\u8d85\u65f6\uff0c\u4f7f\u7528\u672c\u5730\u7f13\u5b58')
    # Step 2: Regenerate config
    try:
        r = subprocess.run([sys.executable, gen_script], capture_output=True, text=True, timeout=30, cwd=BASE_DIR, creationflags=0x08000000)
        if r.returncode == 0:
            msgs.append(r.stdout.strip() or '\u914d\u7f6e\u5df2\u66f4\u65b0')
            reload_clash_config()
            return jsonify({'ok': True, 'msg': ' | '.join(msgs)})
        return jsonify({'ok': False, 'msg': r.stderr.strip() or r.stdout.strip() or '\u5931\u8d25'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

def _find_sub_url():
    """Find subscription URL from Clash Verge profiles.yaml"""
    profiles_yaml = os.path.join(os.path.expanduser('~'), '.config', 'clash-verge', 'profiles', 'profiles.yaml')
    if not os.path.isfile(profiles_yaml):
        return None, None
    try:
        with open(profiles_yaml, 'r', encoding='utf-8') as f:
            pdata = yaml.safe_load(f)
        for item in pdata.get('items', []):
            if item.get('type') == 'remote' and item.get('url'):
                dest = os.path.join(os.path.expanduser('~'), '.config', 'clash-verge', 'profiles', item.get('file', 'subscription.yaml'))
                return item['url'], dest
    except Exception:
        pass
    return None, None

@app.route('/api/version')
def api_version():
    v = clash_api('/version') if check_port(API_PORT) else None
    return jsonify({'manager': 'v4.0', 'engine': v.get('version','?') if v else '未运行'})

@app.route('/api/traffic')
def api_traffic():
    """Get current traffic snapshot via connections endpoint"""
    d = clash_api('/connections')
    if not d: return jsonify({'ok': False})
    return jsonify({'ok': True, 'upload': d.get('uploadTotal',0), 'download': d.get('downloadTotal',0)})

@app.route('/api/logs')
def api_logs():
    """Get recent logs by pulling from Clash log level endpoint"""
    level = request.args.get('level', 'info')
    limit = int(request.args.get('limit', '100'))
    # Clash /logs is a streaming SSE endpoint — calling it blocks forever
    # Frontend uses WebSocket directly to Clash API for real-time logs
    return jsonify({'ok': True, 'logs': [], 'note': '使用工具页的MetaCubeXD面板查看完整日志流'})

@app.route('/api/connections/close', methods=['POST'])
def api_close_connection():
    """Close a specific connection by ID"""
    data = request.get_json(silent=True) or {}
    conn_id = data.get('id', '')
    if not conn_id: return jsonify({'ok': False, 'msg': '缺少连接ID'})
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}/connections/{conn_id}', method='DELETE')
        urllib.request.urlopen(req, timeout=5)
        return jsonify({'ok': True, 'msg': f'连接 {conn_id[:8]}... 已关闭'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/connections/close-all', methods=['POST'])
def api_close_all_connections():
    """Close all active connections"""
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}/connections', method='DELETE')
        urllib.request.urlopen(req, timeout=5)
        return jsonify({'ok': True, 'msg': '所有连接已关闭'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/tun', methods=['GET'])
def api_tun_status():
    """Get TUN mode status"""
    d = clash_api('/configs')
    if not d: return jsonify({'ok': False, 'enabled': False})
    tun = d.get('tun', {})
    return jsonify({'ok': True, 'enabled': tun.get('enable', False), 'stack': tun.get('stack', 'gvisor'), 'device': tun.get('device', '')})

@app.route('/api/tun', methods=['POST'])
def api_tun_toggle():
    """Toggle TUN mode on/off"""
    data = request.get_json(silent=True) or {}
    enable = data.get('enable', False)
    try:
        payload = json.dumps({'tun': {'enable': enable}}).encode()
        req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}/configs', data=payload, method='PATCH', headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
        return jsonify({'ok': True, 'msg': f'TUN模式已{"开启" if enable else "关闭"}'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/mode')
def api_mode_get():
    """Get current proxy mode (rule/global/direct)"""
    d = clash_api('/configs')
    if not d: return jsonify({'ok': False, 'mode': 'unknown'})
    return jsonify({'ok': True, 'mode': d.get('mode', 'rule')})

@app.route('/api/mode', methods=['POST'])
def api_mode_set():
    """Switch proxy mode"""
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'rule')
    if mode not in ('rule', 'global', 'direct'):
        return jsonify({'ok': False, 'msg': 'Invalid mode'})
    try:
        payload = json.dumps({'mode': mode}).encode()
        req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}/configs', data=payload, method='PATCH', headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
        return jsonify({'ok': True, 'mode': mode, 'msg': f'模式切换为 {mode}'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/config/reload', methods=['POST'])
def api_config_reload():
    """Reload Clash configuration file"""
    try:
        payload = json.dumps({'path': CLASH_CONFIG}).encode()
        req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}/configs?force=true', data=payload, method='PUT', headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=30)
        return jsonify({'ok': True, 'msg': '配置已重载'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/rules/providers')
def api_rule_providers():
    """Get rule providers info"""
    d = clash_api('/providers/rules')
    if not d: return jsonify({'ok': False, 'providers': {}})
    return jsonify({'ok': True, 'providers': d.get('providers', {})})

@app.route('/api/providers/proxies')
def api_proxy_providers():
    """Get proxy providers info"""
    d = clash_api('/providers/proxies')
    if not d: return jsonify({'ok': False, 'providers': {}})
    providers = {}
    for name, info in d.get('providers', {}).items():
        if info.get('vehicleType') == 'Compatible': continue
        providers[name] = {
            'name': name,
            'type': info.get('type', ''),
            'vehicleType': info.get('vehicleType', ''),
            'updatedAt': info.get('updatedAt', ''),
            'nodeCount': len(info.get('proxies', [])),
        }
    return jsonify({'ok': True, 'providers': providers})

@app.route('/api/providers/proxies/update', methods=['POST'])
def api_update_proxy_provider():
    """Update a specific proxy provider"""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '')
    if not name: return jsonify({'ok': False, 'msg': '缺少提供者名称'})
    try:
        req = urllib.request.Request(
            f'http://127.0.0.1:{API_PORT}/providers/proxies/{urllib.parse.quote(name)}',
            method='PUT', data=b'')
        urllib.request.urlopen(req, timeout=30)
        return jsonify({'ok': True, 'msg': f'代理提供者 {name} 已更新'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/providers/rules/update', methods=['POST'])
def api_update_rule_provider():
    """Update a specific rule provider"""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '')
    if not name: return jsonify({'ok': False, 'msg': '缺少提供者名称'})
    try:
        req = urllib.request.Request(
            f'http://127.0.0.1:{API_PORT}/providers/rules/{urllib.parse.quote(name)}',
            method='PUT', data=b'')
        urllib.request.urlopen(req, timeout=30)
        return jsonify({'ok': True, 'msg': f'规则集 {name} 已更新'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/engine/info')
def api_engine_info():
    """Get engine runtime info: memory, mode, version"""
    cfg = clash_api('/configs')
    ver = clash_api('/version')
    if not cfg: return jsonify({'ok': False})
    # Get clash-meta process memory usage (avoid /memory SSE endpoint)
    mem_bytes = 0
    try:
        out = run_ps("(Get-Process clash-meta -ErrorAction SilentlyContinue | Select-Object -First 1).WorkingSet64", timeout=5)
        if out: mem_bytes = int(out)
    except: pass
    return jsonify({
        'ok': True,
        'mode': cfg.get('mode', '?'),
        'logLevel': cfg.get('log-level', '?'),
        'ipv6': cfg.get('ipv6', False),
        'sniff': cfg.get('sniff', False),
        'memory': mem_bytes,
        'version': ver.get('version', '?') if ver else '?',
    })

# ===== System proxy guard (background thread) =====
_proxy_guard_enabled = False
_proxy_guard_thread = None

def _proxy_guard_loop():
    """Background thread: re-enable system proxy if it gets disabled while guard is on"""
    global _proxy_guard_enabled
    while _proxy_guard_enabled:
        try:
            out = run_ps(f'(Get-ItemProperty -Path "{REG_PATH}" -Name ProxyEnable -ErrorAction SilentlyContinue).ProxyEnable')
            if out and out.strip() != '1' and check_port(MIXED_PORT):
                run_ps(f'Set-ItemProperty -Path "{REG_PATH}" -Name ProxyEnable -Value 1 -Type DWord')
                run_ps(f'Set-ItemProperty -Path "{REG_PATH}" -Name ProxyServer -Value "127.0.0.1:{MIXED_PORT}"')
        except: pass
        time.sleep(10)

@app.route('/api/proxy/guard', methods=['GET'])
def api_proxy_guard_status():
    return jsonify({'ok': True, 'enabled': _proxy_guard_enabled})

@app.route('/api/proxy/guard', methods=['POST'])
def api_proxy_guard_toggle():
    global _proxy_guard_enabled, _proxy_guard_thread
    data = request.get_json(silent=True) or {}
    enable = data.get('enable', False)
    _proxy_guard_enabled = enable
    if enable and (_proxy_guard_thread is None or not _proxy_guard_thread.is_alive()):
        _proxy_guard_thread = threading.Thread(target=_proxy_guard_loop, daemon=True)
        _proxy_guard_thread.start()
    return jsonify({'ok': True, 'msg': f'代理守护已{"开启" if enable else "关闭"}'})


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VPN Manager v4.0</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🛡</text></svg>">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; background:#0f172a; color:#e2e8f0; min-height:100vh; }
.container { max-width:960px; margin:0 auto; padding:16px; }
h1 { text-align:center; font-size:1.6rem; margin-bottom:4px; background:linear-gradient(135deg,#60a5fa,#a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.subtitle { text-align:center; color:#64748b; font-size:0.8rem; margin-bottom:12px; }
/* Tabs */
.tabs { display:flex; gap:2px; margin-bottom:14px; background:#1e293b; border-radius:10px; padding:3px; border:1px solid #334155; }
.tab-btn { flex:1; padding:8px 4px; border:none; border-radius:8px; font-size:0.8rem; font-weight:600; cursor:pointer; background:transparent; color:#94a3b8; transition:.2s; }
.tab-btn:hover { color:#e2e8f0; }
.tab-btn.active { background:#334155; color:#60a5fa; box-shadow:0 2px 8px rgba(0,0,0,.3); }
.tab-pane { display:none; }
.tab-pane.active { display:block; }
/* Nodes panel */
.proxy-group { background:#1e293b; border-radius:10px; border:1px solid #334155; margin-bottom:10px; overflow:hidden; }
.pg-header { display:flex; align-items:center; justify-content:space-between; padding:10px 14px; cursor:pointer; }
.pg-header:hover { opacity:.85; }
.pg-name { font-weight:600; font-size:.9rem; }
.pg-now { font-size:.75rem; color:#4ade80; }
.pg-type { font-size:.65rem; color:#64748b; padding:2px 6px; background:#334155; border-radius:4px; }
.pg-body { border-top:1px solid #334155; max-height:280px; overflow-y:auto; }
.node-row { display:flex; align-items:center; padding:6px 14px; font-size:.8rem; gap:8px; border-bottom:1px solid #1a2332; cursor:pointer; transition:.15s; }
.node-row:hover { background:#263548; }
.node-row.selected { background:#1e3a5f; border-left:3px solid #60a5fa; }
.node-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.node-type { font-size:.65rem; color:#64748b; min-width:50px; }
.node-delay { font-size:.75rem; min-width:50px; text-align:right; font-weight:500; }
.node-delay.fast { color:#4ade80; }
.node-delay.medium { color:#fbbf24; }
.node-delay.slow { color:#f87171; }
.node-delay.timeout { color:#475569; }
/* Tools panel */
.tool-section { background:#1e293b; border-radius:10px; border:1px solid #334155; padding:14px; margin-bottom:10px; }
.tool-title { font-size:.9rem; font-weight:600; margin-bottom:10px; display:flex; align-items:center; gap:6px; }
.tool-row { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
.tool-input { flex:1; padding:8px 12px; border:1px solid #334155; border-radius:6px; background:#0f172a; color:#e2e8f0; font-size:.82rem; outline:none; }
.tool-input:focus { border-color:#60a5fa; }
.diag-item { display:flex; align-items:center; gap:8px; padding:5px 0; font-size:.82rem; }
.diag-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.diag-dot.pass { background:#4ade80; }
.diag-dot.fail { background:#f87171; }
.diag-dot.skip { background:#475569; }
.diag-name { min-width:120px; color:#94a3b8; }
.diag-detail { color:#e2e8f0; }
.link-card { display:inline-flex; align-items:center; gap:6px; padding:8px 14px; background:#334155; border-radius:8px; color:#60a5fa; text-decoration:none; font-size:.82rem; font-weight:500; transition:.2s; margin-right:8px; margin-bottom:6px; }
.link-card:hover { background:#475569; transform:translateY(-1px); }

/* Toast */
#toast { position:fixed; top:20px; right:20px; z-index:9999; display:flex; flex-direction:column; gap:8px; }
.toast-msg { padding:12px 20px; border-radius:10px; font-size:0.85rem; font-weight:500; animation:slideIn 0.3s ease; max-width:360px; box-shadow:0 4px 20px rgba(0,0,0,0.4); }
.toast-msg.ok { background:#065f46; color:#a7f3d0; border:1px solid #059669; }
.toast-msg.err { background:#7f1d1d; color:#fca5a5; border:1px solid #dc2626; }
.toast-msg.info { background:#1e3a5f; color:#93c5fd; border:1px solid #2563eb; }
@keyframes slideIn { from{transform:translateX(100px);opacity:0}to{transform:translateX(0);opacity:1} }

/* Status bar */
.status-bar { display:flex; gap:12px; margin-bottom:20px; flex-wrap:wrap; }
.status-card { flex:1; min-width:140px; background:#1e293b; border-radius:12px; padding:14px; border:1px solid #334155; transition:border-color 0.3s; }
.status-card.active { border-color:#059669; }
.status-card .label { font-size:0.75rem; color:#94a3b8; text-transform:uppercase; letter-spacing:1px; }
.status-card .value { font-size:1.1rem; font-weight:600; margin-top:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.status-card .value.long { font-size:0.85rem; }
.status-card .value.on { color:#4ade80; }
.status-card .value.off { color:#f87171; }
.status-card .value.warn { color:#fbbf24; }

/* Quick actions - prominent */
.quick-actions { display:flex; gap:12px; margin-bottom:16px; }
.btn-hero { flex:1; padding:16px; border:none; border-radius:12px; font-size:1rem; font-weight:700; cursor:pointer; transition:all 0.2s; text-align:center; letter-spacing:1px; }
.btn-hero:hover { transform:translateY(-2px); filter:brightness(1.15); }
.btn-hero:active { transform:translateY(0); }
.btn-hero:disabled { opacity:0.5; cursor:not-allowed; transform:none; }
.btn-hero.on { background:linear-gradient(135deg,#059669,#10b981); color:white; box-shadow:0 4px 15px rgba(5,150,105,0.4); }
.btn-hero.off { background:linear-gradient(135deg,#dc2626,#ef4444); color:white; box-shadow:0 4px 15px rgba(220,38,38,0.4); }

/* Secondary actions */
.actions { display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }
.btn { padding:8px 14px; border:none; border-radius:8px; font-size:0.8rem; font-weight:600; cursor:pointer; transition:all 0.2s; display:inline-flex; align-items:center; gap:5px; }
.btn:hover { transform:translateY(-1px); filter:brightness(1.1); }
.btn:active { transform:translateY(0); }
.btn:disabled { opacity:0.5; cursor:not-allowed; transform:none; }
.btn-blue { background:#2563eb; color:white; }
.btn-gray { background:#475569; color:white; }
.btn-amber { background:#d97706; color:white; }
.btn-green { background:#059669; color:white; }
.btn-red { background:#dc2626; color:white; }
.spinner { display:inline-block; width:14px; height:14px; border:2px solid rgba(255,255,255,0.3); border-top-color:white; border-radius:50%; animation:spin 0.6s linear infinite; }
@keyframes spin { to{transform:rotate(360deg)} }

/* Toggle switch */
.toggle-row { display:flex; align-items:center; justify-content:space-between; padding:10px 16px; background:#1e293b; border-radius:8px; margin-bottom:8px; border:1px solid #334155; transition:border-color 0.3s; }
.toggle-row.active { border-color:#059669; }
.toggle-row .info { display:flex; align-items:center; gap:10px; }
.toggle-row .info .name { font-weight:500; }
.toggle-row .info .detail { font-size:0.75rem; color:#94a3b8; }
.toggle { position:relative; width:44px; height:24px; cursor:pointer; flex-shrink:0; }
.toggle input { display:none; }
.toggle .slider { position:absolute; inset:0; background:#475569; border-radius:12px; transition:0.3s; }
.toggle .slider:before { content:''; position:absolute; width:18px; height:18px; left:3px; bottom:3px; background:white; border-radius:50%; transition:0.3s; }
.toggle input:checked + .slider { background:#059669; }
.toggle input:checked + .slider:before { transform:translateX(20px); }

/* Category */
.category { margin-bottom:12px; }
.cat-header { display:flex; align-items:center; gap:8px; padding:10px 0; cursor:pointer; user-select:none; }
.cat-header:hover { opacity:0.85; }
.cat-header .chevron { color:#64748b; font-size:0.7rem; transition:transform 0.2s; width:16px; }
.cat-header .chevron.open { transform:rotate(90deg); }
.cat-header .icon { font-size:1.2rem; }
.cat-header .title { font-size:0.95rem; font-weight:600; }
.cat-header .badge { font-size:0.65rem; padding:2px 7px; border-radius:10px; font-weight:500; }
.cat-header .badge.vpn { background:#059669; color:white; }
.cat-header .badge.direct { background:#475569; color:#94a3b8; }
.cat-header .count { font-size:0.7rem; color:#64748b; }
.cat-header .reason { font-size:0.7rem; color:#64748b; margin-left:auto; }
.cat-body { padding-left:8px; overflow:hidden; transition:max-height 0.3s ease; }

/* App row */
.app-row { display:flex; align-items:center; padding:7px 12px; border-radius:6px; margin-bottom:3px; font-size:0.82rem; gap:8px; }
.app-row.running { background:#1e293b; }
.app-row.stopped { background:transparent; opacity:0.55; }
.app-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.app-dot.on { background:#4ade80; }
.app-dot.off { background:#475569; }
.app-name { flex:1; }
.app-pids { font-size:0.68rem; color:#64748b; }
.app-window { font-size:0.68rem; color:#64748b; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

/* Connectivity */
.conn-bar { display:flex; gap:14px; margin-top:16px; padding:14px; background:#1e293b; border-radius:12px; border:1px solid #334155; flex-wrap:wrap; align-items:center; }
.conn-item { display:flex; align-items:center; gap:6px; font-size:0.85rem; }
.conn-dot { width:10px; height:10px; border-radius:50%; transition:background 0.3s; }
.conn-dot.ok { background:#4ade80; box-shadow:0 0 6px rgba(74,222,128,0.5); }
.conn-dot.fail { background:#f87171; box-shadow:0 0 6px rgba(248,113,113,0.5); }
.conn-dot.unknown { background:#475569; }
.conn-dot.loading { background:#fbbf24; animation:pulse 1s infinite; }
@keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.3} }

.footer { text-align:center; margin-top:20px; font-size:0.7rem; color:#475569; }

/* Custom confirm modal */
.modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.6); z-index:9998; display:flex; align-items:center; justify-content:center; animation:fadeIn 0.2s; }
.modal-box { background:#1e293b; border:1px solid #334155; border-radius:14px; padding:28px; max-width:360px; text-align:center; box-shadow:0 8px 30px rgba(0,0,0,0.5); }
.modal-box p { margin-bottom:20px; font-size:0.95rem; }
.modal-box .modal-actions { display:flex; gap:10px; justify-content:center; }
.modal-box .modal-btn { padding:10px 24px; border:none; border-radius:8px; font-weight:600; cursor:pointer; font-size:0.85rem; }
.modal-box .modal-btn.yes { background:#dc2626; color:white; }
.modal-box .modal-btn.no { background:#475569; color:white; }
@keyframes fadeIn { from{opacity:0}to{opacity:1} }

/* Toggle loading */
.toggle.loading .slider { background:#fbbf24 !important; }
.toggle.loading .slider:before { animation:spin 0.6s linear infinite; }

/* Per-app route button */
.route-btn { padding:2px 8px; border:none; border-radius:4px; font-size:0.68rem; font-weight:600; cursor:pointer; transition:all 0.2s; letter-spacing:0.5px; flex-shrink:0; }
.route-btn.proxy { background:#059669; color:white; }
.route-btn.direct { background:#475569; color:#94a3b8; }
.route-btn:hover { filter:brightness(1.2); transform:scale(1.05); }
.route-btn:disabled { opacity:0.5; cursor:wait; }

/* Uncategorized processes */
.uncat-panel { margin-top:16px; background:#1e293b; border-radius:12px; border:1px solid #334155; overflow:hidden; }
.uncat-header { display:flex; align-items:center; justify-content:space-between; padding:12px 16px; cursor:pointer; user-select:none; }
.uncat-header:hover { opacity:0.85; }
.uncat-header .title { font-size:0.9rem; font-weight:600; display:flex; align-items:center; gap:8px; }
.uncat-header .count { font-size:0.7rem; color:#94a3b8; }
.uncat-body { max-height:300px; overflow-y:auto; }
.uncat-row { display:flex; align-items:center; padding:6px 16px; font-size:0.78rem; gap:8px; border-top:1px solid #1a2332; }
.uncat-row:hover { background:#263548; }
.uncat-name { flex:1; color:#e2e8f0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uncat-pids { font-size:0.68rem; color:#64748b; min-width:60px; }
.uncat-add { padding:2px 8px; border:none; border-radius:4px; font-size:0.65rem; font-weight:600; cursor:pointer; transition:all 0.2s; }
.uncat-add.vpn { background:#1d4ed8; color:white; }
.uncat-add.direct { background:#475569; color:#94a3b8; }
.uncat-add:hover { filter:brightness(1.2); }
.uncat-configured { font-size:0.65rem; padding:2px 6px; border-radius:3px; background:#334155; color:#94a3b8; }

/* Connections panel */
.conn-panel { margin-top:16px; background:#1e293b; border-radius:12px; border:1px solid #334155; overflow:hidden; }
.conn-header { display:flex; align-items:center; justify-content:space-between; padding:12px 16px; cursor:pointer; user-select:none; }
.conn-header:hover { opacity:0.85; }
.conn-header .title { font-size:0.9rem; font-weight:600; display:flex; align-items:center; gap:8px; }
.conn-header .stats { font-size:0.75rem; color:#94a3b8; display:flex; gap:12px; }
.conn-header .stats .up { color:#60a5fa; }
.conn-header .stats .dn { color:#4ade80; }
.conn-list { max-height:300px; overflow-y:auto; }
.conn-row { display:flex; align-items:center; padding:6px 16px; font-size:0.75rem; gap:8px; border-top:1px solid #1a2332; }
.conn-row:hover { background:#263548; }
.conn-proc { color:#fbbf24; min-width:80px; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.conn-host { flex:1; color:#e2e8f0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.conn-chain { color:#94a3b8; font-size:0.68rem; min-width:60px; text-align:right; }
.conn-traffic { color:#64748b; font-size:0.68rem; min-width:70px; text-align:right; }
.conn-close { background:none; border:none; color:#ef4444; cursor:pointer; font-size:0.8rem; padding:0 4px; opacity:0.6; }
.conn-close:hover { opacity:1; }

/* Traffic bar */
.traffic-bar { display:flex; gap:20px; justify-content:center; padding:10px; background:#1e293b; border-radius:8px; margin:10px 0; border:1px solid #334155; }
.traffic-item { display:flex; align-items:center; gap:6px; }
.traffic-label { color:#94a3b8; font-size:0.8rem; }
.traffic-val { color:#60a5fa; font-size:1rem; font-weight:600; font-family:'Cascadia Code',monospace; }

/* Rule rows */
.rule-row { display:flex; align-items:center; gap:8px; padding:6px 12px; border-bottom:1px solid #1e293b; font-size:0.75rem; }
.rule-row:hover { background:#1e293b; }
.rule-idx { color:#475569; min-width:32px; text-align:right; font-size:0.65rem; }
.rule-type { color:#a78bfa; min-width:100px; font-weight:600; }
.rule-payload { flex:1; color:#e2e8f0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.rule-proxy { color:#4ade80; min-width:80px; text-align:right; }

/* Log entries */
.log-entry { padding:2px 0; border-bottom:1px solid #1e293b22; }
.log-time { color:#475569; }
.log-info { color:#60a5fa; }
.log-warning { color:#fbbf24; }
.log-error { color:#ef4444; }
.log-debug { color:#94a3b8; }
/* Speed chart */
.speed-chart { display:flex; align-items:flex-end; gap:1px; height:60px; background:#0f172a; border-radius:8px; padding:4px; border:1px solid #334155; overflow:hidden; }
.speed-bar { flex:1; min-width:2px; border-radius:1px 1px 0 0; transition:height 0.3s; }
.speed-bar.up { background:#60a5fa; }
.speed-bar.dn { background:#4ade80; }
.speed-label { display:flex; justify-content:space-between; font-size:.7rem; color:#94a3b8; padding:2px 4px; }
.speed-val { font-family:'Cascadia Code',monospace; font-weight:600; }
.speed-val.up { color:#60a5fa; }
.speed-val.dn { color:#4ade80; }
/* Engine info */
.engine-bar { display:flex; gap:12px; flex-wrap:wrap; padding:8px 12px; background:#1e293b; border-radius:8px; margin:8px 0; border:1px solid #334155; font-size:.75rem; color:#94a3b8; }
.engine-bar span { white-space:nowrap; }
.engine-bar .val { color:#e2e8f0; font-weight:500; }
/* Connection search */
.conn-search { width:100%; padding:6px 12px; background:#0f172a; color:#e2e8f0; border:1px solid #334155; border-radius:6px; font-size:.8rem; margin-bottom:8px; outline:none; }
.conn-search:focus { border-color:#60a5fa; }
/* Provider cards */
.prov-card { display:flex; align-items:center; justify-content:space-between; padding:8px 14px; background:#1e293b; border-radius:8px; margin-bottom:6px; border:1px solid #334155; }
.prov-info { flex:1; }
.prov-name { color:#e2e8f0; font-weight:600; font-size:.85rem; }
.prov-detail { color:#64748b; font-size:.7rem; margin-top:2px; }
.prov-btn { background:#1e40af; color:#e2e8f0; border:none; padding:4px 12px; border-radius:6px; cursor:pointer; font-size:.75rem; }
.prov-btn:hover { background:#2563eb; }

/* Mode switching bar */
.mode-bar { display:flex; gap:4px; margin-bottom:14px; background:#1e293b; border-radius:10px; padding:3px; border:1px solid #334155; }
.mode-btn { flex:1; padding:10px 8px; border:none; border-radius:8px; font-size:0.85rem; font-weight:600; cursor:pointer; background:transparent; color:#94a3b8; transition:.2s; text-align:center; }
.mode-btn:hover { color:#e2e8f0; background:#263548; }
.mode-btn.active { background:#334155; color:#60a5fa; box-shadow:0 2px 8px rgba(0,0,0,.3); }
.mode-btn .mode-icon { font-size:1rem; margin-right:4px; }

/* Node card grid */
.node-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; padding:10px; }
@media(max-width:600px) { .node-grid { grid-template-columns:1fr; } }
.node-card { background:#0f172a; border:1px solid #334155; border-radius:10px; padding:10px 12px; cursor:pointer; transition:all .2s; position:relative; border-left:3px solid transparent; }
.node-card:hover { background:#1a2744; border-color:#475569; transform:translateY(-1px); }
.node-card.selected { background:#1e3a5f; border-left-color:#60a5fa; border-color:#3b82f6; }
.node-card .nc-top { display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; }
.node-card .nc-name { font-size:0.88rem; font-weight:600; color:#e2e8f0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.node-card .nc-check { padding:3px 10px; border:1px solid #475569; border-radius:6px; background:transparent; color:#94a3b8; font-size:0.72rem; font-weight:500; cursor:pointer; transition:.2s; flex-shrink:0; }
.node-card .nc-check:hover { border-color:#60a5fa; color:#60a5fa; background:#1e3a5f; }
.node-card .nc-check.testing { color:#fbbf24; border-color:#fbbf24; }
.node-card .nc-bottom { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.nc-badge { font-size:0.62rem; padding:2px 6px; border-radius:4px; font-weight:600; letter-spacing:.3px; }
.nc-badge.proto { background:#334155; color:#94a3b8; }
.nc-badge.proto-trojan { background:#7c3aed20; color:#a78bfa; border:1px solid #7c3aed40; }
.nc-badge.proto-vmess { background:#2563eb20; color:#60a5fa; border:1px solid #2563eb40; }
.nc-badge.proto-ss { background:#059669; color:white; }
.nc-badge.proto-ssr { background:#d97706; color:white; }
.nc-badge.proto-vless { background:#0891b2; color:white; }
.nc-badge.proto-hysteria { background:#db2777; color:white; }
.nc-badge.feat { background:#475569; color:#cbd5e1; }
.nc-badge.feat-udp { background:#065f4620; color:#34d399; border:1px solid #065f4640; }
.nc-badge.feat-tfo { background:#92400e20; color:#fbbf24; border:1px solid #92400e40; }
.nc-delay { font-size:0.75rem; font-weight:600; margin-left:auto; font-family:'Cascadia Code',monospace; }
.nc-delay.fast { color:#4ade80; }
.nc-delay.medium { color:#fbbf24; }
.nc-delay.slow { color:#f87171; }
.nc-delay.timeout { color:#475569; }

/* Enhanced group header */
.pg-header-v2 { display:flex; align-items:center; padding:12px 14px; cursor:pointer; gap:10px; }
.pg-header-v2:hover { opacity:.85; }
.pg-header-v2 .pg-icon { font-size:1.1rem; }
.pg-header-v2 .pg-info { flex:1; }
.pg-header-v2 .pg-name { font-weight:600; font-size:.92rem; }
.pg-header-v2 .pg-sub { font-size:.7rem; color:#64748b; margin-top:2px; }
.pg-header-v2 .pg-actions { display:flex; gap:6px; align-items:center; }
.pg-action-btn { background:none; border:1px solid #334155; border-radius:6px; padding:4px 8px; cursor:pointer; color:#94a3b8; font-size:.75rem; transition:.2s; }
.pg-action-btn:hover { border-color:#60a5fa; color:#60a5fa; background:#1e3a5f; }
.pg-action-btn.active { border-color:#4ade80; color:#4ade80; }

/* Node sorting/filter bar */
.node-toolbar { display:flex; align-items:center; gap:8px; padding:8px 14px; border-top:1px solid #334155; background:#1a2332; }
.node-toolbar select { background:#0f172a; color:#e2e8f0; border:1px solid #334155; border-radius:6px; padding:4px 8px; font-size:.75rem; outline:none; cursor:pointer; }
.node-toolbar select:focus { border-color:#60a5fa; }
.node-toolbar .node-count { font-size:.72rem; color:#64748b; margin-left:auto; }
.node-search { flex:1; max-width:200px; padding:4px 10px; background:#0f172a; color:#e2e8f0; border:1px solid #334155; border-radius:6px; font-size:.75rem; outline:none; }
.node-search:focus { border-color:#60a5fa; }
</style>
</head>
<body>
<div id="toast"></div>
<div class="container">
    <h1>VPN Manager</h1>
    <p class="subtitle">按应用智能路由 · Mihomo 内核 · 进程级精确匹配 · v4.0</p>

    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('overview')">&#9889; 概览</button>
        <button class="tab-btn" onclick="switchTab('apps')">&#128187; 应用</button>
        <button class="tab-btn" onclick="switchTab('nodes')">&#127760; 节点</button>
        <button class="tab-btn" onclick="switchTab('rules')">&#128220; 规则</button>
        <button class="tab-btn" onclick="switchTab('conns')">&#128279; 连接</button>
        <button class="tab-btn" onclick="switchTab('logs')">&#128196; 日志</button>
        <button class="tab-btn" onclick="switchTab('tools')">&#128295; 工具</button>
    </div>

    <div class="tab-pane active" id="pane-overview">
    <div class="status-bar" id="statusBar">
        <div class="status-card" id="scClash"><div class="label">代理引擎</div><div class="value" id="stClash">...</div></div>
        <div class="status-card" id="scSysProxy"><div class="label">系统代理</div><div class="value" id="stSysProxy">...</div></div>
        <div class="status-card" id="scGit"><div class="label">Git代理</div><div class="value" id="stGit">...</div></div>
        <div class="status-card" id="scEnv"><div class="label">环境变量</div><div class="value" id="stEnv">...</div></div>
    </div>

    <div class="quick-actions">
        <button class="btn-hero on" id="btnQuickOn" onclick="quickOn()">&#9889; 一键开启</button>
        <button class="btn-hero off" id="btnQuickOff" onclick="quickOff()">&#9632; 一键关闭</button>
    </div>

    <div class="actions">
        <button class="btn btn-green" onclick="clashStart()" id="btnStart">&#9654; 启动引擎</button>
        <button class="btn btn-red" onclick="clashStop()" id="btnStop">&#9632; 停止引擎</button>
        <button class="btn btn-blue" onclick="testConn()" id="btnTest">&#128269; 测试连通</button>
        <button class="btn btn-amber" onclick="cleanAll()">&#128465; 彻底清理</button>
        <button class="btn btn-gray" onclick="refresh()">&#128260; 刷新</button>
    </div>

    <div class="toggle-row" id="trSys">
        <div class="info"><div class="name">系统代理</div><div class="detail">浏览器/大部分应用自动走VPN (含bypass列表)</div></div>
        <label class="toggle"><input type="checkbox" id="tglSysProxy" onchange="toggleProxy('system',this.checked)"><span class="slider"></span></label>
    </div>
    <div class="toggle-row" id="trGit">
        <div class="info"><div class="name">Git 代理</div><div class="detail">git clone/push/pull 走代理</div></div>
        <label class="toggle"><input type="checkbox" id="tglGit" onchange="toggleProxy('git',this.checked)"><span class="slider"></span></label>
    </div>
    <div class="toggle-row" id="trNpm">
        <div class="info"><div class="name">NPM 代理</div><div class="detail">npm install 走代理</div></div>
        <label class="toggle"><input type="checkbox" id="tglNpm" onchange="toggleProxy('npm',this.checked)"><span class="slider"></span></label>
    </div>
    <div class="toggle-row" id="trTun">
        <div class="info"><div class="name">TUN 模式</div><div class="detail">虚拟网卡全局代理（需管理员权限）</div></div>
        <label class="toggle"><input type="checkbox" id="tglTun" onchange="toggleTun(this.checked)"><span class="slider"></span></label>
    </div>
    <div class="toggle-row" id="trGuard">
        <div class="info"><div class="name">代理守护</div><div class="detail">自动检测并恢复系统代理（防止被其他软件关闭）</div></div>
        <label class="toggle"><input type="checkbox" id="tglGuard" onchange="toggleGuard(this.checked)"><span class="slider"></span></label>
    </div>

    <div class="engine-bar" id="engineBar">
        <span>内核: <span class="val" id="eiVer">-</span></span>
        <span>模式: <span class="val" id="eiMode">-</span></span>
        <span>内存: <span class="val" id="eiMem">-</span></span>
        <span>日志: <span class="val" id="eiLog">-</span></span>
    </div>

    <div style="margin:8px 0">
        <div class="speed-label"><span>&#8593; 上传 <span class="speed-val up" id="spdUp">0 B/s</span></span><span>&#8595; 下载 <span class="speed-val dn" id="spdDn">0 B/s</span></span></div>
        <div style="display:flex;gap:4px;height:64px">
            <div class="speed-chart" id="chartUp" style="flex:1"></div>
            <div class="speed-chart" id="chartDn" style="flex:1"></div>
        </div>
    </div>

    <div class="conn-bar" id="connBar">
        <strong style="font-size:0.85rem;">网络检测:</strong>
        <div class="conn-item"><div class="conn-dot unknown" id="cdGoogle"></div>Google</div>
        <div class="conn-item"><div class="conn-dot unknown" id="cdGithub"></div>GitHub</div>
        <div class="conn-item"><div class="conn-dot unknown" id="cdBaidu"></div>Baidu</div>
    </div>
    </div><!-- /pane-overview -->

    <div class="tab-pane" id="pane-apps">
    <div id="categories"></div>
    <div class="uncat-panel" id="uncatPanel" style="display:none">
        <div class="uncat-header" onclick="toggleUncatPanel()">
            <div class="title">📌 未分类进程 <span class="count" id="uncatCount">(0)</span></div>
        </div>
        <div class="uncat-body" id="uncatBody" style="display:none"></div>
    </div>
    </div><!-- /pane-apps -->

    <div class="tab-pane" id="pane-nodes">
    <div class="mode-bar" id="modeBar">
        <button class="mode-btn" onclick="switchMode('global')" id="modeGlobal"><span class="mode-icon">&#127760;</span> Global</button>
        <button class="mode-btn active" onclick="switchMode('rule')" id="modeRule"><span class="mode-icon">&#128279;</span> Rule</button>
        <button class="mode-btn" onclick="switchMode('direct')" id="modeDirect"><span class="mode-icon">&#10132;</span> Direct</button>
    </div>
    <div class="actions" style="margin-bottom:10px">
        <button class="btn btn-blue" onclick="loadProxies()" id="btnLoadNodes">&#128260; 刷新节点</button>
        <button class="btn btn-amber" onclick="testAllDelays()" id="btnTestAll">&#9201; 全部测速</button>
        <input class="node-search" id="nodeSearchGlobal" placeholder="搜索节点..." oninput="filterNodes()" style="margin-left:auto">
    </div>
    <div id="proxyGroups"><div style="color:#64748b;padding:20px;text-align:center">点击「刷新节点」加载代理组</div></div>
    </div><!-- /pane-nodes -->

    <div class="tab-pane" id="pane-rules">
    <div class="actions" style="margin-bottom:10px">
        <button class="btn btn-blue" onclick="loadRules()">&#128260; 刷新规则</button>
        <span id="ruleCount" style="color:#94a3b8;font-size:.8rem;margin-left:10px"></span>
    </div>
    <div id="rulesList"><div style="color:#64748b;padding:20px;text-align:center">点击「刷新规则」加载</div></div>
    </div><!-- /pane-rules -->

    <div class="tab-pane" id="pane-conns">
    <div class="actions" style="margin-bottom:10px">
        <button class="btn btn-blue" onclick="refreshConns()">&#128260; 刷新</button>
        <button class="btn btn-red" onclick="closeAllConns()">&#128465; 关闭全部</button>
        <span id="connCount2" style="color:#94a3b8;font-size:.8rem;margin-left:10px"></span>
    </div>
    <input class="conn-search" id="connSearch" placeholder="搜索连接（进程名/域名/链路）..." oninput="filterConns()">
    <div class="conn-panel" id="connPanel">
        <div class="conn-header">
            <div class="title">&#128279; 实时连接 <span id="connCount" style="font-size:0.7rem;color:#94a3b8">(0)</span></div>
            <div class="stats"><span class="up" id="connUp">↑ 0 B</span><span class="dn" id="connDn">↓ 0 B</span></div>
        </div>
        <div class="conn-list" id="connList"></div>
    </div>
    </div><!-- /pane-conns -->

    <div class="tab-pane" id="pane-logs">
    <div class="actions" style="margin-bottom:10px">
        <select id="logLevel" style="background:#1e293b;color:#e2e8f0;border:1px solid #334155;padding:4px 8px;border-radius:6px;font-size:.8rem" onchange="startLogStream()">
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
            <option value="debug">Debug</option>
        </select>
        <button class="btn btn-blue" onclick="startLogStream()">&#9654; 开始</button>
        <button class="btn btn-red" onclick="stopLogStream()">&#9632; 停止</button>
        <button class="btn btn-gray" onclick="clearLogs()">&#128465; 清空</button>
        <span id="logStatus" style="color:#94a3b8;font-size:.75rem;margin-left:8px"></span>
    </div>
    <div id="logContainer" style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;max-height:500px;overflow-y:auto;font-family:'Cascadia Code',monospace;font-size:.72rem;line-height:1.5"></div>
    </div><!-- /pane-logs -->

    <div class="tab-pane" id="pane-tools">
    <div class="tool-section">
        <div class="tool-title">&#128269; 一键诊断</div>
        <button class="btn btn-blue" onclick="runDiagnose()" id="btnDiag" style="margin-bottom:10px">开始诊断</button>
        <div id="diagResults"></div>
    </div>
    <div class="tool-section">
        <div class="tool-title">&#127760; DNS 查询</div>
        <div class="tool-row">
            <input class="tool-input" id="dnsInput" placeholder="输入域名，如 google.com">
            <button class="btn btn-blue" onclick="dnsQuery()">查询</button>
        </div>
        <div id="dnsResult" style="font-size:.8rem;margin-top:6px;color:#94a3b8"></div>
    </div>
    <div class="tool-section">
        <div class="tool-title">&#128260; 订阅更新</div>
        <p style="font-size:.8rem;color:#94a3b8;margin-bottom:8px">从订阅源重新生成 clash-config.yaml 并热加载</p>
        <button class="btn btn-amber" onclick="updateSubscription()" id="btnSub">更新订阅配置</button>
        <div id="subResult" style="font-size:.8rem;margin-top:6px"></div>
    </div>
    <div class="tool-section">
        <div class="tool-title">&#128260; 配置管理</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn btn-blue" onclick="reloadConfig()">&#128260; 热重载配置</button>
            <button class="btn btn-gray" onclick="viewConfig()" style="margin-bottom:0">查看配置文件</button>
        </div>
        <pre id="configView" style="display:none;max-height:300px;overflow:auto;background:#0f172a;padding:10px;border-radius:6px;font-size:.72rem;line-height:1.4;border:1px solid #334155;margin-top:8px"></pre>
    </div>
    <div class="tool-section">
        <div class="tool-title">&#128230; 代理提供者</div>
        <button class="btn btn-blue" onclick="loadProxyProviders()" style="margin-bottom:8px">刷新提供者</button>
        <div id="proxyProviders"><div style="color:#64748b;font-size:.8rem">点击刷新加载</div></div>
    </div>
    <div class="tool-section">
        <div class="tool-title">&#128220; 规则提供者</div>
        <button class="btn btn-blue" onclick="loadRuleProviders()" style="margin-bottom:8px">刷新规则集</button>
        <button class="btn btn-amber" onclick="updateAllRuleProviders()" style="margin-bottom:8px">全部更新</button>
        <div id="ruleProviders"><div style="color:#64748b;font-size:.8rem">点击刷新加载</div></div>
    </div>
    <div class="tool-section">
        <div class="tool-title">&#128279; 快捷链接</div>
        <a class="link-card" href="http://127.0.0.1:9097/ui/" target="_blank">&#127912; MetaCubeXD 官方面板</a>
        <a class="link-card" href="http://127.0.0.1:9097" target="_blank">&#128295; Clash API</a>
    </div>
    </div><!-- /pane-tools -->

    <div class="footer" id="footerInfo">VPN Manager v3.5 &middot; Mihomo &middot; Port 7890/9097/9098</div>
</div>

<script>
function toast(msg, type='ok') {
    const d = document.getElementById('toast');
    const el = document.createElement('div');
    el.className = 'toast-msg ' + type;
    el.textContent = msg;
    d.appendChild(el);
    setTimeout(() => { el.style.opacity='0'; el.style.transition='opacity 0.3s'; setTimeout(()=>el.remove(),300); }, 3000);
}

async function api(path, method='GET', body=null) {
    const opts = {method, headers:{'Content-Type':'application/json'}};
    if(body) opts.body = JSON.stringify(body);
    try {
        const r = await fetch(path, opts);
        return r.json();
    } catch(e) {
        toast('接口错误: '+e.message, 'err');
        return null;
    }
}

let collapsed = {};

async function refresh() {
    const d = await api('/api/status');
    if(!d) return;
    // Clash
    const stC = document.getElementById('stClash');
    stC.textContent = d.clash.proxy_port ? '运行中' : '已停止';
    stC.className = 'value ' + (d.clash.proxy_port ? 'on' : 'off');
    document.getElementById('scClash').className = 'status-card' + (d.clash.proxy_port ? ' active' : '');
    // System proxy
    const stS = document.getElementById('stSysProxy');
    stS.textContent = d.system_proxy.enabled ? d.system_proxy.server : '未开启';
    stS.className = 'value ' + (d.system_proxy.enabled ? 'on' : 'off') + (d.system_proxy.server&&d.system_proxy.server.length>12?' long':'');
    document.getElementById('scSysProxy').className = 'status-card' + (d.system_proxy.enabled ? ' active' : '');
    document.getElementById('tglSysProxy').checked = d.system_proxy.enabled;
    document.getElementById('trSys').className = 'toggle-row' + (d.system_proxy.enabled ? ' active' : '');
    // Git
    const stG = document.getElementById('stGit');
    const gitOn = !!d.git_proxy.http;
    stG.textContent = gitOn ? d.git_proxy.http : '未开启';
    stG.className = 'value ' + (gitOn ? 'on' : 'off') + (gitOn&&d.git_proxy.http.length>12?' long':'');
    document.getElementById('scGit').className = 'status-card' + (gitOn ? ' active' : '');
    document.getElementById('tglGit').checked = gitOn;
    document.getElementById('trGit').className = 'toggle-row' + (gitOn ? ' active' : '');
    // Env
    const stE = document.getElementById('stEnv');
    const envOn = !!d.env_proxy.HTTP_PROXY;
    stE.textContent = envOn ? d.env_proxy.HTTP_PROXY : '未开启';
    stE.className = 'value ' + (envOn ? 'warn' : 'off');
    // NPM - independent check
    api('/api/npm/status').then(ns => {
        if(!ns) return;
        document.getElementById('tglNpm').checked = ns.enabled;
        document.getElementById('trNpm').className = 'toggle-row' + (ns.enabled ? ' active' : '');
    });

    // Uncategorized processes
    const uncatPanel = document.getElementById('uncatPanel');
    const uncat = d.uncategorized || [];
    if(uncat.length > 0) {
        uncatPanel.style.display = '';
        document.getElementById('uncatCount').textContent = `(${uncat.length})`;
        const body = document.getElementById('uncatBody');
        body.innerHTML = uncat.map(u=>{
            const pidStr = u.pids.length>3 ? u.pids.slice(0,3).join(',')+'+' +(u.pids.length-3) : u.pids.join(',');
            const safeProc = escHtml(u.process);
            const safeWin = u.window ? escHtml(u.window) : '';
            const procAttr = u.process.replace(/'/g,"\\'");
            if(u.in_config) {
                return `<div class="uncat-row"><div class="app-dot on"></div><span class="uncat-name">${safeProc}</span><span class="uncat-configured">${u.route}</span><span class="uncat-pids">PID: ${pidStr}</span></div>`;
            }
            return `<div class="uncat-row"><div class="app-dot on"></div><span class="uncat-name">${safeProc}${safeWin?' - '+safeWin:''}</span><button class="uncat-add vpn" onclick="addAppRule('${procAttr}','PROXY',this)">+VPN</button><button class="uncat-add direct" onclick="addAppRule('${procAttr}','DIRECT',this)">→直连</button><span class="uncat-pids">PID: ${pidStr}</span></div>`;
        }).join('');
    } else {
        uncatPanel.style.display = 'none';
    }

    // Categories - only rebuild if data changed
    const cats = document.getElementById('categories');
    const catKey = JSON.stringify(d.categories.map(c=>c.apps.map(a=>[a.running,a.pids.length,a.route])));
    if(cats.dataset.key === catKey && cats.children.length > 0) return;
    cats.dataset.key = catKey;
    cats.innerHTML = '';
    for(const cat of d.categories) {
        const running = cat.apps.filter(a=>a.running);
        const total = cat.apps.length;
        const isCollapsed = collapsed[cat.id] === true;
        let html = `<div class="category">
            <div class="cat-header" onclick="toggleCat('${cat.id}',this)">
                <span class="chevron ${isCollapsed?'':'open'}">&#9654;</span>
                <span class="icon">${cat.icon}</span>
                <span class="title">${cat.label}</span>
                <span class="badge ${cat.need_vpn?'vpn':'direct'}">${cat.need_vpn?'VPN':'直连'}</span>
                <span class="count">${running.length}/${total}</span>
                <span class="reason">${cat.reason}</span>
            </div>
            <div class="cat-body" style="${isCollapsed?'display:none':''}">`;
        for(const a of cat.apps) {
            const cls = a.running ? 'running' : 'stopped';
            const dot = a.running ? 'on' : 'off';
            const pidStr = a.pids.length > 3 ? a.pids.slice(0,3).join(',')+'+'+(a.pids.length-3) : a.pids.join(',');
            const pids = pidStr ? 'PID: '+pidStr : '';
            const isProxy = a.route === 'PROXY';
            const routeCls = isProxy ? 'proxy' : 'direct';
            const routeLabel = isProxy ? 'VPN' : '直连';
            const newRoute = isProxy ? 'DIRECT' : 'PROXY';
            html += `<div class="app-row ${cls}">
                <div class="app-dot ${dot}"></div>
                <span class="app-name">${a.display} <small style="color:#64748b">(${a.process})</small></span>
                <button class="route-btn ${routeCls}" onclick="toggleAppRoute('${a.process}','${newRoute}',this)" title="点击切换 ${a.process} 路由">${routeLabel}</button>
                <span class="app-pids">${pids}</span>
            </div>`;
        }
        html += '</div></div>';
        cats.innerHTML += html;
    }
}

function toggleCat(id, el) {
    collapsed[id] = !collapsed[id];
    const body = el.nextElementSibling;
    const chev = el.querySelector('.chevron');
    if(collapsed[id]) { body.style.display='none'; chev.classList.remove('open'); }
    else { body.style.display=''; chev.classList.add('open'); }
}

async function withLoading(btnId, fn) {
    const btn = document.getElementById(btnId);
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> ...';
    try { await fn(); } finally { btn.innerHTML = orig; btn.disabled = false; }
}

async function quickOn() {
    await withLoading('btnQuickOn', async()=>{
        const r = await api('/api/quick-on','POST');
        if(r) toast(r.ok ? 'VPN已开启' : '启动失败: '+r.msg, r.ok?'ok':'err');
        await refresh();
    });
}
async function quickOff() {
    await withLoading('btnQuickOff', async()=>{
        const r = await api('/api/quick-off','POST');
        if(r) toast('代理已关闭', 'info');
        await refresh();
    });
}
async function clashStart() {
    await withLoading('btnStart', async()=>{
        const r = await api('/api/clash/start','POST');
        if(r) toast(r.ok ? '代理引擎已启动' : '启动失败', r.ok?'ok':'err');
        await refresh();
    });
}
async function clashStop() {
    await withLoading('btnStop', async()=>{
        const r = await api('/api/clash/stop','POST');
        if(r) toast('引擎已停止，系统代理已自动关闭', 'info');
        await refresh();
    });
}
async function toggleProxy(type, on) {
    const names = {system:'系统',git:'Git',npm:'NPM'};
    const tgl = document.getElementById('tgl'+(type==='system'?'SysProxy':type==='git'?'Git':'Npm'));
    const label = tgl.closest('.toggle');
    label.classList.add('loading');
    try {
        const r = await api(`/api/proxy/${type}`,'POST',{enable:on});
        if(r) toast(`${names[type]||type}代理 ${on?'已开启':'已关闭'}`, on?'ok':'info');
        await refresh();
    } finally { label.classList.remove('loading'); }
}
function cleanAll() {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `<div class="modal-box"><p>确认清理所有代理设置?<br><small style="color:#94a3b8">系统代理 · Git代理 · NPM代理 · 环境变量</small></p><div class="modal-actions"><button class="modal-btn no" onclick="this.closest('.modal-overlay').remove()">取消</button><button class="modal-btn yes" id="modalConfirm">确认清理</button></div></div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener('click', e => { if(e.target===overlay) overlay.remove(); });
    document.getElementById('modalConfirm').onclick = async () => {
        overlay.remove();
        const r = await api('/api/proxy/clean','POST');
        if(r) toast('全部代理已清理', 'info');
        refresh();
    };
}
async function testConn() {
    await withLoading('btnTest', async()=>{
        ['cdGoogle','cdGithub','cdBaidu'].forEach(id=>{
            document.getElementById(id).className='conn-dot loading';
        });
        const r = await api('/api/connectivity','POST');
        if(!r) return;
        document.getElementById('cdGoogle').className='conn-dot '+(r.google===true?'ok':r.google===false?'fail':'unknown');
        document.getElementById('cdGithub').className='conn-dot '+(r.github===true?'ok':r.github===false?'fail':'unknown');
        document.getElementById('cdBaidu').className='conn-dot '+(r.baidu===true?'ok':r.baidu===false?'fail':'unknown');
        const ok = [r.google,r.github,r.baidu].filter(v=>v===true).length;
        toast(`网络检测: ${ok}/3 通过`, ok===3?'ok':ok>0?'info':'err');
    });
}

async function toggleAppRoute(process, newRoute, btn) {
    btn.disabled = true;
    btn.textContent = '...';
    try {
        const r = await api('/api/app/route','POST',{process, route:newRoute});
        if(r&&r.ok) toast(`${process} → ${newRoute==='PROXY'?'VPN代理':'直连'}`, newRoute==='PROXY'?'ok':'info');
        else toast('切换失败: '+(r?r.msg:''), 'err');
        await refresh();
    } finally { btn.disabled = false; }
}

let connOpen = false;
function toggleConnPanel() {
    connOpen = !connOpen;
    document.getElementById('connList').style.display = connOpen ? '' : 'none';
    if(connOpen) refreshConns();
}

function fmtBytes(b) {
    if(b<1024) return b+'B';
    if(b<1048576) return (b/1024).toFixed(1)+'K';
    if(b<1073741824) return (b/1048576).toFixed(1)+'M';
    return (b/1073741824).toFixed(2)+'G';
}

function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
async function refreshConns() {
    const d = await api('/api/connections');
    if(!d) return;
    document.getElementById('connCount').textContent = `(${d.connections.length})`;
    document.getElementById('connUp').textContent = '↑ '+fmtBytes(d.upload);
    document.getElementById('connDn').textContent = '↓ '+fmtBytes(d.download);
    const list = document.getElementById('connList');
    if(!connOpen) return;
    const cnt2 = document.getElementById('connCount2');
    if(cnt2) cnt2.textContent = `${d.connections.length} 个活跃连接`;
    list.innerHTML = d.connections.length === 0 ? '<div style="padding:12px 16px;color:#64748b;font-size:0.8rem">无活跃连接</div>' :
        d.connections.map(c=>`<div class="conn-row">
            <span class="conn-proc" title="${escHtml(c.process)}">${escHtml(c.process)||'?'}</span>
            <span class="conn-host" title="${escHtml(c.host)}:${c.port}">${escHtml(c.host)}${c.port?':'+c.port:''}</span>
            <span class="conn-chain">${escHtml(c.chain)}</span>
            <span class="conn-traffic">↑${fmtBytes(c.ul)} ↓${fmtBytes(c.dl)}</span>
            <button class="conn-close" title="关闭" onclick="closeConn('${c.id}')">&#10005;</button>
        </div>`).join('');
    filterConns();
}

let uncatOpen = false;
function toggleUncatPanel() {
    uncatOpen = !uncatOpen;
    document.getElementById('uncatBody').style.display = uncatOpen ? '' : 'none';
}
async function addAppRule(process, route, btn) {
    btn.disabled = true;
    btn.textContent = '...';
    const r = await api('/api/app/add','POST',{process, route});
    if(r&&r.ok) toast(r.msg, 'ok');
    else toast('添加失败', 'err');
    await refresh();
}

// ===== Tab switching =====
let currentTab = 'overview';
function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('pane-'+tab).classList.add('active');
    document.querySelectorAll('.tab-btn').forEach(b => {
        if(b.textContent.includes({overview:'概览',apps:'应用',nodes:'节点',rules:'规则',conns:'连接',logs:'日志',tools:'工具'}[tab]||'')) b.classList.add('active');
    });
    if(tab==='nodes') loadProxies();
    if(tab==='conns') { connOpen=true; refreshConns(); }
    if(tab==='apps') refresh();
    if(tab==='rules') loadRules();
    if(tab==='logs') startLogStream();
}

// ===== Mode switching =====
let currentMode = 'rule';
async function loadMode() {
    const d = await api('/api/mode');
    if(d&&d.ok) { currentMode = d.mode; updateModeUI(); }
}
function updateModeUI() {
    ['global','rule','direct'].forEach(m => {
        const btn = document.getElementById('mode'+m.charAt(0).toUpperCase()+m.slice(1));
        if(btn) btn.classList.toggle('active', m===currentMode);
    });
    const modeEl = document.getElementById('eiMode');
    if(modeEl) modeEl.textContent = currentMode;
}
async function switchMode(mode) {
    const d = await api('/api/mode','POST',{mode});
    if(d&&d.ok) { currentMode = mode; updateModeUI(); toast(d.msg,'ok'); }
    else toast('模式切换失败','err');
}

// ===== Proxy nodes =====
let proxyData = [];
let nodeSortBy = 'default';
let expandedGroups = new Set();

async function loadProxies() {
    const el = document.getElementById('proxyGroups');
    el.innerHTML = '<div style="color:#64748b;padding:20px;text-align:center"><span class="spinner"></span> 加载中...</div>';
    const [pd, md] = await Promise.all([api('/api/proxies'), api('/api/mode')]);
    if(!pd || !pd.groups.length) { el.innerHTML = '<div style="color:#64748b;padding:20px;text-align:center">无代理组（引擎未运行？）</div>'; return; }
    proxyData = pd.groups;
    if(md&&md.ok) { currentMode = md.mode; updateModeUI(); }
    renderProxies();
}

function protoBadgeClass(type) {
    const t = (type||'').toLowerCase();
    if(t==='trojan') return 'proto-trojan';
    if(t==='vmess') return 'proto-vmess';
    if(t==='vless') return 'proto-vless';
    if(t.includes('hysteria')) return 'proto-hysteria';
    if(t==='ss'||t==='shadowsocks') return 'proto-ss';
    if(t==='ssr') return 'proto-ssr';
    return 'proto';
}

function groupIcon(type) {
    if(type==='Selector') return '&#128279;';
    if(type==='URLTest') return '&#9201;';
    if(type==='Fallback') return '&#128737;';
    if(type==='LoadBalance') return '&#9878;';
    return '&#128279;';
}

function sortNodes(nodes) {
    if(nodeSortBy==='delay') return [...nodes].sort((a,b)=>{
        const da=a.delay>0?a.delay:99999, db=b.delay>0?b.delay:99999;
        return da-db;
    });
    if(nodeSortBy==='name') return [...nodes].sort((a,b)=>a.name.localeCompare(b.name));
    if(nodeSortBy==='type') return [...nodes].sort((a,b)=>(a.type||'').localeCompare(b.type||''));
    return nodes;
}

function filterNodes() {
    const q = (document.getElementById('nodeSearchGlobal')||{}).value||'';
    renderProxies(q.trim().toLowerCase());
}

function renderProxies(filter) {
    const el = document.getElementById('proxyGroups');
    el.innerHTML = proxyData.map(g => {
        const isSelector = g.type === 'Selector';
        const expanded = expandedGroups.has(g.name);
        let nodes = sortNodes(g.nodes);
        if(filter) nodes = nodes.filter(n => n.name.toLowerCase().includes(filter) || (n.type||'').toLowerCase().includes(filter));
        const nodeCount = g.nodes.length;
        const aliveCount = g.nodes.filter(n=>n.delay>0).length;

        return `<div class="proxy-group">
            <div class="pg-header-v2" onclick="togglePG2('${esc(g.name)}')">
                <span class="pg-icon">${groupIcon(g.type)}</span>
                <div class="pg-info">
                    <div class="pg-name">${escHtml(g.name)} <span class="pg-type">${g.type}</span></div>
                    <div class="pg-sub">${g.now ? escHtml(g.now) : '-'} · ${aliveCount}/${nodeCount} 可用</div>
                </div>
                <div class="pg-actions">
                    <button class="pg-action-btn" onclick="event.stopPropagation();testGroupDelay('${esc(g.name)}')" title="测速全组">&#9201;</button>
                    <button class="pg-action-btn" onclick="event.stopPropagation();togglePG2('${esc(g.name)}')" title="展开/收起">${expanded?'&#9650;':'&#9660;'}</button>
                </div>
            </div>
            ${expanded ? `<div class="node-toolbar">
                <select onchange="nodeSortBy=this.value;renderProxies()">
                    <option value="default"${nodeSortBy==='default'?' selected':''}>默认排序</option>
                    <option value="delay"${nodeSortBy==='delay'?' selected':''}>延迟排序</option>
                    <option value="name"${nodeSortBy==='name'?' selected':''}>名称排序</option>
                    <option value="type"${nodeSortBy==='type'?' selected':''}>类型排序</option>
                </select>
                <span class="node-count">${nodes.length} 节点</span>
            </div>
            <div class="node-grid">
                ${nodes.map(n => {
                    const sel = n.name === g.now ? ' selected' : '';
                    const dc = delayClass(n.delay);
                    const dl = n.delay > 0 ? n.delay+'ms' : (n.delay === 0 ? '-' : 'timeout');
                    const click = isSelector ? ` onclick="selectNode('${esc(g.name)}','${esc(n.name)}')"` : '';
                    const pbc = protoBadgeClass(n.type);
                    return `<div class="node-card${sel}"${click}>
                        <div class="nc-top">
                            <span class="nc-name">${escHtml(n.name)}</span>
                            <button class="nc-check" id="ck-${css(n.name)}" onclick="event.stopPropagation();checkNode('${esc(n.name)}','${esc(g.name)}')">Check</button>
                        </div>
                        <div class="nc-bottom">
                            <span class="nc-badge ${pbc}">${escHtml(n.type)}</span>
                            ${n.udp?'<span class="nc-badge feat-udp">UDP</span>':''}
                            ${n.tfo?'<span class="nc-badge feat-tfo">TFO</span>':''}
                            <span class="nc-delay ${dc}" id="nd-${css(n.name)}">${dl}</span>
                        </div>
                    </div>`;
                }).join('')}
            </div>` : ''}
        </div>`;
    }).join('');
}

function esc(s){return s.replace(/'/g,"\\'").replace(/"/g,'&quot;')}
function css(s){return s.replace(/[^a-zA-Z0-9]/g,'_')}
function delayClass(d){if(d<=0)return 'timeout';if(d<200)return 'fast';if(d<500)return 'medium';return 'slow'}

function togglePG2(name) {
    if(expandedGroups.has(name)) expandedGroups.delete(name);
    else expandedGroups.add(name);
    renderProxies();
}

async function selectNode(group, name) {
    const r = await api(`/api/proxies/${encodeURIComponent(group)}/select`,'POST',{name});
    if(r&&r.ok) { toast(r.msg,'ok'); loadProxies(); }
    else toast('切换失败','err');
}

async function checkNode(name, group) {
    const ck = document.getElementById('ck-'+css(name));
    if(ck) { ck.textContent = '...'; ck.classList.add('testing'); }
    const r = await api(`/api/proxies/${encodeURIComponent(name)}/delay`,'POST');
    const node = proxyData.flatMap(g=>g.nodes).find(n=>n.name===name);
    if(r&&r.ok) {
        if(node) node.delay = r.delay;
        const el = document.getElementById('nd-'+css(name));
        if(el) { el.textContent = r.delay+'ms'; el.className='nc-delay '+delayClass(r.delay); }
        if(ck) { ck.textContent = 'Check'; ck.classList.remove('testing'); }
    } else {
        if(node) node.delay = -1;
        const el = document.getElementById('nd-'+css(name));
        if(el) { el.textContent = 'timeout'; el.className='nc-delay timeout'; }
        if(ck) { ck.textContent = 'Check'; ck.classList.remove('testing'); }
    }
}

async function testGroupDelay(group) {
    toast('正在测速: '+group,'info');
    const r = await api(`/api/proxies/${encodeURIComponent(group)}/delay-all`,'POST');
    if(r&&r.ok&&r.delays) {
        const g = proxyData.find(g=>g.name===group);
        if(g) {
            for(const [name,delay] of Object.entries(r.delays)) {
                const node = g.nodes.find(n=>n.name===name);
                if(node) node.delay = typeof delay==='number'?delay:0;
                const el = document.getElementById('nd-'+css(name));
                if(el) { el.textContent = typeof delay==='number'&&delay>0?delay+'ms':'timeout'; el.className='nc-delay '+delayClass(typeof delay==='number'?delay:0); }
            }
        }
        toast('测速完成: '+group,'ok');
    } else { toast('测速失败','err'); }
}

async function testAllDelays() {
    if(!proxyData.length) { toast('请先刷新节点','info'); return; }
    await withLoading('btnTestAll', async()=>{
        for(const g of proxyData) {
            await testGroupDelay(g.name);
        }
        toast('全部测速完成','ok');
    });
}

// ===== Diagnostics =====
async function runDiagnose() {
    await withLoading('btnDiag', async()=>{
        document.getElementById('diagResults').innerHTML = '<span class="spinner"></span> 诊断中（约10秒）...';
        const d = await api('/api/diagnose','POST');
        if(!d) { document.getElementById('diagResults').innerHTML = '诊断失败'; return; }
        document.getElementById('diagResults').innerHTML =
            `<div style="font-size:.85rem;font-weight:600;margin-bottom:8px;color:${d.passed===d.total?'#4ade80':'#fbbf24'}">通过 ${d.passed}/${d.total}</div>` +
            d.results.map(r => {
                const cls = r.ok===true?'pass':r.ok===false?'fail':'skip';
                return `<div class="diag-item"><div class="diag-dot ${cls}"></div><span class="diag-name">${r.name}</span><span class="diag-detail">${r.detail}</span></div>`;
            }).join('');
    });
}

// ===== DNS Query =====
async function dnsQuery() {
    const name = document.getElementById('dnsInput').value.trim();
    if(!name) { toast('请输入域名','info'); return; }
    document.getElementById('dnsResult').textContent = '查询中...';
    const d = await api('/api/dns/query','POST',{name, type:'A'});
    if(d&&d.ok) {
        const result = d.result;
        let html = '';
        if(result.Answer) html = result.Answer.map(a=>`<div>${escHtml(a.Name||'')} → <strong>${escHtml(a.data||a.Data||'')}</strong> (TTL:${a.TTL||''})</div>`).join('');
        else html = `<pre style="white-space:pre-wrap">${JSON.stringify(result,null,2)}</pre>`;
        document.getElementById('dnsResult').innerHTML = html;
    } else {
        document.getElementById('dnsResult').textContent = d?d.msg:'查询失败';
    }
}

// ===== Config viewer =====
async function viewConfig() {
    const pre = document.getElementById('configView');
    if(pre.style.display !== 'none') { pre.style.display='none'; return; }
    pre.textContent = '加载中...';
    pre.style.display = '';
    const d = await api('/api/config/view');
    if(d&&d.ok) pre.textContent = d.content;
    else pre.textContent = '加载失败: '+(d?d.msg:'');
}

// ===== Subscription update =====
async function updateSubscription() {
    await withLoading('btnSub', async()=>{
        document.getElementById('subResult').textContent = '更新中...';
        const d = await api('/api/subscription/update','POST');
        if(d&&d.ok) { document.getElementById('subResult').innerHTML = '<span style="color:#4ade80">'+escHtml(d.msg)+'</span>'; toast('订阅更新成功','ok'); }
        else { document.getElementById('subResult').innerHTML = '<span style="color:#f87171">'+escHtml(d?d.msg:'失败')+'</span>'; toast('订阅更新失败','err'); }
    });
}

// ===== TUN toggle =====
async function toggleTun(enable) {
    const r = await api('/api/tun','POST',{enable});
    if(r&&r.ok) toast(r.msg,'ok');
    else { toast('TUN切换失败: '+(r?r.msg:''),'err'); document.getElementById('tglTun').checked=!enable; }
}

// ===== Rules =====
async function loadRules() {
    const el = document.getElementById('rulesList');
    el.innerHTML = '<div style="color:#64748b;padding:20px;text-align:center"><span class="spinner"></span> 加载中...</div>';
    const d = await api('/api/rules');
    if(!d||!d.rules) { el.innerHTML = '<div style="color:#64748b;padding:20px;text-align:center">加载失败</div>'; return; }
    document.getElementById('ruleCount').textContent = `共 ${d.rules.length} 条规则`;
    el.innerHTML = d.rules.slice(0,500).map((r,i)=>`<div class="rule-row">
        <span class="rule-idx">${i+1}</span>
        <span class="rule-type">${r.type||''}</span>
        <span class="rule-payload">${r.payload||''}</span>
        <span class="rule-proxy">${r.proxy||''}</span>
    </div>`).join('');
}

// ===== Close connections =====
async function closeConn(id) {
    const r = await api('/api/connections/close','POST',{id});
    if(r&&r.ok) { toast(r.msg,'ok'); refreshConns(); }
    else toast('关闭失败','err');
}
async function closeAllConns() {
    const r = await api('/api/connections/close-all','POST');
    if(r&&r.ok) { toast(r.msg,'ok'); refreshConns(); }
    else toast('关闭失败','err');
}

// ===== Log streaming via WebSocket =====
let logWS = null;
let logEntries = [];
function startLogStream() {
    stopLogStream();
    const level = document.getElementById('logLevel').value;
    try {
        logWS = new WebSocket(`ws://127.0.0.1:9097/logs?level=${level}`);
        document.getElementById('logStatus').textContent = '⬤ 已连接';
        document.getElementById('logStatus').style.color = '#4ade80';
        logWS.onmessage = (e) => {
            try {
                const d = JSON.parse(e.data);
                const t = new Date().toLocaleTimeString();
                const cls = 'log-'+(d.type||'info').toLowerCase();
                logEntries.push(`<div class="log-entry"><span class="log-time">[${t}]</span> <span class="${cls}">[${(d.type||'INFO').toUpperCase()}]</span> ${escHtml(d.payload||d.message||'')}</div>`);
                if(logEntries.length > 500) logEntries.shift();
                const container = document.getElementById('logContainer');
                container.innerHTML = logEntries.join('');
                container.scrollTop = container.scrollHeight;
            } catch(ex) {}
        };
        logWS.onerror = () => {
            document.getElementById('logStatus').textContent = '⬤ 连接失败';
            document.getElementById('logStatus').style.color = '#ef4444';
        };
        logWS.onclose = () => {
            document.getElementById('logStatus').textContent = '○ 已断开';
            document.getElementById('logStatus').style.color = '#94a3b8';
        };
    } catch(e) {
        document.getElementById('logStatus').textContent = 'WebSocket不可用';
    }
}
function stopLogStream() {
    if(logWS) { logWS.close(); logWS=null; }
}
function clearLogs() {
    logEntries = [];
    document.getElementById('logContainer').innerHTML = '';
}

// ===== Speed chart (rolling history) =====
const CHART_SIZE = 60;
let speedHistory = {up: new Array(CHART_SIZE).fill(0), dn: new Array(CHART_SIZE).fill(0)};
let lastTraffic = {up: 0, dn: 0, ts: Date.now()};

function renderChart(id, data, cls) {
    const el = document.getElementById(id);
    const max = Math.max(...data, 1);
    el.innerHTML = data.map(v => {
        const h = Math.max(1, (v / max) * 56);
        return '<div class="speed-bar '+cls+'" style="height:'+h+'px"></div>';
    }).join('');
}

function fmtSpeed(b) {
    if(b < 1024) return b.toFixed(0)+' B/s';
    if(b < 1048576) return (b/1024).toFixed(1)+' KB/s';
    return (b/1048576).toFixed(2)+' MB/s';
}

async function refreshSpeed() {
    const d = await api('/api/traffic');
    if(!d||!d.ok) return;
    const now = Date.now();
    const dt = (now - lastTraffic.ts) / 1000;
    if(dt > 0 && lastTraffic.ts > 0) {
        const upSpd = Math.max(0, (d.upload - lastTraffic.up) / dt);
        const dnSpd = Math.max(0, (d.download - lastTraffic.dn) / dt);
        speedHistory.up.push(upSpd); speedHistory.up.shift();
        speedHistory.dn.push(dnSpd); speedHistory.dn.shift();
        document.getElementById('spdUp').textContent = fmtSpeed(upSpd);
        document.getElementById('spdDn').textContent = fmtSpeed(dnSpd);
        renderChart('chartUp', speedHistory.up, 'up');
        renderChart('chartDn', speedHistory.dn, 'dn');
    }
    lastTraffic = {up: d.upload, dn: d.download, ts: now};
}

// ===== Engine info =====
async function refreshEngineInfo() {
    const d = await api('/api/engine/info');
    if(!d||!d.ok) return;
    document.getElementById('eiVer').textContent = d.version;
    document.getElementById('eiMode').textContent = d.mode;
    document.getElementById('eiMem').textContent = fmtBytes(d.memory);
    document.getElementById('eiLog').textContent = d.logLevel;
}

// ===== Proxy guard =====
async function toggleGuard(on) {
    const r = await api('/api/proxy/guard','POST',{enable:on});
    if(r&&r.ok) toast(r.msg,'ok');
    else { toast('操作失败','err'); document.getElementById('tglGuard').checked = !on; }
}

async function refreshGuardStatus() {
    const r = await api('/api/proxy/guard');
    if(r&&r.ok) document.getElementById('tglGuard').checked = r.enabled;
}

// ===== Connection filter =====
function filterConns() {
    const q = document.getElementById('connSearch').value.toLowerCase();
    document.querySelectorAll('#connList .conn-row').forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
}

// ===== Config reload =====
async function reloadConfig() {
    const r = await api('/api/config/reload','POST');
    if(r&&r.ok) toast(r.msg,'ok');
    else toast('重载失败: '+(r?r.msg:''),'err');
}

// ===== Proxy providers =====
async function loadProxyProviders() {
    const d = await api('/api/providers/proxies');
    const el = document.getElementById('proxyProviders');
    if(!d||!d.ok) { el.innerHTML='<div style="color:#ef4444">加载失败</div>'; return; }
    const provs = Object.values(d.providers);
    if(!provs.length) { el.innerHTML='<div style="color:#64748b;font-size:.8rem">无代理提供者</div>'; return; }
    el.innerHTML = provs.map(p => {
        const safeName = escHtml(p.name);
        const nameAttr = p.name.replace(/'/g,"\\'");
        return '<div class="prov-card"><div class="prov-info"><div class="prov-name">'+safeName+'</div>' +
        '<div class="prov-detail">'+escHtml(p.vehicleType)+' · '+p.nodeCount+'个节点 · '+(p.updatedAt?new Date(p.updatedAt).toLocaleString():'未更新')+'</div></div>' +
        '<button class="prov-btn" onclick="updateProxyProvider(\''+nameAttr+'\')">更新</button></div>';
    }).join('');
}

async function updateProxyProvider(name) {
    toast('正在更新 '+name+'...','ok');
    const r = await api('/api/providers/proxies/update','POST',{name});
    if(r&&r.ok) { toast(r.msg,'ok'); loadProxyProviders(); }
    else toast('更新失败: '+(r?r.msg:''),'err');
}

// ===== Rule providers =====
async function loadRuleProviders() {
    const d = await api('/api/rules/providers');
    const el = document.getElementById('ruleProviders');
    if(!d||!d.ok) { el.innerHTML='<div style="color:#ef4444">加载失败</div>'; return; }
    const provs = Object.entries(d.providers);
    if(!provs.length) { el.innerHTML='<div style="color:#64748b;font-size:.8rem">无规则提供者</div>'; return; }
    el.innerHTML = provs.map(([name,p]) => {
        const safeName = escHtml(name);
        const nameAttr = name.replace(/'/g,"\\'");
        return '<div class="prov-card"><div class="prov-info"><div class="prov-name">'+safeName+'</div>' +
        '<div class="prov-detail">'+escHtml(p.vehicleType||p.type||'')+' · '+(p.ruleCount||'?')+'条规则 · '+(p.updatedAt?new Date(p.updatedAt).toLocaleString():'未更新')+'</div></div>' +
        '<button class="prov-btn" onclick="updateRuleProvider(\''+nameAttr+'\')">更新</button></div>';
    }).join('');
}

async function updateRuleProvider(name) {
    toast('正在更新 '+name+'...','ok');
    const r = await api('/api/providers/rules/update','POST',{name});
    if(r&&r.ok) { toast(r.msg,'ok'); loadRuleProviders(); }
    else toast('更新失败: '+(r?r.msg:''),'err');
}

async function updateAllRuleProviders() {
    const d = await api('/api/rules/providers');
    if(!d||!d.ok) return;
    const names = Object.keys(d.providers);
    toast('正在更新 '+names.length+' 个规则集...','ok');
    for(const n of names) { await api('/api/providers/rules/update','POST',{name:n}); }
    toast('全部规则集已更新','ok');
    loadRuleProviders();
}

// ===== TUN status on refresh =====
const origRefresh = refresh;
refresh = async function() {
    await origRefresh();
    try {
        const t = await api('/api/tun');
        if(t&&t.ok) document.getElementById('tglTun').checked = t.enabled;
    } catch(e) {}
    refreshGuardStatus();
    refreshEngineInfo();
    loadMode();
};

refresh();
setInterval(refresh, 15000);
setInterval(()=>{ if(currentTab==='conns') refreshConns(); }, 5000);
setInterval(refreshSpeed, 2000);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    port = 9098
    url = f'http://127.0.0.1:{port}'
    no_auto = '--no-auto' in sys.argv
    print(f"VPN Manager v4.0 - 按应用智能路由")
    print(f"目录: {BASE_DIR}")
    print(f"管理面板: {url}")
    print(f"MetaCubeXD: http://127.0.0.1:{API_PORT}/ui/")
    if not no_auto:
        # Auto-start clash-meta if not running
        if not check_port(MIXED_PORT) and os.path.isfile(CLASH_META):
            print("正在启动代理引擎...")
            subprocess.Popen([CLASH_META, '-d', BASE_DIR, '-f', CLASH_CONFIG], creationflags=0x08000000)
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host='127.0.0.1', port=port, debug=False)
