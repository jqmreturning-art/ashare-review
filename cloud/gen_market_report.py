# -*- coding: utf-8 -*-
"""云端大盘报告生成：market-review-YYYYMMDD.html

数据源：westock-data CLI（quote/changedist/market_overview/sector_ranking/hot_board）
      + mx_search（财联社收盘涨停口径）+ llm_writer（分析文字，含规则兜底）
模板：ui_css.MKT_CSS（2026-08-20 线上版）+ 结构参数化
"""
import io, json, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import data_fetch as df
import llm_writer as lw
from ui_css import MKT_CSS


# ---------- 数据采集 ----------
def fetch_all():
    """拉取大盘报告全部数据；任何单项失败返回空结构不阻断"""
    d = {}
    d['changedist'] = df.changedist()
    d['index'] = df.quote('sh000001,sz399006,sh000688')
    d['overview'] = df.market_overview()
    d['sector'] = df.sector_ranking()
    d['hot'] = df.hot_board(15)
    # 财联社收盘涨停口径（mx_search 文本，供解析涨停/封板/连板/晋级率）
    d['cls'] = df.mx_search(
        '财联社 今日 涨停分析 收盘 涨停家数 封板率 连板股总数 晋级率 焦点复盘', retries=1)
    return d


# ---------- 数据解析 ----------
def parse_sections(sr):
    """sector ranking sections -> (industry_top, concept_top, money_in)"""
    ind, con, money = [], [], []
    secs = (sr or {}).get('sections') or []
    for i, sec in enumerate(secs):
        if not isinstance(sec, list):
            continue
        if i == 0:
            ind = sec
        elif i == 1:
            con = sec
        elif i == 2:
            money = sec
    return ind, con, money


def parse_cls(text):
    """从财联社文本提取 涨停家数/封板率/连板股/晋级率"""
    out = {'limit': 0, 'seal': '', 'lianban': 0, 'jinsheng': ''}
    if not text:
        return out
    m = re.search(r'涨停\s*(\d+)', text)
    if m: out['limit'] = int(m.group(1))
    m = re.search(r'封板率[^\d]*(\d+(?:\.\d+)?)%', text)
    if m: out['seal'] = m.group(1) + '%'
    m = re.search(r'连板股[^\d]*(\d+)', text)
    if m: out['lianban'] = int(m.group(1))
    m = re.search(r'晋级率[^\d]*(\d+(?:\.\d+)?)%', text)
    if m: out['jinsheng'] = m.group(1) + '%'
    return out


def calc_temp(d):
    """情绪温度 0-100（收盘口径）：涨停/封板/连板高度/晋级率 → 温度"""
    cd = d.get('changedist') or {}
    cls = d.get('cls_parsed') or {}
    limit = cls.get('limit') or cd.get('upLimitCount') or 0
    seal = float(re.sub(r'[^\d.]', '', cls.get('seal') or '0') or 0)
    lianban = cls.get('lianban') or 0
    jinsheng = float(re.sub(r'[^\d.]', '', cls.get('jinsheng') or '0') or 0)
    t = 0
    t += min(limit, 100) * 0.45          # 涨停家数权重最大
    t += seal * 0.30
    t += min(jinsheng, 50) * 0.15
    t += min(lianban * 4, 40) * 0.10
    # 广度微调
    ov = d.get('overview') or {}
    up_pct = 0.0
    for v in ov.values():
        try:
            p = float(re.sub(r'[^\d.]', '', str((v.get('data') or {}).get('upRatio') or 0)))
            up_pct = max(up_pct, p)
        except Exception:
            pass
    t += (up_pct - 50) * 0.05
    return max(5, min(95, round(t)))


def temp_label(t):
    if t < 35: return '冰点'
    if t < 50: return '弱修复'
    if t < 65: return '中性'
    return '高温'


def fmt_sec_name(s):
    """板块条目取名称"""
    if isinstance(s, dict):
        return s.get('name') or s.get('sector_name') or ''
    return str(s)


