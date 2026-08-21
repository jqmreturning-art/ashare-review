# -*- coding: utf-8 -*-
"""云端主流程脚本。

- main_us.py: 美股日报（07:00 北京）
- main_cn.py: A股大盘 + AI 产业链 + Excel（16:00 北京）
- 交易日门禁 → 取数 → 生成 → 校验 → git 推送 → 摘要
- 本地/云端通用：通过环境变量 CLOUD_WORKDIR 指定仓库根目录
"""
import io, json, os, re, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get('CLOUD_REPO', os.path.abspath(os.path.join(BASE, '..')))


def run(cmd, cwd=None, timeout=300):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding='utf-8', timeout=timeout)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except Exception as e:
        return -1, str(e)


def is_trading_day_cn():
    """A股交易日门禁：指数数据日期必须等于今天（北京）且涨跌家数>100。
    防止周末/节假日误判（接口可能返回上一交易日数据）。"""
    sys.path.insert(0, BASE)
    import data_fetch as df
    it = df.quote('sh000001').get('sh000001') or {}
    data_date = (it.get('time') or '')[:10]
    if data_date != df.today_cn():
        return False
    cd = df.changedist()
    total = (cd.get('upCount') or 0) + (cd.get('downCount') or 0) + (cd.get('flatCount') or 0)
    return total > 100


def git_push(msg, date_str):
    """推送报告到仓库并 push origin main。
    环境变量 CLOUD_SKIP_PUSH=1 时只 commit 不 push（由 workflow 统一推送）。"""
    code, out = run(['git', 'add', '-A'], cwd=REPO)
    if code != 0:
        return False, 'git add 失败: ' + out[-300:]
    code, out = run(['git', 'commit', '-m', msg], cwd=REPO)
    if code != 0 and 'nothing to commit' not in out:
        return False, 'git commit 失败: ' + out[-300:]
    if os.environ.get('CLOUD_SKIP_PUSH') == '1':
        return True, 'commit 完成（跳过 push，由 workflow 推送）'
    code, out = run(['git', 'push', 'origin', 'main'], cwd=REPO, timeout=180)
    if code != 0:
        return False, 'git push 失败: ' + out[-400:]
    return True, 'ok'


def copy_report(src, dst):
    """拷贝报告到仓库对应子目录（index.html 覆盖 + 日期版归档）"""
    os.makedirs(dst, exist_ok=True)
    code, out = run(['cp', src, os.path.join(dst, 'index.html')])
    if code != 0:
        return False
    code, out = run(['cp', src, os.path.join(dst, os.path.basename(src))])
    return code == 0


def main_cn(date_str=None):
    sys.path.insert(0, BASE)
    import data_fetch as df
    import gen_market_report, gen_ai_report
    date_str = date_str or df.date_compact()

    # 1. 门禁
    if not is_trading_day_cn():
        print('今日非交易日（涨跌家数=0），跳过')
        return 0

    # 2. 生成大盘报告
    mkt_out, mkt_ok = gen_market_report.main(date_str)
    # 3. 生成 AI 报告
    ai_out, ai_ok = gen_ai_report.main(date_str)

    if not (mkt_ok and ai_ok):
        print('报告校验失败，不推送')
        return 1

    # 4. 拷贝到仓库
    copy_report(mkt_out, os.path.join(REPO, 'market-review'))
    copy_report(ai_out, os.path.join(REPO, 'ai-review'))
    # Excel 若存在则一并拷贝（由 gen_track_excel 生成）
    xlsx = os.path.join(BASE, 'ai-track-stocks-%s.xlsx' % date_str)
    if os.path.exists(xlsx):
        run(['cp', xlsx, os.path.join(REPO, 'ai-review', os.path.basename(xlsx))])

    # 5. 推送
    ok, msg = git_push('A股复盘 %s: 大盘+AI产业链 (云端自动)' % date_str, date_str)
    print('推送:', '成功' if ok else '失败: ' + msg)
    print('大盘温度:', gen_market_report.calc_temp  # noqa
          if False else '见报告')
    return 0 if ok else 1


def main_us(date_str=None):
    """美股日报：占位——云端暂以 A股为准，美股报告后续可接入
    返回 0 表示成功（无报告生成时返回 0 但不推送）"""
    print('美股日报云端任务：预留接入点（当前 A股流程已覆盖核心需求）')
    return 0


if __name__ == '__main__':
    kind = sys.argv[1] if len(sys.argv) > 1 else 'cn'
    date_str = sys.argv[2] if len(sys.argv) > 2 else None
    rc = main_cn(date_str) if kind == 'cn' else main_us(date_str)
    sys.exit(rc)
