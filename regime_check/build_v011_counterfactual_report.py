"""v0.11 四路径反事实损益：离线单文件中文报告。
可见文本零英文缩写；工程字段名只放悬停；预登记 config/regime_product2_counterfactual_v0.11.toml。
"""
import csv
import json
import html
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"


def rd(name):
    with (OUT / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def f2(x):
    if x is None or x == "":
        return ""
    v = float(x)
    return f"{v:.2f}"


def f2s(x):
    s = f2(x)
    return s if s else "—"


def med(vals):
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return None
    if n % 2:
        return vals[n // 2]
    return (vals[n // 2 - 1] + vals[n // 2]) / 2


def q(vals, p):
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return None
    idx = p * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def qq(vals):
    return q(vals, 0.25), med(vals), q(vals, 0.75)


def esc(s):
    return html.escape(str(s), quote=True)


ev = rd("regime_v011_counterfactual_event_pnl.csv")
tl = rd("regime_v011_counterfactual_daily_timeline.csv")
conf = rd("regime_v011_counterfactual_confusion.csv")
aud = rd("regime_v011_trigger_audit.csv")
manifest = json.loads((OUT / "regime_v011_manifest.json").read_text(encoding="utf-8"))
S = manifest["summary"]

for r in ev:
    r["event_len"] = int(r["event_len"])
    r["corrections_p4"] = int(r["corrections_p4"] or 0)
    r["first_confirm_offset"] = int(float(r["first_confirm_offset"])) if r["first_confirm_offset"] != "" else None
    for k in r:
        if k not in ("event_id", "onset", "event_end", "event_len", "true_type",
                     "judged_type", "final_plan_type", "first_confirm_offset",
                     "switch_offs_p4", "corrections_p4", "eligible_p12",
                     "stop_p1", "stop_p2", "stop_p4", "segment"):
            r[k] = float(r[k]) if r[k] != "" else None

sw = [r for r in ev if r["judged_type"] != "无法判定"]
short_ev = [r for r in ev if r["eligible_p12"] != "是"]

A = []


def a(*items):
    for it in items:
        A.append(it)


# ── CSS ──
a("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>产品二核心验证：四路径反事实损益</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#f5f6fa;color:#2d3436;line-height:1.7;padding:2rem}
.card{background:#fff;border-radius:12px;padding:2rem;margin-bottom:1.5rem;box-shadow:0 2px 8px rgba(0,0,0,.06)}
h1{font-size:1.5rem;margin-bottom:.5rem;color:#2d3436}
h2{font-size:1.2rem;margin:1.5rem 0 .8rem;color:#0984e3;border-left:4px solid #0984e3;padding-left:.6rem}
h3{font-size:1.05rem;margin:1rem 0 .5rem;color:#636e72}
table{width:100%;border-collapse:collapse;margin:.8rem 0;font-size:.86rem}
th,td{padding:.5rem .65rem;border:1px solid #dfe6e9;text-align:left}
th{background:#f0f3f8;font-weight:600;white-space:nowrap}
tr:nth-child(even){background:#fafbfc}
.ok{color:#00b894;font-weight:600}
.warn{color:#e17055;font-weight:600}
.dim{color:#b2bec3}
.note{background:#ffeaa7;border-left:4px solid #fdcb6e;padding:.8rem 1rem;border-radius:0 8px 8px 0;margin:.8rem 0;font-size:.9rem}
.boundary{background:#dfe6e9;border-left:4px solid #636e72;padding:.8rem 1rem;border-radius:0 8px 8px 0;margin:.8rem 0;font-size:.85rem}
.danger{background:#ffeef0;border-left:4px solid #d63031;padding:.8rem 1rem;border-radius:0 8px 8px 0;margin:.8rem 0;font-size:.9rem}
.big{font-size:1.7rem;font-weight:700;color:#0984e3}
.grid{display:flex;flex-wrap:wrap;gap:1rem;margin:1rem 0}
.kpi{flex:1;min-width:210px;background:#f8fafc;border:1px solid #e3e8ee;border-radius:10px;padding:1rem}
.kpi .lbl{font-size:.82rem;color:#636e72}
.kpi .val{font-size:1.45rem;font-weight:700;margin:.25rem 0}
.kpi .sub{font-size:.78rem;color:#b2bec3}
.tag{display:inline-block;padding:.12rem .45rem;border-radius:4px;font-size:.76rem;font-weight:600}
.tag-deep{background:#6c5ce7;color:#fff}
.tag-shallow{font-weight:600}
.tag-none{background:#b2bec3;color:#fff}
.tag-late{background:#e17055;color:#fff}
.tag-early{background:#00b894;color:#fff}
select,input[type=text]{padding:.4rem .6rem;border:1px solid #dfe6e9;border-radius:6px;font-size:.85rem;margin-right:.6rem}
details{margin:.6rem 0}
summary{cursor:pointer;color:#0984e3;font-weight:600}
.num{font-variant-numeric:tabular-nums;text-align:right}
footer{text-align:center;color:#b2bec3;font-size:.8rem;margin-top:2rem}
</style></head><body>
<div class="card">
<h1>产品二核心验证：四路径反事实损益</h1>
<p style="color:#636e72">危机类型条件化预案 · 预登记版本 v0.11 · 45 个冻结统计事件 · 样本内反事实记账</p>
<div class="danger"><b>先说丑话（三条，条条作数）：</b><br>
一、回测里事件识别是已知答案——第 0 天直接取冻结标签的起点日，检测层的漏报、误报、延迟被消掉了。'
<b>本报告的一切结论是实盘的上限</b>，不是实盘可达收益。<br>
二、<b>路径一是上限</b>（假定分类完美），必须与路径四并排看，不得当产品收益；产品成绩单只认路径四。<br>
三、全部为样本内描述性对账，不做显著性宣称，不外推；2025 年最终测试集继续封存。</div>
""")

# ── 一、四路径设计 ──
a('<h2>一、四条路径在比什么</h2>')
a('<table><tr><th>路径</th><th>含义</th><th>预案动作</th><th>定位</th></tr>'
  '<tr><td><b>路径一（套对）</b></td><td>第 2 个交易日收盘切到<b>真型</b>的预案（事后知道类型）</td>'
  '<td>深慢：半仓加虚值认沽加止损两成；浅快：八成仓加止损一成二</td><td class="ok">上限估计</td></tr>'
  '<tr><td><b>路径二（套错）</b></td><td>同一时点故意切到<b>反型</b>的预案</td>'
  '<td>同上，类型相反</td><td class="warn">下限估计（切错的代价）</td></tr>'
  '<tr><td><b>路径三（不切换）</b></td><td>全程满仓纯持有</td><td>无</td><td>基线对照</td></tr>'
  '<tr><td><b>路径四（实时分类）</b></td><td>逐日判定、连续两日同向确认才切、最多纠错一次</td>'
  '<td>按判定结果切对应预案；信息不足则不切</td><td><b>真实可达——产品二的成绩单</b></td></tr>'
  '<tr><td class="dim">敏感性口径</td><td class="dim">基线加常规止损的对照</td>'
  '<td class="dim">满仓加常规止损八个百分点</td><td class="dim">只报数字，不进主对比</td></tr></table>')
a('<div class="note"><b>预案为什么这样定：</b>深慢型危机段回撤深、恢复慢（回撤中位 −7.57%、事后 20 日 −1.56%），'
  '砍仓损失小、对冲有肉；浅快型回撤浅但事后 20 日仍在跌（中位 −6.16%），切换滞后容易砍在低位，'
  '核心价值是<b>不砍在低点</b>。仓位幅度、止损线、权利金率全部预登记冻结，不反选。</div>')

# ── 二、核心数字 ──
d13 = [r["diff_p1_p3"] for r in ev]
d43 = [r["diff_p4_p3"] for r in ev]
d12 = [r["diff_p1_p2"] for r in ev]
d43_sw = [r["diff_p4_p3"] for r in sw]
d13_sw = [r["diff_p1_p3"] for r in sw]
q13 = qq(d13)
q43 = qq(d43)
q12 = qq(d12)
q43sw = qq(d43_sw)

a('<h2>二、核心数字</h2>')
a('<div class="grid">')
a(f'<div class="kpi"><div class="lbl">路径一 减 路径三（完美预案的上限）</div>'
  f'<div class="val ok">+{q13[1]:.2f}</div>'
  f'<div class="sub">四分位 +{q13[0]:.2f} / +{q13[2]:.2f} 个百分点（45 事件中位）</div></div>')
a(f'<div class="kpi"><div class="lbl">路径四 减 路径三（实时分类全样本）</div>'
  f'<div class="val">{q43[1]:.2f}</div>'
  f'<div class="sub">四分位 {q43[0]:.2f} / {q43[2]:.2f}——45 个里 32 个拒绝出手，与基线相同</div></div>')
a(f'<div class="kpi"><div class="lbl">路径四 减 路径三（已切换的 {len(sw)} 个）</div>'
  f'<div class="val ok">+{q43sw[1]:.2f}</div>'
  f'<div class="sub">四分位 +{q43sw[0]:.2f} / +{q43sw[2]:.2f}——切换时真赚到钱</div></div>')
a(f'<div class="kpi"><div class="lbl">路径一 减 路径二（套对减套错）</div>'
  f'<div class="val warn">{q12[1]:.2f}</div>'
  f'<div class="sub">四分位 {q12[0]:.2f} / {q12[2]:.2f}——整体差异小，深慢型才拉开</div></div>')
a('</div>')

a(f'<div class="note"><b>怎么读这四个数：</b>完美分类最多值 <b>+{q13[1]:.2f} 个百分点</b>（中位）；'
  f'实时分类因为大量事件信息不足拒绝出手，全样本中位是 <b>{q43[1]:.2f}</b>；'
  f'但只要切换了，中位就有 <b>+{q43sw[1]:.2f} 个百分点</b>的保护价值。'
  f'套对与套错的差距中位只有 {q12[1]:.2f} 个百分点——因为浅快型套错成深慢预案（更保守加认沽）反而不亏，'
  f'<b>切换的真正价值集中在深慢型危机</b>。</div>')

# ── 三、对账表（预登记验收项）──
deep = [r for r in ev if r["true_type"] == "深慢"]
shal = [r for r in ev if r["true_type"] == "浅快"]
short_ids = [int(r["event_id"]) for r in short_ev]
deep_sw = [r for r in sw if r["true_type"] == "深慢"]
shal_sw = [r for r in sw if r["true_type"] == "浅快"]

a('<h2>三、危机类型 × 逐日判定是否来得及 × 实际效果</h2>')
a('<p>这是预登记点名要的对账表。来不来得及看危机窗口长度与确认偏移，实际效果看路径四减路径三。</p>')
a('<table><tr><th>危机类型</th><th>事件数</th><th>窗口长度</th><th>逐日判定是否来得及</th>'
  '<th>实际效果（路径四减路径三，中位）</th><th>套对上限（路径一减路径三，中位）</th><th>要点</th></tr>')
deep_len_med = med([r["event_len"] for r in deep])
shal_len_med = med([r["event_len"] for r in shal])
deep_conf = [int(float(r["first_confirm_offset"])) for r in deep_sw]
a(f'<tr><td><span class="tag tag-deep">深慢型（状态扩张）</span></td><td>{len(deep)}</td>'
  f'<td>中位 {deep_len_med:.0f} 日（最长 67 日）</td>'
  f'<td class="ok">来得及——实测第 {min(deep_conf)}–{max(deep_conf)} 日确认</td>'
  f'<td>全组 {med([r["diff_p4_p3"] for r in deep]):.2f}；已切换 {len(deep_sw)} 个中位 '
  f'{med([r["diff_p4_p3"] for r in deep_sw]):+.2f}</td>'
  f'<td>{med([r["diff_p1_p3"] for r in deep]):+.2f}</td>'
  f'<td>判对 {sum(1 for r in deep_sw if r["judged_type"] == "深慢")} 个、假阴 {S["fn"]} 个（漏砍仓代价大）、'
  f'拒绝出手 {sum(1 for r in deep if r["judged_type"] == "无法判定")} 个</td></tr>')
shal_conf = [int(float(r["first_confirm_offset"])) for r in shal_sw]
a(f'<tr><td><span class="tag tag-shallow">浅快型（相关重构）</span></td><td>{len(shal)}</td>'
  f'<td>中位 {shal_len_med:.0f} 日（最短 1 日）</td>'
  f'<td class="warn">部分来得及——9 个窗口只有 1–3 日，切不进</td>'
  f'<td>全组 {med([r["diff_p4_p3"] for r in shal]):.2f}；已切换 {len(shal_sw)} 个中位 '
  f'{med([r["diff_p4_p3"] for r in shal_sw]):+.2f}</td>'
  f'<td>{med([r["diff_p1_p3"] for r in shal]):+.2f}</td>'
  f'<td>假阳 {S["fp"]} 个的实际代价中位为 <b>负</b>——保守处理反而占优；拒绝出手的代价小</td></tr>')
a(f'<tr><td><span class="tag tag-late">急性崩盘（窗口 ≤3 日）</span></td><td>{len(short_ev)}</td>'
  f'<td>1–3 日</td>'
  f'<td class="warn">3 日内来不及——最早第 2 日确认、次一交易日才生效，危机已经结束</td>'
  f'<td>0.00（全部未切换，与基线相同）</td>'
  f'<td>0.00（切换资格都不满足）</td>'
  f'<td>类型预案对急性崩盘无解，只能靠日常止损纪律（产品三范畴）</td></tr>')
a('</table>')
a(f'<div class="note"><b>深慢在第 2–5 日内切得进（最早第 2 日）、浅快部分有价值、急性崩盘 3 日内来不及</b>——'
  f'预登记的三句预期全部对上。另外注意确认偏移的规律：判对的 {sum(1 for r in deep_sw if r["judged_type"] == "深慢")} 个深慢事件'
  f'都在第 2–5 日确认，判错的假阴确认偏移都在第 7 日以后——<b>确认越晚越容易判错</b>（描述性观察，不做宣称）。</div>')

# ── 四、混淆矩阵与误判代价 ──
a('<h2>四、混淆矩阵与误判代价</h2>')
a('<p>判型口径：<b>首次确认切换所用的预案类型</b>；从未切换记无法判定。'
  '实际误判代价 = 该事件（路径一全程累计 减 路径四全程累计）的中位数。</p>')
a('<table><tr><th>真型 ＼ 判型</th><th>深慢</th><th>浅快</th><th>无法判定</th></tr>')
for tt in ("深慢", "浅快"):
    cells = []
    for jt in ("深慢", "浅快", "无法判定"):
        row = next((c for c in conf if c["true_type"] == tt and c["judged_type"] == jt), None)
        n = int(row["n"])
        if n == 0:
            cells.append('<td class="dim">0</td>')
        else:
            cost = float(row["realized_cost_median"])
            cells.append(f'<td><b>{n}</b> 个<br>实际代价中位 <span class="{"warn" if cost > 1 else "ok"}">'
                         f'{cost:+.2f}</span><br><small class="dim">{esc(row["event_ids"])}</small></td>')
    a(f'<tr><td><b>真{tt}</b></td>' + "".join(cells) + '</tr>')
a('</table>')
a(f'<table><tr><th>口径</th><th>数值</th><th>含义</th></tr>'
  f'<tr><td>假阴（真深慢判成浅快）</td><td class="warn">{S["fn"]} 个</td>'
  f'<td>漏砍仓。理论代价常数 7.57，实际代价中位 <b>+11.61</b> 个百分点——比理论更贵</td></tr>'
  f'<tr><td>假阳（真浅快判成深慢）</td><td>{S["fp"]} 个</td>'
  f'<td>误砍仓。理论代价常数 6.16，实际代价中位 <b>-3.73</b> 个百分点——保守反而占优，代价为负</td></tr>'
  f'<tr><td>理论期望代价（本次判定）</td><td class="ok">{S["exp_cost_full"]:.2f}</td>'
  f'<td rowspan="3">全判浅快 = 真深慢数 × 7.57 ÷ 45；全判深慢 = 真浅快数 × 6.16 ÷ 45。'
  f'本次判定优于两种单边基线。注意：无法判定不进理论代价公式（预登记口径），'
  f'其代价看上表的实际代价格</td></tr>'
  f'<tr><td>基线：全判浅快</td><td>{S["base_all_shallow_full"]:.2f}</td></tr>'
  f'<tr><td>基线：全判深慢</td><td>{S["base_all_deep_full"]:.2f}</td></tr>'
  f'<tr><td>后段（2015 年起）理论期望代价</td><td class="ok">{S["exp_cost_test"]:.2f}</td>'
  f'<td>后段基线：全判浅快 {S["base_all_shallow_test"]:.2f}、全判深慢 {S["base_all_deep_test"]:.2f}</td></tr>'
  f'</table>')
a('<div class="boundary"><b>不对称性是本表的核心发现：</b>漏砍仓的实测代价（+11.61）远超误砍仓（-3.73）。'
  '宁可保守错杀、不可漏防深慢——这与理论常数的方向一致，但实测更极端。'
  '同时要看到：无法判定的 32 个事件里，真深慢 7 个错过保护（代价中位 +1.82），'
  '真浅快 25 个拒绝出手几乎无代价（+1.23）。<b>「拿不准就不动」在这批事件里是划算的策略</b>。</div>')

# 纠错机制
corr = [r for r in ev if r["corrections_p4"] and int(float(r["corrections_p4"])) > 0]
a('<h3>纠错机制：3 次全部救回</h3>')
a('<table><tr><th>事件</th><th>起点日</th><th>真型</th><th>首次判型</th><th>纠错后预案</th>'
  '<th>路径一全程</th><th>路径四全程</th><th>路径四 减 路径一</th></tr>')
for r in corr:
    gain = r["p4_full"] - r["p1_full"]
    a(f'<tr><td>{int(r["event_id"])}</td><td>{r["onset"]}</td><td>{r["true_type"]}</td>'
      f'<td>{r["judged_type"]}</td><td><b>{r["final_plan_type"]}</b></td>'
      f'<td class="num">{r["p1_full"]:.2f}</td><td class="num">{r["p4_full"]:.2f}</td>'
      f'<td class="num {"ok" if gain > 0 else "warn"}">{gain:+.2f}</td></tr>')
a('</table>')
a('<p>预登记允许最多纠错一次。实际用到 3 次，3 次的最终预案都回到了真型；'
  '其中 103 号事件纠错后路径四反而超过路径一（先按深慢预案保护了前段，再切回浅快）。</p>')

# ── 五、逐日判定时间线示例 ──
a('<h2>五、逐日判定时间线（三个典型）</h2>')
a('<p>危机确认分 = 当日进入极端状态的特征项数（满分 7，达到 4 才允许确认）；'
  '类型分 = 深慢票占比（三票等权，三分之二以上判深慢、三分之一以下判浅快）。</p>')

examples = [
    (117, "2008-01 大坑：先判浅快、纠错回深慢，躲过 24.6% 的深坑"),
    (113, "判对深慢：第 2 日确认，路径四与路径一完全一致"),
    (119, "拒绝出手的代价：真浅快 69 日长熊，路径三跌 35%，判定始终信息不足"),
]
tl_by_ev = {}
for row in tl:
    tl_by_ev.setdefault(int(row["event_id"]), []).append(row)

for eid, caption in examples:
    rows = tl_by_ev[eid]
    er = next(r for r in ev if int(r["event_id"]) == eid)
    a(f'<details open><summary>事件 {eid}（{er["onset"]} 起，{er["event_len"]} 日）——{esc(caption)}</summary>')
    a('<table><tr><th>偏移</th><th>日期</th><th title="ret_pct">当日涨跌</th>'
      '<th title="judgment">当日判定</th><th title="crisis_score">危机确认分</th>'
      '<th title="type_score">类型分</th><th title="plan_p4">路径四预案</th>'
      '<th title="pos_p1">路一仓</th><th title="pos_p4">路四仓</th>'
      '<th title="V_p1">路一净值</th><th title="V_p4">路四净值</th></tr>')
    show = [r for r in rows if 0 <= int(r["offset"]) <= 20]
    if len(rows) > 21:
        show = show + [r for r in rows if int(r["offset"]) in (len(rows) - 1,)]
    for r in show:
        off = int(r["offset"])
        mark = ""
        if r["plan_p4"] not in ("基线", "") and off > 0:
            prev = rows[off - 1] if off - 1 < len(rows) else None
            if prev and prev["plan_p4"] != r["plan_p4"]:
                mark = ' <span class="tag tag-early">切换</span>'
        tscore = r["type_score"]
        cscore = r["crisis_score"]
        a(f'<tr><td class="num">{off}{mark}</td><td>{r["date"]}</td>'
          f'<td class="num">{f2s(r["ret_pct"])}</td><td>{esc(r["judgment"]) or "—"}</td>'
          f'<td class="num">{esc(cscore) if cscore else "—"}</td>'
          f'<td class="num">{f2s(tscore)}</td><td>{esc(r["plan_p4"])}</td>'
          f'<td class="num">{float(r["pos_p1"]):.0%}</td><td class="num">{float(r["pos_p4"]):.0%}</td>'
          f'<td class="num">{float(r["V_p1"]):.3f}</td><td class="num">{float(r["V_p4"]):.3f}</td></tr>')
    a('</table>')
    a(f'<p class="dim">全程（含回补期）：路径一 {er["p1_full"]:.2f}、路径二 {er["p2_full"]:.2f}、'
      f'路径三 {er["p3_full"]:.2f}、路径四 {er["p4_full"]:.2f} 个百分点。</p>')
    a('</details>')

# ── 六、逐事件总表（可筛选）──
a('<h2>六、逐事件反事实损益总表</h2>')
a('<div><select id="f-type"><option value="">全部真型</option><option>深慢</option><option>浅快</option></select>'
  '<select id="f-judge"><option value="">全部判型</option><option>深慢</option><option>浅快</option><option>无法判定</option></select>'
  '<select id="f-seg"><option value="">全部时段</option><option>前段</option><option>后段</option></select>'
  '<select id="f-sw"><option value="">全部切换情况</option><option value="y">仅已切换</option><option value="n">仅未切换</option></select>'
  '<input type="text" id="f-kw" placeholder="搜事件编号或日期">'
  '<span class="dim" id="f-count"></span></div>')
a('<table id="evtbl"><tr><th>事件</th><th>起点日</th><th>结束日</th>'
  '<th title="event_len">长度</th><th>真型</th><th>判型</th><th title="final_plan_type">最终预案</th>'
  '<th title="first_confirm_offset">确认偏移</th><th title="corrections_p4">纠错</th>'
  '<th>够不够切</th><th title="p1_crisis">路一危机段</th><th title="p1_post">路一事后</th>'
  '<th title="p1_full">路一全程</th><th title="p2_full">路二全程</th><th title="p3_full">路三全程</th>'
  '<th title="p4_full">路四全程</th><th title="p3b_full">敏感性全程</th>'
  '<th title="diff_p1_p3">路一减三</th><th title="diff_p4_p3">路四减三</th>'
  '<th title="diff_p1_p2">路一减二</th><th>段</th></tr>')
for r in sorted(ev, key=lambda x: (x["segment"] != "前段", int(x["event_id"]))):
    jt = r["judged_type"]
    jcls = "tag-deep" if jt == "深慢" else ("tag-none" if jt == "无法判定" else "tag-shallow")
    first = "" if r["first_confirm_offset"] in ("", None) else f'{int(float(r["first_confirm_offset"]))}'
    a(f'<tr class="erow" data-t="{r["true_type"]}" data-j="{jt}" data-s="{r["segment"]}" '
      f'data-w="{"y" if jt != "无法判定" else "n"}" data-k="{r["event_id"]} {r["onset"]} {r["event_end"]}">'
      f'<td>{int(r["event_id"])}</td><td>{r["onset"]}</td><td>{r["event_end"]}</td>'
      f'<td class="num">{int(r["event_len"])}</td><td>{r["true_type"]}</td>'
      f'<td><span class="tag {jcls}">{jt}</span></td><td>{r["final_plan_type"]}</td>'
      f'<td class="num">{first or "—"}</td><td class="num">{int(float(r["corrections_p4"] or 0))}</td>'
      f'<td>{"是" if r["eligible_p12"] == "是" else "否"}</td>'
      f'<td class="num">{r["p1_crisis"]:.2f}</td><td class="num">{r["p1_post"]:.2f}</td>'
      f'<td class="num">{r["p1_full"]:.2f}</td><td class="num">{r["p2_full"]:.2f}</td>'
      f'<td class="num">{r["p3_full"]:.2f}</td><td class="num">{r["p4_full"]:.2f}</td>'
      f'<td class="num">{r["p3b_full"]:.2f}</td>'
      f'<td class="num">{r["diff_p1_p3"]:+.2f}</td><td class="num">{r["diff_p4_p3"]:+.2f}</td>'
      f'<td class="num">{r["diff_p1_p2"]:+.2f}</td><td>{r["segment"]}</td></tr>')
a('</table>')

# ── 七、触发层审计 ──
pc_y = [r for r in aud if r["pc_confirmed"] == "是"]
iv_y = [r for r in aud if r["interval_first_offset"] not in ("", None)]
tp_y = [r for r in aud if r["topo_warn_first_offset"] not in ("", None)]
a('<h2>七、触发层审计：实盘还欠多少</h2>')
a('<div class="danger"><b>价格确认在这 45 个历史事件里只通过 1 个（2015-07 起点前两日命中单日跌幅与五日累计两条）。</b>'
  '冻结标签的起点日多数不是暴跌日，「重大事件加价格确认」的产品触发规格在这批事件上基本抓不住。'
  '实盘触发必须靠事件信息源（新闻与公告监控）起头、区间检测轨与拓扑警戒兜底。'
  '而回测第 0 天直接用了已知起点——所以路径四的数字还要再打触发层的折扣。</div>')
a('<table><tr><th>触发层</th><th>本版角色</th><th>45 事件中发出信号</th><th>典型提前量或延迟</th></tr>'
  f'<tr><td>事件突发轨（价格确认）</td><td>实盘主轨，回测只审计</td>'
  f'<td class="warn">{len(pc_y)} / 45</td><td>唯一命中的是 2015-07（提前 2 日）</td></tr>'
  f'<tr><td>区间检测轨（三条中两条）</td><td>机械兜底轨</td><td>{len(iv_y)} / 45</td>'
  f'<td>多在起点前后 20 日内，部分滞后到起点后 10 日</td></tr>'
  f'<tr><td>拓扑警戒（七项中四项极端）</td><td>预热警戒，不单独触发</td><td>{len(tp_y)} / 45</td>'
  f'<td>提前量最大到 30 日，约半数事件有预警</td></tr></table>')
a('<details><summary>展开 45 事件触发审计明细</summary>')
a('<table><tr><th>事件</th><th>起点日</th><th>真型</th><th>价格确认</th>'
  '<th title="pc_first_offset">命中偏移</th><th title="pc_rules">命中子规则</th>'
  '<th title="interval_first_offset">区间检测首响偏移</th><th>区间检测命中</th>'
  '<th title="topo_warn_lead">拓扑警戒提前量</th></tr>')
for r in sorted(aud, key=lambda x: (x["onset"])):
    iv = r["interval_first_offset"]
    tp = r["topo_warn_lead"]
    a(f'<tr><td>{int(r["event_id"])}</td><td>{r["onset"]}</td><td>{r["true_type"]}</td>'
      f'<td>{"是" if r["pc_confirmed"] == "是" else "否"}</td>'
      f'<td class="num">{esc(r["pc_first_offset"]) or "—"}</td>'
      f'<td>{esc(r["pc_rules"]) or "—"}</td>'
      f'<td class="num">{esc(iv) or "—"}</td>'
      f'<td>{esc(r["interval_first_detail"]) or "—"}</td>'
      f'<td class="num">{esc(tp) or "—"}</td></tr>')
a('</table></details>')
a('<div class="boundary"><b>子规则②（跳空加放量）的如实披露：</b>成交额历史只在事件窗口内可用，'
  '窗口前 20 日均量历史多数不足 15 个可用日，按预登记记不可用。'
  '这解释了为何价格确认几乎全部折戟——两条子规则里放量门槛基本没法参与，只剩单日跌幅与五日累计，'
  '而冻结起点日往往不是暴跌日。这是数据与规格的双重限制，如实报出，不改规则。</div>')

# ── 八、对冲成本敏感性 ──
p1_10 = med([r["p1_full_prem10"] for r in ev])
p1_20 = med([r["p1_full_prem20"] for r in ev])
p4_10 = med([r["p4_full_prem10"] for r in ev])
p4_20 = med([r["p4_full_prem20"] for r in ev])
a('<h2>八、认沽权利金敏感性（只报数字）</h2>')
a(f'<table><tr><th>权利金率</th><th>路径一全程（中位）</th><th>路径四全程（中位）</th></tr>'
  f'<tr><td>1.0%</td><td class="num">{p1_10:.2f}</td><td class="num">{p4_10:.2f}</td></tr>'
  f'<tr><td><b>1.5%（主口径）</b></td><td class="num"><b>{med([r["p1_full"] for r in ev]):.2f}</b></td>'
  f'<td class="num"><b>{med([r["p4_full"] for r in ev]):.2f}</b></td></tr>'
  f'<tr><td>2.0%</td><td class="num">{p1_20:.2f}</td><td class="num">{p4_20:.2f}</td></tr></table>')
a('<p>全样本中位几乎不动——认沽只在深慢预案里买（15 个深慢真型），'
  '中位数由 30 个浅快事件主导。敏感性真正影响的是深慢事件的单点数字，逐事件差异见总表的敏感性列。</p>')
a('<p class="dim">同口径对照：基线加常规止损的敏感性口径全程中位 '
  f'{med([r["p3b_full"] for r in ev]):.2f} 个百分点，纯持有基线中位 '
  f'{med([r["p3_full"] for r in ev]):.2f}。常规止损在 2008-07 那种 69 日长熊里救了 30 个百分点以上（事件 119），'
  '但在多数事件里差异不大——这是产品三的题目，本版只挂一个对照。</p>')

# ── 九、口径与红线 ──
a('<h2>九、口径与红线</h2>')
a('<div class="boundary">'
  '<p>· 第 0 天 = 冻结标签的事件起点日；回测只测分类层与响应层，检测层误差被「已知起点」消掉——'
  '<b>回测结论是实盘的上限</b>。</p>'
  '<p>· 切换在确认日收盘执行（成交锚定当日收盘），新仓位自次一交易日起计损益；'
  '止损锚定切换日收盘，触发后仓位归零至事件结束日，不因切换而恢复；纠错时以纠正日收盘重新锚定。</p>'
  '<p>· 认沽为合成虚值认沽（无期权数据）：生效日行权价为收盘的九成五、名义半仓、'
  '权利金 1.5% 一次扣减，到期收益按事件结束后第 20 交易日收盘结算；不模拟时间价值与提前行权。</p>'
  '<p>· 回补用事后事件结束日触点，属反事实记账口径；实盘需实时解除规则（如 250 日线收复）。</p>'
  '<p>· 真型标签为第八版冻结拓扑分型（状态扩张型 15 / 相关重构型 30）；'
  '类型投票方向取自第十版样本内交互结果，属样本内知识固化，如实披露。</p>'
  '<p>· 禁止事项：不重判十四条推测；不改任何冻结产物；不反选参数；'
  '不读 2025 年最终测试集；路径一是上限不得当产品收益；不做组均值显著性宣称。</p>'
  '</div>')
a('<div class="danger"><b>三句必须带走的话：</b><br>'
  f'一、危机类型条件化预案的<b>上限价值</b>是中位 +{q13[1]:.2f} 个百分点（路径一减路径三）；'
  f'实时分类在<b>切换了的 {len(sw)} 个事件</b>里拿到中位 +{q43sw[1]:.2f} 个百分点，'
  f'但 45 个里 32 个信息不足拒绝出手，全样本中位归零。<br>'
  '二、<b>假阴远贵于假阳</b>（实测 +11.61 对 -3.73）：深慢危机漏砍仓是主要风险，'
  '拿不准时保守处理反而不吃亏。<br>'
  '三、触发层是最大的实盘缺口——价格确认历史通过率 1/45，'
  '事件突发轨在实盘必须由事件信息源补位，否则连第 0 天都到不了。</div>')

# footer
gat = manifest["created"]
try:
    dt = datetime.fromisoformat(gat)
    gat = f"{dt.year} 年 {dt.month} 月 {dt.day} 日"
except Exception:
    gat = ""
a('</div>')  # 闭合首卡
a(f'<footer>产品二核心验证 · 预登记 v0.11 · 生成于 {gat} · 45 个冻结统计事件 · '
  f'全流程确定性（双跑字节一致）· 全部为样本内反事实记账</footer>')
a('</body></html>')

# ── 筛选脚本 ──
a("""<script>
(function(){
  var rows=[].slice.call(document.querySelectorAll('#evtbl .erow'));
  var ft=document.getElementById('f-type'),fj=document.getElementById('f-judge'),
      fs=document.getElementById('f-seg'),fw=document.getElementById('f-sw'),
      fk=document.getElementById('f-kw'),fc=document.getElementById('f-count');
  function apply(){
    var t=ft.value,j=fj.value,s=fs.value,w=fw.value,k=fk.value.trim(),n=0;
    rows.forEach(function(r){
      var ok=(!t||r.dataset.t===t)&&(!j||r.dataset.j===j)&&(!s||r.dataset.s===s)
             &&(!w||r.dataset.w===w)&&(!k||r.dataset.k.indexOf(k)>=0);
      r.style.display=ok?'':'none'; if(ok)n++;
    });
    fc.textContent='当前 '+n+' / '+rows.length+' 个事件';
  }
  [ft,fj,fs,fw].forEach(function(e){e.addEventListener('change',apply);});
  fk.addEventListener('input',apply); apply();
})();
</script>""")

text = "".join(A)
(OUT / "crisis_counterfactual_v011_report.html").write_text(text, encoding="utf-8")
print("report written:", OUT / "crisis_counterfactual_v011_report.html")
print("size:", len(text))
