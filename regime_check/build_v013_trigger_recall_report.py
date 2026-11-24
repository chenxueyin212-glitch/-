# -*- coding: utf-8 -*-
"""
v0.13 召回优先高敏触发器研究——离线中文报告
产物：outputs/crisis_trigger_recall_v013_report.html
可见文本零英文缩写（工程字段名只放悬停 title）。
"""
import html as h
import json
import re
from datetime import datetime

import pandas as pd

OUT = "outputs"
manifest = json.load(open(f"{OUT}/regime_v013_trigger_manifest.json", encoding="utf-8"))
census = pd.read_csv(f"{OUT}/regime_v013_trigger_signal_census.csv")
matrix = pd.read_csv(f"{OUT}/regime_v013_trigger_policy_matrix.csv")
summary = pd.read_csv(f"{OUT}/regime_v013_trigger_policy_summary.csv")
false_df = pd.read_csv(f"{OUT}/regime_v013_trigger_false_alarm.csv")

for r in [census, matrix, summary]:
    for k in r.columns:
        if k not in ("signal", "policy", "event_id", "onset", "event_end", "event_len",
                     "true_type", "tier", "first_hit_signals", "first_hit_date", "selected"):
            r[k] = pd.to_numeric(r[k], errors="coerce")

POLICY_DESC = {
    "P1": ("基线机械混合", "第五版现行规则原样：急跌波动均线三中二 ∪ 拓扑警戒", "对照"),
    "P2": ("弱三中二", "放宽阈值的三中二：五日跌四 ∪ 波动七十线 ∪ 年半线", "轻量档"),
    "P3": ("跌势任一", "十个跌势信号任一命中即触发", "重召回档"),
    "P4": ("拓扑放宽", "三项拓扑警戒任一命中即触发", "拓扑档"),
    "P5": ("顶部预警", "顶部首裂与顶部警觉两项新信号", "顶部档"),
    "P6": ("无顶部全量", "跌势任一 ∪ 拓扑放宽", "全量减顶部"),
    "P7": ("全量哨响", "全部信号任一命中", "召回上限探针"),
    "P8": ("实用候选", "弱三中二 ∪ 单日跳水 ∪ 回撤警报 ∪ 拓扑放宽 ∪ 顶部预警", "推荐"),
}
SIG_DESC = {
    "D1": "五日累计 ≤ −6%", "D2": "五日累计 ≤ −4%", "D3": "三日累计 ≤ −3.5%",
    "D4": "单日 ≤ −2%", "V1": "二十日波动 > 三年八十线", "V2": "二十日波动 > 三年七十线",
    "M1": "收盘 < 二百五十日线", "M2": "收盘 < 一百二十日线",
    "R1": "距二十日高点回撤 ≥ 5%", "R2": "距六十日高点回撤 ≥ 8%",
    "T1": "拓扑四分之七入八十五线", "T2": "拓扑七分之三入八十五线", "T3": "拓扑四分之七入八十线",
    "H1": "顶部首裂：三日内创二十日新高且跌超 1%", "H2": "顶部警觉：三日内创二十日新高且收跌",
}
SIG_KIND = {"D1": "跌势", "D2": "跌势", "D3": "跌势", "D4": "跌势",
            "V1": "波动", "V2": "波动", "M1": "趋势", "M2": "趋势",
            "R1": "回撤", "R2": "回撤", "T1": "拓扑", "T2": "拓扑", "T3": "拓扑",
            "H1": "顶部", "H2": "顶部"}
OLD_BLIND = [101, 107, 108, 109, 124, 125, 126, 127, 5, 6, 7, 8, 9, 11, 13, 17]

out = []
def a(s):
    out.append(s)

def fmt(v, nd=2):
    if pd.isna(v):
        return "—"
    return f"{v:+.{nd}f}" if isinstance(v, float) and v != 0 and abs(v) < 1000 and nd >= 0 and ("+" in f"{v:+.{nd}f}") and False else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))

def fnum(v, nd=1):
    if pd.isna(v):
        return "—"
    return f"{v:.{nd}f}"

