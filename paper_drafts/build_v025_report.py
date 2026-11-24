# -*- coding: utf-8 -*-
"""生成 v0.25 条件化抱团拓扑实验报告（独立HTML）。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tda_project" / "outputs"
PREFIX = "regime_v025_crowding_topo"


def fmt(x, n=3):
    if pd.isna(x):
        return "—"
    return f"{float(x):+.{n}f}"


CSS = """
:root{--ink:#1d2733;--muted:#627181;--line:#dfe6ee;--paper:#f6f8fb;--card:#fff;
--red:#b42318;--redbg:#fef3f2;--green:#067647;--greenbg:#ecfdf3;--amber:#8a5a00;--amberbg:#fffaeb;--blue:#1849a9;--bluebg:#eff4ff}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:"Noto Sans SC","Microsoft YaHei","PingFang SC",Arial,sans-serif;line-height:1.65}
.wrap{max-width:1180px;margin:0 auto;padding:34px 28px 64px}
h1{font-size:29px;line-height:1.3;margin:0 0 8px}h2{font-size:21px;margin:34px 0 12px}
h3{font-size:16px;margin:20px 0 8px}p{margin:8px 0}.sub{color:var(--muted)}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:22px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi b{display:block;font-size:25px;line-height:1.2}.kpi span{font-size:12px;color:var(--muted)}
.verdict{background:var(--redbg);border:1px solid #fecdca;border-left:5px solid var(--red);
border-radius:10px;padding:16px 18px;margin:18px 0}
.verdict b{color:var(--red)}
.note{background:var(--bluebg);border:1px solid #c7d7fe;border-left:5px solid var(--blue);
border-radius:10px;padding:14px 18px;margin:14px 0}
.warn{background:var(--amberbg);border:1px solid #fedf89;border-left:5px solid var(--amber);
border-radius:10px;padding:14px 18px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0}
table{width:100%;border-collapse:collapse;background:var(--card);font-size:13px}
th,td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
th{background:#f0f4f9;color:#344054;font-weight:600;white-space:nowrap}
tr:hover td{background:#fafcff}.neg{color:var(--red);font-weight:600}.pos{color:var(--green);font-weight:600}
.tag{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;border:1px solid var(--line);white-space:nowrap}
.no{background:var(--redbg);color:var(--red);border-color:#fecdca}.ye{background:var(--amberbg);color:var(--amber);border-color:#fedf89}
.ok{background:var(--greenbg);color:var(--green);border-color:#abefc6}
.small{font-size:12px;color:var(--muted)}.mono{font-family:Consolas,monospace;font-size:12px}
ul{margin:8px 0 8px 22px;padding:0}li{margin:5px 0}
@media(max-width:900px){.kpis{grid-template-columns:repeat(2,1fr)}.wrap{padding:22px 14px}}
"""


def main():
    E = pd.read_csv(OUT / f"{PREFIX}_events.csv")
    T = pd.read_csv(OUT / f"{PREFIX}_tests.csv")
    P = pd.read_csv(OUT / f"{PREFIX}_placebo_compare.csv")
    post = pd.read_csv(OUT / f"{PREFIX}_posthoc_simple_baselines.csv")
    summary = json.loads((OUT / f"{PREFIX}_summary.json").read_text(encoding="utf-8"))

    test_rows = []
    names = {
        "m1_z_dtp0_20": "方法1 · 组内H0总持续性变化（随机组z）",
        "m2_delta_area_20": "方法2 · 嵌入存活面积变化",
        "m3_survival_days": "方法3 · 固定尺度连通寿命",
        "m4_delta_frag_20": "方法4 · Mapper碎裂度变化",
    }
    for _, r in T.iterrows():
        gate = "<span class='tag no'>否</span>" if not bool(r.positive_gate) else "<span class='tag ok'>是</span>"
        test_rows.append(
            f"<tr><td>{names.get(r.metric,r.metric)}</td>"
            f"<td class='mono'>{r.metric}</td><td>{int(r.expected_sign):+d}</td>"
            f"<td class='{'neg' if r.rho*r.expected_sign<0 else ''}'>{fmt(r.rho)}</td>"
            f"<td>{fmt(r.p)}</td><td>{fmt(r['q'])}</td>"
            f"<td>{int(r.loo_ok)}/{int(r.loo_n)}</td><td>{fmt(r.partial_r)} ({fmt(r.partial_p)})</td>"
            f"<td>{gate}</td></tr>")
    placebo_rows = []
    pn = {"m1_dtp0_20":"组内H0持续性变化", "m2_delta_area_20":"嵌入存活面积变化",
          "m3_survival_days":"连通寿命", "m4_delta_frag_20":"Mapper碎裂度变化"}
    for _, r in P.iterrows():
        placebo_rows.append(f"<tr><td>{pn.get(r.metric,r.metric)}</td><td class='mono'>{r.metric}</td>"
                            f"<td>{fmt(r.real_median)}</td><td>{fmt(r.placebo_median)}</td>"
                            f"<td>{fmt(r.mw_p)}</td><td>{int(r.n_real)} / {int(r.n_placebo)}</td></tr>")
    ev_rows = []
    for _, r in E.sort_values("onset").iterrows():
        ev_rows.append(f"<tr><td>{int(r.event_id)}</td><td>{r.onset}</td><td>{r['round']}</td>"
                       f"<td>{r.kind}</td><td class='{'neg' if r.spread<0 else 'pos'}'>{fmt(r.spread,2)}</td>"
                       f"<td>{int(r.gsize)}</td><td>{fmt(r.m1_z_dtp0_20,2)}</td>"
                       f"<td>{fmt(r.m2_delta_area_20,3)}</td><td>{int(r.m3_survival_days)}</td>"
                       f"<td>{fmt(r.m4_delta_frag_20,0)}</td></tr>")
    m1 = T[T.metric == "m1_z_dtp0_20"].iloc[0]
    m2 = T[T.metric == "m2_delta_area_20"].iloc[0]
    m3 = T[T.metric == "m3_survival_days"].iloc[0]
    m4 = T[T.metric == "m4_delta_frag_20"].iloc[0]
    p1 = P[P.metric == "m1_dtp0_20"].iloc[0]
    p2 = P[P.metric == "m2_delta_area_20"].iloc[0]
    m3max = int((E.m3_survival_days == 42).sum())
    m4zero = int((E.m4_delta_frag_20 == 0).sum())

    html = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>条件化抱团拓扑四法实验 · v0.25</title><style>{CSS}</style>
<div class="wrap">
<div class="sub">A股危机拓扑研究 · 探索性预登记实验 v0.25 · 2026-11-21</div>
<h1>条件化抱团拓扑四法实验：四门全否，方法1出现稳定反向关联</h1>
<p class="sub">样本：2007-05 至 2025-03，31 个标签段、9 个危机轮次；只使用训练期，2026 段未读取。预登记于计算前冻结：<span class="mono">regime_crowding_topo_v0.25.toml</span>。</p>

<div class="kpis">
<div class="kpi"><b>31</b><span>可用事件段</span></div>
<div class="kpi"><b>9</b><span>危机轮次（聚类单位）</span></div>
<div class="kpi"><b>200</b><span>每事件随机行业组</span></div>
<div class="kpi"><b>0 / 4</b><span>通过预登记门槛</span></div>
<div class="kpi"><b>逐字节</b><span>双跑一致（事件表/检验表）</span></div>
</div>

<div class="verdict"><b>判定：四法均未通过。</b> 方法1 的 q=0.076 看似过线，但方向与预登记相反，按规则记否定；不能把符号翻过来再宣称通过。最实质的发现是：行业指数层面的抱团瓦解更像“抱得更紧、一起跌”的共跌型，而不是“组内结构散开”的分化型。</div>

<h2>一、四个主指标</h2>
<table><thead><tr><th>方法</th><th>指标</th><th>预期符号</th><th>Spearman ρ</th><th>p</th><th>BH q</th><th>留一轮同向</th><th>控 pre_q5+年份</th><th>过门</th></tr></thead>
<tbody>{''.join(test_rows)}</tbody></table>
<p class="small">q 为四个主指标一个 BH 族；留一轮同向按预登记方向计，方法1 的 0/9 是因为实际 9/9 全部为反向。控 pre_q5+年份列为偏相关 r（括号内 p）。</p>

<div class="card"><h3>方法1：反向关联不是噪声</h3>
<p>{m1.metric} 与 signed spread 的 ρ=+{m1.rho:.3f}（p={m1.p:.3f}，q={m1['q']:.3f}）。留一轮 9/9 仍为正，区间约 +0.31 至 +0.61；控制 pre_q5 与年份后 r=+{m1.partial_r:.3f}（p={m1.partial_p:.3f}）。</p>
<p>时间安慰剂：真实事件第 20 日组内 H0 总持续性变化中位 <b>{p1.real_median:+.3f}</b>，同年代非危机日 <b>{p1.placebo_median:+.3f}</b>（MW p={p1.mw_p:.4f}，{int(p1.n_real)} 个真实段对 {int(p1.n_placebo)} 个合格安慰剂日）。危机中组内点云不是散开，而是更紧。把“瓦解”预设成 H0 上升，方向写反了。</p>
<p class="small">这不是可升级的确认结果：预登记方向已失败，反向解释属于事后假设生成。且行业指数会平均掉个股差异，不能冒充个股抱团。</p></div>

<div class="card"><h3>方法2：有危机共性，没有横截面判别</h3>
<p>嵌入存活面积变化与 spread 方向一致（ρ=+{m2.rho:.3f}），但 p={m2.p:.3f}、q={m2['q']:.3f}，控制 pre_q5+年份后 p={m2.partial_p:.3f}。时间安慰剂真实 {p2.real_median:+.4f} vs 非危机 {p2.placebo_median:+.4f}（p={p2.mw_p:.3f}）：危机中强势组确实更容易通过外部行业混成一片，但它不能区分“哪一组跌得更惨”。</p></div>

<div class="card"><h3>方法3、4：当前构造基本退化</h3>
<p>方法3 有 {m3max}/31 段存活到观察末的 42 日，只有两段提前死亡，近乎常量，无法检验。方法4 有 {m4zero}/31 段碎裂度变化为 0；方向虽为负（ρ={m4.rho:.3f}），p={m4.p:.3f}，且随机组同向校验未过。</p>
<p class="small">这不能被写成“Zigzag/Mapper 已证明无效”；只能写成“固定尺度连通寿命/当前Mapper参数在本样本退化”。</p></div>

<h2>二、时间安慰剂</h2>
<table><thead><tr><th>指标</th><th>字段</th><th>真实事件中位</th><th>同年代非危机日中位</th><th>MW p</th><th>n</th></tr></thead>
<tbody>{''.join(placebo_rows)}</tbody></table>
<p class="small">安慰剂日为同一年份、距任何事件起点至少 40 个交易日的最远非危机日；每个安慰剂日重新按自身前 250 日构造强势组，不搬用真实事件的 G。仅作描述，不参与主判据。</p>

<h2>三、事后简单基准核对</h2>
<p>方法1 与“组内平均相关变化”几乎不相关（ρ=−0.062，p=0.742）；控制该变量后，方法1 与 spread 的偏相关仍为 +0.353（p=0.051）。它<strong>不是平均相关的简单换皮</strong>，但方向仍是共跌，不是结构散开。</p>
<p class="small">该核对在看完主结果后进行，只能用于解释，不得用来追加“通过”结论。</p>

<h2>四、全部事件明细</h2>
<table><thead><tr><th>ID</th><th>起点</th><th>危机轮次</th><th>形态</th><th>spread</th><th>|G|</th><th>M1 z</th><th>M2 Δ面积</th><th>M3 日</th><th>M4 Δ碎裂</th></tr></thead>
<tbody>{''.join(ev_rows)}</tbody></table>
<p class="small">spread=Q5−Q1（股票层，百分点）；负值表示前期最强组更惨。G 为起点前第21个交易日按过去250日收益取前20%的行业组。</p>

<h2>五、判读与下一步</h2>
<div class="note"><b>可以带走的结论：</b>全局汇总的 50 个变化量无稳定信号；锁定事前强势组后，组内 H0 变化确实与事后风格差相关，但方向是“抱团更紧、一起跌”，而不是“结构散开”。嵌入存活只显示危机共性，Zigzag 近似和 Mapper 在当前构造下退化。</div>
<div class="warn"><b>不能带走的结论：</b>没有找到可直接升级的抱团瓦解拓扑参数；q=0.076 不能单独摘出宣称显著；行业指数结果不等于个股抱团；四法均否不构成“拓扑方法整体无效”的证明。</div>
<ol>
<li><b>下一道门：</b>另立预登记，把“组内 H0 下降 = 共跌型抱团瓦解”作为新假设，而不是改 v0.25 的符号。</li>
<li><b>必须加的基准：</b>组内平均相关、首特征值、H0 水平、G−B 收益差；方法1 目前只排除了平均相关这一项。</li>
<li><b>分辨率：</b>若要继续追抱团，行业指数不够；需要个股点云或持仓/成交集中度。没有这些数据时，只能称“前期强势组”。</li>
<li><b>产品：</b>本实验不改 S3、B10、确认票、判型或仓位核算；不构成产品升级证据。</li>
</ol>

<p class="small">产物：{PREFIX}_events.csv / _tests.csv / _summary.json / _placebo.csv / _placebo_compare.csv / _posthoc_simple_baselines.csv；预登记 config/regime_crowding_topo_v0.25.toml；双跑日志 run1/run2。报告生成于 {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}。</p>
</div></html>"""
    path = OUT / "crowding_topo_v025_report.html"
    path.write_text(html, encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
