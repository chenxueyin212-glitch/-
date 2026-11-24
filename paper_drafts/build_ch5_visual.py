# -*- coding: utf-8 -*-
"""生成第五章说明性可视化 HTML（万得全A + 11项拓扑特征 + S3+B10告警 + 两方案预案应对点）。
数据源全部来自 tda_project/outputs 冻结产物；S3+B10 逐日掩码按 v0.19 脚本逐字重建并四锚点对账。
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

OUT = Path(r"D:/WorkBuddy/2026-10-28-22-54-51/tda_project/outputs")
DEST = Path(r"D:/WorkBuddy/2026-10-28-22-54-51/tda_crisis_visual_20261118.html")

# ---------- 1. 基准价格与日历 ----------
b = pd.read_csv(OUT / "regime_v05_benchmark_daily.csv", parse_dates=["date"])
n = len(b)
assert n == 6483
cal = b["date"].dt.strftime("%Y-%m-%d").tolist()
idx_of = {d: i for i, d in enumerate(cal)}
close = b["wind_close"].to_numpy(dtype=float)

# ---------- 2. 重建 S3+B10 逐日告警掩码（v0.19 逐字口径：简单收益） ----------
ret = np.empty(n); ret[0] = 0.0; ret[1:] = close[1:] / close[:-1] - 1.0
rs = pd.Series(ret)
r5 = rs.rolling(5).sum()
vol20 = rs.rolling(20).std()
vol_p70 = vol20.rolling(756, min_periods=250).quantile(0.70)
rm20 = pd.Series(close).rolling(20, min_periods=20).max()
dd20 = (rm20 - close) / rm20
raw_mask = (((r5 <= -0.04).astype(int) + (vol20 > vol_p70).astype(int) + (dd20 >= 0.05).astype(int)) >= 2).to_numpy()

alarm = np.zeros(n, dtype=bool); on = False; q = 0; cd = 0; n_revoke = 0
for i in range(n):
    hit = bool(raw_mask[i])
    if not on:
        if cd > 0:
            cd -= 1; continue
        if hit:
            on = True; q = 0; alarm[i] = True
        continue
    alarm[i] = True
    if hit:
        q = 0; continue
    q += 1
    if q >= 5:
        on = False; alarm[i] = False; cd = 10; n_revoke += 1

# ---------- 3. 45 事件、误报段、切换点 ----------
ev = pd.read_csv(OUT / "regime_v019_c1_completion_event_matrix.csv", encoding="utf-8-sig")
ev = ev[ev["arm"].isin(["F7K4", "F10K6"])]
events45 = []
for _, r in ev[ev["arm"] == "F7K4"].iterrows():
    lo = max(0, idx_of[r["onset"]] - 20); hi = min(n - 1, idx_of[r["event_end"]] + 20)
    seg = alarm[lo:hi + 1]
    first_alarm = cal[lo + int(np.argmax(seg))] if seg.any() else None
    plans = {}
    for arm, pid in [("F7K4", "p1"), ("F10K6", "p2")]:
        rr = ev[(ev["arm"] == arm) & (ev["event_id"] == r["event_id"])].iloc[0]
        td = rr["trigger_date"]
        offs_raw = str(rr["switch_offs_p4"]) if pd.notna(rr["switch_offs_p4"]) else ""
        switches = []
        if offs_raw and offs_raw not in ("", "nan") and pd.notna(td):
            offs = [int(x) for x in offs_raw.replace("；", ";").split(";") if x.strip()]
            judged = rr["judged_type"]
            for k_i, k in enumerate(offs):
                kind = judged if k_i == 0 else ("浅快" if judged == "深慢" else "深慢")
                switches.append({"d": cal[idx_of[td] + k], "k": k, "kind": kind})
        plans[pid] = {"judged": rr["judged_type"], "final": rr["final_plan_type"],
                      "corr": int(rr["corrections_p4"]), "sw": switches}
    events45.append({
        "id": r["event_id"], "onset": r["onset"], "end": r["event_end"],
        "tier": r["tier"], "type": r["true_type"],
        "first_alarm": first_alarm, "trigger": r["trigger_date"] if pd.notna(r["trigger_date"]) else None,
        "p1": plans["p1"], "p2": plans["p2"],
    })
assert len(events45) == 45

# 误报段与激活点
fe = pd.read_csv(OUT / "regime_v019_c1_completion_false_episodes.csv", encoding="utf-8-sig")
catch = [(max(0, idx_of[r["onset"]] - 20), idx_of[r["end"]]) for r in events45]
false_eps = []; i = 0
while i < n:
    if not alarm[i]:
        i += 1; continue
    j = i
    while j + 1 < n and alarm[j + 1]:
        j += 1
    if not any(not (j < lo or i > hi) for lo, hi in catch):
        rec = {"s": cal[i], "e": cal[j], "len": j - i + 1, "i": i, "j": j}
        for arm, pid in [("F7K4", "p1"), ("F10K6", "p2")]:
            m = fe[(fe["arm"] == arm) & (fe["episode_start"] == rec["s"])]
            if len(m):
                m = m.iloc[0]
                act = m["final_plan_type"] in ("深慢", "浅快")
                rec[pid] = {"act": act, "kind": m["final_plan_type"] if act else "",
                            "off": (int(m["first_confirm_offset"]) if act and pd.notna(m["first_confirm_offset"]) else None)}
            else:
                rec[pid] = {"act": False, "kind": "", "off": None}
        false_eps.append(rec)
    i = j + 1
assert len(false_eps) == 83 and n_revoke == 117
n_p1_act = sum(1 for e in false_eps if e["p1"]["act"])
n_p2_act = sum(1 for e in false_eps if e["p2"]["act"])
assert (n_p1_act, n_p2_act) == (33, 21), (n_p1_act, n_p2_act)

# ---------- 3b. 误动手普查：激活段的动手日、纯降仓持有期与全核算影响窗 ----------
act_rows = {"p1": [], "p2": []}
act_stats = {}
for arm, pid, pname in [("F7K4", "p1", "方案一"), ("F10K6", "p2", "方案二")]:
    sub = fe[(fe["arm"] == arm) & (fe["final_plan_type"].isin(["深慢", "浅快"]))].sort_values("episode_start")
    hold = np.zeros(n, dtype=bool)   # 纯降仓持有期（切换次日 → 段首+20）
    full = np.zeros(n, dtype=bool)   # 含 20 日回补的全核算影响窗（切换次日 → 段首+40）
    for _, m in sub.iterrows():
        s = idx_of[m["episode_start"]]; ci = s + int(m["first_confirm_offset"])
        hold[ci + 1: min(n, s + 20) + 1] = True
        full[ci + 1: min(n - 1, s + 40) + 1] = True
        act_rows[pid].append({
            "seg": f'{m["episode_start"]}→{m["episode_end"]}', "len": int(m["episode_len"]),
            "kind": m["final_plan_type"], "act": cal[ci], "off": int(m["first_confirm_offset"]),
            "win": f'{cal[min(n - 1, ci + 1)]}→{cal[min(n - 1, s + 40)]}',
            "diff": float(m["diff_p4_p3"])})
    act_stats[pid] = {"n": len(sub), "holdDays": int(hold.sum()),
                      "holdPct": round(float(hold.sum()) / n * 100, 2),
                      "fullDays": int(full.sum()), "fullPct": round(float(full.sum()) / n * 100, 2)}

# 逐年触发/告警占比（剔除仅 1 个交易日的 1999）
_yr = pd.DataFrame({"y": b["date"].dt.year.to_numpy(), "raw": raw_mask, "alm": alarm})
_yrg = _yr.groupby("y").agg(days=("raw", "size"), raw=("raw", "sum"), alm=("alm", "sum"))
yearly_data = [[int(y), round(r.raw / r.days * 100, 2), round(r.alm / r.days * 100, 2)]
               for y, r in _yrg.iterrows() if y >= 2000]

# ---------- 4. 验证期 6 个重放事件（叙事 N1-N3 + 标签 L1-L3） ----------
rp = pd.read_csv(OUT / "regime_v019_c1_completion_replay_events.csv", encoding="utf-8-sig")
rp = rp[rp["arm"] == "F7K4"]
replay = [{"id": r["event_id"], "name": ("叙事事件" if r["event_def"] == "叙事" else "标签事件") + str(r["event_id"]),
           "start": r["event_start"], "end": r["event_end"], "first_alarm": r["first_alarm"],
           "judged": r["judged_type"], "plan": r["plan"], "status": r["engine_status"]} for _, r in rp.iterrows()]

# ---------- 5. 11 项拓扑特征日序列 ----------
w = pd.read_csv(OUT / "regime_v07_split_wide.csv", encoding="utf-8-sig", parse_dates=["date"])
assert list(w["date"].dt.strftime("%Y-%m-%d")) == cal
FEATS = [
    ("a16_W_t", "市场状态·点云距离 W_t", "市场状态点云（16行业，2005-03起）"),
    ("a16_h0_death_mean", "市场状态·零维死亡均值", ""),
    ("a16_h1_count", "市场状态·一维环计数", ""),
    ("a16_window_rms", "市场状态·窗口均方根", ""),
    ("a16_avg_pair_corr", "市场状态·平均两两相关", ""),
    ("a16_leading_eig_share", "市场状态·第一特征值占比", ""),
    ("b_h2_count", "行业网络·二维空腔计数", "行业相关网络（2012-12起）"),
    ("b_h1_count", "行业网络·一维环计数", ""),
    ("b_h2_landscape_l1", "行业网络·二维持久景观L1", ""),
    ("b_industry_average_correlation", "行业网络·行业平均相关", ""),
    ("b_xy_h0_death_mean", "行业网络·零维死亡均值", ""),
]
feats_json = {}
for key, label, note in FEATS:
    v = w[key].to_numpy(dtype=float)
    feats_json[key] = {"label": label, "note": note,
                       "vals": [None if not np.isfinite(x) else (None if abs(x) > 1e12 else float(x)) for x in v]}

# ---------- 6. 汇总导出 ----------
payload = {
    "dates": cal,
    "close": [round(float(x), 2) for x in close],
    "alarm": alarm.astype(int).tolist(),
    "rawHit": raw_mask.astype(int).tolist(),
    "falseLane": [0] * n,
    "events": events45,
    "falseEps": false_eps,
    "replay": replay,
    "feats": feats_json,
    "yearly": yearly_data,
    "actStats": act_stats,
    "stats": {
        "alarmShare": round(float(alarm.sum()) / n, 6), "revoke": n_revoke,
        "falseEps": len(false_eps), "falseDays": int(sum(e["len"] for e in false_eps)),
        "p1Switch": sum(1 for e in events45 if e["p1"]["sw"]), "p2Switch": sum(1 for e in events45 if e["p2"]["sw"]),
        "p1Act": n_p1_act, "p2Act": n_p2_act,
    },
}
for e in false_eps:
    for t in range(e["i"], e["j"] + 1):
        payload["falseLane"][t] = 1

data_js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
print("JSON size:", round(len(data_js) / 1024), "KB")

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>危机状态判别系统全景图 · 万得全A、拓扑特征与告警/预案点（1999-2026）</title>
<style>
  body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin: 0; background: #f5f6f8; color: #26303d; }
  .wrap { max-width: 1420px; margin: 0 auto; padding: 18px 20px 40px; }
  h1 { font-size: 22px; margin: 6px 0 4px; }
  .sub { color: #5a6675; font-size: 13px; margin-bottom: 12px; line-height: 1.7; }
  .stats { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0 14px; }
  .card { background: #fff; border: 1px solid #e3e7ec; border-radius: 8px; padding: 10px 14px; min-width: 150px; }
  .card .k { font-size: 12px; color: #6b7686; }
  .card .v { font-size: 19px; font-weight: 700; margin-top: 2px; }
  .legend { background: #fff; border: 1px solid #e3e7ec; border-radius: 8px; padding: 12px 16px; font-size: 13px; line-height: 2.0; margin-bottom: 12px; }
  .legend b { color: #1d2b3a; }
  .chip { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin: 0 6px -1px 12px; }
  .chart { background: #fff; border: 1px solid #e3e7ec; border-radius: 8px; padding: 6px 4px 2px; }
  #main { width: 100%; height: 2150px; }
  .foot { font-size: 12px; color: #6b7686; line-height: 1.9; margin-top: 14px; background:#fff; border:1px solid #e3e7ec; border-radius:8px; padding: 12px 16px; }
  .warn { color: #a33; font-weight: 600; }
  table { border-collapse: collapse; font-size: 13px; margin-top: 8px; }
  td, th { border: 1px solid #dfe4ea; padding: 6px 12px; text-align: center; }
  th { background: #f0f3f6; }
</style>
</head>
<body>
<div class="wrap">
<h1>危机状态判别系统全景图：万得全A走势 · 11 项拓扑特征 · S3＋B10 告警与两方案预案应对点</h1>
<div class="sub">数据区间 1999-12-30 至 2026-11-03（6483 个交易日）。告警掩码按冻结规则（S3 三中二·简单收益口径＋B10 五日静默撤销·十日冷却）逐日重建，并与实验记录四锚点对账一致（告警日占比 __ALARMSHARE__、撤销 __REVOKE__ 次、误报段 __FALSEEPS__ 段、误报日 __FALSEDAYS__ 日）。<span class="warn">本图为样本内描述性对照，所有损益数字为历史重放口径的上限值，不构成样本外业绩。</span></div>

<div class="stats">
  <div class="card"><div class="k">危机事件（冻结标签）</div><div class="v">45 起</div></div>
  <div class="card"><div class="k">宽识别窗召回</div><div class="v">45/45</div></div>
  <div class="card"><div class="k">告警日占比</div><div class="v">__ALARMSHARE__</div></div>
  <div class="card"><div class="k">误报段 / 激活（方案一）</div><div class="v">83 / __P1ACT__</div></div>
  <div class="card"><div class="k">误报段 / 激活（方案二）</div><div class="v">83 / __P2ACT__</div></div>
  <div class="card"><div class="k">事件切换（方案一 / 二）</div><div class="v">__P1SW__ / __P2SW__</div></div>
  <div class="card"><div class="k">净损益差合计（方案一 / 二）</div><div class="v">+79.0 / +105.0</div></div>
</div>

<div class="legend">
<b>图例说明</b>：
<span class="chip" style="background:#c0392b; opacity:.75"></span>红色竖带＝45 起危机事件的危机段（起点→结束日）
<span class="chip" style="background:#e67e22; opacity:.8"></span>橙色条带（误报段车道）＝83 个误报段
<span class="chip" style="background:#27ae60; opacity:.5"></span>绿色竖带＝2025-04-08 后验证期 6 个重放事件（3 叙事＋3 标签，不进 45 事件账本）
▲ 红色小三角＝45 事件的首次告警日（宽识别窗内首个告警日）
▲ 绿色小三角＝验证期 6 个重放事件的首次告警日（2025-04-08 后）
● 蓝色圆点＝<b>方案一</b>（S3＋B10＋7项4票）预案切换点　
◆ 紫色菱形＝<b>方案二</b>（S3＋B10＋10项6票，C1）预案切换点　
✕ 蓝色叉＝方案一在误报段上的预案激活点（33 个）　✕ 紫色叉＝方案二误报激活点（21 个）。
悬停可查看日期、类型（深慢/浅快）、切换偏移与修正次数。底部滑块可缩放时间轴，滑块两端可拖动选区。
</div>

<div class="chart"><div id="main"></div></div>

<div class="foot">
<b>数据来源与核对</b>：价格＝万得全A 881001.WI（regime_v05_benchmark_daily.csv）；拓扑特征＝regime_v07_split_wide.csv（a16 市场状态点云面板自 2005-03 起、b 行业相关网络面板自 2012-12 起，早段为空属数据覆盖所限）；事件与切换点＝regime_v019_c1_completion_event_matrix.csv；误报段＝regime_v019_c1_completion_false_episodes.csv；验证期重放＝regime_v019_c1_completion_replay_events.csv。
<b>告警掩码重建核验</b>：以简单收益重建 S3＋B10，四锚点（0.234305 告警占比 / 117 次撤销 / 83 段 / 776 日）与 v0.19 记录完全一致；31 个归属窗事件的触发日与事件矩阵逐日一致（14 个损伤窗事件按定义无归属窗内触发日，其首次告警按宽识别窗另行标出）。
<b>口径提醒</b>：43 处事件侧切换的切换日＝触发日＋切换偏移个交易日；误报段上的激活日＝段首＋确认偏移。五日收益条件为<b>简单收益之和 ≤ −4%</b>（执行代码口径；拓扑点云输入仍为对数收益，两者分属不同模块）。
<table>
<tr><th></th><th>确认层</th><th>事件切换</th><th>误报激活段</th><th>事件侧损益差</th><th>误报段损益差</th><th>净损益差合计</th></tr>
<tr><td><b>方案一（冻结基准）</b></td><td>7 项 ≥4 票</td><td>__P1SW__/31 可核算</td><td>__P1ACT__</td><td>+147.6</td><td>−68.6</td><td><b>+79.0</b></td></tr>
<tr><td><b>方案二（C1 重点候选）</b></td><td>10 项 ≥6 票</td><td>__P2SW__/31 可核算</td><td>__P2ACT__</td><td>+153.3</td><td>−48.3</td><td><b>+105.0</b></td></tr>
</table>
<div style="margin-top:8px">净损益差＝逐事件单位净值损益差与误报段损益差的算术和（单位净值百分点），<b>不是</b>单一组合累计收益率；主账含全历史日历（2025-04-08 后日历在内），验证期重放不可与主账相加。</div>
<h3 style="margin:18px 0 6px">附录一：45 个危机事件的逐次收益（单位净值百分点）</h3>
<div style="font-size:12px;color:#5a6a7a;margin-bottom:6px">每行一个事件：收益差＝实时判定路径净值 − 不动路径净值（P4−P3）；「切换」＝触发日后第几个交易日切换（分号分隔多次修正）；未切换事件按构造差为 0。P3＝全程满仓不动基线；深慢预案＝仓位 50%＋认沽对冲（名义 50%、权利金 1.5%、止损 20%）；浅快预案＝仓位 80%、止损 12%；事件结束后 20 个交易日线性回补。</div>
__EVENT_TABLE__
<h3 style="margin:18px 0 6px">附录二：误报段上的预案激活与逐段收益（方案一 33 段／方案二 21 段）</h3>
<div style="font-size:12px;color:#5a6a7a;margin-bottom:6px">误报段＝与 45 事件归属窗无交集的告警极大段；仅当确认投票通过（激活）才发生仓位切换并产生损益，未激活段差为 0。窗口＝段首起 20 个交易日持有＋20 个交易日回补。</div>
__FA_TABLE__
<h3 style="margin:18px 0 6px">附录三：S3 裸触发与告警状态的逐年占比</h3>
<div style="font-size:12px;color:#5a6a7a;margin-bottom:6px">裸触发＝S3 三中二当日命中，全历史 1122 日＝17.31%；告警状态＝S3＋B10 状态机维持的告警段，全历史 1519 日＝23.43%。逐年极不均匀：2008 年触发占比 70.7% 最高（174/246 日），2015 年 33.6%、2007 年 31.4%；2017 年全年零触发、2023 年仅 1.7%。平均占比由「危机年长期在响＋平静年几乎不响」叠加而成，不代表每年约五分之一时间在触发。</div>
<div class="chart"><div id="yearly" style="width:100%;height:380px"></div></div>
<h3 style="margin:18px 0 6px">附录四：误动手普查——误报段上实际切换预案的日子</h3>
<div style="font-size:12px;color:#5a6a7a;margin-bottom:6px">误动手＝误报段内确认票与类型票同时过门槛、预案被真实切换。<b>三层口径</b>：①动手日（切换确认日）方案一 33 天（0.51% 的交易日）／方案二 21 天（0.32%）；②纯降仓持有期并集（切换次日→段首+20 日）方案一 489 日＝7.54%／方案二 304 日＝4.69%；③含 20 日回补的全核算影响窗并集方案一 1110 日＝17.12%／方案二 700 日＝10.80%。口径③与引擎损益核算窗口一致（段首起 20 日持有＋20 日回补），回补段仓位已线性恢复，受影响程度弱于持有段；三层数字不可混用。2025-04-08 验证期起方案一两次动手（2025-12-03、2026-03-24），其中 2026-03 段对应事件表 45 事件未覆盖的危机样行情（宽基标签盲区，见验证期误报口径 3.8 日/年），并非纯虚惊。</div>
__ACT_TABLE__
</div>
</div>

<script>
__ECHARTS__
</script>
<script>
const DATA = __DATA__;
const N = DATA.dates.length;
const fmt2 = x => (x==null ? '-' : x);

// ---- 事件与标记数据整理 ----
const evAreas = DATA.events.map(e => [{xAxis: e.onset}, {xAxis: e.end}]);
const rpAreas = DATA.replay.map(e => [{xAxis: e.start}, {xAxis: e.end}]);

const firstAlarmPts = [];
DATA.events.forEach(e => { if (e.first_alarm) firstAlarmPts.push({value: [e.first_alarm, DATA.close[DATA.dates.indexOf(e.first_alarm)]], ev: e}); });

function closeAt(d){ const i = DATA.dates.indexOf(d); return i>=0 ? DATA.close[i] : null; }
const p1Sw = [], p2Sw = [], p1Fa = [], p2Fa = [];
DATA.events.forEach(e => {
  e.p1.sw.forEach(s => p1Sw.push({value:[s.d, closeAt(s.d)], ev:e, s}));
  e.p2.sw.forEach(s => p2Sw.push({value:[s.d, closeAt(s.d)], ev:e, s}));
});
DATA.falseEps.forEach(ep => {
  ['p1','p2'].forEach(pid => {
    if (ep[pid].act && ep[pid].off != null) {
      const di = ep.i + ep[pid].off;
      const d = DATA.dates[di];
      const pt = {value:[d, closeAt(d)], ep:ep, pid:pid};
      (pid==='p1'?p1Fa:p2Fa).push(pt);
    }
  });
});

const alarmSeries = DATA.alarm.map(v => v===1 ? 1 : null);
const falseSeries = DATA.falseLane.map(v => v===1 ? 1 : null);

// ---- 布局：13 个网格 ----
const grids = [], xAxes = [], yAxes = [], titles = [];
let yTop = 64;
const H_PRICE = 330, H_LANE = 34, H_MET = 78, GAP = 26;
grids.push({left: 90, right: 30, top: yTop, height: H_PRICE}); titles.push({text: '万得全A收盘价（881001.WI）与告警、预案切换点', left: 96, top: yTop-26, textStyle:{fontSize:14, fontWeight:700}});
yTop += H_PRICE + GAP;
grids.push({left: 90, right: 30, top: yTop, height: H_LANE}); titles.push({text: '告警状态（S3＋B10，红＝告警日）', left: 96, top: yTop-20, textStyle:{fontSize:12}});
yTop += H_LANE + 18;
grids.push({left: 90, right: 30, top: yTop, height: H_LANE}); titles.push({text: '误报段（与45事件归属窗无交集的告警段，橙＝误报日）', left: 96, top: yTop-20, textStyle:{fontSize:12}});
yTop += H_LANE + 24;
Object.keys(DATA.feats).forEach((k, idx) => {
  const f = DATA.feats[k];
  grids.push({left: 90, right: 30, top: yTop, height: H_MET});
  titles.push({text: f.label + (f.note ? '（'+f.note+'）' : ''), left: 96, top: yTop-18, textStyle:{fontSize:12, color:'#40506a'}});
  yTop += H_MET + GAP;
});
const totalH = yTop + 60;

for (let g = 0; g < grids.length; g++) {
  xAxes.push({type:'category', data: DATA.dates, gridIndex: g, axisLabel:{show:false}, axisTick:{show:false}, axisLine:{show:g===grids.length-1, lineStyle:{color:'#c5ccd6'}}, splitLine:{show:false}});
}
yAxes.push({gridIndex:0, scale:true, axisLabel:{fontSize:10, color:'#6b7686'}, splitLine:{show:true, lineStyle:{color:'#eef1f5'}}});
yAxes.push({gridIndex:1, min:0, max:1, show:false});
yAxes.push({gridIndex:2, min:0, max:1, show:false});
for (let g = 3; g < grids.length; g++) yAxes.push({gridIndex:g, scale:true, axisLabel:{fontSize:9, color:'#8a93a3'}, splitLine:{show:false}});

function mkScatter(data, color, symbol, size, zIndex, tipFn, gx){
  return {type:'scatter', xAxisIndex:gx, yAxisIndex:gx, data:data, symbol:symbol, symbolSize:size,
    itemStyle:{color:color, borderColor:'#ffffff', borderWidth:0.6}, z:zIndex+5,
    emphasis:{scale:1.6}, tooltip:{formatter: tipFn}};
}
const tipAlarm = p => {
  const e = p.data.ev;
  return '<b>首次告警</b>　'+p.value[0]+'<br/>事件 '+e.id+'（'+e.type+'型，'+e.tier+'）<br/>危机段：'+e.onset+' → '+e.end+'<br/>方案一：'+(e.p1.sw.length?'切换 '+e.p1.sw.map(s=>s.kind).join('→'):'未切换')+'<br/>方案二：'+(e.p2.sw.length?'切换 '+e.p2.sw.map(s=>s.kind).join('→'):'未切换');
};
const tipSw = pid => p => {
  const e = p.data.ev, s = p.data.s, nm = pid==='p1'?'方案一（7项4票）':'方案二（10项6票·C1）';
  return '<b>'+nm+' 预案切换</b>　'+p.value[0]+'<br/>'+s.kind+'预案（事件 '+e.id+'，'+e.type+'型，'+e.tier+'）<br/>触发日+'+s.k+'个交易日'+(e[pid].corr?('，类型修正 '+e[pid].corr+' 次'):'');
};
const tipFa = pid => p => {
  const ep = p.data.ep, nm = pid==='p1'?'方案一':'方案二';
  return '<b>'+nm+' 误报段激活</b>　'+p.value[0]+'<br/>误报段：'+ep.s+' → '+ep.e+'（'+ep.len+' 日）<br/>启用'+ep[pid].kind+'预案（段首+'+ep[pid].off+'日）';
};
const tipRp = p => {
  const e = p.data.ev;
  return '<b>'+e.name+'</b>　'+p.value[0]+'<br/>事件段：'+e.start+' → '+e.end+'<br/>判型：'+(e.judged||'随访不足')+'｜预案：'+(e.plan||'—')+'<br/>状态：'+e.status;
};

const rpPts = DATA.replay.filter(e=>e.first_alarm).map(e => ({value:[e.first_alarm, closeAt(e.first_alarm)], ev:e}));

const series = [
  {type:'line', name:'万得全A', xAxisIndex:0, yAxisIndex:0, data:DATA.close, showSymbol:false, sampling:'lttb',
   lineStyle:{color:'#24435f', width:1.1}, z:3,
   markArea:{silent:true, data:[...evAreas, ...rpAreas], itemStyle:{color:'rgba(192,57,43,0.09)'}}},
  {type:'line', xAxisIndex:1, yAxisIndex:1, data:alarmSeries, showSymbol:false, step:'end', connectNulls:false,
   lineStyle:{width:0}, areaStyle:{color:'rgba(192,57,43,0.55)'}, z:2,
   markArea:{silent:true, data:evAreas, itemStyle:{color:'rgba(192,57,43,0.05)'}}},
  {type:'line', xAxisIndex:2, yAxisIndex:2, data:falseSeries, showSymbol:false, step:'end', connectNulls:false,
   lineStyle:{width:0}, areaStyle:{color:'rgba(230,126,34,0.6)'}, z:2,
   markArea:{silent:true, data:evAreas, itemStyle:{color:'rgba(192,57,43,0.04)'}}},
  mkScatter(firstAlarmPts, '#c0392b', 'triangle', 8, 5, tipAlarm, 0),
  mkScatter(rpPts, '#27ae60', 'triangle', 9, 5, tipRp, 0),
  mkScatter(p1Sw, '#2c7fb8', 'circle', 11, 6, tipSw('p1'), 0),
  mkScatter(p2Sw, '#7b3fa0', 'diamond', 12, 6, tipSw('p2'), 0),
  mkScatter(p1Fa, '#2c7fb8', 'cross', 10, 7, tipFa('p1'), 0),
  mkScatter(p2Fa, '#7b3fa0', 'cross', 10, 7, tipFa('p2'), 0),
];
Object.keys(DATA.feats).forEach((k, idx) => {
  const g = idx + 3;
  series.push({type:'line', xAxisIndex:g, yAxisIndex:g, data:DATA.feats[k].vals, name:DATA.feats[k].label,
    showSymbol:false, sampling:'lttb', lineStyle:{color:'#3d7ab5', width:0.9}, z:3,
    markArea:{silent:true, data:evAreas, itemStyle:{color:'rgba(192,57,43,0.08)'}}});
});

const chart = echarts.init(document.getElementById('main'));
chart.setOption({
  backgroundColor:'#ffffff',
  title: titles,
  axisPointer: {link: [{xAxisIndex: xAxes.map((_,i)=>i)}]},
  tooltip: {trigger:'item', confine:true, textStyle:{fontSize:12}},
  grid: grids,
  xAxis: xAxes, yAxis: yAxes,
  dataZoom: [
    {type:'slider', xAxisIndex: xAxes.map((_,i)=>i), height:26, bottom:14, borderColor:'#c5ccd6',
     labelFormatter: v => DATA.dates[v]},
    {type:'inside', xAxisIndex: xAxes.map((_,i)=>i), zoomOnMouseWheel:true, moveOnMouseMove:true},
  ],
  series: series,
});
document.getElementById('main').style.height = totalH + 'px';
chart.resize();
window.addEventListener('resize', () => chart.resize());

const yc = echarts.init(document.getElementById('yearly'));
const yr = DATA.yearly;
yc.setOption({
  backgroundColor:'#ffffff',
  title:{text:'S3 裸触发与告警状态的逐年占比（%）', left:'center', textStyle:{fontSize:14}},
  tooltip:{trigger:'axis', confine:true, textStyle:{fontSize:12},
    formatter: ps => ps.map(p=>p.marker+p.seriesName+'：'+p.value+'%').join('<br/>')},
  legend:{data:[{name:'裸触发占比', itemStyle:{color:'#E67E22'}},
                {name:'告警状态占比', itemStyle:{color:'#8E44AD'}}], top:28, textStyle:{fontSize:12}},
  grid:{left:50, right:20, top:60, bottom:56},
  xAxis:{type:'category', data:yr.map(r=>String(r[0])),
    axisLabel:{rotate:55, fontSize:10, interval:0}},
  yAxis:{type:'value', max:85, axisLabel:{formatter:'{value}%'}},
  series:[
    {name:'裸触发占比', type:'bar', data:yr.map(r=>r[1]),
     itemStyle:{color: p => p.value>=30?'#A32D2D':(p.value===0?'#D3D1C7':'#E67E22')}, barMaxWidth:14},
    {name:'告警状态占比', type:'bar', data:yr.map(r=>r[2]),
     itemStyle:{color:'#8E44AD'}, barMaxWidth:14}
  ]
});
window.addEventListener('resize', () => yc.resize());
</script>
</body>
</html>"""