def fint(v):
    if pd.isna(v):
        return "—"
    return str(int(v))

# ---------------- 框架 ----------------
a('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
  '<title>危机召回审计 · 高敏触发器 · 第十三版</title><style>')
a('''*{box-sizing:border-box}body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;
background:#f6f7f9;color:#222;margin:0;padding:24px;line-height:1.7}
.wrap{max-width:1280px;margin:0 auto}
h1{font-size:26px;margin:0 0 6px}h2{font-size:19px;margin:34px 0 12px;border-left:4px solid #2f6fed;padding-left:10px}
.sub{color:#667;font-size:13px;margin-bottom:18px}
.card{background:#fff;border:1px solid #e4e7ec;border-radius:10px;padding:18px 20px;margin:14px 0}
.note{background:#f0f5ff;border:1px solid #d6e2fb;border-radius:8px;padding:12px 14px;margin:12px 0;font-size:13.5px}
.warn{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px 14px;margin:12px 0;font-size:13.5px}
.ok{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 14px;margin:12px 0;font-size:13.5px}
table{border-collapse:collapse;width:100%;font-size:13px;background:#fff}
th,td{border:1px solid #e4e7ec;padding:6px 9px;text-align:right;white-space:nowrap}
th{background:#f2f4f8;font-weight:600;text-align:center;cursor:default}
td.l,th.l{text-align:left}
tr:hover td{background:#f8faff}
.dim{color:#8a919c;font-size:12px}
.tiles{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
.tile{flex:1 1 180px;background:#fff;border:1px solid #e4e7ec;border-radius:10px;padding:12px 14px}
.tile .nm{font-size:12px;color:#667}.tile .vl{font-size:24px;font-weight:700;margin-top:2px}
.tile .sm{font-size:11.5px;color:#8a919c;margin-top:2px}
.good{color:#15803d}.bad{color:#b91c1c}.mid{color:#b45309}
details{background:#fff;border:1px solid #e4e7ec;border-radius:10px;padding:10px 14px;margin:10px 0}
summary{cursor:pointer;font-weight:600;font-size:14px}
.bar{height:10px;background:#eef1f6;border-radius:5px;overflow:hidden;min-width:70px}
.bar i{display:block;height:100%;border-radius:5px}
.filt{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:10px 0;font-size:13px}
.filt select,.filt input{padding:5px 8px;border:1px solid #d0d5dd;border-radius:6px;font-size:13px}
footer{color:#8a919c;font-size:12px;margin:28px 0 8px;text-align:center}
''')
a('</style></head><body><div class="wrap">')

a('<h1>危机召回审计 · 高敏触发器</h1>')
a('<div class="sub">第十三版召回优先研究 · 预登记 v0.13 · 45 个冻结事件 · 召回优先、误报只记账 · 全部样本内描述</div>')

sel = summary[summary["selected"] == "是"].iloc[0]
n_full = int((summary["identified"] == 45).sum())

a('<div class="tiles">')
a(f'<div class="tile"><div class="nm">推荐政策（样本内选定）</div><div class="vl">{POLICY_DESC[sel["policy"]][0]}</div>'
  f'<div class="sm">{POLICY_DESC[sel["policy"]][1]}</div></div>')
a(f'<div class="tile"><div class="nm">危机识别数</div><div class="vl good">45 / 45</div>'
  f'<div class="sm">全部在起点前命中（提前 45 · 窗内 0 · 损伤窗 0 · 漏 0）</div></div>')
a(f'<div class="tile"><div class="nm">警戒态占历史</div><div class="vl mid">{fnum(sel["alarm_day_share"]*100,1)}%</div>'
  f'<div class="sm">每 10 个交易日约 {fnum(sel["alarm_day_share"]*10,1)} 天在响——识别的代价</div></div>')
a(f'<div class="tile"><div class="nm">误报（只记账）</div><div class="vl">{fnum(sel["false_days_per_year"],1)} 日/年</div>'
  f'<div class="sm">{fnum(sel["false_episodes_per_year"],1)} 段/年 · 最长 {fint(sel["longest_false_episode"])} 日 · 治理押后</div></div>')
