# -*- coding: utf-8 -*-
"""
v0.15 弱三中二最小补丁研究（先登记后计算）
预登记：config/regime_lightpatch_v0.15.toml（2026-11-14T13:11:09+08:00）
底座：弱三中二 3中2(D2,V2,M2) 冻结；网格 = 并联 15 + 表决 12 + 换件 4 + 对照 2 + 底座 1 = 34 行。
硬红线 = 识别 45/45；主指标 = 警戒占历史最小。无随机数、验收 = 双跑字节一致。
"""
import hashlib
import json
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

BASE = "."
OUT = f"{BASE}/outputs"
REG_TS = "2026-11-14T13:11:09+08:00"

PRE_DAYS = 20
POST_DAYS = 20
ROLL_PCT = 756
MIN_VOL_OBS = 250
MIN_TOPO_OBS = 120
TRADING_DAYS_YEAR = 250

# ---------------- 输入（与 v0.13 逐字同源） ----------------
wide = pd.read_csv(f"{OUT}/regime_v07_split_wide.csv", parse_dates=["date"])
bench = pd.read_csv(f"{OUT}/regime_v05_benchmark_daily.csv", parse_dates=["date"])
tim0 = pd.read_csv(f"{OUT}/regime_v012_trigger_event_timing.csv")
v013_sum = pd.read_csv(f"{OUT}/regime_v013_trigger_policy_summary.csv")

w = wide.merge(bench[["date", "wind_close"]], on="date", how="left").sort_values("date").reset_index(drop=True)
assert len(w) == 6483, len(w)
assert w["wind_close"].notna().all()

close = w["wind_close"].to_numpy(dtype=float)
n = len(w)
cal = w["date"].dt.strftime("%Y-%m-%d").tolist()
idx_of = {d: i for i, d in enumerate(cal)}

ret = np.empty(n)
ret[0] = 0.0
ret[1:] = close[1:] / close[:-1] - 1.0
ret_s = pd.Series(ret)

# ---------------- 信号（15 项，v0.13 冻结阈值逐字重建） ----------------
r3 = ret_s.rolling(3).sum()
r5 = ret_s.rolling(5).sum()
vol20 = ret_s.rolling(20).std()
vol_p80 = vol20.rolling(ROLL_PCT, min_periods=MIN_VOL_OBS).quantile(0.80)
vol_p70 = vol20.rolling(ROLL_PCT, min_periods=MIN_VOL_OBS).quantile(0.70)
ma120 = pd.Series(close).rolling(120).mean()
ma250 = pd.Series(close).rolling(250).mean()
roll_max20 = pd.Series(close).rolling(20, min_periods=20).max()
roll_max60 = pd.Series(close).rolling(60, min_periods=60).max()
dd20 = (roll_max20 - close) / roll_max20
dd60 = (roll_max60 - close) / roll_max60

new_high = (pd.Series(close) == roll_max20).to_numpy()
new_high_3d = pd.Series(new_high.astype(int)).rolling(3, min_periods=1).max().astype(bool).to_numpy()

S = {}
S["D1"] = (r5 <= -0.06).to_numpy()
S["D2"] = (r5 <= -0.04).to_numpy()
S["D3"] = (r3 <= -0.035).to_numpy()
S["D4"] = (ret_s <= -0.02).to_numpy()
S["V1"] = (vol20 > vol_p80).to_numpy()
S["V2"] = (vol20 > vol_p70).to_numpy()
S["M1"] = (pd.Series(close) < ma250).to_numpy()
S["M2"] = (pd.Series(close) < ma120).to_numpy()
S["R1"] = (dd20 >= 0.05).to_numpy()
S["R2"] = (dd60 >= 0.08).to_numpy()

TOPO = [("a16_avg_pair_corr", "up"), ("a16_leading_eig_share", "up"),
        ("b_industry_average_correlation", "up"),
        ("b_h2_count", "down"), ("b_h1_count", "down"),
        ("b_h2_landscape_l1", "down"), ("b_xy_h0_death_mean", "down")]

