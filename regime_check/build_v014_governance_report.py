# -*- coding: utf-8 -*-
"""
v0.14 误报治理报告生成（crisis_falsealarm_governance_v014_report.html）
离线单文件、全中文、可见文本零拉丁（工程字段只放悬停 title）。
"""
import html as h
import json
import re
from datetime import datetime

import pandas as pd

BASE = "."
OUT = f"{BASE}/outputs"

summary = pd.read_csv(f"{OUT}/regime_v014_governance_summary.csv")
matrix = pd.read_csv(f"{OUT}/regime_v014_governance_matrix.csv")
episodes = pd.read_csv(f"{OUT}/regime_v014_governance_episodes.csv")
sup = pd.read_csv(f"{OUT}/regime_v014_governance_suppressed.csv")
manifest = json.load(open(f"{OUT}/regime_v014_manifest.json", encoding="utf-8"))

for c in ("first_offset_median", "delay_median", "false_days_per_year",
          "false_episodes_per_year", "alarm_day_share"):
    summary[c] = pd.to_numeric(summary[c], errors="coerce")
matrix["raw_first_offset"] = pd.to_numeric(matrix["raw_first_offset"], errors="coerce")
matrix["gov_first_offset"] = pd.to_numeric(matrix["gov_first_offset"], errors="coerce")
matrix["delay_vs_raw"] = pd.to_numeric(matrix["delay_vs_raw"], errors="coerce")
matrix["n_alarm_days_in_window"] = pd.to_numeric(matrix["n_alarm_days_in_window"], errors="coerce")

VNAME = {r["variant"]: r["variant_name"] for _, r in summary.iterrows()}
sel_id = manifest["summary"]["selected_variant"]
sel = summary[summary["variant"] == sel_id].iloc[0]
g0 = summary[summary["variant"] == "G0"].iloc[0]

def fnum(x, nd=1):
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x:,.{nd}f}"

out = []
def a(s):
    out.append(s)

# ---------------- 头部 ----------------
a('<html><head><meta charset="utf-8"><title>误报治理——警报态撤销与冷却期 · v0.14</title><style>')
a('body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#f7f8fa;color:#222;margin:0;padding:28px 5%;}'
  'h1{font-size:25px;margin:0 0 6px} h2{font-size:19px;margin:30px 0 10px;border-left:4px solid #4a6fa5;padding-left:10px;}'
  'h3{font-size:15px;margin:18px 0 8px;color:#444;}'
  '.meta{color:#777;font-size:12.5px;margin-bottom:18px;line-height:1.9;}'
  '.tiles{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0;}'
  '.tile{background:#fff;border:1px solid #e3e6ec;border-radius:10px;padding:14px 18px;min-width:150px;flex:1;}'
  '.tile .nm{font-size:12px;color:#888;} .tile .vl{font-size:26px;font-weight:700;margin:4px 0;}'
  '.tile .sm{font-size:11.5px;color:#999;} .vl.mid{color:#b25a00;} .vl.good{color:#b23a3a;} .vl.ok{color:#2a7a4b;}'
  '.warn{background:#fff7f0;border:1px solid #f0c9a8;border-radius:10px;padding:14px 18px;margin:14px 0;font-size:13.5px;line-height:2.05;}'
  '.warn b{color:#b25a00;}'
  '.note{background:#fff;border:1px solid #e3e6ec;border-radius:10px;padding:12px 16px;margin:10px 0;font-size:13px;line-height:1.95;color:#555;}'
  'table{border-collapse:collapse;width:100%;background:#fff;font-size:12.5px;margin:8px 0;}'
  'th,td{border:1px solid #e3e6ec;padding:6px 8px;text-align:center;}'
  'th{background:#eef1f6;position:sticky;top:0;}'
  'td.lft,th.lft{text-align:left;} tr.hl{background:#fdf3e3;} tr.g0{background:#f2f4f8;}'
  'details{background:#fff;border:1px solid #e3e6ec;border-radius:10px;padding:10px 16px;margin:12px 0;}'
  'summary{cursor:pointer;font-weight:600;font-size:14px;}'
  '.dim{color:#999;} .up{color:#b23a3a;} .dn{color:#2a7a4b;}'
  '.filt{margin:10px 0;font-size:13px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;}'
  'select,input{padding:5px 8px;border:1px solid #ccd2dc;border-radius:6px;font-size:13px;}'
  '.scroll{max-height:520px;overflow:auto;border:1px solid #e3e6ec;border-radius:8px;}'
  'footer{margin:34px 0 10px;color:#999;font-size:11.5px;line-height:1.9;}'
  '</style></head><body>')