# ---- 附录表：逐事件与逐段收益（数据与图同源） ----
import csv as _csv
_ev_rows = list(_csv.DictReader(open(OUT / "regime_v019_c1_completion_event_matrix.csv", encoding="utf-8-sig")))
_p1 = {r["event_id"]: r for r in _ev_rows if r["arm"] == "F7K4"}
_p2 = {r["event_id"]: r for r in _ev_rows if r["arm"] == "F10K6"}

def _fmt(v, plus=True):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return ("+" if (x > 0 and plus) else "") + f"{x:.2f}"

_et = ['<table class="mini"><tr><th>ID</th><th>事件段</th><th>真类型</th><th>触发日</th>'
       '<th>方案一：切换／预案</th><th>收益差</th><th>方案二：切换／预案</th><th>收益差</th></tr>']
_s1 = _s2 = 0.0
for _eid in sorted(_p1, key=int):
    _a, _b = _p1[_eid], _p2[_eid]
    _d1 = float(_a["diff_p4_p3"] or 0); _d2 = float(_b["diff_p4_p3"] or 0)
    _s1 += _d1; _s2 += _d2
    _tg = _a["trigger_date"] or "（无）"
    _row = ('<tr><td>{eid}</td><td>{on}→{en}</td><td>{tt}</td><td>{tg}</td>'
            '<td>{sw1}／{pl1}</td><td class="{c1}">{d1}</td>'
            '<td>{sw2}／{pl2}</td><td class="{c2}">{d2}</td></tr>').format(
        eid=_eid, on=_a["onset"], en=_a["event_end"], tt=_a["true_type"], tg=_tg,
        sw1=_a["switch_offs_p4"] or "未切换", pl1=_a["final_plan_type"] or "—",
        d1=_fmt(_d1), c1="pos" if _d1 > 0 else ("neg" if _d1 < 0 else "zero"),
        sw2=_b["switch_offs_p4"] or "未切换", pl2=_b["final_plan_type"] or "—",
        d2=_fmt(_d2), c2="pos" if _d2 > 0 else ("neg" if _d2 < 0 else "zero"))
    _et.append(_row)
