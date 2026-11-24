# -*- coding: utf-8 -*-
"""
v0.15 弱三中二最小补丁报告生成（crisis_lightpatch_v015_report.html）
离线单文件、全中文、可见文本零拉丁（工程字段只放悬停 title）。
"""
import html as h
import json
import re
from datetime import datetime

import pandas as pd

BASE = "."
OUT = f"{BASE}/outputs"

summary = pd.read_csv(f"{OUT}/regime_v015_lightpatch_summary.csv")
matrix = pd.read_csv(f"{OUT}/regime_v015_lightpatch_matrix.csv")
manifest = json.load(open(f"{OUT}/regime_v015_lightpatch_manifest.json", encoding="utf-8"))

summary["alarm_day_share"] = pd.to_numeric(summary["alarm_day_share"], errors="coerce")
summary["false_days_per_year"] = pd.to_numeric(summary["false_days_per_year"], errors="coerce")
summary["false_episodes_per_year"] = pd.to_numeric(summary["false_episodes_per_year"], errors="coerce")
summary["first_offset_median"] = pd.to_numeric(summary["first_offset_median"], errors="coerce")
matrix["first_hit_offset"] = pd.to_numeric(matrix["first_hit_offset"], errors="coerce")

sel_id = manifest["summary"]["selected_policy"]
sel = summary[summary["policy"] == sel_id].iloc[0]
p2 = summary[summary["policy"] == "P2"].iloc[0]
ref8 = summary[summary["policy"] == "REF8"].iloc[0]
qualified = summary[(summary["identified"] == 45) & (~summary["policy"].isin(["REF8", "REF1"]))].sort_values("alarm_day_share")

def fnum(x, nd=1):
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x:,.{nd}f}"

out = []
def a(s):
    out.append(s)

a('<html><head><meta charset="utf-8"><title>弱三中二最小补丁研究 · v0.15</title><style>')
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

a('<h1>弱三中二最小补丁研究</h1>')
a('<div class="meta">产品二触发层 · 预登记 v0.15 · 底座＝弱三中二（44/45、警戒 21.1%）冻结不动 · '
  '34 行补丁网格同表保留（并联 15 / 表决 12 / 换件 4 / 对照 2 / 底座 1）· '
  '45 个冻结统计事件 · 全部为样本内描述性对账 · 无随机数、全流程确定性（双跑字节一致）</div>')

# ---------------- 大数字 ----------------
a('<div class="tiles">')
a(f'<div class="tile"><div class="nm">完全识别（选定行）</div><div class="vl ok">45 / 45</div>'
  f'<div class="sm">底座 44/45（漏 126 号）→ 补齐</div></div>')
a(f'<div class="tile"><div class="nm">警戒占历史</div><div class="vl ok">{fnum(sel["alarm_day_share"]*100)}%</div>'
  f'<div class="sm">底座 {fnum(p2["alarm_day_share"]*100)}% → 反降 {(p2["alarm_day_share"]-sel["alarm_day_share"])*100:.1f} 个百分点</div></div>')
a(f'<div class="tile"><div class="nm">误报日 / 年</div><div class="vl good">{fnum(sel["false_days_per_year"])}</div>'
  f'<div class="sm">底座 {fnum(p2["false_days_per_year"])} → 降 {(1-sel["false_days_per_year"]/p2["false_days_per_year"])*100:.0f}%</div></div>')
a(f'<div class="tile"><div class="nm">误报段 / 年</div><div class="vl ok">{fnum(sel["false_episodes_per_year"])}</div>'
  f'<div class="sm">底座 {fnum(p2["false_episodes_per_year"])}（本来就不频闪）</div></div>')
a(f'<div class="tile"><div class="nm">126 号盲区</div><div class="vl mid">已抓 · 损伤窗</div>'
  f'<div class="sm">崩盘第 4 日才响（详见丑话）</div></div>')
a('</div>')