a('<h1>误报治理——警报态撤销与冷却期</h1>')
a('<div class="meta">产品二触发层 · 预登记 v0.14 · 底座＝第十三版实用候选（45/45 全识别词表）冻结不动，只加警报态治理层 · '
  '45 个冻结统计事件 × 9 个治理变体 · 全部为样本内描述性对账 · 无随机数、全流程确定性（双跑字节一致）</div>')

# ---------------- 大数字 ----------------
a('<div class="tiles">')
a(f'<div class="tile"><div class="nm">误报日 / 年（选定行）</div><div class="vl mid">{fnum(sel["false_days_per_year"])}</div>'
  f'<div class="sm">原始 {fnum(g0["false_days_per_year"])} → 降 {(1-sel["false_days_per_year"]/g0["false_days_per_year"])*100:.0f}%</div></div>')
a(f'<div class="tile"><div class="nm">误报段 / 年（碎片化）</div><div class="vl good">{fnum(sel["false_episodes_per_year"])}</div>'
  f'<div class="sm">原始 {fnum(g0["false_episodes_per_year"])} → 降 {(1-sel["false_episodes_per_year"]/g0["false_episodes_per_year"])*100:.0f}%，频闪治好</div></div>')
a(f'<div class="tile"><div class="nm">警戒态占历史</div><div class="vl mid">{fnum(sel["alarm_day_share"]*100)}%</div>'
  f'<div class="sm">原始 {fnum(g0["alarm_day_share"]*100)}% → 只压下小半步</div></div>')
a(f'<div class="tile"><div class="nm">完全识别</div><div class="vl ok">45 / 45</div>'
  f'<div class="sm">硬红线守住（九个变体全部守住）</div></div>')
a(f'<div class="tile"><div class="nm">提前档（保护时点）</div><div class="vl mid">{int(sel["n_pre"])} / 45</div>'
  f'<div class="sm">原始 45 → 5 个事件失去提前量（价码）</div></div>')
a('</div>')

# ---------------- 丑话 ----------------
a('<div class="warn"><b>两句丑话（先读）：</b><br>'
  '<b>一、撤销单独用，误报日反而暴增。</b>只撤销不冷却（无冷却档）误报日从 62.0 涨到 107.1（收复静默）/ 121.2（纯静默）——'
  '迟滞合并把频闪并成整段，段内静默日全部计为警报日。撤销的功劳只有「不再频闪」（段/年 21.6 → 11.7 / 8.7），'
  '<b>省误报日要靠冷却期</b>，而冷却 5 日、10 日都不够——只有冷却 20 日才把误报日压到原始以下（51.5）。<br>'
  '<b>二、省下的 10.5 个误报日/年是用保护时点换的。</b>冷却二十日档（选定行）5 个事件失去提前量：'
  '107 号拖 15 日落到损伤窗、116 号拖 20 日、5 号拖 2 日、8 号拖 20 日、17 号拖 26 日落到窗内；'
  '合计 18 个事件首响被拖延，440 个识别窗内原始命中被冷却吃掉（警报在，但响得晚）。'
  '预登记的选定规则（识别 45/45 硬资格 → 误报日/年取小）机械选出此行——但价码必须摆在台面上。</div>')

# ---------------- 九变体全表 ----------------
a('<h2>九个治理变体同表（无论好坏不删）</h2>')
a('<div class="note">变体 = 撤销规则 × 冷却期。撤销规则甲＝收复静默（连续 3 日无命中且 3 日收盘均站上 250 日均线，或连续 5 日无命中，先到先撤）；'
  '乙＝纯静默（连续 5 日无命中即撤）。冷却期＝撤销后连续若干个交易日原始命中不点燃警报（实盘无事后视角，不对识别窗豁免）。'
  '选定规则（计算前固定）：硬资格＝识别 45/45，合格者误报日/年取小，并列比提前数、段/年、冷却短。</div>')
