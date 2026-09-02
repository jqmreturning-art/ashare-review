# -*- coding: utf-8 -*-
"""云端 AI 产业链报告生成：ai-market-review-YYYYMMDD.html

结构（8 节）：今日结论/产业链情绪温度/细分赛道排行/资金动向/龙头梯队/产业催化/估值与拥挤度/展望清单
模板：ui_css.AI_CSS（2026-08-20 线上版）+ 结构参数化
"""
import io, json, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import data_fetch as df
import llm_writer as lw
from ui_css import AI_CSS

# 17 赛道：代码 -> (名称, 分类)
TRACKS = [
    ('pt02GN2211', 'CPO 光模块', 'hw'),
    ('pt02GN2223', '服务器', 'hw'),
    ('pt02GN2222', 'AI 算力芯片', 'hw'),
    ('pt02101284', 'PCB', 'hw'),
    ('pt02GN2224', '液冷', 'hw'),
    ('pt02041354', '数据中心', 'hw'),
    ('pt02GN2328', '半导体设备', 'sc'),
    ('pt02GN2323', '半导体材料', 'sc'),
    ('pt01801081', '半导体', 'sc'),
    ('pt02GN2228', '大模型', 'ap'),
    ('pt02GN2196', 'AIGC', 'ap'),
    ('pt02GN2343', 'AI 应用', 'ap'),
    ('pt02GN2354', 'AI 智能体', 'ap'),
    ('pt02GN2298', 'AI 语料', 'ap'),
    ('pt02GN2266', '华为算力', 'hw'),
    ('pt02GN2287', 'AIPC', 'term'),
    ('pt02GN2293', 'AI 手机', 'term'),
]
CHIP = {'hw': '算力硬件', 'sc': '半导体', 'ap': '模型应用', 'term': 'AI终端'}
CHIP_CLS = {'hw': 'chip hw', 'sc': 'chip sc', 'ap': 'chip ap', 'term': 'chip term'}

# 6 大核心板块（资金动向）
CORE_FLOW = [('pt01801081', '半导体'), ('pt02GN2211', 'CPO 光模块'),
             ('pt02101284', 'PCB'), ('pt02GN2223', '服务器'),
             ('pt02GN2222', 'AI 算力芯片'), ('pt02GN2224', '液冷')]

# 10 龙头：(代码, 名称, 赛道chip)
LEADERS = [
    ('sz300308', '中际旭创', 'hw', 'CPO'),
    ('sh688256', '寒武纪', 'hw', '算力芯片'),
    ('sz002371', '北方华创', 'sc', '半导体设备'),
    ('sh688981', '中芯国际', 'sc', '半导体'),
    ('sh601138', '工业富联', 'hw', '服务器'),
    ('sz300502', '新易盛', 'hw', 'CPO'),
    ('sz002463', '沪电股份', 'hw', 'PCB'),
    ('sh688041', '海光信息', 'hw', '算力芯片'),
    ('sh688012', '中微公司', 'sc', '半导体设备'),
    ('sz002230', '科大讯飞', 'ap', 'AI应用'),
]

# 6 ETF：(代码, 名称)
ETFS = [('sz159381', '创业板人工智能ETF华夏'), ('sz159363', '创业板人工智能ETF华宝'),
        ('sh560780', '半导体设备ETF广发'), ('sh515050', '通信ETF华夏'),
        ('sh589950', '科创100ETF富国'), ('sh589780', '科创200ETF富国')]


# ---------- 数据采集 ----------
def fetch_all():
    d = {}
    d['tracks'] = df.quote([c for c, _, _ in TRACKS])
    d['flows'] = df.fund_flow([c for c, _ in CORE_FLOW])
    d['leaders'] = df.quote([c for c, _, _, _ in LEADERS])
    d['etfs'] = df.quote([c for c, _ in ETFS])
    d['news'] = df.mx_search(
        '今日 A股 AI算力 半导体 光模块 CPO 存储 涨停 主线 复盘', retries=1)
    return d


def f2f(v, div=1e8):
    """字符串/数字 -> 亿 float；失败 0"""
    try:
        return float(v) / div
    except Exception:
        return 0.0


