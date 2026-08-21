# -*- coding: utf-8 -*-
"""云端数据获取层：封装 westock-data CLI + mx_search 妙想搜索。

- westock-data: 纯 Node 脚本（deps/westock-data/scripts/index.js），腾讯自选股数据接口
- mx_search:    deps/mx_search.py，东方财富妙想资讯搜索（读 MX_APIKEY 环境变量）
- 所有日期统一用北京时间（GitHub Actions 环境为 UTC，需 +8）
"""
import io, json, os, re, subprocess, sys
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
NODE = os.environ.get('NODE_BIN', 'node')
SCRIPT = os.environ.get(
    'WESTOCK_SCRIPT',
    os.path.join(BASE, 'deps', 'westock-data', 'scripts', 'index.js'))
MX_PY = os.environ.get(
    'MX_PY',
    os.path.join(BASE, 'deps', 'mx_search.py'))
CN_TZ = timezone(timedelta(hours=8))

def now_cn():
    return datetime.now(CN_TZ)

def today_cn():
    return now_cn().strftime('%Y-%m-%d')

def date_compact(d=None):
    """YYYY-MM-DD -> YYYYMMDD"""
    d = d or today_cn()
    return d.replace('-', '')

def weekday_cn(d=None):
    w = (now_cn() if d is None else datetime.strptime(d, '%Y-%m-%d')).weekday()
    return ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][w]

def run_cli(*args, timeout=60):
    """运行 westock CLI，返回 stdout 文本；失败返回 ''"""
    try:
        r = subprocess.run([NODE, SCRIPT] + list(args),
                           capture_output=True, text=True, encoding='utf-8',
                           timeout=timeout)
        return r.stdout or ''
    except Exception:
        return ''

def cli_json(*args, timeout=60):
    """运行 westock CLI 并解析 JSON；失败返回 None"""
    out = run_cli(*args, timeout=timeout)
    try:
        return json.loads(out)
    except Exception:
        return None

# ---------- 行情 ----------
def _norm_codes(codes):
    """codes 支持 list[str] 或 'a,b,c' 字符串，统一返回 list[str]"""
    if isinstance(codes, str):
        return [c.strip() for c in codes.split(',') if c.strip()]
    return list(codes or [])

def quote(codes):
    """批量实时行情。codes: list[str]|str -> {symbol: data}"""
    codes = _norm_codes(codes)
    if not codes:
        return {}
    raw = cli_json('quote', ','.join(codes), '--raw')
    if raw is None:
        return {}
    items = raw['data'] if isinstance(raw, dict) else raw
    if isinstance(items, dict):
        items = list(items.values())
    recs = {}
    for it in items:
        d = it['data'] if 'data' in it else it
        if isinstance(d, dict) and d.get('symbol'):
            recs[d['symbol']] = d
    return recs

def kline(code, n=105):
    raw = cli_json('kline', code, '--raw')
    return raw[:n] if isinstance(raw, list) else []

# ---------- 市场分布 ----------
def changedist():
    """涨跌分布。返回 dict(upCount, downCount, flatCount, upLimitCount, downLimitCount)"""
    d = cli_json('changedist', '--raw')
    return d if isinstance(d, dict) else {}

def market_overview():
    """市场画像总评（summary + updown）"""
    raw = cli_json('market-overview', '--type', 'summary,updown', '--raw')
    if not isinstance(raw, list):
        return {}
    out = {}
    for it in raw:
        t = (it.get('info') or {}).get('type')
        if t:
            out[t] = it
    return out

def sector_ranking():
    """板块排行。返回 dict(sections=[行业涨幅, 概念涨幅, 资金流入])"""
    d = cli_json('sector', 'ranking', '--raw')
    return d if isinstance(d, dict) else {}

def hot_board(limit=15):
    """热搜板块。可能限流失败，失败返回 []"""
    raw = cli_json('hot', 'board', '--limit', str(limit), '--raw')
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get('data'), list):
        return raw['data']
    return []

def fund_flow(codes):
    """板块主力资金流。codes: list[str]|str -> {code: data}"""
    codes = _norm_codes(codes)
    if not codes:
        return {}
    raw = cli_json('fund', 'flow', ','.join(codes), '--raw')
    if not isinstance(raw, list):
        return {}
    out = {}
    for it in raw:
        if isinstance(it, dict) and it.get('symbol'):
            out[it['symbol']] = it
    return out

def sector_constituent(code):
    """板块成分股（Excel 用）"""
    raw = cli_json('sector', 'constituent', code, '--raw')
    return raw if isinstance(raw, list) else []

# ---------- 妙想资讯搜索 ----------
def mx_search(query, out_dir=None, retries=2):
    """调用 mx_search.py，返回 stdout 格式化文本（含标题/内容/来源）；失败返回 ''
    注意：mx_search.py 需要 MX_APIKEY 环境变量"""
    out_dir = out_dir or os.path.join(BASE, 'mx_data')
    os.makedirs(out_dir, exist_ok=True)
    py = sys.executable
    last = ''
    for _ in range(retries + 1):
        try:
            r = subprocess.run(
                [py, MX_PY, query, out_dir],
                capture_output=True, text=True, encoding='utf-8',
                timeout=120)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
            last = r.stderr.strip() or last
        except Exception as e:
            last = str(e)
    return last

def mx_search_json(query, out_dir=None):
    """调用 mx_search.py 原始输出（返回最后生成的 JSON 文件内容 dict）"""
    out_dir = out_dir or os.path.join(BASE, 'mx_data')
    os.makedirs(out_dir, exist_ok=True)
    try:
        r = subprocess.run([sys.executable, MX_PY, query, out_dir],
                           capture_output=True, text=True, encoding='utf-8',
                           timeout=120)
        if r.returncode == 0:
            js = sorted([f for f in os.listdir(out_dir) if f.endswith('.json')])
            if js:
                with io.open(os.path.join(out_dir, js[-1]), encoding='utf-8') as f:
                    return json.load(f)
    except Exception:
        pass
    return {}
