# -*- coding: utf-8 -*-
"""
v0.13 召回优先高敏触发器研究（先登记后计算）
预登记：config/regime_trigger_recall_v0.13.toml（2026-11-14T12:21:03+08:00）
目标：45 个冻结事件全部识别（识别窗 [起点-20, 事件结束+20]，分档 提前/窗内/损伤窗/漏），
     误报只记账不治理。无随机数、全流程确定性，验收=双跑字节一致。
"""
import hashlib
import json
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

BASE = "."
OUT = f"{BASE}/outputs"
REG_TS = "2026-11-14T12:21:03+08:00"

PRE_DAYS = 20          # 识别窗：起点前
POST_DAYS = 20         # 识别窗：事件结束后（损伤窗）
ROLL_PCT = 756         # 分位回看窗
MIN_VOL_OBS = 250      # 波动率分位最少观测
MIN_TOPO_OBS = 120     # 拓扑分位最少观测
TRADING_DAYS_YEAR = 250

# ---------------- 输入 ----------------
wide = pd.read_csv(f"{OUT}/regime_v07_split_wide.csv", parse_dates=["date"])
bench = pd.read_csv(f"{OUT}/regime_v05_benchmark_daily.csv", parse_dates=["date"])
tim0 = pd.read_csv(f"{OUT}/regime_v012_trigger_event_timing.csv")

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

# ---------------- 信号（15 项，阈值预登记固定） ----------------
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

# 20 日新高（当日收盘 = 含当日 20 日最高收盘）
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

# 拓扑 7 特征（v0.11 冻结：升向 >= 分位，降向 <= 下侧分位）
TOPO = [("a16_avg_pair_corr", "up"), ("a16_leading_eig_share", "up"),
        ("b_industry_average_correlation", "up"),
        ("b_h2_count", "down"), ("b_h1_count", "down"),
        ("b_h2_landscape_l1", "down"), ("b_xy_h0_death_mean", "down")]

def topo_extreme(q_up):
    """方向感知极端：升向 >= 上侧分位；降向 <= 下侧分位。q_up=0.85 → 85/15；0.80 → 80/20。"""
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

# ---------------- 组合政策（8 条，预登记固定） ----------------
k2_D1V1M1 = (S["D1"].astype(int) + S["V1"].astype(int) + S["M1"].astype(int)) >= 2
k2_D2V2M2 = (S["D2"].astype(int) + S["V2"].astype(int) + S["M2"].astype(int)) >= 2

P = {}
P["P1"] = k2_D1V1M1 | S["T1"]
P["P2"] = k2_D2V2M2
P["P3"] = (S["D1"] | S["D2"] | S["D3"] | S["D4"] | S["V1"] | S["V2"]
           | S["M1"] | S["M2"] | S["R1"] | S["R2"])
P["P4"] = S["T1"] | S["T2"] | S["T3"]
P["P5"] = S["H1"] | S["H2"]
P["P6"] = P["P3"] | P["P4"]
P["P7"] = P["P3"] | P["P4"] | P["P5"]
P["P8"] = P["P2"] | S["D4"] | S["R1"] | P["P4"] | P["P5"]

POLICY_ORDER = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]

# ---------------- 45 事件 ----------------
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

# 识别窗掩码（全部事件的并集，用于误报归属）
in_window_mask = np.zeros(n, dtype=bool)
for evd in events:
    lo = max(0, evd["i0"] - PRE_DAYS)
    hi = min(n - 1, evd["i1"] + POST_DAYS)
    in_window_mask[lo:hi + 1] = True

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
    k = int(np.argmax(seg))
    return lo + k