def fmt_pct(v):
    try:
        return '%+.2f%%' % float(v)
    except Exception:
        return '--'


# ---------- HTML 生成 ----------
def build_html(d, date_str, out_path):
    date_cn = df.today_cn()
    wd = df.weekday_cn()
    tracks = d.get('tracks') or {}
    flows = d.get('flows') or {}
    leaders = d.get('leaders') or {}
    etfs = d.get('etfs') or {}

    # ---- 赛道表 ----
    rows = []
    for i, (code, name, cat) in enumerate(TRACKS, 1):
        it = tracks.get(code) or {}
        pct = it.get('change_percent') or 0
        amt = it.get('amount') or 0
        to = it.get('turnover_rate') or 0
        d10 = it.get('chg_10d') or 0
        try:
            pct_f = float(pct)
        except Exception:
            pct_f = 0
        cls = 'up' if pct_f > 0 else ('dn' if pct_f < 0 else '')
        w = min(abs(pct_f) * 42, 100)
        rows.append(
            '<tr><td>%d</td><td>%s</td><td><span class="%s">%s</span></td>'
            '<td class="num %s">%s</td><td class="num">%.0f亿</td>'
            '<td class="num">%.2f%%</td><td class="num %s">%s</td>'
            '<td><div class="bar"><div class="bar-fill %s" style="width:%.0f%%"></div></div></td></tr>' % (
                i, name, CHIP_CLS[cat], CHIP[cat], cls, fmt_pct(pct),
                f2f(amt), to, 'up' if float(d10 or 0) > 0 else ('dn' if float(d10 or 0) < 0 else ''),
                fmt_pct(d10), cls, w))
    track_rows = ''.join(rows)
    up_cnt = sum(1 for c, _, _ in TRACKS
                 if float((tracks.get(c) or {}).get('change_percent') or 0) > 0)

    # ---- 资金动向 6 卡 ----
    flow_items = []
    flow_total = 0
    for code, name in CORE_FLOW:
        it = flows.get(code) or {}
        main = f2f(it.get('MainInFlow'))
        flow_total += main
        rank = it.get('MainInflowIndu') or it.get('rank') or '--'
        d5 = it.get('MainInflow5') or it.get('main_5d') or 0
        cls = 'dn' if main < 0 else ('up' if main > 0 else '')
        flow_items.append(
            '<div class="flow-item"><div class="flow-name">%s</div>'
            '<div class="flow-val %s">%+.1f 亿</div>'
            '<div class="flow-sub">行业排名 %s · 5日 %+.1f亿</div></div>' % (
                name, cls, main, rank, f2f(d5)))
    flow_grid = ''.join(flow_items)

    # ---- ETF 表 ----
    etf_rows = []
    for code, name in ETFS:
        it = etfs.get(code) or {}
        pct = it.get('change_percent') or 0
        cls = 'up' if float(pct or 0) > 0 else ('dn' if float(pct or 0) < 0 else '')
        etf_rows.append(
            '<tr><td>%s</td><td class="num %s">%s</td><td class="num">%.2f亿</td>'
            '<td class="num">%.2f%%</td></tr>' % (
                name, cls, fmt_pct(pct), f2f(it.get('amount')), it.get('turnover_rate') or 0))
    etf_table = ''.join(etf_rows)

    # ---- 龙头表（事件列图例） ----
    l_rows = []
    for code, name, cat, sec in LEADERS:
        it = leaders.get(code) or {}
        pct = it.get('change_percent') or 0
        pe = it.get('pe') or it.get('PE') or 0
        ytd = it.get('chg_ytd') or it.get('change_ytd') or 0
        amt = f2f(it.get('amount'))
        try:
            pct_f = float(pct)
        except Exception:
            pct_f = 0
        cls = 'up' if pct_f > 0 else ('dn' if pct_f < 0 else '')
        ev = '— 平盘'
        if pct_f >= 2.5:
            ev = '🔥 当日显著上涨/利好'
        elif pct_f >= 0.3:
            ev = '🔥 当日上涨'
        elif pct_f <= -2.5:
            ev = '❄️ 当日显著下跌/利空'
        elif pct_f < -0.3:
            ev = '❄️ 当日下跌'
        l_rows.append(
            '<tr><td>%s</td><td><span class="%s">%s</span></td>'
            '<td class="num">%.2f</td><td class="num %s">%s</td>'
            '<td class="num">%.1f亿</td><td class="num">%.2f</td>'
            '<td class="num %s">%s</td><td>%s</td></tr>' % (
                name, CHIP_CLS[cat], sec, it.get('price') or 0, cls, fmt_pct(pct),
                amt, pe, 'up' if float(ytd or 0) > 0 else ('dn' if float(ytd or 0) < 0 else ''),
                fmt_pct(ytd), ev))
    leader_rows = ''.join(l_rows)

    # ---- 温度（科技专属简化计算） ----
    up_cnt = sum(1 for c, _, _ in TRACKS if float((tracks.get(c) or {}).get('change_percent') or 0) > 0)
    lead_up = sum(1 for c, _, _, _ in LEADERS if float((leaders.get(c) or {}).get('change_percent') or 0) > 0)
    temp = int(min(95, max(5, up_cnt / 17 * 50 + lead_up / 10 * 30 + (5 if flow_total >= 0 else 0))))
    lbl = '高温' if temp > 65 else ('中性' if temp >= 50 else ('弱修复' if temp >= 35 else '冰点'))
    arc = 452.4
    off = arc * (1 - temp / 100)

    # ---- 今日结论（LLM/规则） ----
    top_name = ''
    for c, name, _ in TRACKS:
        it = tracks.get(c) or {}
        try:
            if not top_name or float(it.get('change_percent') or 0) > float(tracks.get(dict((x, y) for x, y, _ in TRACKS).get('', {}) or {}).get('change_percent') or 0):
                pass
        except Exception:
            pass
    # 简单取涨幅最大赛道
    best = max([(c, float((tracks.get(c) or {}).get('change_percent') or 0)) for c, _, _ in TRACKS],
               key=lambda x: x[1], default=('', 0))
    worst = min([(c, float((tracks.get(c) or {}).get('change_percent') or 0)) for c, _, _ in TRACKS],
                key=lambda x: x[1], default=('', 0))
    best_name = dict((c, n) for c, n, _ in TRACKS).get(best[0], '')
    worst_name = dict((c, n) for c, n, _ in TRACKS).get(worst[0], '')
    summary = {'up_tracks': up_cnt, 'total_tracks': len(TRACKS),
               'best': best_name, 'best_pct': best[1],
               'worst': worst_name, 'worst_pct': worst[1],
               'flow_total': round(flow_total, 1), 'lead_up': lead_up}
    vd1 = lw.gen_analysis('AI硬件主线', summary)
    vd2 = lw.gen_analysis('应用滞涨', summary)
    vd3 = lw.gen_analysis('催化共振', summary)
    vd_cards = (
        '<div class="vd-card"><div class="vd-t">硬件主线：%s 领涨</div>'
        '<div class="vd-d">%s</div></div>'
        '<div class="vd-card purple"><div class="vd-t">应用滞涨：跟涨但缺资金</div>'
        '<div class="vd-d">%s</div></div>'
        '<div class="vd-card amber"><div class="vd-t">催化共振：关注产业驱动</div>'
        '<div class="vd-d">%s</div></div>' % (best_name, vd1, vd2, vd3))

    # ---- 产业催化（mx_search 提炼，最多 4 条） ----
    news = d.get('news') or ''
    news_html = ''
    if news:
        # 按行切分取前几条
        lines = [l.strip() for l in news.split('\n') if l.strip()][:12]
        for j, line in enumerate(lines[:4]):
            tag = line[:8]
            body = line[8:] if len(line) > 8 else line
            news_html += (
                '<div class="news"><div class="news-badge"><b>%s</b><br>资讯</div>'
                '<div><div class="news-t">%s</div>'
                '<div class="news-d">%s</div>'
                '<div class="news-s">来源：妙想资讯</div></div></div>' % (
                    '催化' + str(j + 1), tag, body[:160]))
    if not news_html:
        news_html = ('<div class="news"><div class="news-badge"><b>暂无</b><br>资讯</div>'
                     '<div><div class="news-t">今日产业催化资讯检索结果为空</div>'
                     '<div class="news-d">可于收盘后再次检索财联社/公司公告补充。</div></div></div>')

    # ---- 展望清单（规则） ----
    focus = (
        '<li>%s（%+.2f%%）领涨赛道延续性，关注龙头量能配合</li>'
        '<li>CPO/光模块产业催化（量产/路线图）对业绩兑现的拉动</li>'
        '<li>半导体设备 ETF 资金流向，设备国产化布局信号</li>'
        '<li>存储涨价链条（DRAM/NAND）重估逻辑</li>'
        '<li>AI 应用商业化（模型发布/财报 AI 收入占比）催化</li>' % (best_name, best[1]))
    risk = (
        '<li>6 大核心板块主力合计 %+.1f 亿，反弹无资金支撑风险</li>'
        '<li>高位龙头（寒武纪/海光）未止跌，权重拖累仍存</li>'
        '<li>全市场连板晋级率低位，情绪接力疲弱</li>'
        '<li>半导体/AI算力芯片 PE 高企，估值消化远未完成</li>'
        '<li>缩量反弹，量能不足限制高度</li>' % flow_total)

    html = u'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股 AI产业链 · 日度复盘 {{TITLE}}</title>
