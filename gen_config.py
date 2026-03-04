import re, os, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Read from already-downloaded subconverter YAML
# Try multiple known locations for the subscription file
# Add your subscription YAML path here
_candidates = [
    os.path.join(BASE_DIR, 'subscription.yaml'),
    os.path.join(os.path.expanduser('~'), '.config', 'clash-verge', 'profiles', 'subscription.yaml'),
    os.path.join(os.path.expanduser('~'), '.config', 'clash-verge', 'profiles', 'sakuracat_sub.yaml'),
]
src = None
for _c in _candidates:
    if os.path.isfile(_c):
        src = _c
        break
if not src:
    print(f'ERROR: subscription YAML not found. Place your subscription YAML at: {_candidates[0]}')
    sys.exit(1)
with open(src, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract proxy lines (YAML inline format)
proxy_lines = re.findall(r'^\s+-\s+\{name:.*\}$', content, re.MULTILINE)

proxies_yaml = []
names_all = []
names_hk = []
names_jp = []
names_us = []

info_keywords = ['剩余流量', '距离下次', '套餐到期']
emoji_re = re.compile(r'[\U0001F1E0-\U0001F1FF\U0001F300-\U0001F9FF\u2600-\u27BF]+')

def clean_name(raw):
    n = raw.strip().strip('"').strip("'")
    n = emoji_re.sub('', n)
    n = n.strip().lstrip('|').strip()
    return n

for line in proxy_lines:
    m = re.search(r'name:\s*([^,}]+)', line)
    if not m:
        continue
    raw_name = m.group(1).strip()
    name = clean_name(raw_name)
    if not name or any(k in name for k in info_keywords):
        continue
    # Rebuild line with cleaned name
    new_line = re.sub(r'name:\s*[^,}]+', f'name: {name}', line.strip())
    if not new_line.startswith('  '):
        new_line = '  ' + new_line
    proxies_yaml.append(new_line)
    q_name = f'      - {name}'
    names_all.append(q_name)
    if '香港' in name:
        names_hk.append(q_name)
    elif '日本' in name:
        names_jp.append(q_name)
    elif '美国' in name:
        names_us.append(q_name)

hk_block = '\n'.join(names_hk) if names_hk else '      - DIRECT'
jp_block = '\n'.join(names_jp) if names_jp else '      - DIRECT'
us_block = '\n'.join(names_us) if names_us else '      - DIRECT'
all_block = '\n'.join(names_all)
proxies_block = '\n'.join(proxies_yaml)

# ===== 读取现有 PROCESS-NAME 规则（保留用户自定义） =====
existing_process_rules = []
out = os.path.join(BASE_DIR, 'clash-config.yaml')
if os.path.isfile(out):
    try:
        import yaml
        with open(out, 'r', encoding='utf-8') as f:
            old_cfg = yaml.safe_load(f)
        for rule in (old_cfg or {}).get('rules', []):
            if rule.startswith('PROCESS-NAME,'):
                existing_process_rules.append(f'  - {rule}')
    except Exception as e:
        print(f'WARNING: Failed to read existing process rules: {e}')

process_rules_block = '\n'.join(existing_process_rules) if existing_process_rules else ''
process_rules_section = f"\n  # === 按应用路由（由 VPN Manager Web UI 管理）===\n{process_rules_block}\n" if process_rules_block else ''

config = f"""# ============================================================
# Mihomo (Clash Meta) 配置文件
# 由 gen_config.py 自动生成
# 项目: clash-agent | 源: {os.path.basename(src)}
# ============================================================

# --- 基础设置 ---
mixed-port: 7890          # HTTP+SOCKS5 混合代理端口
allow-lan: false          # 禁止局域网连接
mode: rule                # 规则模式
log-level: info           # 日志级别: silent/error/warning/info/debug

# --- API 与面板 ---
external-controller: 127.0.0.1:9097   # RESTful API
external-ui: ui                       # MetaCubeXD 面板目录

# --- 进程匹配 ---
find-process-mode: strict    # 按应用路由的基础

# --- 地理数据（Loyalsoldier 增强版）---
geodata-mode: true
geox-url:
  geoip: https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat
  geosite: https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat
  mmdb: https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/country.mmdb
geo-auto-update: true
geo-update-interval: 168  # 每7天自动更新

# --- DNS 设置 ---
dns:
  enable: true
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - https://dns.alidns.com/dns-query
    - https://doh.pub/dns-query
  fallback:
    - https://dns.google/dns-query
    - https://cloudflare-dns.com/dns-query
  fallback-filter:
    geoip: true
    geoip-code: CN

# --- 嗅探 ---
sniffer:
  enable: true
  sniff:
    HTTP:
      ports: [80, 8080-8880]
    TLS:
      ports: [443, 8443]
    QUIC:
      ports: [443, 8443]

# --- 代理节点 ---
proxies:
{proxies_block}

# --- 代理组 ---
proxy-groups:
  - name: PROXY
    type: select
    proxies:
      - auto-hk
      - auto-jp
      - auto-us
      - DIRECT
{all_block}
  - name: auto-hk
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    tolerance: 50
    proxies:
{hk_block}
  - name: auto-jp
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    tolerance: 50
    proxies:
{jp_block}
  - name: auto-us
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    tolerance: 50
    proxies:
{us_block}

# --- 远程规则集（Loyalsoldier 维护，自动更新）---
rule-providers:
  reject:          # 广告域名
    type: http
    behavior: domain
    url: https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/reject.txt
    path: ./ruleset/reject.yaml
    interval: 86400
  proxy:           # 需要代理的域名
    type: http
    behavior: domain
    url: https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/proxy.txt
    path: ./ruleset/proxy.yaml
    interval: 86400
  direct:          # 直连域名
    type: http
    behavior: domain
    url: https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/direct.txt
    path: ./ruleset/direct.yaml
    interval: 86400
  cncidr:          # 中国IP段
    type: http
    behavior: ipcidr
    url: https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/cncidr.txt
    path: ./ruleset/cncidr.yaml
    interval: 86400
  lancidr:         # 局域网IP段
    type: http
    behavior: ipcidr
    url: https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/lancidr.txt
    path: ./ruleset/lancidr.yaml
    interval: 86400
  telegramcidr:    # Telegram IP段
    type: http
    behavior: ipcidr
    url: https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/telegramcidr.txt
    path: ./ruleset/telegramcidr.yaml
    interval: 86400
  private:         # 私有网络
    type: http
    behavior: domain
    url: https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/private.txt
    path: ./ruleset/private.yaml
    interval: 86400
  gfw:             # GFW域名列表
    type: http
    behavior: domain
    url: https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/gfw.txt
    path: ./ruleset/gfw.yaml
    interval: 86400

# --- 规则（优先级从上到下）---
rules:
{process_rules_section}
  # === 远程规则集 ===
  - RULE-SET,reject,REJECT        # 广告拦截
  - RULE-SET,private,DIRECT       # 私有网络直连
  - RULE-SET,lancidr,DIRECT       # 局域网直连
  - RULE-SET,telegramcidr,PROXY   # Telegram走代理
  - RULE-SET,gfw,PROXY            # GFW域名走代理
  - RULE-SET,proxy,PROXY          # 代理域名
  - RULE-SET,direct,DIRECT        # 直连域名
  - RULE-SET,cncidr,DIRECT        # 中国IP直连

  # === 手动补充规则 ===
  - DOMAIN-SUFFIX,openai.com,PROXY
  - DOMAIN-SUFFIX,anthropic.com,PROXY
  - DOMAIN-SUFFIX,claude.ai,PROXY
  - DOMAIN-SUFFIX,gemini.google.com,PROXY
  - DOMAIN-SUFFIX,codeium.com,PROXY
  - DOMAIN-SUFFIX,windsurf.com,PROXY

  # === 兜底 ===
  - GEOIP,CN,DIRECT               # 中国IP直连
  - MATCH,PROXY                   # 其余全走代理
"""

out = os.path.join(BASE_DIR, 'clash-config.yaml')
with open(out, 'w', encoding='utf-8') as f:
    f.write(config)

print(f'Config written: {len(config)} bytes, {len(proxies_yaml)} nodes')
print(f'HK:{len(names_hk)} JP:{len(names_jp)} US:{len(names_us)} Other:{len(names_all)-len(names_hk)-len(names_jp)-len(names_us)}')