# ---------------- 45 × 政策 识别矩阵 ----------------
matrix_rows = []
for policy in POLICY_ORDER:
    mask = P[policy]
    for evd in events:
        h = first_hit(mask, evd)
        if h is None:
            matrix_rows.append({
                "event_id": evd["event_id"], "onset": evd["onset"], "event_end": evd["event_end"],
                "event_len": evd["event_len"], "true_type": evd["true_type"],
                "policy": policy, "first_hit_date": "", "first_hit_offset": "",
                "tier": "漏", "first_hit_signals": "", "n_hit_days_in_window": "",
            })
            continue
        off = h - evd["i0"]
        fired = [s for s in SIG_ORDER if S[s][h]]
        lo = max(0, evd["i0"] - PRE_DAYS)
        hi = min(n - 1, evd["i1"] + POST_DAYS)
        matrix_rows.append({
            "event_id": evd["event_id"], "onset": evd["onset"], "event_end": evd["event_end"],
            "event_len": evd["event_len"], "true_type": evd["true_type"],
            "policy": policy, "first_hit_date": cal[h], "first_hit_offset": off,
            "tier": tier_of(off, evd["e_off"]), "first_hit_signals": "+".join(fired),
            "n_hit_days_in_window": int(mask[lo:hi + 1].sum()),
        })
matrix = pd.DataFrame(matrix_rows)

# ---------------- 15 单信号普查 ----------------
census_rows = []
for s in SIG_ORDER:
    mask = S[s]
    tiers = {"提前": 0, "窗内": 0, "损伤窗": 0, "漏": 0}
    offs = []
    for evd in events:
        h = first_hit(mask, evd)
        if h is None:
            tiers["漏"] += 1
        else:
            off = h - evd["i0"]
            tiers[tier_of(off, evd["e_off"])] += 1
            offs.append(off)
    false_mask = mask & ~in_window_mask
    f_days = int(false_mask.sum())
    # 误报段：连续误报日最大连续段
    runs = 0
    longest = 0
    i = 0
    while i < n:
        if not false_mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and false_mask[j + 1]:
            j += 1
        runs += 1
        longest = max(longest, j - i + 1)
        i = j + 1
    years = n / TRADING_DAYS_YEAR
    census_rows.append({
        "signal": s, "identified": tiers["提前"] + tiers["窗内"] + tiers["损伤窗"],
        "n_pre": tiers["提前"], "n_in_window": tiers["窗内"],
        "n_damage": tiers["损伤窗"], "n_miss": tiers["漏"],
        "first_offset_median": float(np.median(offs)) if offs else np.nan,
        "fire_days_total": int(mask.sum()),
        "alarm_day_share": float(mask.sum()) / n,
        "false_days_total": f_days,
        "false_days_per_year": f_days / years,
        "false_episodes": runs,
        "false_episodes_per_year": runs / years,
        "longest_false_episode": longest,
    })
census = pd.DataFrame(census_rows)

# ---------------- 8 政策汇总 ----------------
false_rows = []
summary_rows = []
years = n / TRADING_DAYS_YEAR
for policy in POLICY_ORDER:
    mask = P[policy]
    sub = matrix[matrix["policy"] == policy]
    n_pre = int((sub["tier"] == "提前").sum())
    n_in = int((sub["tier"] == "窗内").sum())
    n_dmg = int((sub["tier"] == "损伤窗").sum())
    n_miss = int((sub["tier"] == "漏").sum())
    identified = n_pre + n_in + n_dmg
    offs = pd.to_numeric(sub.loc[sub["tier"] != "漏", "first_hit_offset"])
    false_mask = mask & ~in_window_mask
    f_days = int(false_mask.sum())
    i = 0
    runs = 0
    longest = 0
    while i < n:
        if not false_mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and false_mask[j + 1]:
            j += 1
        runs += 1
        longest = max(longest, j - i + 1)
        false_rows.append({
            "policy": policy, "episode_start": cal[i], "episode_end": cal[j],
            "episode_len": j - i + 1,
        })
        i = j + 1
    summary_rows.append({
        "policy": policy,
        "n_pre": n_pre, "n_in_window": n_in, "n_damage": n_dmg, "n_miss": n_miss,
        "identified": identified, "id_rate": identified / 45.0,
        "first_offset_median": float(offs.median()) if len(offs) else np.nan,
        "first_offset_q1": float(offs.quantile(0.25)) if len(offs) else np.nan,
        "first_offset_q3": float(offs.quantile(0.75)) if len(offs) else np.nan,
        "fire_days_total": int(mask.sum()),
        "alarm_day_share": float(mask.sum()) / n,
        "false_days_total": f_days,
        "false_days_per_year": f_days / years,
        "false_episodes": runs,
        "false_episodes_per_year": runs / years,
        "longest_false_episode": longest,
    })