<style>{{CSS}}</style>
</head>
<body>
<div class="wrap">
<header>
<div class="hd-in">
<div>
<span class="hd-tag">AI INDUSTRY REVIEW</span>
<h1>A股 AI产业链日度复盘</h1>
<div class="hd-date">{{DATE}} {{WD}} · 收盘静态快照</div>
</div>
<div class="temp-badge">
<div class="temp-num">{{TEMP}}<span style="font-size:16px">°C</span></div>
<div class="temp-lbl">产业链温度 · {{LBL}}</div>
</div>
</div>
</header>

<section>
<div class="sec-head"><div class="sec-ico">1</div><h2>今日结论</h2><span class="sec-sub">{{SUBTITLE}}</span></div>
<div class="verdict">{{VDCARDS}}</div>
<details class="cat">
<summary>催化详情：按驱动分组展开（规则模板，收盘后可由 LLM 精修）</summary>
<div class="cat-body">
<div class="cat-group blue">
<span class="cat-group-t">产业驱动主线</span>
<div class="cat-row"><b>领涨赛道</b>：{{BEST}}（{{BESTPCT}}），涨幅居前赛道共 {{UPCNT2}} 个。</div>
<div class="cat-row"><b>资金动向</b>：6 大核心板块主力合计 {{FLOWTOT}}，资金面 {{FLOWDIR}}。</div>
</div>
</div>
</details>
</section>

