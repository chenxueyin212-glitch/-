#!/usr/bin/env python
"""v0.24 拓扑分散签名探测臂 —— 按 config/regime_topo_probe_v0.24.toml 实现。

登记时刻 2026-11-20T16:34:36+08:00 早于本脚本任何输出。探测臂：不改 v0.23 与冻结层。
所有阈值继承（0.85/0.15 来自 v0.16 票箱；-8%/-4%/0.7/20 日来自 v0.23），零新拟合。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("D:/WorkBuddy/2026-10-28-22-54-51")
OUT = ROOT / "tda_project/outputs"
CFG = ROOT / "tda_project/config/regime_topo_probe_v0.24.toml"

HIST, MINP = 756, 120
PCT_HI, PCT_LO = 0.85, 0.15
DD_CUT, EXIT_DD, POS_ACTIVE, REC_DAYS = -0.08, -0.04, 0.7, 20
TRAIN_END = pd.Timestamp("2025-04-07")
VAL_START = pd.Timestamp("2025-04-08")

FEATS = ["b_h1_count", "b_h2_count", "b_h2_landscape_l1", "b_xy_h0_death_mean"]

# ---------------- 1. 特征 + 两种分位 ----------------
w = pd.read_csv(OUT / "regime_v07_split_wide.csv", usecols=["date"] + FEATS)
w["date"] = pd.to_datetime(w["date"])
w = w.set_index("date").sort_index()

pctA = pd.DataFrame({f: w[f].rolling(HIST, min_periods=MINP).rank(pct=True) for f in FEATS})
train_vals = {f: w.loc[:TRAIN_END, f].dropna().values for f in FEATS}


def cdf_rank(f: str, s: pd.Series) -> pd.Series:
    ref = np.sort(train_vals[f])
    return s.map(lambda x: float(np.searchsorted(ref, x, side="right")) / len(ref) if np.isfinite(x) else np.nan)


pctB = pd.DataFrame({f: cdf_rank(f, w[f]) for f in FEATS})
z250 = pd.DataFrame({f: (w[f] - w[f].rolling(250, min_periods=60).mean()) / w[f].rolling(250, min_periods=60).std()
                     for f in FEATS})

# ---------------- 2. 基准 dd20 / ret + v0.23 基线列 ----------------
bm = pd.read_csv(OUT / "regime_v05_benchmark_daily.csv", parse_dates=["date"])
bm = bm[["date", "benchmark_close", "benchmark_ret_pct"]].set_index("date").sort_index()
bm["dd20"] = bm["benchmark_close"] / bm["benchmark_close"].rolling(20).max() - 1
bm["ret"] = bm["benchmark_ret_pct"] / 100.0

v23 = pd.read_csv(OUT / "regime_v023_parallel_channel_daily.csv", parse_dates=["date"]).set_index("date")
base = bm.join(v23[["pr30", "corr30"]], how="left")
print(f"日历 {base.index.min().date()} → {base.index.max().date()}，{len(base)} 日")

# ---------------- 3. 规则与状态机 ----------------
def rule_masks(pct: pd.DataFrame) -> dict[str, pd.Series]:
    r1 = pct["b_h1_count"] >= PCT_HI
    r2 = pct["b_h2_count"] >= PCT_HI
    r3 = pct["b_h2_landscape_l1"] >= PCT_HI
    r4 = r1 | r2 | r3
    r5 = pct["b_xy_h0_death_mean"] <= PCT_LO
    v23cond = (base["pr30"] >= 2.50) & (base["corr30"] <= 0.60)
    r6 = r4 | v23cond
    return {"R1_h1高": r1, "R2_h2高": r2, "R3_land高": r3, "R4_拓扑合并": r4,
            "R5_传染低对照": r5, "R6_拓扑∪v23": r6, "R0_v23基线": v23cond}


def build_state(cond: pd.Series) -> pd.DataFrame:
    out = base.copy()
    active = np.zeros(len(out), bool)
    pos = np.ones(len(out))
    state, rec = 0, 0
    dd = out["dd20"].values
    cv = cond.reindex(out.index).fillna(False).values
    for i in range(len(out)):
        if state == 1:
            if dd[i] > EXIT_DD:
                state, rec = 0, REC_DAYS
            else:
                active[i] = True
                pos[i] = POS_ACTIVE
        if state == 0:
            if cv[i] and np.isfinite(dd[i]) and dd[i] <= DD_CUT:
                state, rec = 1, 0
                active[i] = True
                pos[i] = POS_ACTIVE
            elif rec > 0:
                rec -= 1
                pos[i] = POS_ACTIVE + (1 - POS_ACTIVE) * (REC_DAYS - rec) / REC_DAYS
    out["active"] = active
    out["pos"] = pos
    return out

# ---------------- 4. 覆盖掩码（与 v0.23 逐字同口径） ----------------
led = pd.read_csv(OUT / "regime_v023_miss_ledger.csv", parse_dates=["onset", "worst_date", "label_end_date", "end"])
cal = base.index
pos_of = {d: i for i, d in enumerate(cal)}


def td_add(d: pd.Timestamp, k: int) -> int:
    i = pos_of.get(d)
    if i is None:
        j = cal.searchsorted(d)
        i = int(j) if j < len(cal) else len(cal) - 1
    return min(max(i + k, 0), len(cal) - 1)


covered = np.zeros(len(cal), bool)
for r in led.itertuples():
    covered[td_add(r.onset, -5): td_add(r.label_end_date, 20) + 1] = True
VAL_EPISODES = [("2026-02-25", "2026-03-02"), ("2026-03-18", "2026-03-23"), ("2026-06-18", "2026-07-10"),
                ("2026-07-09", "2026-07-31"), ("2026-09-09", "2026-09-28"), ("2026-10-20", "2026-11-03")]
for a_, b_ in VAL_EPISODES:
    covered[td_add(pd.Timestamp(a_), -5): td_add(pd.Timestamp(b_), 20) + 1] = True

# ---------------- 5. 逐臂评价 ----------------
def eval_arm(st: pd.DataFrame, cond: pd.Series) -> tuple[dict, pd.DataFrame]:
    fa = st["active"].values & ~covered
    train_m = np.asarray(cal <= TRAIN_END)
    val_m = np.asarray(cal >= VAL_START)
    fa_train, fa_val = int((fa & train_m).sum()), int((fa & val_m).sum())
    yrs_train, yrs_val = train_m.sum() / 244, val_m.sum() / 244

    rows = []
    for r in led.itertuples():
        a, w_, le = td_add(r.onset, -5), td_add(r.worst_date, 0), td_add(r.label_end_date, 20)
        seg = st.iloc[a: w_ + 1]
        fire_idx = np.where(seg["active"].values)[0]
        caught = len(fire_idx) > 0
        fire_date = str(seg.index[fire_idx[0]])[:10] if caught else ""
        fire_off = int(fire_idx[0]) - 5 if caught else np.nan
        e, s0 = td_add(r.worst_date, 20), td_add(r.onset, 0)
        win = st.iloc[s0: e + 1]
        rr = win["ret"].fillna(0.0).values
        nav_f = float(np.prod(1 + rr))
        nav_c = float(np.prod(1 + win["pos"].values * rr))
        rows.append(dict(event_id=int(r.event_id), onset=str(r.onset)[:10], judged=r.judged_type,
                         miss_layer=r.miss_layer, caught=caught, fire_date=fire_date,
                         fire_offset=fire_off,
                         pnl_diff_pp=round((nav_c - nav_f) * 100, 3)))
    ev = pd.DataFrame(rows)
    miss9 = ev[ev.event_id.isin([5, 6, 7, 8, 9, 11, 13, 15, 17])]
    caught9 = miss9[miss9.caught]
    pnl_sum = float(ev.loc[ev.caught & (ev.onset <= "2025-04-07"), "pnl_diff_pp"].sum())

    def episode(a: str, b: str, lab: str) -> dict:
        seg = st.loc[a: b]
        act = seg[seg.active]
        s0, e0 = td_add(pd.Timestamp(a), 0), td_add(pd.Timestamp(b), 20)
        win = st.iloc[s0: e0 + 1]
        rr = win["ret"].fillna(0.0).values
        nav_f = float(np.prod(1 + rr))
        nav_c = float(np.prod(1 + win["pos"].values * rr))
        return dict(episode=lab, active_days=int(seg.active.sum()),
                    first_active=str(act.index[0])[:10] if len(act) else "",
                    pnl_diff_pp=round((nav_c - nav_f) * 100, 3))

    eps = [episode("2026-06-01", "2026-08-15", "L2/N2 6-7月"),
           episode("2026-08-20", "2026-11-03", "L3/N3 9-10月"),
           episode("2026-02-20", "2026-04-05", "N1/L1 2-3月(应沉默)")]

    rejects = []
    if fa_train > 20 * yrs_train:
        rejects.append(f"训练期误报 {fa_train}日 > {20*yrs_train:.0f}日")
    if len(caught9) == 0:
        rejects.append("漏保9事件捕获=0")
    if pnl_sum <= 0:
        rejects.append(f"训练期损益差和 {pnl_sum:.2f}pp ≤ 0")

    summary = dict(
        false_alarm_train_days=fa_train, false_alarm_train_per_year=round(fa_train / yrs_train, 1),
        false_alarm_val_days=fa_val, false_alarm_val_per_year=round(fa_val / yrs_val, 1),
        active_days=int(st.active.sum()),
        miss9_caught=int(len(caught9)), miss9_caught_ids=[int(x) for x in caught9.event_id],
        e11_caught=bool(ev.loc[ev.event_id == 11, "caught"].iloc[0]),
        e13_caught=bool(ev.loc[ev.event_id == 13, "caught"].iloc[0]),
        train_pnl_diff_pp_sum=round(pnl_sum, 2),
        val_episodes=eps, reject_triggered=rejects,
        verdict="不过否定门槛" if rejects else "过否定门槛(探测口径)")
    return summary, ev


DISPERSED = [("E11 2021抱团瓦解", "2021-02-18", "2021-03-09"), ("E13 2022-09", "2022-09-06", "2022-10-10"),
             ("L2 2026-06~07", "2026-06-18", "2026-07-10"), ("L3 2026-09", "2026-09-09", "2026-09-28"),
             ("N3 2026-10", "2026-10-15", "2026-10-30")]
COMOVE = [("2008雷曼", "2008-09-15", "2008-10-10"), ("2015股灾", "2015-06-15", "2015-07-08"),
          ("2016熔断", "2016-01-04", "2016-01-28"), ("2020新冠", "2020-02-03", "2020-02-28"),
          ("N1 2026-03", "2026-03-18", "2026-03-31")]

print("\n=== 描述统计（窗内中位：原始值 / 756日分位 / 训练参照分位）===")
desc_rows = []
for grp, wins in [("分散目标", DISPERSED), ("共动对照", COMOVE)]:
    for lab, a, b in wins:
        row = dict(group=grp, window=lab)
        for f in FEATS:
            raw = w[f].loc[a: b]
            row[f + "_raw"] = round(float(raw.median()), 2)
            row[f + "_pA"] = round(float(pctA[f].loc[a: b].median()), 2)
            row[f + "_pB"] = round(float(pctB[f].loc[a: b].median()), 2)
        desc_rows.append(row)
desc = pd.DataFrame(desc_rows)
print(desc[["group", "window", "b_h1_count_raw", "b_h1_count_pA", "b_h1_count_pB",
            "b_h2_count_raw", "b_h2_count_pA", "b_h2_count_pB"]].to_string(index=False))

results, ev_all = {}, {}
for basis_name, pct in [("A_756日分位", pctA), ("B_训练参照分位", pctB)]:
    masks = rule_masks(pct)
    for arm, cond in masks.items():
        if basis_name.startswith("B") and arm == "R0_v23基线":
            continue
        st = build_state(cond.fillna(False))
        s, ev = eval_arm(st, cond)
        key = f"{basis_name}|{arm}"
        results[key] = s
        ev["arm"] = key
        ev_all[key] = ev
        print(f"\n--- {key} ---")
        print(f"  训练误报 {s['false_alarm_train_days']}日 ({s['false_alarm_train_per_year']}/年)  "
              f"验证误报 {s['false_alarm_val_days']}日  激活 {s['active_days']}日")
        print(f"  漏保9捕获 {s['miss9_caught']}/9 ids={s['miss9_caught_ids']}  E11={s['e11_caught']} E13={s['e13_caught']}")
        print(f"  训练损益差和 {s['train_pnl_diff_pp_sum']}pp  → {s['verdict']}")
        for e in s["val_episodes"]:
            print(f"    {e['episode']}: 激活{e['active_days']}日 首激活{e['first_active']} 损益差{e['pnl_diff_pp']}pp")

# 描述 z 分数（不设规则）
print("\n=== z250 描述（窗内中位）===")
for grp, wins in [("分散", DISPERSED), ("共动", COMOVE)]:
    for lab, a, b in wins:
        zz = z250.loc[a: b]
        print(f"  {grp:3s} {lab:18s} h1_z={zz['b_h1_count'].median():+.2f}  h2_z={zz['b_h2_count'].median():+.2f}")

# ---------------- 6. 落盘 ----------------
(OUT / "regime_v024_topo_probe_summary.json").write_text(
    json.dumps(dict(generated_at=datetime.now().isoformat(timespec="seconds"),
                    config=str(CFG.name),
                    registered_at="2026-11-20T16:34:36+08:00",
                    thresholds_inherited="0.85/0.15(v0.16票箱), -8%/-4%/0.7/20日(v0.23)",
                    results=results), ensure_ascii=False, indent=2), encoding="utf-8")
desc.to_csv(OUT / "regime_v024_topo_probe_desc.csv", index=False, encoding="utf-8-sig")
pd.concat(ev_all.values()).to_csv(OUT / "regime_v024_topo_probe_events.csv", index=False, encoding="utf-8-sig")
print("\n落盘: regime_v024_topo_probe_{summary,desc,events}.*")
