# -*- coding: utf-8 -*-
"""
v0.16 消音治理后的触发器接回端到端损益账本 报告生成
（crisis_governed_pnl_v016_report.html）
离线单文件、全中文、可见文本零拉丁（工程字段只放悬停 title）。
"""
import html as h
import json

import pandas as pd

BASE = "."
OUT = f"{BASE}/outputs"

summary = pd.read_csv(f"{OUT}/regime_v016_governed_pnl_summary.csv")
matrix = pd.read_csv(f"{OUT}/regime_v016_governed_pnl_event_matrix.csv")
false_df = pd.read_csv(f"{OUT}/regime_v016_governed_pnl_false_alarm.csv")
manifest = json.load(open(f"{OUT}/regime_v016_governed_pnl_manifest.json", encoding="utf-8"))
v012 = pd.read_csv(f"{OUT}/regime_v012_trigger_policy_summary.csv")

for c in ("net_reference", "e2e_p4_p3_total", "e2e_p1_p3_total", "false_cost_total",
          "diff_p4_p3_median_switched", "diff_p1_p3_median", "alarm_day_share",
          "false_days_per_year", "false_days_ident_per_year", "caught_rate"):
    summary[c] = pd.to_numeric(summary[c], errors="coerce")
for c in ("diff_p4_p3", "diff_p1_p3", "diff_p1_p2", "diff_p1_p4", "trigger_offset",
          "gov_first_offset", "delay_vs_raw", "raw_first_offset"):
    matrix[c] = pd.to_numeric(matrix[c], errors="coerce")

sel_id = manifest["selection_note"] and manifest["selected_variant"]
sel = summary[summary["variant"] == sel_id].iloc[0]
g0 = summary[summary["variant"] == "G0"].iloc[0]
b20 = summary[summary["variant"] == "B20"].iloc[0]
v12 = {r["policy"]: r for _, r in v012.iterrows()}


def fnum(x, nd=1):
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x:,.{nd}f}"


out = []
def a(s):
    out.append(s)

