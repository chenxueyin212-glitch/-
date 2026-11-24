# -*- coding: utf-8 -*-
"""生成单张「动作总览图」：万得全A收盘价 + 45 次危机区间带 + 方案一/方案二动手节点。
只标注三样东西：价格、45 个危机事件段（红色竖带）、两方案全部动手点
（事件侧切换＋误报段激活，实心/空心区分），其余一概不放。
数据与 build_ch5_visual.py 同源（v0.19 冻结产物），自包含单 HTML。
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

OUT = Path(r"D:/WorkBuddy/2026-10-28-22-54-51/tda_project/outputs")
ECH = Path(r"D:/WorkBuddy/2026-10-28-22-54-51/paper_drafts/echarts.min.js")
DEST = Path(r"D:/WorkBuddy/2026-10-28-22-54-51/tda_crisis_action_overview_20261118.html")

# ---------- 1. 价格与日历 ----------
b = pd.read_csv(OUT / "regime_v05_benchmark_daily.csv", parse_dates=["date"])
n = len(b)
assert n == 6483
cal = b["date"].dt.strftime("%Y-%m-%d").tolist()
idx_of = {d: i for i, d in enumerate(cal)}
close = b["wind_close"].to_numpy(dtype=float)

# ---------- 2. 45 危机区间带 ----------
ev = pd.read_csv(OUT / "regime_v019_c1_completion_event_matrix.csv", encoding="utf-8-sig")
ev = ev[ev["arm"].isin(["F7K4", "F10K6"])]
bands = []
p1_evt, p2_evt = [], []   # 事件侧动手点（含修正切换）
for _, r in ev[ev["arm"] == "F7K4"].iterrows():
    bands.append({"on": r["onset"], "en": r["event_end"], "id": r["event_id"]})
    for arm, pid, lst in [("F7K4", "p1", p1_evt), ("F10K6", "p2", p2_evt)]:
        rr = ev[(ev["arm"] == arm) & (ev["event_id"] == r["event_id"])].iloc[0]
        td = rr["trigger_date"]
        offs_raw = str(rr["switch_offs_p4"]) if pd.notna(rr["switch_offs_p4"]) else ""
        if offs_raw and offs_raw not in ("", "nan") and pd.notna(td):
            offs = [int(x) for x in offs_raw.replace("；", ";").split(";") if x.strip()]
            judged = rr["judged_type"]
            for k_i, k in enumerate(offs):
                kind = judged if k_i == 0 else ("浅快" if judged == "深慢" else "深慢")
                lst.append({"d": cal[idx_of[td] + k], "off": k, "kind": kind,
                            "eid": r["event_id"], "fix": k_i > 0})

# ---------- 3. 误报段动手点 ----------
fe = pd.read_csv(OUT / "regime_v019_c1_completion_false_episodes.csv", encoding="utf-8-sig")
p1_fa, p2_fa = [], []
for arm, pid, lst in [("F7K4", "p1", p1_fa), ("F10K6", "p2", p2_fa)]:
    sub = fe[(fe["arm"] == arm) & (fe["final_plan_type"].isin(["深慢", "浅快"]))]
    for _, m in sub.iterrows():
        lst.append({"d": cal[idx_of[m["episode_start"]] + int(m["first_confirm_offset"])],
                    "kind": m["final_plan_type"], "off": int(m["first_confirm_offset"]),
                    "seg": f'{m["episode_start"]}→{m["episode_end"]}', "fix": False})

assert (len(p1_evt), len(p2_evt)) == (22, 20), (len(p1_evt), len(p2_evt))
assert (len(p1_fa), len(p2_fa)) == (33, 21), (len(p1_fa), len(p2_fa))

payload = {
    "dates": cal,
    "close": [round(float(x), 2) for x in close],
    "bands": bands,
    "p1evt": p1_evt, "p2evt": p2_evt, "p1fa": p1_fa, "p2fa": p2_fa,
}
# close 数值编进每个点，避免 JS 端查表
def inject(pid):
    for p in payload[pid]:
        p["c"] = round(float(close[idx_of[p["d"]]]), 2)

for k in ("p1evt", "p2evt", "p1fa", "p2fa"):
    inject(k)

data_js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

HTML = """<html lang="zh-CN">
<head><meta charset="UTF-8">
<title>动作总览 · 万得全A走势与 45 次危机区间、两方案动手节点（1999-2026）</title>
<style>
 body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin:0; background:#f5f6f8; color:#26303d; }
 .wrap { max-width: 1420px; margin: 0 auto; padding: 18px 20px 40px; }
 h1 { font-size: 20px; margin: 6px 0 4px; }
 .sub { color:#5a6675; font-size:13px; margin-bottom:10px; line-height:1.7; }
 .legend { background:#fff; border:1px solid #e3e7ec; border-radius:8px; padding:10px 16px; font-size:13px; line-height:2.0; margin-bottom:10px; }
 .chip { display:inline-block; width:12px; height:12px; border-radius:3px; margin:0 6px -1px 10px; }
 .chart { background:#fff; border:1px solid #e3e7ec; border-radius:8px; padding:6px 4px 2px; }
 #main { width:100%; height:640px; }
 .warn { color:#a33; font-weight:600; }
</style></head>
<body><div class="wrap">
<h1>动作总览：万得全A走势 · 45 次危机区间 · 方案一／方案二动手节点</h1>
<div class="sub">数据区间 1999-12-30 至 2026-11-03（6483 个交易日）。本图只标注三样东西：收盘价走势、45 个危机事件段（红色竖带，起点→结束日）、两方案全部动手点。<span class="warn">动手点为历史重放口径，样本内描述性对照，不构成样本外业绩。</span></div>
<div class="legend">
<b>图例</b>：
<span class="chip" style="background:rgba(192,57,43,0.35)"></span>红色竖带＝45 起危机事件段（起点→结束日，不含前后各 20 日识别窗）
● <span style="color:#2c7fb8">蓝色实心圆</span>＝方案一在真实危机中切换预案（22 点＝19 事件＋3 次类型修正）
○ <span style="color:#2c7fb8">蓝色空心圆</span>＝方案一在误报段上动手（33 点）
◆ <span style="color:#7b3fa0">紫色实心菱形</span>＝方案二在真实危机中切换预案（20 点＝17 事件＋3 次修正）
◇ <span style="color:#7b3fa0">紫色空心菱形</span>＝方案二在误报段上动手（21 点）
悬停可查看日期、事件编号、预案类型与切换偏移。底部滑块可缩放时间轴，滚轮缩放。
</div>
<div class="chart"><div id="main"></div></div>
<div class="sub" style="margin-top:10px">误报段＝与 45 事件归属窗无交集的告警极大段；其上的动手点说明系统当时确认票与类型票均已过门槛、预案被真实切换，事后未演成冻结标签意义的危机。两方案告警层（S3＋B10）完全共用，动手点差异全部来自确认层票数门槛（7项4票 vs 10项6票）。</div>
</div>
<script>
__ECHARTS__
</script>
<script>
const DATA = __DATA__;
const N = DATA.dates.length;
const evAreas = DATA.bands.map(b => [{xAxis:b.on}, {xAxis:b.en}]);

function mkScatter(lst, name, color, sym, size, tipFn, hollow){
  return {name:name, type:'scatter', symbol:sym, symbolSize:size,
    data: lst.map(p => [p.d, __CLOSE_LOOKUP__(p.d), p]),
    itemStyle:{color: hollow ? 'rgba(255,255,255,0.92)' : color, borderColor:color, borderWidth:1.6},
    tooltip:{formatter: ps => tipFn(ps.data[2])}};
}

const tipEvt = (nm) => (p) => `<b>${nm} · 危机事件 ${p.eid} 切换</b><br/>` +
  `${p.d}（触发后第 ${p.off} 个交易日）<br/>启用${p.kind}预案${p.fix ? '（类型修正）' : ''}`;
const tipFa = (nm) => (p) => `<b>${nm} · 误报段动手</b><br/>` +
  `${p.d}（段首后第 ${p.off} 个交易日确认）<br/>误报段：${p.seg}<br/>启用${p.kind}预案`;

const chart = echarts.init(document.getElementById('main'));
chart.setOption({
  backgroundColor:'#ffffff',
  tooltip:{trigger:'item', confine:true, textStyle:{fontSize:12}},
  legend:{top:6, textStyle:{fontSize:12}, data:['万得全A','方案一·事件切换','方案一·误报动手','方案二·事件切换','方案二·误报动手']},
  grid:{left:64, right:24, top:44, bottom:74},
  xAxis:{type:'category', data:DATA.dates, axisLabel:{fontSize:10}},
  yAxis:{type:'value', scale:true, name:'收盘价', nameTextStyle:{fontSize:11}},
  dataZoom:[
    {type:'slider', xAxisIndex:0, height:26, bottom:14, borderColor:'#c5ccd6', labelFormatter:v=>DATA.dates[v]},
    {type:'inside', xAxisIndex:0, zoomOnMouseWheel:true, moveOnMouseMove:true}
  ],
  series:[
    {name:'万得全A', type:'line', data:DATA.close, showSymbol:false, sampling:'lttb',
     lineStyle:{color:'#24435f', width:1.2}, z:3,
     markArea:{silent:true, data:evAreas, itemStyle:{color:'rgba(192,57,43,0.12)'}}},
    mkScatter(DATA.p1evt, '方案一·事件切换', '#2c7fb8', 'circle', 11, tipEvt('方案一'), false),
    mkScatter(DATA.p1fa,  '方案一·误报动手', '#2c7fb8', 'circle', 9,  tipFa('方案一'), true),
    mkScatter(DATA.p2evt, '方案二·事件切换', '#7b3fa0', 'diamond', 13, tipEvt('方案二'), false),
    mkScatter(DATA.p2fa,  '方案二·误报动手', '#7b3fa0', 'diamond', 11, tipFa('方案二'), true),
  ]
});
window.addEventListener('resize', () => chart.resize());
</script>
</body></html>"""

# 把 JS 中的占位查表函数替换为读点内 c 字段
HTML = HTML.replace("__CLOSE_LOOKUP__(p.d)", "p.c")

html = (HTML.replace("__DATA__", data_js)
            .replace("__ECHARTS__", ECH.read_text(encoding="utf-8")))
DEST.write_text(html, encoding="utf-8")
print("written:", DEST, round(DEST.stat().st_size / 1024), "KB")
print("bands:", len(bands), "| p1: evt", len(p1_evt), "fa", len(p1_fa),
      "| p2: evt", len(p2_evt), "fa", len(p2_fa))