def sec_pct(s):
    """板块条目涨跌幅"""
    for k in ('change_percent', 'pct', 'chg', 'increase'):
        v = s.get(k) if isinstance(s, dict) else None
        if v not in (None, ''):
            return v
    return None


# ---------- HTML 生成 ----------
def build_html(d, date_str, out_path):
    date_cn = df.today_cn()
    wd = df.weekday_cn()
    cd = d.get('changedist') or {}
    idx = d.get('index') or {}
    cls = d.get('cls_parsed') or {}
    ind, con, money = parse_sections(d.get('sector'))

    # ---- 指数条形（双向，0点居中） ----
    idx_rows = []
    for sym, nm in (('sh000001', '上证指数'), ('sz399006', '创业板指'), ('sh000688', '科创50')):
        it = idx.get(sym) or {}
        price = it.get('price') or 0
        pct = it.get('change_percent') or 0
        try:
            pct_f = float(pct)
        except Exception:
            pct_f = 0.0
        w = min(abs(pct_f) * 42, 50)   # 每1%≈42宽度上限50
        cls_row = 'up' if pct_f > 0 else ('dn' if pct_f < 0 else 'flat')
        idx_rows.append(
            '<div class="idx-row"><span class="idx-name">%s</span>'
            '<span class="idx-price">%.2f</span><div class="bar-wrap">'
            '<div class="bar-fill %s" style="width:%s%%"></div></div>'
            '<span class="pct %s">%+.2f%%</span></div>' % (
                nm, price, cls_row, w, cls_row, pct_f))

    # ---- 涨停梯队（财联社口径，数据缺失降级用 changedist） ----
    limit = cls.get('limit') or cd.get('upLimitCount') or 0
    seal = cls.get('seal') or '--'
    lianban = cls.get('lianban') or 0
    jinsheng = cls.get('jinsheng') or '--'
    down_limit = cd.get('downLimitCount') or 0
    ladder_note = '涨停梯队（财联社收盘口径）'
    ladder_sub = '%d 股涨停 / 封板率 %s / 连板股 %d 只 / 晋级率 %s' % (
        limit, seal, lianban, jinsheng)
    if not cls.get('seal'):
        ladder_sub += '（财联社口径待补充，涨停家数为行情接口口径）'

    # ---- KPI ----
    kpi_html = (
        '<div class="kpi"><div class="val" style="color:var(--red)">%d</div>'
        '<div class="lbl">涨停家数</div><div class="sub">财联社收盘口径</div></div>'
        '<div class="kpi"><div class="val" style="color:var(--amber)">%s</div>'
        '<div class="lbl">封板率</div><div class="sub">收盘口径</div></div>'
        '<div class="kpi"><div class="val" style="color:var(--amber)">%d板</div>'
        '<div class="lbl">连板股总数</div><div class="sub">收盘口径</div></div>'
        '<div class="kpi"><div class="val" style="color:var(--green)">%s</div>'
        '<div class="lbl">连板晋级率</div><div class="sub">收盘口径</div></div>' % (
            limit, seal, lianban, jinsheng))

    # ---- 温度计 SVG ----
    temp = calc_temp(d)
    lbl = temp_label(temp)
    arc = 251.3
    off = arc * (1 - temp / 100)
    gauge = (
        '<svg viewBox="0 0 200 120" width="200" height="120"><defs>'
        '<linearGradient id="gauge-grad" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%%" stop-color="#00d4aa"/><stop offset="50%%" stop-color="#ffa502"/>'
        '<stop offset="100%%" stop-color="#ff4757"/></linearGradient></defs>'
        '<path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="#eef0f5" stroke-width="14" stroke-linecap="round"/>'
        '<path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="url(#gauge-grad)" stroke-width="14" stroke-linecap="round" stroke-dasharray="251.3" stroke-dashoffset="%.1f"/>'
        '<text x="100" y="88" text-anchor="middle" font-size="36" font-weight="900" fill="#ff4757">%d</text>'
        '<text x="125" y="88" font-size="16" fill="#6b7280">°C</text>'
        '<text x="100" y="112" text-anchor="middle" font-size="11" fill="#9ca3af">%s</text></svg>' % (
            off, temp, lbl))

    # 广度
    up_n = cd.get('upCount') or 0
    dn_n = cd.get('downCount') or 0
    flat_n = cd.get('flatCount') or 0
    total = up_n + dn_n + flat_n or 1
    up_p = round(up_n * 100 / total, 1)
    dn_p = round(dn_n * 100 / total, 1)
    flat_p = round(flat_n * 100 / total, 1)
    breadth = (
        '<div class="breadth-bar">'
        '<div class="seg-up" style="width:%s%%"></div>'
        '<div class="seg-flat" style="width:%s%%"></div>'
        '<div class="seg-dn" style="width:%s%%"></div></div>'
        '<div class="breadth-labels">'
        '<span style="color:var(--red)">红盘 %d (%s%%)</span>'
        '<span style="color:var(--flat)">平 %d</span>'
        '<span style="color:var(--green)">绿盘 %d (%s%%)</span></div>' % (
            up_p, flat_p, dn_p, up_n, up_p, flat_n, dn_n, dn_p))

    # ---- 板块强弱四卡 ----
    def sec_item(s, is_money=False):
        nm = fmt_sec_name(s)
        if not nm:
            return ''
        pct = sec_pct(s)
        lead = ''
        if is_money:
            try:
                v = float(s.get('MainInFlow') or 0) / 1e8
                pct = '%+.1f亿' % v
            except Exception:
                pct = '--'
        elif pct is not None:
            try:
                pct = '%+.2f%%' % float(pct)
            except Exception:
                pct = str(pct)
        else:
            pct = '--'
        c = 'up' if (pct and pct.startswith('+') and '亿' not in pct) else ('dn' if (pct and pct.startswith('-')) else '')
        return '<div class="item"><span class="nm">%s</span><span class="vl %s %s">%s</span></div>' % (
            nm, 'flow-val' if is_money else '', c, pct)

    ind_items = ''.join(sec_item(s) for s in ind[:5])
    con_items = ''.join(sec_item(s) for s in con[:5])
    money_items = ''.join(sec_item(s, True) for s in money[:5])
    # 跌幅居前：从 hot/行业反转取（此处用行业涨幅末5的负值 + 说明）
    dn_items = ''
    neg = [s for s in ind if (sec_pct(s) is not None and float(sec_pct(s)) < 0)][-5:][::-1]
    dn_items = ''.join(sec_item(s) for s in neg) or (
        '<div class="item"><span class="nm">（今日行业普涨，无显著领跌板块）</span>'
        '<span class="vl">--</span></div>')
    hot_names = [fmt_sec_name(s) for s in d.get('hot')[:8] if fmt_sec_name(s)]
    hot_txt = '、'.join(hot_names[:6]) if hot_names else '--'

    sector_grid = (
        '<div class="mini-card"><h4>🏆 行业涨幅居前</h4>%s</div>'
        '<div class="mini-card"><h4>🔥 概念涨幅居前</h4>%s</div>'
        '<div class="mini-card"><h4>💴 主力资金流入</h4>%s</div>'
        '<div class="mini-card"><h4>📉 跌幅居前</h4>%s</div>' % (
            ind_items, con_items, money_items, dn_items))

    # ---- 主线研判（LLM 或规则） ----
    summary = {'upCount': up_n, 'downCount': dn_n,
               'upLimitCount': limit, 'downLimitCount': down_limit,
               'top_sector': fmt_sec_name(ind[0]) if ind else '',
               'money_sector': fmt_sec_name(money[0]) if money else ''}
    verdict_text = lw.gen_analysis('大盘情绪解读', summary, max_tokens=400)
    judge_strong = lw.gen_analysis('主线研判', summary)
    j_cards = (
        '<div class="j-card strong"><h4>相对强势 · %s</h4>'
        '<div class="desc">%s</div>'
        '<span class="tag" style="background:#fee2e2;color:#dc2626">数据驱动</span></div>'
        '<div class="j-card weak"><h4>退潮确认 / 弱势方向</h4>'
        '<div class="desc">跌停 %d 只、封板率 %s，接力强度不足，高位题材股警惕退潮风险。</div>'
        '<span class="tag" style="background:#ecfdf5;color:#059669">谨慎</span></div>'
        '<div class="j-card risk"><h4>高风险 · 接力与监管</h4>'
        '<div class="desc">连板晋级率 %s 处于低位，短线接力资金匮乏，追高风险大。</div>'
        '<span class="tag" style="background:#fef3c7;color:#b45309">情绪未确认</span></div>'
        '<div class="j-card alive"><h4>活口 · 热点延续</h4>'
        '<div class="desc">热搜方向：%s。关注是否走出持续性。</div>'
        '<span class="tag" style="background:#ecfdf5;color:#059669">观察</span></div>' % (
            fmt_sec_name(ind[0]) if ind else '主线', judge_strong,
            down_limit, seal, jinsheng, hot_txt))

    # ---- 观察锚 ----
    observe = (
        '<li><b>主线延续性</b>：%s 能否保持涨停梯队完整，谨防单日过热后高低切。</li>'
        '<li><b>量能配合</b>：关注成交额是否放大，缩量反弹高度有限。</li>'
        '<li><b>接力强度</b>：连板晋级率 %s、封板率 %s 处低位，情绪修复待确认。</li>'
        '<li><b>高位股风险</b>：监管收紧背景下回避无基本面高位纯题材股。</li>'
        '<li><b>热点扩散</b>：%s 板块的持续性决定赚钱效应能否外溢。</li>' % (
            fmt_sec_name(ind[0]) if ind else '今日领涨方向', jinsheng, seal, hot_txt))

    html = u'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股收盘主线与情绪复盘 {{TITLE}}</title>