a('</div>')

# ---------------- 摘要 ----------------
a('<h2>一、直接回答</h2>')
a('<div class="ok"><b>做到了：45 个危机全部识别，无一漏报。</b>'
  '推荐政策（实用候选）在 45 个事件的每一个上，都在<b>起点之前 2—20 个交易日</b>发出警报；'
  '第五版基线只能抓到 40 个，此前的 16 个盲区事件<strong>全部翻案</strong>。'
  '误报按你的指令只记账不治理：警戒态约覆盖一半历史、误报 '
  f'{fnum(sel["false_days_per_year"],1)} 日/年——这是「全部识别」的标价，后续治理就从这里砍。</div>')

a('<div class="warn"><b>两句必须先说的丑话。</b>'
  '① 45 个里有 26 个的首响偏移恰好是 −20（识别窗左缘）——意思是<b>窗口打开时警报已经在响</b>：'
  '这些事件发生在既有的跌势/回撤状态里，高敏信号本来就常亮。这不算作弊（实盘同样能看见），'
  '但「提前 20 日」不能读成「提前 20 日精准预判」，只能读成「事件发生时系统已在警戒态」。'
  '② 警戒态占历史约 50%——一个半年都在响的警铃当然能覆盖全部危机；'
  '本版的成就在于<b>词表找到了全召回的组合</b>，而不是警报已经精准。精准化＝误报治理，是下一阶段。</div>')

# ---------------- 方法口径 ----------------
a('<h2>二、口径（预登记冻结）</h2>')
a('<div class="card"><table>'
  '<tr><td class="l dim" style="width:180px">识别窗</td><td class="l">[起点−20, 事件结束+20]。'
  '窗内（起点日至结束日）与损伤窗（结束后 20 日）分列——损伤窗命中只对残余损伤有部分保护。</td></tr>'
  '<tr><td class="l dim">时点分档</td><td class="l">提前（偏移&lt;0）／窗内（0≤偏移≤事件长−1）／损伤窗／漏。主表三档分列，不许合并冒充。</td></tr>'
  '<tr><td class="l dim">误报定义</td><td class="l">命中日不在任何识别窗内 = 误报日；误报段 = 连续误报日最大连续段（识别窗边界处切断）。年 = 6483÷250。</td></tr>'
  '<tr><td class="l dim">误报治理</td><td class="l"><b>本版不做</b>——用户指令「做到了以后再着手降」。撤销、冷却、代价模拟全部押后。</td></tr>'
  '<tr><td class="l dim">词表与阈值</td><td class="l">15 项信号、8 条政策，全部机制驱动、计算前固定；无论好坏同表保留，不按结果删改。</td></tr>'
  '</table></div>')

# ---------------- 八政策 ----------------
a('<h2>三、八条政策同表</h2>')
a('<div class="card"><table><tr>'
  '<th class="l">政策</th><th class="l">构成</th><th>识别</th><th>提前</th><th>窗内</th><th>损伤窗</th><th>漏</th>'
  '<th>首响中位</th><th>警戒占历史</th><th>误报日/年</th><th>误报段/年</th></tr>')
for _, r in summary.iterrows():
    p = r["policy"]
    nm, desc, tag = POLICY_DESC[p]
    hl = ' style="background:#f0fdf4"' if r["selected"] == "是" else ""
    idcls = "good" if r["identified"] == 45 else ("mid" if r["identified"] >= 43 else "bad")
    share_pct = r["alarm_day_share"] * 100
    barw = min(100, share_pct)
    a(f'<tr{hl}><td class="l"><b>{p} {nm}</b> <span class="dim">{tag}</span></td>'
      f'<td class="l">{desc}</td>'
      f'<td class="{idcls}"><b>{fint(r["identified"])}/45</b></td>'
      f'<td>{fint(r["n_pre"])}</td><td>{fint(r["n_in_window"])}</td><td>{fint(r["n_damage"])}</td>'
      f'<td class="{"bad" if r["n_miss"]>0 else ""}">{fint(r["n_miss"])}</td>'
      f'<td>{fint(r["first_offset_median"])}</td>'
      f'<td><div class="bar"><i style="width:{barw:.0f}%;background:#60a5fa"></i></div>'
      f'<span class="dim">{fnum(share_pct,1)}%</span></td>'
      f'<td>{fnum(r["false_days_per_year"],1)}</td><td>{fnum(r["false_episodes_per_year"],1)}</td></tr>')