# ---------------- 丑话 ----------------
a('<div class="warn"><b>两句丑话（先读）：</b><br>'
  '<b>一、选定行抓 126 号是在损伤窗（+4 日），不是提前预判。</b>126 号是顶部反转：崩盘落在事件结束之后，'
  '「回撤警报＋五日跌四」在崩盘第 4 日共现才响。按预登记分档口径这算识别（损伤窗对残余损伤有部分保护），'
  '但<b>要在起点前抓住这类顶部反转，只有并联顶部预警做得到</b>（顶部首裂档警戒 24.0%、126 号在 −8 日响；'
  '顶部警觉档 31.2%、−17 日响）——各有各的价码，取舍见下图。<br>'
  '<b>二、换件是重新洗牌，不是全面碾压。</b>选定行与底座有 16 个事件时点不同：108 号、124 号从损伤窗升到提前，'
  '但 <b>4 号（2016-04）、15 号（2024-10）从提前掉到损伤窗</b>；101 号、127 号同档内变晚。'
  '提前档总数持平（26 个），成员换了人。逐事件对照表全披露。</div>')

# ---------------- 取舍散点图 ----------------
a('<h2>合格行的取舍面：警戒代价 × 提前量</h2>')
a('<div class="note">横轴＝警戒占历史（越小越好），纵轴＝提前档事件数（越大越好）。'
  '只画识别 45/45 的行与两个关键对照。红色＝选定行，灰色＝对照。左上角是理想区——注意没有行能同时占住。</div>')
# 生成散点
pts = []
for _, r in summary.iterrows():
    if r["identified"] == 45 or r["policy"] in ("P2",):
        pts.append(r)
x_min, x_max = 0.14, 0.62
y_min, y_max = 22, 46
W, H = 900, 420
ml, mr, mt, mb = 60, 30, 20, 46
pw, ph = W - ml - mr, H - mt - mb
def sx(v):
    return ml + (v - x_min) / (x_max - x_min) * pw
def sy(v):
    return mt + ph - (v - y_min) / (y_max - y_min) * ph
a(f'<svg viewBox="0 0 {W} {H}" style="width:100%;max-width:900px;background:#fff;border:1px solid #e3e6ec;border-radius:10px;">')
for gx in (0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6):
    a(f'<line x1="{sx(gx):.0f}" y1="{mt}" x2="{sx(gx):.0f}" y2="{mt+ph}" stroke="#eef1f6" stroke-width="1"/>')
    a(f'<text x="{sx(gx):.0f}" y="{mt+ph+18}" text-anchor="middle" font-size="11" fill="#999">{gx*100:.0f}%</text>')
for gy in (25, 30, 35, 40, 45):
    a(f'<line x1="{ml}" y1="{sy(gy):.0f}" x2="{ml+pw}" y2="{sy(gy):.0f}" stroke="#eef1f6" stroke-width="1"/>')
    a(f'<text x="{ml-10}" y="{sy(gy)+4:.0f}" text-anchor="end" font-size="11" fill="#999">{gy}</text>')