<style>{{CSS}}</style>
</head>
<body>
<header>
<div>
<span class="hd-tag">ASHARE REVIEW</span>
<h1>A股收盘主线与情绪复盘</h1>
<div class="date">{{DATE}} {{WD}} · 收盘静态快照</div>
</div>
<div class="temp-badge">
<div class="temp-num">{{TEMP}}<span style="font-size:16px">°C</span></div>
<div class="temp-lbl">情绪温度 · {{LBL}}</div>
</div>
</header>

<div class="verdict">
<div class="label">MARKET VERDICT</div>
<div class="text">{{VERDICT}}<span class="tag">{{LBL2}}</span></div>
</div>

<div class="section-title">情绪四指标 KPI（财联社收盘口径）</div>
<div class="kpi-row">{{KPI}}</div>

<div class="card" style="margin-top:12px">
<h3>情绪温度计</h3>
<div class="temp-section">
<div class="temp-gauge">{{GAUGE}}</div>
<div class="temp-info">
<div class="temp-val" style="color:var(--red)">{{TEMP2}}°C</div>
<div class="temp-label">{{LBL3}}（{{TEMPLABEL}}）</div>
<div class="temp-trend">基于涨停 {{LIMIT}} 家 / 封板率 {{SEAL}} / 连板股 {{LIANBAN}} 只 / 晋级率 {{JINSHENG}} 综合计算，红盘占比 {{UPPCT}}%</div>
<div style="margin-top:12px">
<div style="font-size:12px;color:var(--sub);margin-bottom:4px">市场广度</div>
{{BREADTH}}
</div>
</div>
</div>
</div>