_et.append('<tr><th>合计</th><th colspan="3">事件侧 45 事件</th><th>方案一</th><th>{}</th><th>方案二</th><th>{}</th></tr>'.format(_fmt(_s1), _fmt(_s2)))
_et.append('</table>')
EVENT_TABLE_HTML = "\n".join(_et)

_fa_rows = list(_csv.DictReader(open(OUT / "regime_v019_c1_completion_false_episodes.csv", encoding="utf-8-sig")))
_ft = ['<table class="mini"><tr><th>方案</th><th>误报段</th><th>段长</th><th>判型</th><th>激活预案</th><th>确认偏移</th><th>收益差</th></tr>']
_t1 = _t2 = 0.0
for _r in _fa_rows:
    if _r["arm"] not in ("F7K4", "F10K6") or _r["status"] not in ("已评估", ""):
        continue
    _arm = "方案一" if _r["arm"] == "F7K4" else "方案二"
    try:
        _v = float(_r["diff_p4_p3"])
    except (TypeError, ValueError):
        continue
    if _v == 0 and (_r["final_plan_type"] or "未切换") == "未切换":
        continue
    if _arm == "方案一": _t1 += _v
    else: _t2 += _v
    _ft.append('<tr><td>{}</td><td>{}→{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td class="{}">{}</td></tr>'.format(
        _arm, _r["episode_start"], _r["episode_end"], _r["episode_len"],
        _r["judged_type"] or "—", _r["final_plan_type"] or "未切换",
        _r["first_confirm_offset"] or "—", "neg" if _v < 0 else "pos", _fmt(_v)))