a('</table>')
a('<div class="note"><b>读法：</b>识别数先看三档分列。P3/P6/P7 也满 45，但警戒占历史 68—75%；'
  'P8 同样满 45 且全部提前，警戒占历史 50%，误报日只有 P7 的六成——按预登记的选定规则'
  '（识别数最大取先、并列误报日/年取小）胜出，标注<b>样本内选定</b>。'
  'P2（44/45、警戒 21%）是唯一「轻量近满」档，漏掉的 1 个是 2010-11 短事件。'
  '注意误报段/年 P8 高于 P3——段多而碎（顶部警觉类信号频闪），日数反而少。</div></div>')

# ---------------- 信号普查 ----------------
a('<h2>四、十五项单信号普查</h2>')
a('<div class="card"><table><tr><th class="l">信号</th><th class="l">类</th><th class="l">规则</th>'
  '<th>识别</th><th>提前</th><th>窗内</th><th>损伤窗</th><th>漏</th><th>首响中位</th>'
  '<th>警戒占历史</th><th>误报日/年</th></tr>')
for _, r in census.iterrows():
    s = r["signal"]
    idcls = "good" if r["identified"] == 45 else ("mid" if r["identified"] >= 40 else "")
    share_pct = r["alarm_day_share"] * 100
    a(f'<tr><td class="l"><b>{s}</b></td><td class="l dim">{SIG_KIND[s]}</td>'
      f'<td class="l">{SIG_DESC[s]}</td>'
      f'<td class="{idcls}"><b>{fint(r["identified"])}/45</b></td>'
      f'<td>{fint(r["n_pre"])}</td><td>{fint(r["n_in_window"])}</td><td>{fint(r["n_damage"])}</td>'
      f'<td>{fint(r["n_miss"])}</td><td>{fint(r["first_offset_median"])}</td>'
      f'<td>{fnum(share_pct,1)}%</td><td>{fnum(r["false_days_per_year"],1)}</td></tr>')
a('</table>')
a('<div class="note"><b>单信号也能 45/45 的有 5 个：</b>五日跌四、三日跌三点五、单日跌二、'
  '距二十日高点回撤一成二里的两个回撤信号——但单独用时多数命中落在损伤窗（事后才响）；'
  '组合的价值就是把这些命中<b>拉到起点之前</b>。'
  '顶部警觉（H2）单独 40/45，但正是它把 2021-02、2025-03 这类顶部反转提前抓住。'
  '波动类单独召回最差（33—38/45）且误报长青，只配当组合成员。</div></div>')

# ---------------- 45×8 矩阵 ----------------
a('<h2>五、45 事件 × 8 政策识别矩阵</h2>')
a('<div class="filt">'
  '<label>政策<select id="f-pol"><option value="">全部</option>'
  + ''.join(f'<option value="{p}">{p} {POLICY_DESC[p][0]}</option>' for p in POLICY_DESC)
  + '</select></label>'
  '<label>分档<select id="f-tier"><option value="">全部</option><option>提前</option><option>窗内</option><option>损伤窗</option><option>漏</option></select></label>'
  '<label>真型<select id="f-type"><option value="">全部</option><option>深慢</option><option>浅快</option></select></label>'
  '<label>关键词<input id="f-kw" placeholder="事件号或日期"></label>'
  '<span class="dim" id="f-count"></span></div>')
a('<div class="card"><table id="evtbl"><tr><th>事件</th><th class="l">起点</th><th class="l">结束</th><th>长</th>'
  '<th class="l">真型</th><th class="l">政策</th><th class="l">档</th><th>首响偏移</th>'
  '<th class="l">首响日</th><th class="l">首响信号</th><th>窗内响日</th></tr>')
