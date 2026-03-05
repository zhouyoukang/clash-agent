"""
Node Aggregator — 免费节点聚合器
从多个 GitHub 公开源抓取免费代理节点，去重+测速+输出 Mihomo YAML

来源 (GitHub 高星项目):
  - freefq/free (39K★)
  - ermaozi/get_subscribe (8.7K★)
  - aiboboxx/clashfree (14K★)
  - peasoft/NoMoreWalls (3K★)
  - anaer/Sub (3.5K★)
  - dongchengjie/airport (386★)

用法:
  python node_aggregator.py                    # 抓取+去重+保存
  python node_aggregator.py --test             # 抓取+去重+测速+保存
  python node_aggregator.py --merge config.yaml # 合并到现有配置
"""

import os, sys, re, json, time, base64, hashlib, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent

# === 免费节点订阅源 (raw 链接) ===
SOURCES = {
    'freefq': {
        'name': 'freefq/free',
        'stars': '39K',
        'urls': [
            'https://raw.githubusercontent.com/freefq/free/master/v2',
        ],
        'format': 'base64',
    },
    'ermaozi': {
        'name': 'ermaozi/get_subscribe',
        'stars': '8.7K',
        'urls': [
            'https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt',
        ],
        'format': 'base64',
    },
    'peasoft': {
        'name': 'peasoft/NoMoreWalls',
        'stars': '3K',
        'urls': [
            'https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list_raw.txt',
        ],
        'format': 'raw_links',
    },
    'aiboboxx': {
        'name': 'aiboboxx/clashfree',
        'stars': '14K',
        'urls': 'dynamic',  # 使用日期命名: clash{YYYYMMDD}.yml
        'format': 'clash_yaml',
    },
}

# 代理设置 (通过本地 Clash 代理访问 GitHub)
PROXY_URL = 'http://127.0.0.1:7890'


def fetch_url(url, use_proxy=True, timeout=20):
    """下载 URL 内容，支持代理"""
    handlers = []
    if use_proxy:
        handlers.append(urllib.request.ProxyHandler({
            'http': PROXY_URL, 'https': PROXY_URL
        }))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'clash-agent/4.0',
        'Accept': '*/*',
    })
    try:
        resp = opener.open(req, timeout=timeout)
        return resp.read()
    except Exception as e:
        # 代理失败时无代理重试
        if use_proxy:
            try:
                return fetch_url(url, use_proxy=False, timeout=timeout)
            except:
                pass
        print(f'  FAIL: {url[:60]}... → {e}')
        return None


def decode_base64_links(data):
    """解码 base64 编码的订阅链接列表"""
    try:
        text = base64.b64decode(data).decode('utf-8', errors='replace')
    except:
        text = data.decode('utf-8', errors='replace') if isinstance(data, bytes) else data
    links = []
    for line in text.strip().splitlines():
        line = line.strip()
        if line and '://' in line:
            links.append(line)
    return links


def parse_clash_yaml(data):
    """从 Clash YAML 中提取代理节点"""
    try:
        import yaml
        text = data.decode('utf-8', errors='replace') if isinstance(data, bytes) else data
        cfg = yaml.safe_load(text)
        return cfg.get('proxies', [])
    except Exception as e:
        print(f'  YAML parse error: {e}')
        return []


def link_to_proxy(link):
    """将 v2ray/trojan/ss 链接转换为 Mihomo proxy dict"""
    link = link.strip()
    if link.startswith('vmess://'):
        return _parse_vmess(link)
    elif link.startswith('trojan://'):
        return _parse_trojan(link)
    elif link.startswith('ss://'):
        return _parse_ss(link)
    elif link.startswith('ssr://'):
        return None  # SSR 已过时，跳过
    return None


def _parse_vmess(link):
    """解析 vmess:// 链接"""
    try:
        raw = link[8:]
        # 补齐 base64 padding
        raw += '=' * (4 - len(raw) % 4) if len(raw) % 4 else ''
        j = json.loads(base64.b64decode(raw).decode('utf-8', errors='replace'))
        name = j.get('ps', j.get('add', 'vmess'))
        return {
            'name': _clean_name(name),
            'type': 'vmess',
            'server': j.get('add', ''),
            'port': int(j.get('port', 443)),
            'uuid': j.get('id', ''),
            'alterId': int(j.get('aid', 0)),
            'cipher': j.get('scy', 'auto'),
            'tls': j.get('tls', '') == 'tls',
            'network': j.get('net', 'tcp'),
            'ws-opts': {'path': j.get('path', '/'), 'headers': {'Host': j.get('host', '')}} if j.get('net') == 'ws' else None,
        }
    except:
        return None


def _parse_trojan(link):
    """解析 trojan:// 链接"""
    try:
        rest = link[9:]
        # trojan://password@host:port?params#name
        m = re.match(r'([^@]+)@([^:]+):(\d+)(?:\?([^#]*))?(?:#(.*))?', rest)
        if not m:
            return None
        password, server, port, params, name = m.groups()
        name = urllib.parse.unquote(name or server)
        return {
            'name': _clean_name(name),
            'type': 'trojan',
            'server': server,
            'port': int(port),
            'password': password,
            'sni': _get_param(params, 'sni', server),
            'skip-cert-verify': True,
        }
    except:
        return None