a('<table><tr><th>变体</th><th>撤销规则</th><th>冷却</th><th>识别</th><th>提前</th><th>窗内</th><th>损伤窗</th>'
  '<th>误报日/年</th><th>误报段/年</th><th>警戒占比</th><th>被拖延事件</th><th>窗内抑制命中</th><th>窗内撤防</th><th>选定</th></tr>')
for _, r in summary.iterrows():
    cls = ' class="hl"' if r["variant"] == sel_id else (' class="g0"' if r["variant"] == "G0" else "")
    rule_cn = {"A": "收复静默", "B": "纯静默"}.get(r["revocation_rule"], "—")
    a(f'<tr{cls}><td class="lft">{r["variant_name"]}</td><td>{rule_cn}</td>'
      f'<td>{"无" if r["cooldown_days"]==0 else str(int(r["cooldown_days"]))+" 日"}</td>'
      f'<td>{int(r["identified"])}/45</td><td>{int(r["n_pre"])}</td><td>{int(r["n_in_window"])}</td><td>{int(r["n_damage"])}</td>'
      f'<td>{fnum(r["false_days_per_year"])}</td><td>{fnum(r["false_episodes_per_year"])}</td>'
      f'<td>{fnum(r["alarm_day_share"]*100)}%</td><td>{int(r["n_delayed_events"])}</td>'
      f'<td>{int(r["suppressed_hits_in_window"])}</td><td>{int(r["n_revoke_in_window"])}</td>'
      f'<td>{"★" if r["variant"]==sel_id else ""}</td></tr>')
a('</table>')
a('<div class="note"><b>读表一句话：</b>九行识别全是 45/45（召回地基没塌）；但误报日/年只有「收复静默·冷却二十日」一行低于原始（51.5 &lt; 62.0），'
  '其余全部高于原始——<b>误报日总量不是撤销能治的，是长冷却治的；而长冷却是拿提前量换的。</b>'
  '误报段/年（碎片化）所有治理行都大幅优于原始（21.6 → 4.8～11.7），这一项治理是稳赚的。</div>')

# ---------------- 机制图 ----------------
a('<h2>警报态治理机制（状态机）</h2>')
a('<div class="note">底座是冻结的原始命中掩码（实用候选词表），治理层只改「警报态」的开合逻辑：'
  '命中点燃 → 开态持续 → 撤销条件满足则熄火 → 冷却期内再响不点燃 → 冷却结束恢复。</div>')