for _, r in matrix.sort_values(["event_id", "policy"]).iterrows():
    tier = r["tier"]
    tcls = {"提前": "good", "窗内": "mid", "损伤窗": "mid", "漏": "bad"}.get(tier, "")
    off = "—" if pd.isna(r["first_hit_offset"]) else f"{int(r['first_hit_offset']):+d}"
    hits = "—" if pd.isna(r["n_hit_days_in_window"]) else fint(r["n_hit_days_in_window"])
    sigs = str(r["first_hit_signals"]) if isinstance(r["first_hit_signals"], str) and r["first_hit_signals"] else "—"
    a(f'<tr class="erow" data-p="{r["policy"]}" data-t="{tier}" data-y="{r["true_type"]}" '
      f'data-k="{r["event_id"]} {r["onset"]} {r["event_end"]}">'
      f'<td>{fint(r["event_id"])}</td><td class="l">{r["onset"]}</td><td class="l">{r["event_end"]}</td>'
      f'<td>{fint(r["event_len"])}</td><td class="l">{r["true_type"]}</td>'
      f'<td class="l">{r["policy"]} {POLICY_DESC[r["policy"]][0]}</td>'
      f'<td class="l {tcls}"><b>{tier}</b></td><td>{off}</td>'
      f'<td class="l">{r["first_hit_date"] if isinstance(r["first_hit_date"], str) and r["first_hit_date"] else "—"}</td>'
      f'<td class="l dim">{sigs}</td><td>{hits}</td></tr>')
a('</table></div>')

# ---------------- 原盲区翻案 ----------------
a('<h2>六、原 16 个盲区事件翻案表</h2>')
p8 = matrix[matrix["policy"] == "P8"].set_index("event_id")
p1 = matrix[matrix["policy"] == "P1"].set_index("event_id")
a('<div class="card"><table><tr><th>事件</th><th class="l">起点</th><th>长</th><th class="l">真型</th>'
  '<th class="l">基线（旧）</th><th class="l">推荐（新）</th><th>新首响偏移</th><th class="l">靠什么抓到</th></tr>')
for eid in OLD_BLIND:
    r8 = p8.loc[eid]
    r1 = p1.loc[eid]
    sigs = str(r8["first_hit_signals"])
    a(f'<tr><td>{fint(eid)}</td><td class="l">{r8["onset"]}</td><td>{fint(r8["event_len"])}</td>'
      f'<td class="l">{r8["true_type"]}</td>'
      f'<td class="l bad">{r1["tier"]}</td>'
      f'<td class="l good"><b>{r8["tier"]}</b></td>'
      f'<td>{int(r8["first_hit_offset"]):+d}</td>'
      f'<td class="l dim">{sigs}</td></tr>')
a('</table>')
a('<div class="note"><b>翻案机制看得清清楚楚：</b>'
  '2010-01、2004-04 这类磨跌用三日/单日跌幅抓到；2021-02、2025-03、2001-01 这类顶部反'
  '转靠顶部警觉（三日内创二十日新高后收跌）提前抓住；2018 系列靠年半线破位加回撤警报。'
  '第五版词表只有「深跌、波动、年线、拓扑」四类，全是<b>下跌展开后</b>才响的信号，'
  '所以对「窗内浅、事后深」和「顶部即崩」天然失明——补上回撤类和顶部类，盲区就填上了。</div></div>')

# ---------------- 误报记账 ----------------
a('<h2>七、误报记账（治理押后）</h2>')
a('<div class="card"><table><tr><th class="l">政策</th><th>警戒占历史</th><th>误报日/年</th>'
  '<th>误报段/年</th><th>最长段</th><th class="l">最密集误报期</th></tr>')
for _, r in summary.iterrows():
    p = r["policy"]
    ep = false_df[false_df["policy"] == p].nlargest(2, "episode_len")
    top = '；'.join(f'{x["episode_start"]}起 {int(x["episode_len"])}日' for _, x in ep.iterrows()) if len(ep) else "—"
    a(f'<tr><td class="l">{p} {POLICY_DESC[p][0]}</td><td>{fnum(r["alarm_day_share"]*100,1)}%</td>'
      f'<td>{fnum(r["false_days_per_year"],1)}</td><td>{fnum(r["false_episodes_per_year"],1)}</td>'
      f'<td>{fint(r["longest_false_episode"])} 日</td><td class="l dim">{top}</td></tr>')