def topo_extreme(q_up):
    q_dn = 1.0 - q_up
    ext = np.zeros((n, len(TOPO)), dtype=bool)
    for j, (f, d) in enumerate(TOPO):
        s = w[f]
        if d == "up":
            ext[:, j] = (s >= s.rolling(ROLL_PCT, min_periods=MIN_TOPO_OBS).quantile(q_up)).to_numpy()
        else:
            ext[:, j] = (s <= s.rolling(ROLL_PCT, min_periods=MIN_TOPO_OBS).quantile(q_dn)).to_numpy()
    return ext

ext85 = topo_extreme(0.85)
ext80 = topo_extreme(0.80)
S["T1"] = ext85.sum(axis=1) >= 4
S["T2"] = ext85.sum(axis=1) >= 3
S["T3"] = ext80.sum(axis=1) >= 4
S["H1"] = new_high_3d & (ret_s <= -0.01).to_numpy()
S["H2"] = new_high_3d & (ret_s < 0).to_numpy()

SIG_ORDER = ["D1", "D2", "D3", "D4", "V1", "V2", "M1", "M2", "R1", "R2",
             "T1", "T2", "T3", "H1", "H2"]
assert set(SIG_ORDER) == set(S)

SIG_CN = {
    "D1": "五日深跌", "D2": "五日跌四", "D3": "三日磨跌", "D4": "单日跳水",
    "V1": "波动高位", "V2": "波动抬升", "M1": "年线下", "M2": "半年线下",
    "R1": "回撤警报", "R2": "深回撤", "T1": "拓扑严", "T2": "拓扑中",
    "T3": "拓扑宽", "H1": "顶部首裂", "H2": "顶部警觉",
}

# ---------------- 组合 ----------------
k2_base = (S["D2"].astype(int) + S["V2"].astype(int) + S["M2"].astype(int)) >= 2

P = {}
NAMES = {}
P["P2"] = k2_base
NAMES["P2"] = "弱三中二（底座）"

# 家族一：并联补丁 15 行
for x in SIG_ORDER:
    pid = f"U-{x}"
    P[pid] = k2_base | S[x]
    NAMES[pid] = f"弱三中二∪{SIG_CN[x]}"

# 家族二：表决扩容 12 行
for x in SIG_ORDER:
    if x in ("D2", "V2", "M2"):
        continue
    pid = f"K-{x}"
    P[pid] = ((S["D2"].astype(int) + S["V2"].astype(int) + S["M2"].astype(int) + S[x].astype(int)) >= 2)
    NAMES[pid] = f"四中二（加{SIG_CN[x]}）"

# 家族三：换件/放宽 4 行
P["S1"] = (S["D3"].astype(int) + S["V2"].astype(int) + S["M2"].astype(int)) >= 2
NAMES["S1"] = "三中二（磨跌换深跌）"
P["S2"] = (S["D4"].astype(int) + S["V2"].astype(int) + S["M2"].astype(int)) >= 2
NAMES["S2"] = "三中二（跳水换深跌）"
P["S3"] = (S["D2"].astype(int) + S["V2"].astype(int) + S["R1"].astype(int)) >= 2
NAMES["S3"] = "三中二（回撤换年线）"
P["S4"] = (S["D2"].astype(int) + S["V2"].astype(int) + S["M2"].astype(int)) >= 1
NAMES["S4"] = "三中一（任一即响）"

# 对照 2 行（v0.13 原样重建）
k2_D1V1M1 = (S["D1"].astype(int) + S["V1"].astype(int) + S["M1"].astype(int)) >= 2
P3 = (S["D1"] | S["D2"] | S["D3"] | S["D4"] | S["V1"] | S["V2"]
      | S["M1"] | S["M2"] | S["R1"] | S["R2"])
P4 = S["T1"] | S["T2"] | S["T3"]
P5 = S["H1"] | S["H2"]
P["REF8"] = k2_base | S["D4"] | S["R1"] | P4 | P5
NAMES["REF8"] = "实用候选（对照）"
P["REF1"] = k2_D1V1M1 | S["T1"]
NAMES["REF1"] = "基线机械混合（对照）"