a('<svg viewBox="0 0 900 240" style="width:100%;max-width:900px;background:#fff;border:1px solid #e3e6ec;border-radius:10px;">'
  '<rect x="30" y="90" width="120" height="60" rx="10" fill="#eef1f6" stroke="#4a6fa5" stroke-width="2"/>'
  '<text x="90" y="118" text-anchor="middle" font-size="15" fill="#333">关（静默）</text>'
  '<text x="90" y="138" text-anchor="middle" font-size="11" fill="#888">不计警报日</text>'
  '<line x1="150" y1="120" x2="238" y2="120" stroke="#4a6fa5" stroke-width="2.5" marker-end="url(#ar)"/>'
  '<text x="194" y="106" text-anchor="middle" font-size="12" fill="#b25a00">原始命中</text>'
  '<text x="194" y="146" text-anchor="middle" font-size="11" fill="#888">且不在冷却期</text>'
  '<rect x="240" y="90" width="150" height="60" rx="10" fill="#fdeaea" stroke="#b23a3a" stroke-width="2.5"/>'
  '<text x="315" y="118" text-anchor="middle" font-size="15" fill="#333">开（警报中）</text>'
  '<text x="315" y="138" text-anchor="middle" font-size="11" fill="#888">逐日计警报日</text>'
  '<line x1="390" y1="120" x2="478" y2="120" stroke="#b23a3a" stroke-width="2.5" marker-end="url(#ar)"/>'
  '<text x="434" y="96" text-anchor="middle" font-size="12" fill="#b25a00">撤销条件满足</text>'
  '<text x="434" y="152" text-anchor="middle" font-size="11" fill="#888">收复 3 日 或 静默 5 日</text>'
  '<rect x="480" y="90" width="140" height="60" rx="10" fill="#fff7e6" stroke="#c98a1b" stroke-width="2"/>'
  '<text x="550" y="118" text-anchor="middle" font-size="15" fill="#333">撤销（熄火）</text>'
  '<text x="550" y="138" text-anchor="middle" font-size="11" fill="#888">当日起不计警报</text>'
  '<line x1="620" y1="120" x2="708" y2="120" stroke="#c98a1b" stroke-width="2.5" marker-end="url(#ar)"/>'
  '<text x="664" y="106" text-anchor="middle" font-size="12" fill="#b25a00">冷却期</text>'
  '<text x="664" y="146" text-anchor="middle" font-size="11" fill="#888">0 / 5 / 10 / 20 日</text>'
  '<rect x="710" y="90" width="150" height="60" rx="10" fill="#eef1f6" stroke="#4a6fa5" stroke-width="2" stroke-dasharray="6 4"/>'
  '<text x="785" y="118" text-anchor="middle" font-size="15" fill="#333">回到关</text>'
  '<text x="785" y="138" text-anchor="middle" font-size="11" fill="#888">冷却内命中被吃掉</text>'
  '<path d="M 550 150 C 550 215, 315 215, 315 152" fill="none" stroke="#999" stroke-width="1.8" stroke-dasharray="5 4" marker-end="url(#ar2)"/>'
  '<text x="432" y="212" text-anchor="middle" font-size="11.5" fill="#888">冷却结束且再有原始命中 → 重新点燃</text>'
  '<path d="M 315 90 C 315 30, 664 30, 664 96" fill="none" stroke="#bbb" stroke-width="1.5" stroke-dasharray="4 4"/>'
  '<text x="490" y="36" text-anchor="middle" font-size="11.5" fill="#999">开态期间命中 → 静默计数清零，不会撤销</text>'
  '<defs><marker id="ar" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">'
  '<path d="M0,0 L9,4.5 L0,9 z" fill="#4a6fa5"/></marker>'
  '<marker id="ar2" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">'
  '<path d="M0,0 L9,4.5 L0,9 z" fill="#999"/></marker></defs></svg>')

# ---------------- 选定行价码 ----------------
a('<h2>选定行的价码：失去提前量与被拖延的事件</h2>')
sel_m = matrix[matrix["variant"] == sel_id].copy()
lost = sel_m[sel_m["tier"] != "提前"].sort_values("delay_vs_raw", ascending=False)
a(f'<h3>失去提前量的 {len(lost)} 个事件（预登记要求逐一点名）</h3>')
a('<table><tr><th>事件</th><th>起点</th><th>长度</th><th>真型</th><th>原始首响</th><th>治理首响</th><th>分档</th><th>拖延</th></tr>')
for _, r in lost.iterrows():
    a(f'<tr><td>{int(r["event_id"])}</td><td>{r["onset"]}</td><td>{int(r["event_len"])} 日</td><td>{r["true_type"]}</td>'
      f'<td>{int(r["raw_first_offset"])} 日</td><td>{int(r["gov_first_offset"])} 日</td>'
      f'<td class="up">{r["tier"]}</td><td class="up">{int(r["delay_vs_raw"])} 日</td></tr>')
a('</table>')
dly = sel_m[sel_m["delay_vs_raw"] > 0].sort_values("delay_vs_raw", ascending=False)
a(f'<h3>全部被拖延事件 {len(dly)} 个（含仍保住提前档的）</h3>')
a('<table><tr><th>事件</th><th>起点</th><th>真型</th><th>原始首响</th><th>治理首响</th><th>分档</th><th>拖延</th></tr>')
for _, r in dly.iterrows():
    cls = ' class="hl"' if r["tier"] != "提前" else ""
    a(f'<tr{cls}><td>{int(r["event_id"])}</td><td>{r["onset"]}</td><td>{r["true_type"]}</td>'
      f'<td>{int(r["raw_first_offset"])} 日</td><td>{int(r["gov_first_offset"])} 日</td>'
      f'<td>{r["tier"]}</td><td>{int(r["delay_vs_raw"])} 日</td></tr>')