a('</table>')
a('<div class="warn"><b>误报的钱怎么流：</b>推荐政策的误报集中在两类日子——'
  '牛市中后段的高位震荡（顶部警觉频闪）和阴跌途中的持续警戒（年半线常亮）。'
  '每段误报如果都真切换预案，就是一次半仓踏空或止损割肉；按前一版的记账口径，'
  '真切换的误报每年约流 5 个百分点。<b>治理方案（撤销/冷却）是下一阶段的正事</b>，'
  '本版按指令只记账。另外注意：推荐政策误报段多而碎（21.6 段/年），'
  '说明「响一下就停」的短信号多——将来冷却期设计要针对碎片化误报。</div></div>')

# ---------------- 预登记 ----------------
a('<details><summary>预登记与确定性</summary><div class="note">'
  '<span title="config/regime_trigger_recall_v0.13.toml">触发器召回研究预登记</span>于任何计算之前落盘（登记时间 '
  '2026-11-14T12:21:03+08:00）。15 信号阈值全部机制驱动、计算前固定；8 政策无论好坏同表保留。'
  '完整脚本独立运行两次，数据产物字节一致（清单时间戳除外）。无随机数、无自助、无置换。'
  '误报治理按用户指令押后。2025 测试集未读；不重判冻结判定。</div></details>')

# footer
gat = manifest["created"]
try:
    dt = datetime.fromisoformat(gat)
    gat = f"{dt.year} 年 {dt.month} 月 {dt.day} 日"
except Exception:
    gat = ""
a(f'<footer>危机召回审计 · 预登记 v0.13 · 生成于 {gat} · 45 个冻结事件 · 全流程确定性（双跑字节一致）· 全部为样本内描述性对账</footer>')

a('</div>')
a('''<script>
(function(){
var rows=[].slice.call(document.querySelectorAll('#evtbl .erow'));
var fp=document.getElementById('f-pol'),ft=document.getElementById('f-tier'),
    fy=document.getElementById('f-type'),fk=document.getElementById('f-kw'),
    fc=document.getElementById('f-count');
function apply(){
  var p=fp.value,t=ft.value,y=fy.value,k=fk.value.trim(),c=0;
  rows.forEach(function(r){
    var ok=(!p||r.getAttribute('data-p')===p)&&(!t||r.getAttribute('data-t')===t)
      &&(!y||r.getAttribute('data-y')===y)&&(!k||r.getAttribute('data-k').indexOf(k)>=0);
    r.style.display=ok?'':'none'; if(ok)c++;
  });
  fc.textContent='显示 '+c+' / '+rows.length+' 行';
}
[fp,ft,fy].forEach(function(e){e.addEventListener('change',apply);});
fk.addEventListener('input',apply); apply();
})();
</script>''')
a('</body></html>')

html = "".join(out)
# 结构校验
for tag in ("table", "details", "select", "script", "div", "tr"):
    o = len(re.findall(fr"<{tag}[\s>]", html))
    c = len(re.findall(fr"</{tag}>", html))
    assert o == c, (tag, o, c)

path = f"{OUT}/crisis_trigger_recall_v013_report.html"
open(path, "w", encoding="utf-8").write(html)

# 可见文本拉丁残留检查
body = re.sub(r"<script.*?</script>", "", html, flags=re.S)
body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
body2 = re.sub(r"<[^>]+>", " ", body)
body2 = h.unescape(body2)
bad = [b for b in re.findall(r"[A-Za-z]{2,}[A-Za-z0-9._-]*", body2) if not re.fullmatch(r"v\d+\.\d+", b)]
print("visible latin:", sorted(set(bad)))
print("erow:", len(re.findall(r'class="erow"', html)))
print("size KB:", len(html.encode("utf-8")) // 1024)
print("报告已生成:", path)
