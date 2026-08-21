# -*- coding: utf-8 -*-
"""云端 LLM 分析文字生成模块。

- 调用 OpenAI 兼容 API（DeepSeek 等）生成报告各节分析文字
- API 不可用时回退到规则模板（基于涨跌数据的机械结论，保证报告不中断）
- 环境变量：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（未配置则纯规则模板）
"""
import io, json, os, re
import urllib.request

API_KEY = os.environ.get('LLM_API_KEY', '')
BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.deepseek.com')
MODEL = os.environ.get('LLM_MODEL', 'deepseek-chat')


def llm_enabled():
    return bool(API_KEY)


def chat(messages, max_tokens=800, temperature=0.5, timeout=60):
    """调用 OpenAI 兼容 chat completions；失败返回 ''"""
    if not API_KEY:
        return ''
    url = BASE_URL.rstrip('/') + '/chat/completions'
    body = json.dumps({
        'model': MODEL,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
    }).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + API_KEY,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode('utf-8'))
        return (d.get('choices') or [{}])[0].get('message', {}).get('content', '') or ''
    except Exception:
        return ''


def gen_analysis(section, data_summary, max_tokens=600):
    """生成一段分析文字。data_summary 为结构化事实（JSON 文本）。
    section: 段落主题（如 '大盘情绪解读'）。API 失败回退规则模板。"""
    if API_KEY:
        msg = chat([
            {'role': 'system', 'content':
                '你是A股收盘复盘分析师。基于给定事实数据，用中文写一段简洁专业的市场分析，'
                '120字以内，只陈述数据支持的观点，不预测、不荐股，结尾不出现「以上」等字样。'},
            {'role': 'user', 'content': '主题：%s\n数据：%s' % (section, data_summary)},
        ], max_tokens=max_tokens)
        if msg.strip():
            return re.sub(r'\s+', ' ', msg).strip()
    return rule_text(section, data_summary)


# ---------- 规则模板兜底 ----------
def rule_text(section, data_summary):
    s = data_summary
    try:
        if section == '大盘情绪解读':
            up = int(s.get('upCount', 0)); dn = int(s.get('downCount', 0))
            lim = int(s.get('upLimitCount', 0)); dlim = int(s.get('downLimitCount', 0))
            if lim >= 60 and up > dn:
                return '市场情绪高温：涨停%d家、跌停%d家，上涨家数占优，赚钱效应显著，短线资金活跃。' % (lim, dlim)
            if lim >= 30:
                return '市场情绪偏热：涨停%d家、跌停%d家，结构性机会集中在主线板块，注意分化风险。' % (lim, dlim)
            if lim >= 10:
                return '市场情绪中性：涨停%d家、跌停%d家，多空基本均衡，题材轮动加快，宜聚焦确定性主线。' % (lim, dlim)
            return '市场情绪偏冷：涨停仅%d家、跌停%d家，赚钱效应不足，资金观望情绪浓，等待新主线出现。' % (lim, dlim)
        if section == '主线研判':
            top = (s.get('top_sector') or '') + '领涨'
            money = s.get('money_sector') or ''
            return '今日相对强势方向：%s；资金主要流入：%s。需结合涨停梯队与量能确认是否形成主线共振。' % (top, money)
        if section == 'AI硬件主线':
            return 'AI算力硬件方向维持主线地位，关注光模块/PCB/服务器资金延续性与龙头走势。'
        if section == '应用滞涨':
            return 'AI应用端整体滞涨，资金仍偏好确定性硬件环节，应用兑现节奏偏慢。'
        if section == '催化共振':
            return '产业催化（财报/新品/政策）带动相关板块表现，留意催化对资金流向的引导作用。'
    except Exception:
        pass
    return '（规则模板结论：基于当日数据自动生成）'


def gen_verdict(data_summary, max_tokens=400):
    """生成报告顶部定性结论"""
    return gen_analysis('大盘情绪解读', data_summary, max_tokens)


if __name__ == '__main__':
    print('LLM enabled:', llm_enabled())
    demo = {'upCount': 120, 'downCount': 80, 'upLimitCount': 45, 'downLimitCount': 8}
    print(gen_analysis('大盘情绪解读', demo))