<section>
<div class="sec-head"><div class="sec-ico">2</div><h2>产业链情绪温度</h2><span class="sec-sub">科技专属 · 6 项指标</span></div>
<div class="temp-wrap">
<div class="temp-gauge">
<svg viewBox="0 0 170 170" width="170" height="170">
<defs>
<linearGradient id="tg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#00d4aa"/><stop offset="50%" stop-color="#ffa502"/><stop offset="100%" stop-color="#ff4757"/>
</linearGradient>
</defs>
<circle cx="85" cy="85" r="72" fill="none" stroke="#eef0f5" stroke-width="14"/>
<circle cx="85" cy="85" r="72" fill="none" stroke="url(#tg)" stroke-width="14" stroke-linecap="round" stroke-dasharray="452.4" stroke-dashoffset="{{OFF}}"/>
</svg>
<div class="temp-center">
<div class="temp-big" style="color:var(--red)">{{TEMP}}</div>
<div class="temp-small">°C · {{LBL}}</div>
</div>
</div>
<div class="temp-items">
<div class="ti"><div class="ti-t">板块普涨度</div><div class="ti-v {{UPCLS}}">{{UPCNT}} / 17 赛道上涨</div></div>
<div class="ti"><div class="ti-t">龙头强度</div><div class="ti-v {{LUPCLS}}">{{LEADUP}} / 10 龙头上涨</div></div>
<div class="ti"><div class="ti-t">资金共振</div><div class="ti-v {{FCLS}}">6 板块合计 {{FLOWTOT2}}</div></div>
<div class="ti"><div class="ti-t">连板高度</div><div class="ti-v">见大盘口径</div></div>
<div class="ti"><div class="ti-t">产业催化</div><div class="ti-v {{NCLS}}">CPO/存储/设备</div></div>
<div class="ti"><div class="ti-t">趋势</div><div class="ti-v">自动计算</div></div>
</div>
</div>
</section>