a(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#aab" stroke-width="1.5"/>')
a(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#aab" stroke-width="1.5"/>')
a(f'<text x="{ml+pw/2:.0f}" y="{H-8}" text-anchor="middle" font-size="12" fill="#666">警戒占历史（越小越好）</text>')
a(f'<text x="16" y="{mt+ph/2:.0f}" text-anchor="middle" font-size="12" fill="#666" transform="rotate(-90 16 {mt+ph/2:.0f})">提前档事件数（越大越好）</text>')
fam_color = {"底座": "#b23a3a", "并联": "#c98a1b", "表决": "#2a7a4b", "换件": "#4a6fa5", "对照": "#999999"}
label_pols = {"S3", "U-D1", "U-H1", "U-H2", "P2", "REF8", "S4", "U-D4"}
for r in pts:
    x, y = sx(r["alarm_day_share"]), sy(r["n_pre"])
    col = fam_color.get(r["family"], "#888")
    rad = 8 if r["policy"] == sel_id else 5
    ring = f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rad+3}" fill="none" stroke="#b23a3a" stroke-width="2"/>' if r["policy"] == sel_id else ""
    a(f'{ring}<circle cx="{x:.0f}" cy="{y:.0f}" r="{rad}" fill="{col}" fill-opacity="0.85"/>')
    if r["policy"] in label_pols:
        nm = r["policy_name"].replace("弱三中二∪", "∪").replace("（对照）", "")
        dy = -12 if r["n_pre"] < 40 else 16
        a(f'<text x="{x:.0f}" y="{y+dy:.0f}" text-anchor="middle" font-size="11" fill="#555">{nm}</text>')
a('</svg>')
a('<div class="note"><b>读图：</b>换件行（回撤换年线）在左下——警戒最省但提前量一般；'
  '顶部预警并联行在右上——提前量最大（35～42 个）但警戒更贵；'
  '弱三中二∪五日深跌贴着底座右侧一点点——几乎零改动补上盲区。三条路都合法，看产品要什么。</div>')

# ---------------- 126 诊断 ----------------
a('<h2>盲区诊断：126 号为什么漏</h2>')
a('<div class="note">126 号＝2010-11-08 起 4 日急性事件（顶部反转），事后 20 日 −10.0%。'
  '识别窗内弱三中二三要素<b>零共现</b>（计数最大 1）：窗内市场贴着 20 日新高（回撤 0）、价在半年线上（年线元件不亮）、'
  '波动没抬升（波动元件不亮）；崩盘在事件结束后才来，五日跌四/回撤警报到 +4 日才溅出。'
  '窗内<b>提前看见它的只有顶部预警类</b>：顶部警觉 −17 日、顶部首裂 −8 日（实用候选当时就靠顶部警觉抓的）。</div>')
a('<table><tr><th>政策</th><th>126 号首响</th><th>偏移</th><th>分档</th><th>首响信号</th></tr>'
  '<tr class="g0"><td class="lft">弱三中二（底座）</td><td>—</td><td>—</td><td class="up">漏</td><td>—</td></tr>'
  '<tr class="hl"><td class="lft">三中二（回撤换年线）＝选定行</td><td>2010-11-12</td><td>+4</td><td class="mid">损伤窗</td><td>五日跌四＋跳水＋回撤警报</td></tr>'
  '<tr><td class="lft">弱三中二∪顶部首裂</td><td>2010-10-27</td><td class="dn">−8</td><td class="dn">提前</td><td>顶部首裂＋顶部警觉</td></tr>'
  '<tr><td class="lft">弱三中二∪顶部警觉</td><td>2010-10-14</td><td class="dn">−17</td><td class="dn">提前</td><td>顶部警觉</td></tr>'
  '<tr><td class="lft">弱三中二∪单日跳水</td><td>2010-11-12</td><td>+4</td><td class="mid">损伤窗</td><td>跌四＋磨跌＋跳水＋回撤警报</td></tr>'
  '<tr><td class="lft">实用候选（对照）</td><td>2010-10-14</td><td class="dn">−17</td><td class="dn">提前</td><td>顶部警觉</td></tr></table>')

# ---------------- 34 行全表 ----------------
a('<h2>34 行补丁网格（无论好坏不删）</h2>')
a('<div class="note">三个家族：并联补丁＝底座∪单信号（任一元件单独响即触发）；'
  '表决扩容＝四中二（新元件须与旧元件之一共现）；换件＝替换底座的一个元件。'
  '选定规则（计算前固定）：硬资格识别 45/45 → 警戒占比取小 → 误报日/年小 → 提前数大。'
  '小注：五日深跌含于五日跌四，故「并联（加五日深跌）」与「四中二（加五日深跌）」数值完全相同——同机制不是重复登记。</div>')
a('<table><tr><th>政策</th><th>家族</th><th>识别</th><th>提前</th><th>窗内</th><th>损伤窗</th><th>漏</th>'
  '<th>警戒占比</th><th>误报日/年</th><th>误报段/年</th><th>首响中位</th><th>选定</th></tr>')
for _, r in summary.iterrows():
    cls = ' class="hl"' if r["policy"] == sel_id else (' class="g0"' if r["policy"] in ("P2", "REF8", "REF1") else "")
    med = f'{int(r["first_offset_median"])}' if r["first_offset_median"] == r["first_offset_median"] else "—"
    a(f'<tr{cls}><td class="lft">{r["policy_name"]}</td><td>{r["family"]}</td>'
      f'<td>{int(r["identified"])}/45</td><td>{int(r["n_pre"])}</td><td>{int(r["n_in_window"])}</td>'
      f'<td>{int(r["n_damage"])}</td><td>{int(r["n_miss"])}</td>'
      f'<td>{fnum(r["alarm_day_share"]*100)}%</td><td>{fnum(r["false_days_per_year"])}</td>'
      f'<td>{fnum(r["false_episodes_per_year"])}</td><td>{med}</td>'
      f'<td>{"★" if r["policy"]==sel_id else ""}</td></tr>')
a('</table>')
a('<div class="note"><b>16 行过线（识别 45/45）。</b>警戒占比从 17.3% 一路排到 59.8%；'
  '底座之下的只有「回撤换年线」一行（17.3% &lt; 21.1%）——它顺手把年线元件的常亮噪音去掉了，'
  '误报日/年从 16.6 降到 9.9。其余合格行都要付 0.4～39 个百分点的警戒溢价。'
  '两个换件行（磨跌换深跌、跳水换深跌）仍是 44/45——单换深跌元件补不了顶部反转盲区。</div>')

# ---------------- 逐事件差异 ----------------
a('<h2>选定行与底座对照：16 个时点变动的事件</h2>')
a('<div class="note">其余 29 个事件两行完全一致。绿＝改善，红＝退让。</div>')
a('<table><tr><th>事件</th><th>起点</th><th>真型</th><th>底座首响</th><th>底座分档</th>'
  '<th>选定行首响</th><th>选定行分档</th><th>选定行首响信号</th><th>得失</th></tr>')
m_sel = matrix[matrix["policy"] == sel_id].set_index("event_id")
m_p2 = matrix[matrix["policy"] == "P2"].set_index("event_id")
tier_rank = {"提前": 0, "窗内": 1, "损伤窗": 2, "漏": 3}
for eid in m_sel.index:
    ra, rb = m_sel.loc[eid], m_p2.loc[eid]
    same_off = (str(ra["first_hit_offset"]) == str(rb["first_hit_offset"]))
    if ra["tier"] == rb["tier"] and same_off:
        continue
    d_tier = tier_rank[ra["tier"]] - tier_rank[rb["tier"]]
    if ra["tier"] == "提前" and rb["tier"] != "提前":
        verdict, cls = "改善（升档）", "dn"
    elif rb["tier"] == "提前" and ra["tier"] != "提前":
        verdict, cls = "退让（掉档）", "up"
    elif d_tier < 0:
        verdict, cls = "改善（升档）", "dn"
    elif d_tier > 0:
        verdict, cls = "退让（掉档）", "up"
    else:
        a_off = ra["first_hit_offset"]
        b_off = rb["first_hit_offset"]
        if a_off == a_off and b_off == b_off and a_off < b_off:
            verdict, cls = "改善（变早）", "dn"
        else:
            verdict, cls = "退让（变晚）", "up"
    bo = f'{int(rb["first_hit_offset"])}' if rb["first_hit_offset"] == rb["first_hit_offset"] else "—"
    ao = f'{int(ra["first_hit_offset"])}' if ra["first_hit_offset"] == ra["first_hit_offset"] else "—"
    a(f'<tr><td>{int(eid)}</td><td>{ra["onset"]}</td><td>{ra["true_type"]}</td>'
      f'<td>{bo}</td><td>{rb["tier"]}</td><td>{ao}</td><td>{ra["tier"]}</td>'
      f'<td class="lft">{ra["first_hit_signals"]}</td><td class="{cls}">{verdict}</td></tr>')
a('</table>')

# ---------------- 45×34 矩阵 ----------------
a('<h2>45 事件 × 34 政策识别矩阵</h2>')
a('<div class="filt"><b>筛选：</b>'
  '<select id="f-policy"><option value="">全部政策</option>' +
  ''.join(f'<option value="{h.escape(r["policy_name"])}">{h.escape(r["policy_name"])}</option>' for _, r in summary.iterrows()) +
  '</select>'
  '<select id="f-tier"><option value="">全部分档</option><option>提前</option><option>窗内</option><option>损伤窗</option><option>漏</option></select>'
  '<input id="f-kw" placeholder="事件号或起点年份">'
  '<span id="f-count" class="dim"></span></div>')
a('<div class="scroll"><table id="evtbl"><tr><th>事件</th><th>起点</th><th>长度</th><th>真型</th><th>政策</th>'
  '<th>首响</th><th>偏移</th><th>分档</th><th>首响信号</th></tr>')
for _, r in matrix.iterrows():
    kw = f'{int(r["event_id"])} {r["onset"]} {r["onset"][:4]}'
    off = f'{int(r["first_hit_offset"])}' if r["first_hit_offset"] == r["first_hit_offset"] else "—"
    fd = r["first_hit_date"] if r["first_hit_date"] == r["first_hit_date"] else "—"
    a(f'<tr class="erow" data-p="{h.escape(r["policy_name"])}" data-t="{r["tier"]}" data-k="{kw}">'
      f'<td>{int(r["event_id"])}</td><td>{r["onset"]}</td><td>{int(r["event_len"])} 日</td><td>{r["true_type"]}</td>'
      f'<td class="lft">{r["policy_name"]}</td><td>{fd}</td><td>{off}</td><td>{r["tier"]}</td>'
      f'<td class="lft">{r["first_hit_signals"] if r["first_hit_signals"]==r["first_hit_signals"] else "—"}</td></tr>')
a('</table></div>')
a('<div class="dim" style="font-size:11.5px;">偏移单位＝交易日，负数＝在事件起点之前。首响信号＝首个命中日当日点亮的元件清单。</div>')

# ---------------- 结论 ----------------
a('<h2>结论（直说）</h2>')
a('<div class="note">'
  '<b>一、用户的问题有了直接答案：</b>弱三中二可以做到 45/45，而且警戒占比<b>不升反降</b>——'
  '把年线元件换成回撤警报（选定行），警戒 21.1% → 17.3%，误报日/年 16.6 → 9.9，126 号补上。'
  '机制：年线元件是常亮噪音（熊市一亮几个月），回撤警报是事件性亮灯；换掉它既省警戒又添了顶部敏感度。<br>'
  '<b>二、但 126 号是损伤窗才响。</b>要提前抓顶部反转，就得并联顶部预警（24.0%～31.2% 警戒档，提前量 35～42 个）——'
  '这是一条明确的价目表：省警戒（17.3%）→ 损伤窗兜底；买提前（24%+）→ 顶部反转也提前。<br>'
  '<b>三、给产品的建议组合：</b>日常警戒用选定行（最省），顶部预警单独做<b>轻提醒</b>（不进触发主线，只提示「高位转弱」）——'
  '这样 17.3% 的主轨警戒 + 一条不计警戒日的轻提示线，兼顾两边。此建议是产品层设计，不在本版回测口径内。<br>'
  '<b>四、下一步（欠着）：</b>与第十四版治理层（撤销＋冷却）组合、再接第十二版端到端损益——'
  '本版只做触发层词表补丁，不做损益模拟。</div>')

# ---------------- 预登记 ----------------
a('<details><summary>预登记与确定性</summary><div class="note">'
  '预登记于任何计算之前落盘（登记时间 2026-11-14T13:11:09+08:00，'
  '<span title="config/regime_lightpatch_v0.15.toml">补丁研究配置文件</span>）。'
  '盲区诊断（126 号顶部反转）先于登记、只用于网格的机制设计；15 信号阈值一个没动，34 行同表保留、无论好坏不删。'
  '完整脚本独立运行两次，数据产物字节一致（清单时间戳除外）；底座行与两行对照与第十三版逐字段对账一致。'
  '无随机数、无参数反选；不做显著性宣称；2025 测试集封存不动；不重判。</div></details>')

gat = manifest["created"]
try:
    dt = datetime.fromisoformat(gat)
    gat = f"{dt.year} 年 {dt.month} 月 {dt.day} 日"
except Exception:
    gat = ""
a(f'<footer>弱三中二最小补丁 · 预登记 v0.15 · 生成于 {gat} · 45 个冻结统计事件 × 34 个补丁政策 · '
  '全流程确定性（双跑字节一致）· 全部为样本内描述性对账</footer>')

a('<script>'
  'const fp=document.getElementById("f-policy"),ft=document.getElementById("f-tier"),'
  'fk=document.getElementById("f-kw"),fc=document.getElementById("f-count");'
  'function apply(){const p=fp.value,t=ft.value,k=fk.value.trim();'
  'let n=0;document.querySelectorAll("#evtbl .erow").forEach(function(r){'
  'let ok=(!p||r.dataset.p===p)&&(!t||r.dataset.t===t)&&(!k||r.dataset.k.indexOf(k)>=0);'
  'r.style.display=ok?"":"none";if(ok)n++;});fc.textContent="共 "+n+" 行";} '
  'fp.addEventListener("change",apply);ft.addEventListener("change",apply);'
  'fk.addEventListener("input",apply);apply();'
  '</script>')
a('</body></html>')

html = "".join(out)
with open(f"{OUT}/crisis_lightpatch_v015_report.html", "w", encoding="utf-8") as fh:
    fh.write(html)

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