POLICY_ORDER = ["P2"] + [f"U-{x}" for x in SIG_ORDER] + \
               [f"K-{x}" for x in SIG_ORDER if x not in ("D2", "V2", "M2")] + \
               ["S1", "S2", "S3", "S4", "REF8", "REF1"]
assert len(POLICY_ORDER) == 34, len(POLICY_ORDER)
assert set(POLICY_ORDER) == set(P)

# ---------------- 45 事件与识别窗 ----------------
ev = (tim0[tim0["policy"] == "乙"]
      .drop_duplicates(subset=["event_id"])
      .sort_values("onset")
      .reset_index(drop=True))
assert len(ev) == 45, len(ev)

events = []
for _, r in ev.iterrows():
    o = idx_of[r["onset"]]
    e = idx_of[r["event_end"]]
    events.append({
        "event_id": int(r["event_id"]), "onset": r["onset"], "event_end": r["event_end"],
        "event_len": int(r["event_len"]), "true_type": r["true_type"],
        "i0": o, "i1": e, "e_off": e - o,
    })

in_window_mask = np.zeros(n, dtype=bool)
for evd in events:
    lo = max(0, evd["i0"] - PRE_DAYS)
    hi = min(n - 1, evd["i1"] + POST_DAYS)
    in_window_mask[lo:hi + 1] = True

years = n / TRADING_DAYS_YEAR

def tier_of(off, e_off):
    if off < 0:
        return "提前"
    if off <= e_off:
        return "窗内"
    return "损伤窗"

def first_hit(mask, evd):
    lo = max(0, evd["i0"] - PRE_DAYS)
    hi = min(n - 1, evd["i1"] + POST_DAYS)
    seg = mask[lo:hi + 1]
    if not seg.any():
        return None
    return lo + int(np.argmax(seg))