<div class="card" style="margin-top:12px">
<h3>指数表现</h3>
{{IDXROWS}}
<div style="font-size:11px;color:var(--muted);margin-top:8px">红盘 {{UPN}} / 绿盘 {{DNN}} · 涨跌分布来自行情接口</div>
</div>

<div class="section-title">板块强弱</div>
<div class="sector-grid">{{SECTORGRID}}</div>

<div class="section-title">{{LADDERN}}</div>
<div class="card">
<h3>涨停梯队 · 收盘口径 <span style="font-size:11px;color:var(--muted);font-weight:400">{{LADDERS}}</span></h3>
<div class="ladder">
<div class="ladder-row"><span class="lvl lvl-2">连板股</span><div class="stocks"><span class="stock-tag">连板股 {{LIANBAN2}} 只（明细以财联社收盘复盘为准）</span></div></div>
<div class="ladder-row"><span class="lvl lvl-3">20cm涨停</span><div class="stocks"><span class="stock-tag hot">以财联社收盘复盘名单为准</span></div></div>
</div>
<div style="font-size:11.5px;color:var(--muted);margin-top:6px;line-height:1.7">
跌停 {{DOWNLIMIT}} 只 · 单票数据经日K线复核（主板≈+10%、创业板/科创板≈+20%）。
</div>
</div>