a('</table>')
a('<div class="note">对照：冷却十日档（收复静默·冷却十日）11 个事件被拖延但<b>全部保住提前档</b>——'
  '拖延最重的 125 号（18 日）、122 号（11 日）、17 号（9 日）仍落在起点前。'
  '也就是说：<b>冷却十日是「保提前」的极限档，冷却二十日才跨过「真省误报日」的门槛</b>，两者之间就是本版的取舍区间。</div>')

# ---------------- 45×9 矩阵 ----------------
a('<h2>45 事件 × 9 变体命中时点全矩阵</h2>')
a('<div class="filt"><b>筛选：</b>'
  '<select id="f-variant"><option value="">全部变体</option>' +
  ''.join(f'<option value="{h.escape(vname)}">{h.escape(vname)}</option>' for vname in VNAME.values()) +
  '</select>'
  '<select id="f-tier"><option value="">全部分档</option><option>提前</option><option>窗内</option><option>损伤窗</option><option>漏</option></select>'
  '<input id="f-kw" placeholder="事件号或起点年份">'
  '<span id="f-count" class="dim"></span></div>')
a('<div class="scroll"><table id="evtbl"><tr><th>事件</th><th>起点</th><th>长度</th><th>真型</th><th>变体</th>'
  '<th>原始首响</th><th>治理首响</th><th>分档</th><th>拖延</th><th>窗内警报日</th></tr>')
for _, r in matrix.iterrows():
    kw = f'{int(r["event_id"])} {r["onset"]} {r["onset"][:4]}'
    raw_s = f'{int(r["raw_first_offset"])}' if r["raw_first_offset"] == r["raw_first_offset"] else "—"
    gov_s = f'{int(r["gov_first_offset"])}' if r["gov_first_offset"] == r["gov_first_offset"] else "—"
    dly_s = f'{int(r["delay_vs_raw"])}' if r["delay_vs_raw"] == r["delay_vs_raw"] else "—"
    cls = ' class="hl"' if r["tier"] != "提前" and r["variant"] == sel_id else ""
    a(f'<tr class="erow{"" if not cls else " hl"}" data-v="{h.escape(r["variant_name"])}" data-t="{r["tier"]}" data-k="{kw}">'
      f'<td>{int(r["event_id"])}</td><td>{r["onset"]}</td><td>{int(r["event_len"])} 日</td><td>{r["true_type"]}</td>'
      f'<td class="lft">{r["variant_name"]}</td><td>{raw_s}</td><td>{gov_s}</td><td>{r["tier"]}</td>'
      f'<td>{dly_s}</td><td>{int(r["n_alarm_days_in_window"])}</td></tr>')
a('</table></div>')
a('<div class="dim" style="font-size:11.5px;">首响与拖延的单位＝交易日；偏移负数＝在事件起点之前。'
  '「窗内警报日」＝识别窗内警报态为开的日数（保护覆盖的代理指标）。</div>')

# ---------------- 抑制审计 ----------------
a('<h2>冷却吃掉的命中——召回风险审计</h2>')
sel_sup = sup[sup["variant"] == sel_id]
sup_in = sel_sup[sel_sup["in_window"] == "是"]
a(f'<div class="note">选定行合计吃掉 <b>{len(sel_sup)}</b> 个原始命中日，其中落在识别窗内 <b>{len(sup_in)}</b> 个。'
  '被吃掉不等于丢事件——识别仍是 45/45（警报态在窗内总有开的日子），但意味着「警报响得更晚或更稀」。'
  '下表是窗内被吃最多的事件（前 12）。</div>')