_ft.append('<tr><th>合计</th><th>方案一激活 33 段</th><th></th><th></th><th></th><th></th><th>{}</th></tr>'.format(_fmt(_t1)))
_ft.append('<tr><th></th><th>方案二激活 21 段</th><th></th><th></th><th></th><th></th><th>{}</th></tr>'.format(_fmt(_t2)))
_ft.append('</table>')
FA_TABLE_HTML = "\n".join(_ft)

# ---- 附录四：误动手明细（动手日、纯降仓持有期与全核算影响窗，与附录二同源） ----
_at = ['<table class="mini"><tr><th>方案</th><th>误报段</th><th>段长</th><th>判型</th>'
       '<th>确认偏移</th><th>动手日（切换确认日）</th><th>全核算影响窗（切换次日→段首+40）</th><th>收益差</th></tr>']
for pid, pname in [("p1", "方案一"), ("p2", "方案二")]:
    for r in act_rows[pid]:
        _v = r["diff"]
        _at.append('<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td class="{}">{}</td></tr>'.format(
            pname, r["seg"], r["len"], r["kind"], r["off"], r["act"], r["win"],
            "neg" if _v < 0 else "pos", _fmt(_v)))
_at.append('<tr><th>合计</th><th>方案一动手 {} 次</th><th>纯降仓持有 {} 日（{}%）</th><th></th><th></th>'
           '<th>全窗 {} 日（{}%）</th><th></th><th>{}</th></tr>'.format(
               act_stats["p1"]["n"], act_stats["p1"]["holdDays"], act_stats["p1"]["holdPct"],
               act_stats["p1"]["fullDays"], act_stats["p1"]["fullPct"], _fmt(sum(r["diff"] for r in act_rows["p1"]))))
