"""
Proxy Sense — Agent 五感代理感知模块
轻量级代理健康检查，供 Windsurf Agent 在终端中调用。

用法:
  python proxy_sense.py                  # 快速状态 (JSON一行)
  python proxy_sense.py --check          # 深度检查 (连通性+延迟)
  python proxy_sense.py --env            # 输出 PowerShell 环境变量设置
  python proxy_sense.py --env bash       # 输出 Bash 环境变量设置
  python proxy_sense.py --fix            # 自动修复 (重启引擎)
"""

import json, os, sys, time, socket, subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
CLASH_META = BASE_DIR / 'clash-meta.exe'
CLASH_CONFIG = BASE_DIR / 'clash-config.yaml'

# Clash Agent 端口 (固定)
MIXED_PORT = 7890
API_PORT = 9097
PROXY_URL = f'http://127.0.0.1:{MIXED_PORT}'
API_SECRET = 'clash-agent-local'


def check_port(port, host='127.0.0.1', timeout=1):
    """TCP 端口探测"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def quick_status():
    """快速状态 — 无网络请求，仅端口探测"""
    proxy_up = check_port(MIXED_PORT)
    api_up = check_port(API_PORT)
    return {
        'proxy': proxy_up,
        'api': api_up,
        'port': MIXED_PORT,
        'url': PROXY_URL if proxy_up else None,
        'status': 'ready' if proxy_up else 'down',
    }


def deep_check():
    """深度检查 — 实际代理连通性 + API状态"""
    import urllib.request, urllib.error

    result = quick_status()

    # API check
    if result['api']:
        try:
            req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}/configs')
            req.add_header('Authorization', f'Bearer {API_SECRET}')
            data = json.loads(urllib.request.urlopen(req, timeout=3).read())
            result['mode'] = data.get('mode', '?')
            result['allow_lan'] = data.get('allow-lan', False)
            result['tun'] = data.get('tun', {}).get('enable', False)
        except Exception:
            result['api_error'] = True

    # Proxy connectivity
    if result['proxy']:
        try:
            proxy_handler = urllib.request.ProxyHandler({
                'http': PROXY_URL, 'https': PROXY_URL
            })
            opener = urllib.request.build_opener(proxy_handler)
            t0 = time.time()
            resp = opener.open('http://www.gstatic.com/generate_204', timeout=8)
            latency = int((time.time() - t0) * 1000)
            result['connectivity'] = resp.status == 204
            result['latency_ms'] = latency
        except Exception:
            result['connectivity'] = False
            result['latency_ms'] = -1

    # Rule providers
    if result['api']:
        try:
            req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}/providers/rules')
            req.add_header('Authorization', f'Bearer {API_SECRET}')
            data = json.loads(urllib.request.urlopen(req, timeout=3).read())
            providers = {}
            for k, v in data.get('providers', {}).items():
                providers[k] = v.get('ruleCount', 0)
            result['rule_providers'] = providers
        except Exception:
            pass

    # Proxies count
    if result['api']:
        try:
            req = urllib.request.Request(f'http://127.0.0.1:{API_PORT}/proxies')
            req.add_header('Authorization', f'Bearer {API_SECRET}')
            data = json.loads(urllib.request.urlopen(req, timeout=3).read())
            proxies = data.get('proxies', {})
            result['proxy_count'] = sum(1 for p in proxies.values()
                                        if isinstance(p, dict) and p.get('type') not in
                                        ('Selector', 'URLTest', 'Fallback', 'LoadBalance', 'Direct', 'Reject', 'Compatible', 'Pass'))
        except Exception:
            pass

    return result


def env_vars(shell='powershell'):
    """输出代理环境变量设置命令"""
    s = quick_status()
    if not s['proxy']:
        print(f'# Clash proxy is DOWN on port {MIXED_PORT}', file=sys.stderr)
        return

    proxy = PROXY_URL
    socks = f'socks5://127.0.0.1:{MIXED_PORT}'

    if shell == 'bash':
        print(f'export http_proxy={proxy}')
        print(f'export https_proxy={proxy}')
        print(f'export all_proxy={socks}')
        print(f'export HTTP_PROXY={proxy}')
        print(f'export HTTPS_PROXY={proxy}')
        print(f'export ALL_PROXY={socks}')
        print(f'export NO_PROXY=localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16')
    else:
        print(f'$env:http_proxy="{proxy}"')
        print(f'$env:https_proxy="{proxy}"')
        print(f'$env:all_proxy="{socks}"')
        print(f'$env:HTTP_PROXY="{proxy}"')
        print(f'$env:HTTPS_PROXY="{proxy}"')
        print(f'$env:ALL_PROXY="{socks}"')
        print(f'$env:NO_PROXY="localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"')


def auto_fix():
    """自动修复 — 重启引擎"""
    s = quick_status()
    if s['proxy']:
        print(json.dumps({'action': 'none', 'reason': 'proxy already running'}))
        return True

    if not CLASH_META.exists():
        print(json.dumps({'action': 'fail', 'reason': 'clash-meta.exe not found'}))
        return False

    if not CLASH_CONFIG.exists():
        print(json.dumps({'action': 'fail', 'reason': 'clash-config.yaml not found'}))
        return False

    # Start clash-meta
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        [str(CLASH_META), '-d', str(BASE_DIR), '-f', str(CLASH_CONFIG)],
        creationflags=CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for startup
    for _ in range(10):
        time.sleep(1)
        if check_port(MIXED_PORT):
            print(json.dumps({'action': 'started', 'port': MIXED_PORT, 'status': 'ready'}))
            return True

    print(json.dumps({'action': 'fail', 'reason': 'timeout waiting for port'}))
    return False


if __name__ == '__main__':
    args = sys.argv[1:]

    if '--check' in args:
        print(json.dumps(deep_check(), ensure_ascii=False))
    elif '--env' in args:
        shell = args[args.index('--env') + 1] if args.index('--env') + 1 < len(args) else 'powershell'
        env_vars(shell)
    elif '--fix' in args:
        auto_fix()
    else:
        print(json.dumps(quick_status()))