def false_stats(mask):
    fm = mask & ~in_window_mask
    f_days = int(fm.sum())
    runs = 0
    longest = 0
    eps = []
    i = 0
    while i < n:
        if not fm[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and fm[j + 1]:
            j += 1
        runs += 1
        longest = max(longest, j - i + 1)
        eps.append((i, j, j - i + 1))
        i = j + 1
    return f_days, runs, longest, eps

# ---------------- 逐政策计算 ----------------
matrix_rows = []
summary_rows = []
episode_rows = []

for pid in POLICY_ORDER:
    mask = P[pid]
    tiers = {"提前": 0, "窗内": 0, "损伤窗": 0, "漏": 0}
    offs = []
    for evd in events:
        h = first_hit(mask, evd)
        if h is None:
            tiers["漏"] += 1
            matrix_rows.append({
                "event_id": evd["event_id"], "onset": evd["onset"], "event_end": evd["event_end"],
                "event_len": evd["event_len"], "true_type": evd["true_type"],
                "policy": pid, "policy_name": NAMES[pid],
                "first_hit_date": "", "first_hit_offset": "",
                "tier": "漏", "first_hit_signals": "",
                "n_hit_days_in_window": int(mask[max(0, evd["i0"] - PRE_DAYS):
                                                min(n - 1, evd["i1"] + POST_DAYS) + 1].sum()),
            })
            continue
        off = h - evd["i0"]
        t = tier_of(off, evd["e_off"])
        tiers[t] += 1
        offs.append(off)
        fired = [s for s in SIG_ORDER if S[s][h]]
        matrix_rows.append({
            "event_id": evd["event_id"], "onset": evd["onset"], "event_end": evd["event_end"],
            "event_len": evd["event_len"], "true_type": evd["true_type"],
            "policy": pid, "policy_name": NAMES[pid],
            "first_hit_date": cal[h], "first_hit_offset": off,
            "tier": t, "first_hit_signals": "+".join(fired),
            "n_hit_days_in_window": int(mask[max(0, evd["i0"] - PRE_DAYS):
                                            min(n - 1, evd["i1"] + POST_DAYS) + 1].sum()),
        })
    identified = 45 - tiers["漏"]
    f_days, f_runs, f_long, eps = false_stats(mask)
    for (aa, bb, ln) in eps:
        episode_rows.append({
            "policy": pid, "policy_name": NAMES[pid],
            "episode_start": cal[aa], "episode_end": cal[bb], "episode_len": ln,
        })
    summary_rows.append({
        "policy": pid, "policy_name": NAMES[pid],
        "family": ("底座" if pid == "P2" else "并联" if pid.startswith("U-") else
                   "表决" if pid.startswith("K-") else "换件" if pid.startswith("S") else "对照"),
        "n_pre": tiers["提前"], "n_in_window": tiers["窗内"],
        "n_damage": tiers["损伤窗"], "n_miss": tiers["漏"],
        "identified": identified, "id_rate": identified / 45.0,
        "first_offset_median": float(np.median(offs)) if offs else np.nan,
        "fire_days_total": int(mask.sum()),
        "alarm_day_share": float(mask.sum()) / n,
        "false_days_total": f_days,
        "false_days_per_year": f_days / years,
        "false_episodes": f_runs,
        "false_episodes_per_year": f_runs / years,
        "longest_false_episode": f_long,
    })

summary = pd.DataFrame(summary_rows)
matrix = pd.DataFrame(matrix_rows)
episodes = pd.DataFrame(episode_rows)

# ---------------- 对账断言（与 v0.13 逐字段） ----------------
v13 = v013_sum.set_index("policy")
p2 = summary[summary["policy"] == "P2"].iloc[0]
assert int(p2["identified"]) == int(v13.loc["P2", "identified"])
assert int(p2["n_pre"]) == int(v13.loc["P2", "n_pre"])
assert int(p2["n_in_window"]) == int(v13.loc["P2", "n_in_window"])
assert int(p2["n_damage"]) == int(v13.loc["P2", "n_damage"])
assert int(p2["false_days_total"]) == int(v13.loc["P2", "false_days_total"])
assert int(p2["false_episodes"]) == int(v13.loc["P2", "false_episodes"])
r8 = summary[summary["policy"] == "REF8"].iloc[0]
assert int(r8["identified"]) == int(v13.loc["P8", "identified"])
assert int(r8["n_pre"]) == int(v13.loc["P8", "n_pre"])
assert int(r8["false_days_total"]) == int(v13.loc["P8", "false_days_total"])
assert int(r8["false_episodes"]) == int(v13.loc["P8", "false_episodes"])
r1 = summary[summary["policy"] == "REF1"].iloc[0]
assert int(r1["identified"]) == int(v13.loc["P1", "identified"])
assert int(r1["false_days_total"]) == int(v13.loc["P1", "false_days_total"])

# ---------------- 选定规则（预登记固定） ----------------
qualified = summary[(summary["identified"] == 45) & (~summary["policy"].isin(["REF8", "REF1"]))].copy()
if len(qualified):
    qualified = qualified.sort_values(
        ["alarm_day_share", "false_days_per_year", "n_pre", "false_episodes_per_year"],
        ascending=[True, True, False, True], kind="mergesort")
    best_id = qualified.iloc[0]["policy"]
    summary["selected"] = np.where(summary["policy"] == best_id, "是", "否")
    selection_note = "合格"
else:
    cand = summary[~summary["policy"].isin(["REF8", "REF1"])]
    best_id = cand.sort_values(["identified", "n_pre", "alarm_day_share"],
                               ascending=[False, False, True]).iloc[0]["policy"]
    summary["selected"] = np.where(summary["policy"] == best_id, "是", "否")
    selection_note = "无合格（没有补丁行达到 45/45），取识别最大行仅作描述"

best = summary[summary["policy"] == best_id].iloc[0]

# 126 号对照明细
m126 = matrix[matrix["event_id"] == 126][["policy", "policy_name", "first_hit_date",
                                          "first_hit_offset", "tier", "first_hit_signals"]]

# 选定行 vs 底座逐事件对照
m_sel = matrix[matrix["policy"] == best_id].set_index("event_id")
m_p2 = matrix[matrix["policy"] == "P2"].set_index("event_id")
compare_rows = []
for evd in events:
    eid = evd["event_id"]
    a_off = m_sel.loc[eid, "first_hit_offset"]
    b_off = m_p2.loc[eid, "first_hit_offset"]
    a_tier = m_sel.loc[eid, "tier"]
    b_tier = m_p2.loc[eid, "tier"]
    a_off_n = pd.to_numeric(a_off, errors="coerce")
    b_off_n = pd.to_numeric(b_off, errors="coerce")
    if a_tier != b_tier or (a_off_n == a_off_n and b_off_n == b_off_n and a_off_n != b_off_n):
        compare_rows.append({
            "event_id": eid, "onset": evd["onset"], "true_type": evd["true_type"],
            "p2_offset": b_off, "p2_tier": b_tier,
            "sel_offset": a_off, "sel_tier": a_tier,
        })
compare = pd.DataFrame(compare_rows)

# ---------------- 输出 ----------------
summary.to_csv(f"{OUT}/regime_v015_lightpatch_summary.csv", index=False, encoding="utf-8-sig")
matrix.to_csv(f"{OUT}/regime_v015_lightpatch_matrix.csv", index=False, encoding="utf-8-sig")
episodes.to_csv(f"{OUT}/regime_v015_lightpatch_false_alarm.csv", index=False, encoding="utf-8-sig")

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

manifest = {
    "version": "v0.15",
    "title": "弱三中二最小补丁研究",
    "created": datetime.now(timezone(timedelta(hours=8))).isoformat(),
    "registered": REG_TS,
    "inputs": {
        "regime_v07_split_wide.csv": sha(f"{OUT}/regime_v07_split_wide.csv"),
        "regime_v05_benchmark_daily.csv": sha(f"{OUT}/regime_v05_benchmark_daily.csv"),
        "regime_v012_trigger_event_timing.csv": sha(f"{OUT}/regime_v012_trigger_event_timing.csv"),
        "regime_v013_trigger_policy_summary.csv": sha(f"{OUT}/regime_v013_trigger_policy_summary.csv"),
        "config_regime_lightpatch_v0.15.toml": sha(f"{BASE}/config/regime_lightpatch_v0.15.toml"),
    },
    "params": {
        "pre_days": PRE_DAYS, "post_days": POST_DAYS,
        "roll_pct": ROLL_PCT, "min_vol_obs": MIN_VOL_OBS, "min_topo_obs": MIN_TOPO_OBS,
        "trading_days_year": TRADING_DAYS_YEAR, "n_days": n, "n_events": 45,
        "policies": POLICY_ORDER,
    },
    "outputs": {},
    "summary": {
        "selection_note": selection_note,
        "selected_policy": best_id,
        "selected_policy_name": str(best["policy_name"]),
        "selected_identified": int(best["identified"]),
        "selected_n_pre": int(best["n_pre"]),
        "selected_n_in_window": int(best["n_in_window"]),
        "selected_n_damage": int(best["n_damage"]),
        "selected_alarm_day_share": float(best["alarm_day_share"]),
        "selected_false_days_per_year": float(best["false_days_per_year"]),
        "selected_false_episodes_per_year": float(best["false_episodes_per_year"]),
        "p2_identified": int(p2["identified"]),
        "p2_alarm_day_share": float(p2["alarm_day_share"]),
        "ref8_alarm_day_share": float(r8["alarm_day_share"]),
        "n_qualified": int(len(qualified)) if selection_note == "合格" else 0,
        "by_policy": {
            r["policy"]: {
                "identified": int(r["identified"]), "n_pre": int(r["n_pre"]),
                "n_miss": int(r["n_miss"]),
                "alarm_day_share": float(r["alarm_day_share"]),
                "false_days_per_year": float(r["false_days_per_year"]),
            } for _, r in summary.iterrows()
        },
    },
}
for f in ["regime_v015_lightpatch_summary.csv", "regime_v015_lightpatch_matrix.csv",
          "regime_v015_lightpatch_false_alarm.csv"]:
    manifest["outputs"][f] = sha(f"{OUT}/{f}")
with open(f"{OUT}/regime_v015_lightpatch_manifest.json", "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, ensure_ascii=False, indent=2)

print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