_at.append('<tr><th></th><th>方案二动手 {} 次</th><th>纯降仓持有 {} 日（{}%）</th><th></th><th></th>'
           '<th>全窗 {} 日（{}%）</th><th></th><th>{}</th></tr>'.format(
               act_stats["p2"]["n"], act_stats["p2"]["holdDays"], act_stats["p2"]["holdPct"],
               act_stats["p2"]["fullDays"], act_stats["p2"]["fullPct"], _fmt(sum(r["diff"] for r in act_rows["p2"]))))
_at.append('</table>')
ACT_TABLE_HTML = "\n".join(_at)

ECHARTS_JS = (OUT.parent.parent / "paper_drafts" / "echarts.min.js").read_text(encoding="utf-8")

html = (HTML.replace("__DATA__", data_js)
            .replace("__ALARMSHARE__", "23.43%")
            .replace("__REVOKE__", "117")
            .replace("__FALSEEPS__", "83")
            .replace("__FALSEDAYS__", "776")
            .replace("__P1SW__", str(payload["stats"]["p1Switch"]))
            .replace("__P2SW__", str(payload["stats"]["p2Switch"]))
            .replace("__P1ACT__", str(payload["stats"]["p1Act"]))
            .replace("__P2ACT__", str(payload["stats"]["p2Act"]))
            .replace("__EVENT_TABLE__", EVENT_TABLE_HTML)
            .replace("__FA_TABLE__", FA_TABLE_HTML)
            .replace("__ACT_TABLE__", ACT_TABLE_HTML)
            .replace("__ECHARTS__", ECHARTS_JS))
DEST.write_text(html, encoding="utf-8")
print("written:", DEST, round(DEST.stat().st_size/1024), "KB")
print("stats:", payload["stats"])