def _parse_ss(link):
    """解析 ss:// 链接"""
    try:
        rest = link[5:]
        # ss://base64(method:password)@host:port#name
        if '@' in rest:
            encoded, hostpart = rest.split('@', 1)
        else:
            # 全部 base64
            decoded = base64.b64decode(rest.split('#')[0] + '==').decode()
            m = re.match(r'([^:]+):([^@]+)@([^:]+):(\d+)', decoded)
            if not m:
                return None
            return {
                'name': _clean_name(rest.split('#')[-1] if '#' in rest else m.group(3)),
                'type': 'ss',
                'server': m.group(3),
                'port': int(m.group(4)),
                'cipher': m.group(1),
                'password': m.group(2),
            }
        # 解码 method:password
        encoded += '=' * (4 - len(encoded) % 4) if len(encoded) % 4 else ''
        try:
            decoded = base64.b64decode(encoded).decode()
        except:
            decoded = encoded
        method_pass = decoded.split(':', 1) if ':' in decoded else [decoded, '']
        # 解析 host:port#name
        name_part = ''
        if '#' in hostpart:
            hostpart, name_part = hostpart.rsplit('#', 1)
        m2 = re.match(r'([^:]+):(\d+)', hostpart)
        if not m2:
            return None
        return {
            'name': _clean_name(urllib.parse.unquote(name_part) or m2.group(1)),
            'type': 'ss',
            'server': m2.group(1),
            'port': int(m2.group(2)),
            'cipher': method_pass[0],
            'password': method_pass[1] if len(method_pass) > 1 else '',
        }
    except:
        return None


def _get_param(params_str, key, default=''):
    if not params_str:
        return default
    for pair in params_str.split('&'):
        if '=' in pair:
            k, v = pair.split('=', 1)
            if k == key:
                return urllib.parse.unquote(v)
    return default


_emoji_re = re.compile(r'[\U0001F1E0-\U0001F1FF\U0001F300-\U0001F9FF\u2600-\u27BF]+')

def _clean_name(name):
    """清理节点名称"""
    if not name:
        return 'unnamed'
    name = urllib.parse.unquote(str(name))
    name = _emoji_re.sub('', name)
    name = name.strip().lstrip('|').strip()
    name = re.sub(r'\s+', ' ', name)
    return name[:50] if name else 'unnamed'


def proxy_fingerprint(proxy):
    """生成节点指纹用于去重"""
    if isinstance(proxy, dict):
        key = f"{proxy.get('type','')}:{proxy.get('server','')}:{proxy.get('port','')}"
        return hashlib.md5(key.encode()).hexdigest()[:12]
    return None


def test_proxy_delay(proxy, timeout=5):
    """通过 Mihomo API 测试代理延迟 (需要引擎运行)"""
    try:
        name = proxy.get('name', '')
        encoded = urllib.parse.quote(name, safe='')
        url = f'http://127.0.0.1:9097/proxies/{encoded}/delay?timeout={timeout*1000}&url=http://www.gstatic.com/generate_204'
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=timeout+2)
        data = json.loads(resp.read())
        return data.get('delay', -1)
    except:
        return -1