vc = sup_in["event_id"].value_counts().head(12)
a('<table><tr><th>事件</th><th>起点</th><th>窗内被吃命中日</th><th>该事件治理首响</th><th>分档</th></tr>')
for eid, cnt in vc.items():
    row = sel_m[sel_m["event_id"] == eid].iloc[0]
    gov_s = f'{int(row["gov_first_offset"])} 日' if row["gov_first_offset"] == row["gov_first_offset"] else "—"
    a(f'<tr><td>{int(eid)}</td><td>{row["onset"]}</td><td>{int(cnt)}</td><td>{gov_s}</td><td>{row["tier"]}</td></tr>')
a('</table>')

# ---------------- 误报段结构 ----------------
a('<h2>误报段结构：从「频闪」到「整段」</h2>')
g0_ep = episodes[episodes["variant"] == "G0"]
sel_ep = episodes[episodes["variant"] == sel_id]
a('<table><tr><th>口径</th><th>原始（无治理）</th><th>选定行（收复静默·冷却二十日）</th></tr>'
  f'<tr><td class="lft">误报段合计</td><td>{len(g0_ep)}</td><td>{len(sel_ep)}</td></tr>'
  f'<tr><td class="lft">段长中位</td><td>{g0_ep["episode_len"].median():.0f} 日</td><td>{sel_ep["episode_len"].median():.0f} 日</td></tr>'
  f'<tr><td class="lft">最长段</td><td>{int(g0_ep["episode_len"].max())} 日</td><td>{int(sel_ep["episode_len"].max())} 日</td></tr>'
  f'<tr><td class="lft">长度 ≥5 日的段</td><td>{int((g0_ep["episode_len"]>=5).sum())}</td><td>{int((sel_ep["episode_len"]>=5).sum())}</td></tr>'
  f'<tr><td class="lft">误报日合计</td><td>{int(g0["false_days_total"])}</td><td>{int(sel["false_days_total"])}</td></tr></table>')
a('<div class="note">治理后段数从 559 降到 133（−76%），但单段更长（中位 2 日 → 7 日）——'
  '「顶部警觉频闪」被合并成整段误报：<b>操作者被吵醒的次数大减，但每次吵得更久</b>。'
  '对人工值守这是净改善；对自动处置（误报段一响就砍仓）则是另一种风险，接回端到端时必须带段级确认。</div>')

# ---------------- 撤销记账 ----------------
a('<h2>撤销与冷却记账</h2>')
a('<table><tr><th>变体</th><th>撤销次数</th><th>其中收复撤销</th><th>其中静默撤销</th><th>窗内撤防</th>'
  '<th>冷却吃掉命中</th><th>其中窗内</th></tr>')
for _, r in summary.iterrows():
    if r["variant"] == "G0":
        continue
    cls = ' class="hl"' if r["variant"] == sel_id else ""
    a(f'<tr{cls}><td class="lft">{r["variant_name"]}</td><td>{int(r["n_revoke"])}</td>'
      f'<td>{int(r["n_rec3"])}</td><td>{int(r["n_quiet5"])}</td><td>{int(r["n_revoke_in_window"])}</td>'
      f'<td>{int(r["suppressed_hits"])}</td><td>{int(r["suppressed_hits_in_window"])}</td></tr>')
a('</table>')
a('<div class="note">「窗内撤防」＝撤销发生在某个识别窗内部——真危机打到一半警报自己熄火了，是治理层最大的内在风险点（选定行 '
  f'{int(sel["n_revoke_in_window"])} 次）。好在冷却期内即使再响也不点燃只是延迟，识别没有丢；但接回损益端到端时这一项会直接体现为保护缺口。</div>')