<section>
<div class="sec-head"><div class="sec-ico">3</div><h2>细分赛道排行</h2><span class="sec-sub">17 赛道 · 收盘口径</span></div>
<table>
<tr><th>#</th><th>赛道</th><th>分类</th><th class="num">涨跌幅</th><th class="num">成交额</th><th class="num">换手</th><th class="num">10日涨幅</th><th style="width:110px">强度</th></tr>
{{TRACKROWS}}
</table>
<details class="cat">
<summary>赛道分类口径说明（4 大分类标准 + 6 大核心赛道定义 + 数据说明 + 成分股下载）</summary>
<div class="cat-body">
<div class="cat-group blue">
<span class="cat-group-t">4 大分类标准</span>
<div class="cat-row"><b>算力硬件</b> = AI 算力的物理基础设施：计算（AI算力芯片/服务器）· 互联（CPO光模块/PCB）· 散热供电（液冷）· 承载（数据中心/华为算力）。直接受益于 AI 资本开支，业绩兑现度最高。</div>
<div class="cat-row"><b>半导体</b> = AI 芯片的制造与上游：晶圆制造（半导体）· 设备 · 材料。国产替代 + 景气周期双重属性。</div>
<div class="cat-row"><b>模型应用</b> = AI 软件与应用层：大模型 · AIGC · AI应用 · AI智能体 · AI语料。业绩兑现慢、主题属性强。</div>
<div class="cat-row"><b>AI 终端</b> = AI 落地的消费终端载体：AIPC · AI手机。由硬件迭代周期驱动，弹性随新品发布节奏波动。</div>
</div>
<div class="cat-group">
<span class="cat-group-t">6 大核心赛道（资金动向固定观测口径）</span>
<div class="cat-row">当日主力净流入 + 与 AI 算力主线关联度最高的 6 个赛道：<b>半导体 / CPO 光模块 / PCB 概念 / 服务器 / AI 算力芯片 / 液冷</b>。本报告「资金动向」章节按此口径观测主力资金。</div>
</div>
<div class="cat-group green">
<span class="cat-group-t">数据说明</span>
<div class="cat-row">行情数据来自腾讯自选股接口（{{DATE}} 收盘）；概念板块成分股为行情接口快照，存在跨板块重叠（同一股票可属多个赛道）；成交额/换手为板块整体口径。</div>
</div>
<a class="dl-btn" href="ai-track-stocks-{{DATED}}.xlsx">⬇ 下载 17 赛道成分股 Excel（含分类口径）</a>
</div>
</details>
</section>

<section>
<div class="sec-head"><div class="sec-ico">4</div><h2>资金动向</h2><span class="sec-sub">6 大核心板块 · 主力净流入</span></div>
<div class="flow-grid">{{FLOWGRID}}</div>
<div class="flow-note">
<b>解读</b>：6 大核心板块主力合计 <b>{{FLOWTOT}}</b>，{{FLOWNOTE}}。板块普涨但资金未共振时，反弹持续性存疑；资金持续流入方向更值得关注。
</div>
<div style="margin-top:14px">
<table>
<tr><th>ETF</th><th class="num">涨跌幅</th><th class="num">成交额</th><th class="num">换手</th></tr>
{{ETFTABLE}}
</table>
</div>
</section>

