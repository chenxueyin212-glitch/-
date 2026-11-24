# -*- coding: utf-8 -*-
"""v0.22 净值可视化：单文件 HTML（echarts 内联）。

输入（v0.22 冻结产物，只读）：
  tda_project/outputs/regime_v022_netvalue_daily.csv      逐日净值（九臂）+ pos_A2
  tda_project/outputs/regime_v022_netvalue_yearly.csv      分年收益
  tda_project/outputs/regime_v022_netvalue_events.csv      A2 事件日志
  tda_project/outputs/regime_v012_trigger_event_timing.csv 45 事件起止（画事件带）
输出：tda_crisis_netvalue_visual_20261119.html
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tda_project" / "outputs"
ECHARTS = (ROOT / "paper_drafts" / "echarts.min.js").read_text(encoding="utf-8")
HTML = ROOT / "tda_crisis_netvalue_visual_20261119.html"

daily = pd.read_csv(OUT / "regime_v022_netvalue_daily.csv")
yearly = pd.read_csv(OUT / "regime_v022_netvalue_yearly.csv")
events_log = pd.read_csv(OUT / "regime_v022_netvalue_events.csv")
tim0 = pd.read_csv(OUT / "regime_v012_trigger_event_timing.csv")
ev = tim0[tim0["policy"] == "乙"].drop_duplicates(subset=["event_id"]).sort_values("onset")

dates = daily["date"].tolist()
event_bands = [[r["onset"], r["event_end"]] for _, r in ev.iterrows()]

a2_log = events_log[events_log["arm"] == "A2"]
a2_switches = a2_log[a2_log["action"].isin(["切换", "修正"])]
switch_marks = sorted(a2_switches["date"].unique().tolist())
a2_stops = a2_log[a2_log["action"] == "止损"]["date"].tolist()

# 回撤序列
def drawdown(nav_col):
    nav = daily[nav_col]
    peak = nav.cummax()
    return (nav / peak - 1.0)


dd = {c: drawdown(f"nav_{c}").tolist() for c in ["E0", "A2"]}

# 2008 放大窗
mask08 = (daily["date"] >= "2007-06-01") & (daily["date"] <= "2009-06-30")
d08 = daily[mask08]
dates08 = d08["date"].tolist()

years = [c for c in yearly.columns if c != "arm"]
yr_e0 = yearly[yearly["arm"] == "E0"].iloc[0]
yr_a2 = yearly[yearly["arm"] == "A2"].iloc[0]
yrly = [[y, round(float(yr_e0[y]), 2), round(float(yr_a2[y]), 2)] for y in years]

# 降采样导航用全部数据（6483 点 echarts 可承受）；净值取两位小数减小体积
def slim(col):
    return [round(v, 4) for v in daily[col].tolist()]


data = {
    "dates": dates,
    "nav": {c: slim(f"nav_{c}") for c in ["E0", "A2"]},
    "dd": {k: [round(v * 100, 2) for v in dd[k]] for k in dd},
    "dates08": dates08,
    "nav08": {c: [round(v, 4) for v in d08[f"nav_{c}"].tolist()] for c in ["E0", "A2"]},
    "pos_a2": [round(v, 3) for v in daily["pos_A2"].tolist()],
    "event_bands": event_bands,
    "switch_marks": switch_marks,
    "stop_marks": a2_stops,
    "yearly": yrly,
    "years": years,
}
data_js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>净值口径完整核算 · 连续净值曲线（1999-2026）</title>
<style>
  body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin: 0; background: #f5f6f8; color: #26303d; }
  .wrap { max-width: 1380px; margin: 0 auto; padding: 18px 20px 40px; }
  h1 { font-size: 22px; margin: 6px 0 4px; }
  h2 { font-size: 17px; margin: 26px 0 8px; }
  .sub { color: #5a6675; font-size: 13px; margin-bottom: 12px; line-height: 1.7; }
  .stats { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0 14px; }
  .card { background: #fff; border: 1px solid #e3e7ec; border-radius: 8px; padding: 10px 14px; min-width: 170px; }
  .card .k { font-size: 12px; color: #6b7686; }
  .card .v { font-size: 18px; font-weight: 700; margin-top: 2px; }
  .chart { background: #fff; border: 1px solid #e3e7ec; border-radius: 8px; padding: 10px; margin-bottom: 6px; }
  .note { background: #fff8e6; border: 1px solid #eeddab; border-radius: 8px; padding: 12px 16px; font-size: 13px; line-height: 1.8; margin: 12px 0; }
  .foot { color: #6b7686; font-size: 12px; line-height: 1.8; margin-top: 18px; border-top: 1px solid #e3e7ec; padding-top: 10px; }
</style>
<script>__ECHARTS__</script>
</head>
<body>
<div class="wrap">
<h1>净值口径完整核算（v0.22）：连续净值曲线</h1>
<div class="sub">主候选＝方案一＋滚动判定钟 × 回补B（告警静默满10日后20日线性回补）× 认沽＋止损＋修正，成本单边万10。
判定层冻结复用先前实验产物；净值核算不含任何事件结束日前视信息。1999-12-30 起，净值=1，共 6483 个交易日。</div>

<div class="stats">
  <div class="card"><div class="k">基准（全仓持有万得全A）</div><div class="v">年化 6.77% / 回撤 −70.6%</div></div>
  <div class="card"><div class="k">主候选 A2（全件×回补B×万10）</div><div class="v">年化 7.44% / 回撤 −57.2%</div></div>
</div>

<h2>一、净值曲线（对数轴，浅红带＝45 次危机区间）</h2>
<div class="chart"><div id="c1" style="height:520px;"></div></div>
<div class="sub">主候选（红）在 2008、2015-16 的危机带内明显规避了基准（灰）的深坑；2005 年谷底（四年长熊）两线同步下行——仓位层对缓跌无解，认沽才是深熊保护来源。</div>

<h2>二、回撤曲线（峰值回撤 %，越浅越好）</h2>
<div class="chart"><div id="c2" style="height:420px;"></div></div>
<div class="sub">基准最大回撤 −70.6%（2008-11 谷底）；主候选 −57.2%（谷底在 2005-07-18，四年熊累积）。危机年的深回撤被砍掉一截，长熊段与基准同沉。</div>

<h2>三、2008 年放大（2007-06 → 2009-06）</h2>
<div class="chart"><div id="c3" style="height:420px;"></div></div>
<div class="sub">2008 全年：主候选 −32.0% vs 基准 −62.9%——滚动判定钟在两次崩跌段的持续警戒是这一年保护的主体来源。</div>

<h2>四、分年收益对比（基准 vs 主候选）</h2>
<div class="chart"><div id="c4" style="height:430px;"></div></div>
<div class="sub">红柱在 2008/2015/2016 显著高于灰柱＝危机年规避；灰柱高于红柱的年份＝代价年：2022（−18.7 vs −25.3）、2024（+10.0 vs −0.5）、2026（−14.8 vs −21.1）——水平型卡死与回补鞭打原样呈现，未修。</div>

<h2>五、主候选仓位序列（0＝清仓止损，0.5＝深慢，0.8＝浅快，1＝满仓）</h2>
<div class="chart"><div id="c5" style="height:380px;"></div></div>
<div class="sub">27 年里平均仓位 86.5%；低于满仓的交易日集中在危机段与回补斜坡。全史止损仅 3 次（2001-10、2008-03、2008-09）。</div>

<div class="note"><b>认沽口径披露（读图必读）</b>：主候选含合成虚值认沽（1.5% 固定权利金，注册简化口径）。该口径在急跌中严重低估真实对冲成本——2015 年 4 笔认沽净现金流 +2.13（占当期净值两倍以上）是主候选相对基准年化优势的主要放大器，其余年份认沽净现金流合计为负。
对照臂读数（未入图）：去掉认沽后年化 6.99%、回撤 −58.5%，仍优于基准（6.77%／−70.6%）——主候选的优势不全部依赖该口径，但红线与基准的差额中认沽记账占了相当部分，不构成对冲价值证据。</div>

<div class="foot">证据边界：样本内机械模拟，不外推；万得全A 为指数，不可直接交易（跟踪工具费差未计）；停牌与流动性冲击未计；认沽为合成简化记账（无市场期权数据）；判定层（触发/告警/确认/判型/切换）逐字冻结复用，本图只重算仓位与现金流。数据与对账：tda_project/outputs/regime_v022_netvalue_*（三跑逐字节一致）。</div>
</div>

<script>
var D = __DATA__;
function markBands() {
  return D.event_bands.map(function(b, i) {
    return {xAxis: b[0], itemStyle: {color: "rgba(230,80,80,0.07)"}, label: {show: false}};
  });
}
function baseGrid() {
  return {left: 64, right: 24, top: 30, bottom: 46};
}
function axisX(dates) {
  return {type: "category", data: dates, axisLabel: {formatter: function(v) { return v.slice(0, 4); }}};
}

var c1 = echarts.init(document.getElementById("c1"));
c1.setOption({
  tooltip: {trigger: "axis", formatter: function(ps) {
    var s = ps[0].axisValue + "<br/>";
    ps.forEach(function(p) { s += p.marker + p.seriesName + "：" + p.value.toFixed(3) + "<br/>"; });
    return s;
  }},
  legend: {top: 2},
  grid: baseGrid(),
  xAxis: axisX(D.dates),
  yAxis: {type: "log", min: 0.4, axisLabel: {formatter: function(v) { return v.toFixed(1); }}},
  dataZoom: [{type: "inside"}, {type: "slider", height: 18, bottom: 8}],
  series: [
    {name: "基准（全仓持有）", type: "line", data: D.nav.E0, showSymbol: false, lineStyle: {width: 1.6, color: "#8a94a3"}, itemStyle: {color: "#8a94a3"}},
    {name: "主候选 A2", type: "line", data: D.nav.A2, showSymbol: false, lineStyle: {width: 2.0, color: "#d63a3a"}, itemStyle: {color: "#d63a3a"},
     markLine: {symbol: "none", silent: true, data: D.event_bands.map(function(b) { return {xAxis: b[0], lineStyle: {color: "rgba(230,80,80,0.25)", width: 8, type: "solid"}, label: {show: false}}; })}}
  ]
});

var c2 = echarts.init(document.getElementById("c2"));
c2.setOption({
  tooltip: {trigger: "axis", valueFormatter: function(v) { return v.toFixed(1) + "%"; }},
  legend: {top: 2},
  grid: baseGrid(),
  xAxis: axisX(D.dates),
  yAxis: {max: 0, axisLabel: {formatter: "{value}%"}},
  dataZoom: [{type: "inside"}, {type: "slider", height: 18, bottom: 8}],
  series: [
    {name: "基准", type: "line", data: D.dd.E0, showSymbol: false, lineStyle: {width: 1.6, color: "#8a94a3"}, itemStyle: {color: "#8a94a3"}, areaStyle: {opacity: 0.08}},
    {name: "主候选 A2", type: "line", data: D.dd.A2, showSymbol: false, lineStyle: {width: 1.9, color: "#d63a3a"}, itemStyle: {color: "#d63a3a"}}
  ]
});

var c3 = echarts.init(document.getElementById("c3"));
c3.setOption({
  tooltip: {trigger: "axis", valueFormatter: function(v) { return v.toFixed(3); }},
  legend: {top: 2},
  grid: baseGrid(),
  xAxis: {type: "category", data: D.dates08, axisLabel: {formatter: function(v) { return v.slice(0, 7); }}},
  yAxis: {type: "log", min: 0.3},
  series: [
    {name: "基准", type: "line", data: D.nav08.E0, showSymbol: false, lineStyle: {width: 1.6, color: "#8a94a3"}, itemStyle: {color: "#8a94a3"}},
    {name: "主候选 A2", type: "line", data: D.nav08.A2, showSymbol: false, lineStyle: {width: 2.0, color: "#d63a3a"}, itemStyle: {color: "#d63a3a"}}
  ]
});

var c4 = echarts.init(document.getElementById("c4"));
c4.setOption({
  tooltip: {trigger: "axis", valueFormatter: function(v) { return v.toFixed(1) + "%"; }},
  legend: {top: 2},
  grid: {left: 56, right: 20, top: 30, bottom: 56},
  xAxis: {type: "category", data: D.years, axisLabel: {rotate: 45}},
  yAxis: {axisLabel: {formatter: "{value}%"}},
  dataZoom: [{type: "inside"}, {type: "slider", height: 18, bottom: 8}],
  series: [
    {name: "基准", type: "bar", data: D.yearly.map(function(r) { return r[1]; }), itemStyle: {color: "#b9c0cc"}},
    {name: "主候选 A2", type: "bar", data: D.yearly.map(function(r) { return r[2]; }), itemStyle: {color: "#d63a3a"}}
  ]
});

var c5 = echarts.init(document.getElementById("c5"));
c5.setOption({
  tooltip: {trigger: "axis", valueFormatter: function(v) { return (v * 100).toFixed(0) + "% 仓位"; }},
  grid: baseGrid(),
  xAxis: axisX(D.dates),
  yAxis: {min: 0, max: 1, axisLabel: {formatter: function(v) { return (v * 100) + "%"; }}},
  dataZoom: [{type: "inside"}, {type: "slider", height: 18, bottom: 8}],
  series: [
    {name: "主候选仓位", type: "line", data: D.pos_a2, showSymbol: false, step: false,
     lineStyle: {width: 0.8, color: "#d63a3a"}, itemStyle: {color: "#d63a3a"}, areaStyle: {opacity: 0.18, color: "#d63a3a"}}
  ]
});

window.addEventListener("resize", function() { [c1, c2, c3, c4, c5].forEach(function(c) { c.resize(); }); });
</script>
</body>
</html>
"""

html = html.replace("__ECHARTS__", ECHARTS).replace("__DATA__", data_js)
HTML.write_text(html, encoding="utf-8")
print("written:", HTML, f"{HTML.stat().st_size/1e6:.2f} MB")