def aggregate(do_test=False):
    """主聚合流程：抓取 → 解析 → 去重 → (测速) → 保存"""
    all_proxies = []
    stats = {}

    print(f'=== Node Aggregator — {len(SOURCES)} 源 ===')
    print(f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()

    for src_id, src in SOURCES.items():
        print(f'[{src["name"]}] ({src["stars"]}★)')
        count = 0
        urls = src['urls']
        # aiboboxx 使用日期命名文件
        if urls == 'dynamic' and src_id == 'aiboboxx':
            today = datetime.now()
            urls = []
            for days_ago in range(0, 3):  # 尝试今天和前2天
                from datetime import timedelta
                d = today - timedelta(days=days_ago)
                urls.append(f'https://raw.githubusercontent.com/aiboboxx/clashfree/main/clash{d.strftime("%Y%m%d")}.yml')
        for url in urls:
            data = fetch_url(url)
            if not data:
                continue

            if src['format'] == 'raw_links':
                # 纯文本链接列表（每行一个 vmess:// trojan:// ss:// 链接）
                text = data.decode('utf-8', errors='replace') if isinstance(data, bytes) else data
                links = [l.strip() for l in text.strip().splitlines() if l.strip() and '://' in l.strip()]
                print(f'  → {len(links)} 条链接')
                for link in links:
                    proxy = link_to_proxy(link)
                    if proxy and proxy.get('server'):
                        proxy = {k: v for k, v in proxy.items() if v is not None}
                        all_proxies.append(proxy)
                        count += 1

            elif src['format'] == 'base64':
                links = decode_base64_links(data)
                print(f'  → {len(links)} 条链接')
                for link in links:
                    proxy = link_to_proxy(link)
                    if proxy and proxy.get('server'):
                        # 清理 None 值
                        proxy = {k: v for k, v in proxy.items() if v is not None}
                        all_proxies.append(proxy)
                        count += 1

            elif src['format'] == 'clash_yaml':
                proxies = parse_clash_yaml(data)
                print(f'  → {len(proxies)} 个节点')
                for p in proxies:
                    if isinstance(p, dict) and p.get('server'):
                        p['name'] = _clean_name(p.get('name', ''))
                        all_proxies.append(p)
                        count += 1

        stats[src_id] = count
        print(f'  有效: {count}')
        print()

    # 去重
    seen = set()
    unique = []
    for p in all_proxies:
        fp = proxy_fingerprint(p)
        if fp and fp not in seen:
            seen.add(fp)
            unique.append(p)
    dup_count = len(all_proxies) - len(unique)
    print(f'合计: {len(all_proxies)} 节点, 去重后: {len(unique)} ({dup_count} 重复)')

    # 测速 (可选)
    if do_test and unique:
        print(f'\n测速中 (前50个)...')
        tested = 0
        alive = 0
        for p in unique[:50]:
            delay = test_proxy_delay(p)
            p['_delay'] = delay
            if delay > 0:
                alive += 1
            tested += 1
            if tested % 10 == 0:
                print(f'  {tested}/50 tested, {alive} alive')
        # 按延迟排序 (有延迟的在前)
        unique.sort(key=lambda p: (p.get('_delay', -1) <= 0, p.get('_delay', 9999)))
        print(f'存活: {alive}/{tested}')

    # 保存
    output = BASE_DIR / 'free-nodes.yaml'
    _save_yaml(unique, output)

    # 保存统计
    report = {
        'timestamp': datetime.now().isoformat(),
        'sources': stats,
        'total_raw': len(all_proxies),
        'total_unique': len(unique),
        'duplicates_removed': dup_count,
    }
    report_file = BASE_DIR / 'free-nodes-report.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f'\n输出: {output} ({len(unique)} 节点)')
    print(f'报告: {report_file}')
    return unique


def _save_yaml(proxies, path):
    """保存为 Mihomo YAML 格式"""
    try:
        import yaml
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump({'proxies': proxies}, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except ImportError:
        # 无 yaml 时手动生成
        lines = ['proxies:']
        for p in proxies:
            # 清理内部字段
            clean = {k: v for k, v in p.items() if not k.startswith('_')}
            lines.append(f'  - {json.dumps(clean, ensure_ascii=False)}')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


def merge_to_config(config_path):
    """将免费节点合并到现有 Clash 配置"""
    import yaml
    free_nodes_path = BASE_DIR / 'free-nodes.yaml'
    if not free_nodes_path.is_file():
        print('ERROR: free-nodes.yaml 不存在，先运行 node_aggregator.py')
        return False

    with open(free_nodes_path, 'r', encoding='utf-8') as f:
        free_data = yaml.safe_load(f)
    free_proxies = free_data.get('proxies', [])

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    existing = config.get('proxies', [])
    existing_fps = {proxy_fingerprint(p) for p in existing}

    added = 0
    free_names = []
    used_names = {p.get('name', '') for p in existing}
    for p in free_proxies:
        fp = proxy_fingerprint(p)
        if fp not in existing_fps:
            base_name = f"[Free] {p.get('name', 'unnamed')}"
            name = base_name
            counter = 2
            while name in used_names:
                name = f"{base_name} #{counter}"
                counter += 1
            p['name'] = name
            used_names.add(name)
            existing.append(p)
            existing_fps.add(fp)
            added += 1
        free_names.append(p.get('name', ''))

    config['proxies'] = existing

    # 添加 free-auto 代理组
    groups = config.get('proxy-groups', [])
    free_group = {
        'name': 'free-auto',
        'type': 'url-test',
        'url': 'http://www.gstatic.com/generate_204',
        'interval': 300,
        'tolerance': 100,
        'proxies': [n for n in free_names if n],
    }
    # 更新或添加
    found = False
    for i, g in enumerate(groups):
        if g.get('name') == 'free-auto':
            groups[i] = free_group
            found = True
            break
    if not found and free_names:
        groups.append(free_group)
        # 添加到 PROXY 组
        for g in groups:
            if g.get('name') == 'PROXY':
                if 'free-auto' not in g.get('proxies', []):
                    g['proxies'].insert(0, 'free-auto')
                break

    config['proxy-groups'] = groups

    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f'合并完成: 新增 {added} 个免费节点 → {config_path}')
    return True


if __name__ == '__main__':
    args = sys.argv[1:]

    if '--merge' in args:
        idx = args.index('--merge')
        cfg = args[idx+1] if idx+1 < len(args) else str(BASE_DIR / 'clash-config.yaml')
        if not os.path.isfile(cfg):
            print(f'ERROR: 配置文件不存在: {cfg}')
            sys.exit(1)
        aggregate(do_test=False)
        merge_to_config(cfg)
    elif '--test' in args:
        aggregate(do_test=True)
    else:
        aggregate(do_test=False)