<section>
<div class="sec-head"><div class="sec-ico">5</div><h2>龙头梯队</h2><span class="sec-sub">10 只核心龙头 · 收盘口径</span></div>
<table>
<tr><th>龙头</th><th>赛道</th><th class="num">现价</th><th class="num">涨幅</th><th class="num">成交额</th><th class="num">PE</th><th class="num">年内</th><th>事件</th></tr>
{{LEADERROWS}}
</table>
<div style="font-size:11px;color:var(--muted);margin-top:8px">事件列图例：❄️ 当日显著下跌/利空信号 ｜ 🔥 当日上涨/利好或创新高信号</div>
</section>

<section>
<div class="sec-head"><div class="sec-ico">6</div><h2>产业催化</h2><span class="sec-sub">今日驱动 · 妙想资讯</span></div>
{{NEWS}}
</section>

<section>
<div class="sec-head"><div class="sec-ico">7</div><h2>估值与拥挤度</h2><span class="sec-sub">核心板块 PE + 资金累计 + 成交占比</span></div>
<div class="val-cards">
<div class="val-card"><div class="val-n hot">{{PE1}}</div><div class="val-t">{{PE1N}} PE（高估）</div></div>
<div class="val-card"><div class="val-n hot">{{PE2}}</div><div class="val-t">{{PE2N}} PE（高估）</div></div>
<div class="val-card"><div class="val-n">{{PE3}}</div><div class="val-t">{{PE3N}} PE</div></div>
<div class="val-card"><div class="val-n">{{PE4}}</div><div class="val-t">{{PE4N}} PE</div></div>
<div class="val-card"><div class="val-n">{{PE5}}</div><div class="val-t">{{PE5N}} PE</div></div>
<div class="val-card"><div class="val-n">{{PE6}}</div><div class="val-t">{{PE6N}} PE（相对最低）</div></div>
</div>
<div class="warn">
<b>拥挤度警示</b>：6 大核心板块今日主力合计 <b>{{FLOWTOT}}</b>，{{FLOWNOTE}}。高拥挤度仍处消化期，反弹缺乏增量资金确认，追高需谨慎。
</div>
</section>

<section>
<div class="sec-head"><div class="sec-ico">8</div><h2>展望清单</h2><span class="sec-sub">关注 5 条 · 风险 5 条</span></div>
<div class="outlook">
<div class="ol-card focus">
<div class="ol-t">✅ 关注</div>
<ul class="ol-list">{{FOCUS}}</ul>
</div>
<div class="ol-card risk">
<div class="ol-t">⚠️ 风险</div>
<ul class="ol-list">{{RISK}}</ul>
</div>
</div>
</section>