summary = pd.DataFrame(summary_rows)
false_df = pd.DataFrame(false_rows)

# 推荐规则（预登记固定）：识别数最大，并列取误报日/年最小
best = summary.sort_values(["identified", "false_days_per_year"],
                           ascending=[False, True]).iloc[0]
summary["selected"] = np.where(summary["policy"] == best["policy"], "是", "否")

# ---------------- 输出 ----------------
census.to_csv(f"{OUT}/regime_v013_trigger_signal_census.csv", index=False, encoding="utf-8-sig")
matrix.to_csv(f"{OUT}/regime_v013_trigger_policy_matrix.csv", index=False, encoding="utf-8-sig")
summary.to_csv(f"{OUT}/regime_v013_trigger_policy_summary.csv", index=False, encoding="utf-8-sig")
false_df.to_csv(f"{OUT}/regime_v013_trigger_false_alarm.csv", index=False, encoding="utf-8-sig")

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

manifest = {
    "version": "v0.13",
    "title": "召回优先高敏触发器研究",
    "created": datetime.now(timezone(timedelta(hours=8))).isoformat(),
    "registered": REG_TS,
    "inputs": {
        "regime_v07_split_wide.csv": sha(f"{OUT}/regime_v07_split_wide.csv"),
        "regime_v05_benchmark_daily.csv": sha(f"{OUT}/regime_v05_benchmark_daily.csv"),
        "regime_v012_trigger_event_timing.csv": sha(f"{OUT}/regime_v012_trigger_event_timing.csv"),
        "config_regime_trigger_recall_v0.13.toml": sha(f"{BASE}/config/regime_trigger_recall_v0.13.toml"),
    },
    "params": {
        "pre_days": PRE_DAYS, "post_days": POST_DAYS,
        "roll_pct": ROLL_PCT, "min_vol_obs": MIN_VOL_OBS, "min_topo_obs": MIN_TOPO_OBS,
        "trading_days_year": TRADING_DAYS_YEAR, "n_days": n, "n_events": 45,
        "signals": SIG_ORDER, "policies": POLICY_ORDER,
    },
    "outputs": {},
    "summary": {
        "selected_policy": best["policy"],
        "selected_identified": int(best["identified"]),
        "selected_false_days_per_year": float(best["false_days_per_year"]),
        "full_recall_policies": summary.loc[summary["identified"] == 45, "policy"].tolist(),
        "by_policy": {
            r["policy"]: {"identified": int(r["identified"]), "pre": int(r["n_pre"]),
                          "in_window": int(r["n_in_window"]), "damage": int(r["n_damage"]),
                          "miss": int(r["n_miss"]),
                          "alarm_day_share": float(r["alarm_day_share"]),
                          "false_days_per_year": float(r["false_days_per_year"])}
            for _, r in summary.iterrows()
        },
    },
}
for f in ["regime_v013_trigger_signal_census.csv", "regime_v013_trigger_policy_matrix.csv",
          "regime_v013_trigger_policy_summary.csv", "regime_v013_trigger_false_alarm.csv"]:
    manifest["outputs"][f] = sha(f"{OUT}/{f}")
with open(f"{OUT}/regime_v013_trigger_manifest.json", "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, ensure_ascii=False, indent=2)

print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