a('<html><head><meta charset="utf-8"><title>消音治理接回算钱账本 · v0.16</title><style>')
a('body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#f7f8fa;color:#222;margin:0;padding:28px 5%;}'
  'h1{font-size:25px;margin:0 0 6px} h2{font-size:19px;margin:30px 0 10px;border-left:4px solid #4a6fa5;padding-left:10px;}'
  'h3{font-size:15px;margin:18px 0 8px;color:#444;}'
  '.meta{color:#777;font-size:12.5px;margin-bottom:18px;line-height:1.9;}'
  '.tiles{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0;}'
  '.tile{background:#fff;border:1px solid #e3e6ec;border-radius:10px;padding:14px 18px;min-width:150px;flex:1;}'
  '.tile .nm{font-size:12px;color:#888;} .tile .vl{font-size:26px;font-weight:700;margin:4px 0;}'
  '.tile .sm{font-size:11.5px;color:#999;} .vl.mid{color:#b25a00;} .vl.good{color:#2a7a4b;} .vl.ok{color:#2a7a4b;} .vl.bad{color:#b23a3a;}'
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

a('<h1>消音治理接回算钱账本</h1>')
a('<div class="meta">产品二触发层 × 响应层 · 预登记 v0.16 · '
  '底座＝三中二（回撤换年线）触发掩码冻结 · 消音层＝撤销＋冷却 9 变体同表 · '
  '损益引擎与第十二版逐字同（判定 / 切换 / 止损 / 认沽 / 回补 / 复利）· '
  '45 个冻结统计事件 × 9 行 · 全部为样本内反事实记账 · 无随机数、双跑字节一致</div>')

# ---------------- 大数字 ----------------
a('<div class="tiles">')
a(f'<div class="tile"><div class="nm">选定行净账合计</div><div class="vl good">+{fnum(sel["net_reference"])}</div>'
  f'<div class="sm">事件侧 +{fnum(sel["e2e_p4_p3_total"])} 误报 {fnum(sel["false_cost_total"])}（纯静默·冷却十日）</div></div>')
a(f'<div class="tile"><div class="nm">无消音对照</div><div class="vl mid">+{fnum(g0["net_reference"])}</div>'
  f'<div class="sm">同样触发器裸跑：误报把事件侧收益吃掉九成六</div></div>')
a(f'<div class="tile"><div class="nm">第十二版混合用（旧触发）</div><div class="vl mid">+{fnum(v12["丁"]["net_reference"])}</div>'
  f'<div class="sm">引擎同、触发旧：事件侧高但误报更贵</div></div>')
a(f'<div class="tile"><div class="nm">识别</div><div class="vl ok">45 / 45</div>'
  f'<div class="sm">九行变体全部守住（识别窗含损伤窗）</div></div>')
a(f'<div class="tile"><div class="nm">来得及触发</div><div class="vl mid">{int(sel["caught_n"])} / 45</div>'
  f'<div class="sm">归属窗内有警报＝能开时钟；其余 {int(sel["n_late_only"])} 个只在事后响</div></div>')
a('</div>')

# ---------------- 丑话 ----------------
a('<div class="warn"><b>四句丑话（先读）：</b><br>'
  '<b>一、选定是样本内机械择优，不是样本外证据。</b>预登记规则＝识别 45/45 硬门槛 → 净账合计大 → 误报日少 → 冷却短，'
  '九行无论好坏全保留。拿去实盘前必须过 2025 测试集那一关（本版未读）。<br>'
  '<b>二、45 全样本中位一律被「未触发 / 未切换记 0」拉平，别用它评价。</b>未触发（保护期已过）与触发但判定机拒绝出手的事件，'
  '路径四与路径三完全相同、差值按构造记 0。要读的三列是：<b>已切换子集中位、事件侧合计、净账合计</b>。<br>'
  '<b>三、钱主要省在误报上，不是赚在危机里。</b>事件侧合计从无消音的 +114.1 抬到 +147.6（警报态延续让部分事件时钟更早），'
  '但真正的大头是误报代价从 −109.8 砍到 −68.6。第十二版混合用的事件侧（+166.4）仍然更高——它的触发更全，但误报（−139.4）也更贵，'
  '净账反而输。<br>'
  '<b>四、误报日有两个口径，不可混用。</b>账本口径（段不交归属窗 [−20, 结束]，进净账）选定行 '
  f'{fnum(sel["false_days_per_year"])} 日/年；识别窗口径（与第十三—十五版同）{fnum(sel["false_days_ident_per_year"])} 日/年。'
  '报告与清单里两列并存，跨版对照只能用识别窗口径，算钱只能用账本口径。</div>')

# ---------------- 已知不足声明（本版不修） ----------------
a('<div class="warn"><b>已知不足声明（本版不修，立此存照）——账本把「危机何时结束」当成了已知输入：</b><br>'
  '预案的<b>回补</b>（事件结束后二十个交易日线性加回满仓）、<b>止损监测的终点</b>（监测至事件结束）、'
  '<b>认沽的到期日</b>（事件结束后第二十日结算）、以及<b>切换资格的判定</b>（确认日须早于事件结束日，否则算「来不及」）——'
  '这四处全部以「事件结束日」为锚。这个日期来自冻结标签的后视镜口径，<b>实盘不可得</b>：实盘里没人宣布「危机今天结束」。<br>'
  '后果：账本里<b>没有任何「解除信号误差」的成本</b>——解除早了少吃反弹、解除晚了踏空修复，这些代价不存在于任何数字里。'
  '这是「回测结论是实盘的上限」的组成部分之一（另一部分是起点已知）。<br>'
  '<b>处置（按拍板执行）：本版不修补，先正式承认。</b>实盘需要一条独立的解除规则（自然候选是消音层的撤销：'
  '连续五日静默即解除警报态——但该候选从未接进账本检验过，换用它数字会变）。若将来修补，须另行预登记，'
  '不得回改本版任何数字。来源规则见预登记第十一版回补 / 止损 / 对冲三节（登记时已有一行披露，此处升格为正式承认）。</div>')

# ---------------- 10 变体同表 ----------------
a('<h2>九行变体同表：钱的全景</h2>')
a('<div class="note">净账合计 ＝ 事件侧（路径四−路径三）合计 ＋ 误报段损益差合计（带符号相加）。'
  '合计参照是逐事件单位账的算术和（每事件从 1 起算），不是组合收益率。'
  '已切换中位只在真切换了预案的事件上算。深色行为选定行，灰行为无消音对照。</div>')
a('<table><tr><th>变体</th><th>识别</th><th>提前</th><th>窗内</th><th>损伤窗</th><th>来得及</th>'
  '<th>已切换</th><th title="已切换事件上 路径四减路径三 的中位数">已切换中位</th>'
  '<th title="事件侧 45 个事件 路径四减路径三 的算术合计">事件侧合计</th>'
  '<th title="误报段损益差合计（负值＝流失）">误报合计</th><th>净账合计</th>'
  '<th title="账本口径：误报段不与归属窗 [−20, 事件结束] 相交的警报日">误报日/年</th>'
  '<th title="识别窗口径：[−20, +20] 之外的警报日（与第十三—十五版同）">识别窗误报日/年</th>'
  '<th>警戒占比</th></tr>')
for _, r in summary.iterrows():
    cls = ' class="hl"' if r["variant"] == sel_id else (' class="g0"' if r["variant"] == "G0" else '')
    net = r["net_reference"]
    net_cls = "up" if net >= 0 else "dn"
    a(f'<tr{cls}><td class="lft">{r["variant_name"]}</td>'
      f'<td>{int(r["identified"])}/45</td><td>{int(r["n_pre"])}</td><td>{int(r["n_in_window"])}</td>'
      f'<td>{int(r["n_damage"])}</td><td>{int(r["caught_n"])}</td><td>{int(r["switched_n"])}</td>'
      f'<td>{fnum(r["diff_p4_p3_median_switched"], 2)}</td>'
      f'<td>{fnum(r["e2e_p4_p3_total"])}</td><td>{fnum(r["false_cost_total"])}</td>'
      f'<td class="{net_cls}"><b>{fnum(net)}</b></td>'
      f'<td>{fnum(r["false_days_per_year"])}</td><td>{fnum(r["false_days_ident_per_year"])}</td>'
      f'<td>{fnum(r["alarm_day_share"]*100)}%</td></tr>')
a('</table>')

# ---------------- 与 v0.12 对照 ----------------
a('<h2>与第十二版旧触发器对照（引擎逐字同，可比）</h2>')
a('<div class="note">下表是第十二版三行静态引用（同引擎、不同触发掩码）。绝对值与第十一页已知起点口径仍不可跨版比，'
  '但与本表同口径可比。读法：<b>新触发器＋消音赢在误报便宜</b>；旧混合用赢在事件侧覆盖。</div>')
a('<table><tr><th>触发器</th><th>来得及</th><th>已切换</th><th>事件侧合计</th><th>误报合计</th><th>净账合计</th></tr>')
a(f'<tr class="hl"><td class="lft">三中二（回撤换年线）＋纯静默冷却十日（本版选定）</td>'
  f'<td>{int(sel["caught_n"])}</td><td>{int(sel["switched_n"])}</td>'
  f'<td>{fnum(sel["e2e_p4_p3_total"])}</td><td>{fnum(sel["false_cost_total"])}</td>'
  f'<td><b>+{fnum(sel["net_reference"])}</b></td></tr>')
for p, nm in (("乙", "区间检测（旧）"), ("丁", "混合用（旧）"), ("戊", "机械混合（旧）")):
    r = v12[p]
    a(f'<tr><td class="lft">{nm}</td><td>{int(r["caught_n"])}</td><td>{int(r["switched_n"])}</td>'
      f'<td>{fnum(r["e2e_p4_p3_total"])}</td><td>{fnum(r["false_cost_total"])}</td>'
      f'<td>+{fnum(r["net_reference"])}</td></tr>')
a('</table>')

# ---------------- 选定行深挖：与无消音逐事件对照 ----------------
a('<h2>消音改变了什么：选定行与裸触发的逐事件对照</h2>')
ms = matrix[matrix["variant"] == sel_id].set_index("event_id")
mg = matrix[matrix["variant"] == "G0"].set_index("event_id")
rows_up, rows_dn, rows_same = [], [], []
for eid in ms.index:
    rs, rg = ms.loc[eid], mg.loc[eid]
    d = float(rs["diff_p4_p3"]) - float(rg["diff_p4_p3"])
    item = (eid, rs["onset"], rs["true_type"], rg["trigger_offset"], rs["trigger_offset"],
            rg["judged_type"], rs["judged_type"], float(rg["diff_p4_p3"]), float(rs["diff_p4_p3"]), d)
    if abs(d) < 1e-9:
        rows_same.append(item)
    elif d > 0:
        rows_up.append(item)
    else:
        rows_dn.append(item)
rows_up.sort(key=lambda x: -x[9])
rows_dn.sort(key=lambda x: x[9])
a(f'<div class="note">45 个事件里：<b>{len(rows_up)} 个被消音救好</b>（合计 +{fnum(sum(x[9] for x in rows_up))}），'
  f'<b>{len(rows_dn)} 个被拖坏</b>（合计 {fnum(sum(x[9] for x in rows_dn))}），'
  f'{len(rows_same)} 个不变。救好的典型机制是警报态延续把时钟提前（2015 年那类）；'
  '拖坏的是冷却把警报压到危机后半段。全表如下（按影响排序）。</div>')
a('<div class="scroll"><table><tr><th>事件</th><th>起点</th><th>真型</th>'
  '<th title="无消音时 归属窗内首个警报日相对起点的偏移">裸首响</th>'
  '<th title="消音后 归属窗内首个警报日相对起点的偏移">消音首响</th>'
  '<th>裸判型</th><th>消音判型</th><th>裸路径四−三</th><th>消音路径四−三</th><th>差</th></tr>')
for grp, name in ((rows_up, "救好"), (rows_dn, "拖坏"), (rows_same, "不变")):
    for it in grp:
        eid, onset, tt, o1, o2, j1, j2, d1, d2, d = it
        cls = ' class="hl"' if name == "救好" else (' class="g0"' if name == "不变" else '')
        dc = "up" if d > 0 else ("dn" if d < 0 else "dim")
        o1s = "—" if o1 != o1 else f"{int(o1):+d}"
        o2s = "—" if o2 != o2 else f"{int(o2):+d}"
        a(f'<tr{cls}><td>{eid}</td><td>{onset}</td><td>{tt}</td><td>{o1s}</td><td>{o2s}</td>'
          f'<td>{j1}</td><td>{j2}</td><td>{fnum(d1,2)}</td><td>{fnum(d2,2)}</td>'
          f'<td class="{dc}">{fnum(d,2)}</td></tr>')
a('</table></div>')

# ---------------- 案例：2015 ----------------
a('<h2>案例：2015 年那类深危机，消音为什么反而更好</h2>')
a('<div class="note">1 号事件（2015-07，深慢，长 49 日）：裸触发首响在 −10 日，判定机先判浅快、纠错后才转深慢，'
  '路径四−路径三 +26.99；纯静默冷却十日的警报态从更早延续进窗，首响提到 −20 日，判定机直接判深慢，'
  f'路径四−路径三 +52.39。同引擎、同判定机，差别只在时钟早晚——这就是「事件侧合计不降反升」的主要来源。'
  '注意 +52.39 与第十二版触发口径下的 2015 数字同源可比，但与第十一页已知起点口径不可比。</div>')

# ---------------- 误报段 ----------------
a('<h2>误报段损益（账本口径）</h2>')
fa_sel = false_df[false_df["variant"] == sel_id].copy()
fa_sel["diff_p4_p3"] = pd.to_numeric(fa_sel["diff_p4_p3"], errors="coerce")
fa_ev = fa_sel[fa_sel["status"] == "已评估"]
fa_sw = fa_ev[fa_ev["judged_type"] != "无法判定"]
a(f'<div class="note">选定行共 {len(fa_sel)} 段误报（{len(fa_ev)} 段已评估，其余随访不足跳过）；'
  f'其中判定机真切换预案的 {len(fa_sw)} 段，是代价主体。'
  f'误报合计 {fnum(fa_ev["diff_p4_p3"].sum())}，'
  f'折合每年 {fnum(fa_ev["diff_p4_p3"].sum()/(6483/250))}。'
  '最贵的十段如下——注意误报代价集中在牛市中后段与暴跌修复期（半仓踏空）。</div>')
top = fa_ev.nsmallest(10, "diff_p4_p3")
a('<table><tr><th>段起</th><th>段止</th><th>段长</th><th>判型</th><th>最终预案</th><th>确认偏移</th><th>路径四−三</th></tr>')
for _, r in top.iterrows():
    co = "dn" if (r["diff_p4_p3"] == r["diff_p4_p3"] and r["diff_p4_p3"] < 0) else "dim"
    a(f'<tr><td>{r["episode_start"]}</td><td>{r["episode_end"]}</td><td>{int(r["episode_len"])}</td>'
      f'<td>{r["judged_type"] if r["judged_type"]==r["judged_type"] else "—"}</td>'
      f'<td>{r["final_plan_type"] if r["final_plan_type"]==r["final_plan_type"] else "—"}</td>'
      f'<td>{int(r["first_confirm_offset"]) if r["first_confirm_offset"]==r["first_confirm_offset"] else "—"}</td>'
      f'<td class="{co}">{fnum(r["diff_p4_p3"],2)}</td></tr>')
a('</table>')

# ---------------- 45×10 全矩阵 ----------------
a('<h2>45 事件 × 9 变体全矩阵（可筛选）</h2>')
a('<div class="filt">'
  '<label>变体 <select id="f-variant"><option value="">全部</option>')
for v in summary["variant"]:
    nm = summary[summary["variant"] == v].iloc[0]["variant_name"]
    a(f'<option value="{v}">{nm}</option>')
a('</select></label>'
  '<label>判型 <select id="f-judged"><option value="">全部</option>'
  '<option>深慢</option><option>浅快</option><option>无法判定</option><option>未触发</option></select></label>'
  '<label>真型 <select id="f-true"><option value="">全部</option><option>深慢</option><option>浅快</option></select></label>'
  '<label>关键词 <input id="f-kw" placeholder="事件号或日期"></label>'
  '<span id="f-count" class="dim"></span></div>')
a('<div class="scroll"><table id="evtbl"><tr><th>事件</th><th>起点</th><th>长度</th><th>真型</th><th>变体</th>'
  '<th title="识别窗口径首响档：提前 / 窗内 / 损伤窗 / 漏">档</th>'
  '<th title="归属窗内首个警报日相对起点的偏移">时钟</th><th>判型</th><th>最终预案</th>'
  '<th>路径一−三</th><th>路径四−三</th></tr>')
for _, r in matrix.sort_values(["variant", "onset"]).iterrows():
    t13 = r["diff_p1_p3"]
    t43 = r["diff_p4_p3"]
    c43 = "up" if (t43 == t43 and t43 > 0) else ("dn" if (t43 == t43 and t43 < 0) else "dim")
    off = "—" if r["trigger_offset"] != r["trigger_offset"] else f"{int(r['trigger_offset']):+d}"
    a(f'<tr class="erow" data-v="{r["variant"]}" data-j="{r["judged_type"]}" data-t="{r["true_type"]}" '
      f'data-k="{r["event_id"]} {r["onset"]}"><td>{int(r["event_id"])}</td><td>{r["onset"]}</td>'
      f'<td>{int(r["event_len"])}</td><td>{r["true_type"]}</td><td>{r["variant_name"]}</td>'
      f'<td>{r["tier"]}</td><td>{off}</td><td>{r["judged_type"]}</td><td>{r["final_plan_type"]}</td>'
      f'<td>{fnum(t13,2)}</td><td class="{c43}">{fnum(t43,2)}</td></tr>')
a('</table></div>')

# ---------------- 预登记 ----------------
a('<details><summary>预登记与确定性</summary><div class="note">'
  f'<span title="config/regime_governed_pnl_v0.16.toml">预登记</span> 于任何计算之前落盘'
  f'（登记时间 {manifest["registered"]}）。底座掩码与消音状态机、损益引擎分别自第十五、十四、十二版逐字复用，'
  '只组合不改规则。完整脚本独立运行两次，数据产物字节一致（清单时间戳除外）；无随机数、无自助、无置换。'
  '对账断言：无消音行的识别分档与首响偏移与第十五版选定行逐字段一致。'
  '实现护栏：判定基线窗负下标不回绕（不改变任何规则参数）。'
  '<br>口径提醒：路径一是上限不得当产品收益（成绩单只认路径四）；净账合计是逐事件单位账算术和；'
  '误报两口径并存（见丑话四）；样本内、不重判、不反选、2025 测试集未读、不外推。</div></details>')

# ---------------- footer ----------------
gat = manifest["created"]
try:
    dt = pd.Timestamp(gat)
    gat = f"{dt.year} 年 {dt.month} 月 {dt.day} 日"
except Exception:
    gat = ""
a(f'<footer>消音治理接回算钱账本 · 预登记 v0.16 · 生成于 {gat} · 45 个冻结统计事件 × 9 行 · '
  f'全流程确定性（双跑字节一致）· 全部为样本内反事实记账</footer>')

# ---------------- 脚本 ----------------
a('<script>')
a('function apply(){'
  'var v=document.getElementById("f-variant").value;'
  'var j=document.getElementById("f-judged").value;'
  'var t=document.getElementById("f-true").value;'
  'var k=document.getElementById("f-kw").value.trim();'
  'var rows=document.querySelectorAll("#evtbl .erow");var n=0;'
  'rows.forEach(function(r){'
  'var ok=(!v||r.dataset.v===v)&&(!j||r.dataset.j===j)&&(!t||r.dataset.t===t)'
  '&&(!k||r.dataset.k.indexOf(k)>=0);'
  'r.style.display=ok?"":"none";if(ok)n++;});'
  'document.getElementById("f-count").textContent="显示 "+n+" / "+rows.length+" 行";}'
  'document.getElementById("f-variant").addEventListener("change",apply);'
  'document.getElementById("f-judged").addEventListener("change",apply);'
  'document.getElementById("f-true").addEventListener("change",apply);'
  'document.getElementById("f-kw").addEventListener("input",apply);'
  'apply();')
a('</script>')
a('</body></html>')

html_doc = "".join(out)
with open(f"{OUT}/crisis_governed_pnl_v016_report.html", "w", encoding="utf-8") as f:
    f.write(html_doc)
print("report written:", len(html_doc) // 1024, "KB")