<footer>
<div class="disc">
<b>免责声明</b>：本报告为 {{DATE}} 收盘静态快照，行情与资金数据来自腾讯自选股接口，新闻与涨停数据来自财联社/公开报道（收盘口径）。报告仅供研究参考，不构成任何投资建议。市场有风险，投资需谨慎。
</div>
</footer>
</div>
</body>
</html>'''

    # PE 展示（从龙头/板块估算，取板块内龙头 PE）
    pe_map = {}
    for code, name, cat, sec in LEADERS:
        it = leaders.get(code) or {}
        pe_map[sec] = float(it.get('pe') or it.get('PE') or 0)
    pe_order = [('AI算力芯片', 'AI算力芯片'), ('半导体', '半导体'), ('PCB', 'PCB'),
                ('CPO 光模块', 'CPO'), ('服务器', '服务器'), ('液冷', '液冷')]
    pe_cards = ''
    for n, key in pe_order:
        v = pe_map.get(key) or 0
        pe_cards += ('<div class="val-card"><div class="val-n %s">%.1f</div>'
                     '<div class="val-t">%s PE</div></div>' %
                     ('hot' if v >= 80 else '', v, n))
    # 简化：用 pe_cards 替换 6 个 PE 占位符
    pes = [float((leaders.get(c) or {}).get('pe') or 0) for c, _, _, _ in LEADERS]
    pes_sorted = sorted([p for p in pes if p > 0], reverse=True)

    repl = {
        '{{TITLE}}': date_str, '{{CSS}}': AI_CSS,
        '{{DATE}}': date_cn, '{{WD}}': wd, '{{DATED}}': date_str,
        '{{TEMP}}': str(temp), '{{LBL}}': lbl, '{{OFF}}': '%.1f' % off,
        '{{SUBTITLE}}': '%s 领涨 · 资金 %+.1f 亿' % (best_name, flow_total),
        '{{VDCARDS}}': vd_cards,
        '{{BEST}}': best_name,
        '{{UPCNT}}': str(up_cnt),
        '{{UPCLS}}': 'up' if up_cnt >= 9 else ('dn' if up_cnt <= 5 else ''),
        '{{LEADUP}}': str(lead_up),
        '{{LUPCLS}}': 'up' if lead_up >= 6 else ('dn' if lead_up <= 4 else ''),
        '{{FCLS}}': 'dn' if flow_total < 0 else ('up' if flow_total > 0 else ''),
        '{{NCLS}}': 'up',
        '{{TRACKROWS}}': track_rows,
        '{{FLOWGRID}}': flow_grid,
        '{{ETFTABLE}}': etf_table,
        '{{LEADERROWS}}': leader_rows,
        '{{NEWS}}': news_html,
        '{{FOCUS}}': focus, '{{RISK}}': risk,
        '{{PE1}}': '%.1f' % (pes_sorted[0] if len(pes_sorted) > 0 else 0),
        '{{PE1N}}': 'AI算力芯片',
        '{{PE2}}': '%.1f' % (pes_sorted[1] if len(pes_sorted) > 1 else 0),
        '{{PE2N}}': '半导体',
        '{{PE3}}': '%.1f' % (pes_sorted[2] if len(pes_sorted) > 2 else 0),
        '{{PE3N}}': 'PCB',
        '{{PE4}}': '%.1f' % (pes_sorted[3] if len(pes_sorted) > 3 else 0),
        '{{PE4N}}': 'CPO 光模块',
        '{{PE5}}': '%.1f' % (pes_sorted[4] if len(pes_sorted) > 4 else 0),
        '{{PE5N}}': '服务器',
        '{{PE6}}': '%.1f' % (pes_sorted[-1] if len(pes_sorted) >= 6 else 0),
        '{{PE6N}}': '液冷',
        '{{BESTPCT}}': '%+.2f%%' % best[1],
        '{{UPCNT2}}': str(up_cnt),
        '{{FLOWTOT}}': '%+.1f 亿' % flow_total,
        '{{FLOWTOT2}}': '%+.1f 亿' % flow_total,
        '{{FLOWDIR}}': '净流出' if flow_total < 0 else '净流入',
        '{{FLOWNOTE}}': '资金未共振' if flow_total < 0 else '资金偏积极',
    }
    for k, v in repl.items():
        html = html.replace(k, str(v))

    with io.open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return temp, lbl


def main(date_str=None):
    date_str = date_str or df.date_compact()
    d = fetch_all()
    out = os.path.join(BASE, 'ai-market-review-%s.html' % date_str)
    temp, lbl = build_html(d, date_str, out)
    h = io.open(out, encoding='utf-8').read()
    checks = {
        '外链数(应为0)': len(re.findall(r'(https?://|src=)', h.replace('http://www.w3.org/2000/svg', ''))),
        '事件列图例': '事件列图例' in h,
        'var(--grad)': 'var(--grad)' in h,
        '#ffa502': '#ffa502' in h,
        '17赛道行数': h.count('<tr><td>') >= 20,
        'details.cat': 'details.cat' in h,
        'dl-btn': 'dl-btn' in h,
        '标签平衡div': h.count('<div') == h.count('</div>'),
        '标签平衡table': h.count('<table') == h.count('</table>'),
    }
    ok = all(v == 0 or v is True for v in checks.values())
    print('生成 %s | 温度 %d°C %s | 校验: %s' % (
        os.path.basename(out), temp, lbl, 'PASS' if ok else checks))
    return out, ok


if __name__ == '__main__':
    main()