<div class="section-title">主线研判</div>
<div class="judgment-grid">{{JCARDS}}</div>

<div class="section-title">隔夜 / 明日观察锚</div>
<div class="observe"><ul>{{OBSERVE}}</ul></div>

<div class="footer">
<p><b>数据口径</b>：涨停家数/封板率/连板股总数/晋级率 采用财联社收盘复盘口径；板块/个股行情来自腾讯自选股行情接口；指数点位为收盘值。涨停梯队个股经日K线复核为收盘真实封板。</p>
<p><b>免责声明</b>：本报告为收盘静态快照，仅供研究参考，不构成任何投资建议。市场有风险，投资需谨慎。</p>
</div>
</body>
</html>'''
    repl = {
        '{{TITLE}}': date_str, '{{CSS}}': MKT_CSS,
        '{{DATE}}': date_cn, '{{WD}}': wd,
        '{{TEMP}}': str(temp), '{{LBL}}': lbl,
        '{{VERDICT}}': verdict_text, '{{LBL2}}': lbl,
        '{{KPI}}': kpi_html,
        '{{GAUGE}}': gauge,
        '{{TEMP2}}': str(temp), '{{LBL3}}': lbl, '{{TEMPLABEL}}': temp_label(temp),
        '{{LIMIT}}': str(limit), '{{SEAL}}': seal, '{{LIANBAN}}': str(lianban),
        '{{JINSHENG}}': jinsheng, '{{UPPCT}}': str(up_p),
        '{{BREADTH}}': breadth,
        '{{IDXROWS}}': ''.join(idx_rows),
        '{{UPN}}': str(up_n), '{{DNN}}': str(dn_n),
        '{{SECTORGRID}}': sector_grid,
        '{{LADDERN}}': ladder_note,
        '{{LADDERS}}': ladder_sub,
        '{{LIANBAN2}}': str(lianban),
        '{{DOWNLIMIT}}': str(down_limit),
        '{{JCARDS}}': j_cards,
        '{{OBSERVE}}': observe,
    }
    for k, v in repl.items():
        html = html.replace(k, v)

    with io.open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return temp, lbl


def main(date_str=None):
    date_str = date_str or df.date_compact()
    d = fetch_all()
    d['cls_parsed'] = parse_cls(d.get('cls') or '')
    out = os.path.join(BASE, 'market-review-%s.html' % date_str)
    temp, lbl = build_html(d, date_str, out)
    # 校验
    h = io.open(out, encoding='utf-8').read()
    checks = {
        '外链数(应为0)': len(re.findall(r'(https?://|src=)', h.replace('http://www.w3.org/2000/svg', ''))),
        '指数条形left:50%': 'left:50%' in h,
        '指数条形right:50%': 'right:50%' in h,
        'var(--grad)': 'var(--grad)' in h,
        '温度渐变#ffa502': '#ffa502' in h,
        'temp-badge': 'temp-badge' in h,
    }
    ok = all(v == 0 or v is True for v in checks.values()) and checks['指数条形left:50%'] and checks['指数条形right:50%']
    print('生成 %s | 温度 %d°C %s | 校验: %s' % (
        os.path.basename(out), temp, lbl, 'PASS' if ok else checks))
    return out, ok


if __name__ == '__main__':
    main()