# ---------------- 结论 ----------------
a('<h2>结论（直说）</h2>')
a('<div class="note">'
  '<b>一、治理层能做到什么：</b>碎片化治理是稳赢的——误报段/年 21.6 → 5.1，「频闪警铃」变成「整段误报」，值守体验大幅改善。'
  '误报日总量只降 17%（62.0 → 51.5），警戒占比只从 50.0% 压到 41.6%——「把警戒占比压下来」只走了小半步。<br>'
  '<b>二、治理层治不了什么：</b>误报日总量的根源是词表宽（半年在警戒态），撤销与冷却只是开合逻辑，动不了命中密度。'
  '再往下压要动词表（例如顶部警觉不单独触发）——那是改冻结词表，丢召回风险大，须另行预登记，本版不碰。<br>'
  '<b>三、按预登记规则选定「收复静默·冷却二十日」，但它的性价比要看用途：</b>'
  '求「不被频闪吵」→ 冷却十日档即可（误报段/年 6.9、45 个全保住提前档，代价是误报日比原始还多 14%）；'
  '求「误报日真降」→ 只有冷却二十日档，接受 5 个事件时点退让。两条路都合法，看产品定位。<br>'
  '<b>四、下一步（欠着）：</b>把治理后触发接回第十二版端到端损益引擎，看「误报少了、响得晚了」对四路径损益的净影响——'
  '本版只做触发层记账，不做损益模拟。</div>')

# ---------------- 预登记 ----------------
a('<details><summary>预登记与确定性</summary><div class="note">'
  '预登记于任何计算之前落盘（登记时间 2026-11-14T12:51:03+08:00，'
  '<span title="config/regime_trigger_governance_v0.14.toml">治理研究配置文件</span>）。'
  '完整脚本独立运行两次，数据产物字节一致（清单时间戳除外）；原始掩码行与第十三版实用候选汇总逐字段对账一致。'
  '无随机数、无自助、无置换；全流程确定性。词表、阈值、组合冻结不动；9 变体同表保留、无论好坏不删；'
  '不做显著性宣称；2025 测试集封存不动；不重判。</div></details>')

# ---------------- 页脚 ----------------
gat = manifest["created"]
try:
    dt = datetime.fromisoformat(gat)
    gat = f"{dt.year} 年 {dt.month} 月 {dt.day} 日"
except Exception:
    gat = ""
a(f'<footer>误报治理 · 预登记 v0.14 · 生成于 {gat} · 45 个冻结统计事件 × 9 个治理变体 · '
  '全流程确定性（双跑字节一致）· 全部为样本内反事实记账</footer>')

# ---------------- 脚本 ----------------
a('<script>'
  'const fv=document.getElementById("f-variant"),ft=document.getElementById("f-tier"),'
  'fk=document.getElementById("f-kw"),fc=document.getElementById("f-count");'
  'function apply(){const v=fv.value,t=ft.value,k=fk.value.trim();'
  'let n=0;document.querySelectorAll("#evtbl .erow").forEach(function(r){'
  'let ok=(!v||r.dataset.v===v)&&(!t||r.dataset.t===t)&&(!k||r.dataset.k.indexOf(k)>=0);'
  'r.style.display=ok?"":"none";if(ok)n++;});fc.textContent="共 "+n+" 行";} '
  'fv.addEventListener("change",apply);ft.addEventListener("change",apply);'
  'fk.addEventListener("input",apply);apply();'
  '</script>')
a('</body></html>')

html = "".join(out)
with open(f"{OUT}/crisis_falsealarm_governance_v014_report.html", "w", encoding="utf-8") as fh:
    fh.write(html)

# 验收：可见文本零拉丁
body = re.sub(r"<script.*?</script>", "", html, flags=re.S)
body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
titles = re.findall(r'title="([^"]*)"', body)
body2 = re.sub(r"<[^>]+>", " ", body)
body2 = h.unescape(body2)
bad = [b for b in re.findall(r"[A-Za-z]{2,}[A-Za-z0-9._-]*", body2) if not re.fullmatch(r"v\d+\.\d+", b)]
print("visible latin:", sorted(set(bad)) or "NONE")
print("title attrs:", len(titles))
for tag in ("table", "details", "select", "script", "div", "tr"):
    o = len(re.findall(fr"<{tag}[\s>]", html))
    c = len(re.findall(fr"</{tag}>", html))
    print(f"{tag}: {o}/{c} {'OK' if o == c else 'MISMATCH'}")
depth = 0
for m2 in re.finditer(r"<div[\s>]|</div>", html):
    depth += -1 if m2.group(0).startswith("</") else 1
print("final div depth:", depth)
print("erow rows:", len(re.findall(r'class="erow', html)))
print("size KB:", len(html.encode("utf-8")) // 1024)
