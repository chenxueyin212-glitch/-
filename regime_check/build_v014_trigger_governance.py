# -*- coding: utf-8 -*-
"""
v0.14 误报治理——警报态撤销与冷却期（先登记后计算）
预登记：config/regime_trigger_governance_v0.14.toml（2026-11-14T12:51:03+08:00）
底座：v0.13 实用候选（P8）原始命中掩码逐字重建、一字不改；
治理层：撤销（收复＋静默 / 纯静默）× 冷却（0/5/10/20）9 变体同表。
硬红线 = 不丢 45/45 召回。无随机数、全流程确定性，验收 = 双跑字节一致。
"""
import hashlib
import json
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

BASE = "."
OUT = f"{BASE}/outputs"
REG_TS = "2026-11-14T12:51:03+08:00"

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
ma250_s = pd.Series(close).rolling(250).mean()
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
S["M1"] = (pd.Series(close) < ma250_s).to_numpy()
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

# ---------------- 组合（只重建实用候选 P8，冻结） ----------------
k2_D2V2M2 = (S["D2"].astype(int) + S["V2"].astype(int) + S["M2"].astype(int)) >= 2
P3 = (S["D1"] | S["D2"] | S["D3"] | S["D4"] | S["V1"] | S["V2"]
      | S["M1"] | S["M2"] | S["R1"] | S["R2"])
P4 = S["T1"] | S["T2"] | S["T3"]
P5 = S["H1"] | S["H2"]
raw_mask = (k2_D2V2M2 | S["D4"] | S["R1"] | P4 | P5)  # P8
assert raw_mask.dtype == bool

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
window_owner = np.full(n, -1, dtype=int)  # 日 → 所属事件序号（用于抑制明细归属）
for k, evd in enumerate(events):
    lo = max(0, evd["i0"] - PRE_DAYS)
    hi = min(n - 1, evd["i1"] + POST_DAYS)
    in_window_mask[lo:hi + 1] = True
    window_owner[lo:hi + 1] = k

ma250 = ma250_s.to_numpy(dtype=float)
years = n / TRADING_DAYS_YEAR

# ---------------- 警报态状态机 ----------------
def govern(mask, rule, cooldown):
    """rule: 'A'=收复＋静默, 'B'=纯静默。返回 alarm、撤销统计、抑制明细。"""
    alarm = np.zeros(n, dtype=bool)
    state_on = False
    quiet = 0
    cd_left = 0
    n_rec3 = 0     # 收复撤销（规则甲）
    n_quiet5 = 0   # 静默撤销
    n_revoke = 0
    n_revoke_in_window = 0
    suppressed = []  # (day_index, in_window)
    for i in range(n):
        hit = bool(mask[i])
        if not state_on:
            if cd_left > 0:
                cd_left -= 1
                if hit:
                    suppressed.append(i)
                continue
            if hit:
                state_on = True
                quiet = 0
                alarm[i] = True
            continue
        # 开态
        alarm[i] = True
        if hit:
            quiet = 0
            continue
        quiet += 1
        revoked = False
        which = ""
        if rule == "A":
            if quiet >= 3 and i >= 2:
                ok = True
                for k3 in (i - 2, i - 1, i):
                    m3 = ma250[k3]
                    if not (m3 == m3) or close[k3] < m3:  # NaN 或未收复
                        ok = False
                        break
                if ok:
                    revoked = True
                    which = "rec3"
            if not revoked and quiet >= 5:
                revoked = True
                which = "quiet5"
        else:
            if quiet >= 5:
                revoked = True
                which = "quiet5"
        if revoked:
            state_on = False
            alarm[i] = False  # 撤销日不计警报日
            cd_left = cooldown
            n_revoke += 1
            if which == "rec3":
                n_rec3 += 1
            else:
                n_quiet5 += 1
            if in_window_mask[i]:
                n_revoke_in_window += 1
    return alarm, {
        "n_revoke": n_revoke, "n_rec3": n_rec3, "n_quiet5": n_quiet5,
        "n_revoke_in_window": n_revoke_in_window,
        "suppressed": suppressed,
    }

VARIANTS = [
    ("G0", "原始", None, 0),
    ("A0", "收复静默·无冷却", "A", 0),
    ("A5", "收复静默·冷却五日", "A", 5),
    ("A10", "收复静默·冷却十日", "A", 10),
    ("A20", "收复静默·冷却二十日", "A", 20),
    ("B0", "纯静默·无冷却", "B", 0),
    ("B5", "纯静默·冷却五日", "B", 5),
    ("B10", "纯静默·冷却十日", "B", 10),
    ("B20", "纯静默·冷却二十日", "B", 20),
]

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

# ---------------- 逐变体计算 ----------------
summary_rows = []
matrix_rows = []
episode_rows = []
suppressed_rows = []
alarms = {}

for vid, vname, rule, cd in VARIANTS:
    if vid == "G0":
        alarm = raw_mask.copy()
        st = {"n_revoke": 0, "n_rec3": 0, "n_quiet5": 0,
              "n_revoke_in_window": 0, "suppressed": []}
    else:
        alarm, st = govern(raw_mask, rule, cd)
    alarms[vid] = alarm

    # 识别矩阵
    tiers = {"提前": 0, "窗内": 0, "损伤窗": 0, "漏": 0}
    offs = []
    delays = []
    for evd in events:
        h = first_hit(alarm, evd)
        raw_h = first_hit(raw_mask, evd)
        if h is None:
            tiers["漏"] += 1
            matrix_rows.append({
                "event_id": evd["event_id"], "onset": evd["onset"], "event_end": evd["event_end"],
                "event_len": evd["event_len"], "true_type": evd["true_type"],
                "variant": vid, "variant_name": vname,
                "raw_first_offset": (raw_h - evd["i0"]) if raw_h is not None else "",
                "gov_first_hit_date": "", "gov_first_offset": "",
                "tier": "漏", "delay_vs_raw": "",
                "n_alarm_days_in_window": int(alarm[max(0, evd["i0"] - PRE_DAYS):
                                                    min(n - 1, evd["i1"] + POST_DAYS) + 1].sum()),
            })
            continue
        off = h - evd["i0"]
        tiers[tier_of(off, evd["e_off"])] += 1
        offs.append(off)
        raw_off = (raw_h - evd["i0"]) if raw_h is not None else None
        delay = (off - raw_off) if raw_off is not None else ""
        if raw_off is not None:
            delays.append(off - raw_off)
        matrix_rows.append({
            "event_id": evd["event_id"], "onset": evd["onset"], "event_end": evd["event_end"],
            "event_len": evd["event_len"], "true_type": evd["true_type"],
            "variant": vid, "variant_name": vname,
            "raw_first_offset": raw_off if raw_off is not None else "",
            "gov_first_hit_date": cal[h], "gov_first_offset": off,
            "tier": tier_of(off, evd["e_off"]), "delay_vs_raw": delay,
            "n_alarm_days_in_window": int(alarm[max(0, evd["i0"] - PRE_DAYS):
                                                min(n - 1, evd["i1"] + POST_DAYS) + 1].sum()),
        })

    identified = 45 - tiers["漏"]
    f_days, f_runs, f_long, eps = false_stats(alarm)
    for (a, b, ln) in eps:
        episode_rows.append({
            "variant": vid, "variant_name": vname,
            "episode_start": cal[a], "episode_end": cal[b], "episode_len": ln,
        })
    sup_in = 0
    for di in st["suppressed"]:
        inw = bool(in_window_mask[di])
        if inw:
            sup_in += 1
        owner = window_owner[di]
        suppressed_rows.append({
            "variant": vid, "variant_name": vname, "date": cal[di],
            "in_window": "是" if inw else "否",
            "event_id": events[owner]["event_id"] if owner >= 0 else "",
        })

    n_alarm = int(alarm.sum())
    win_cover = int((alarm & in_window_mask).sum())
    summary_rows.append({
        "variant": vid, "variant_name": vname,
        "revocation_rule": rule or "—", "cooldown_days": cd,
        "n_pre": tiers["提前"], "n_in_window": tiers["窗内"],
        "n_damage": tiers["损伤窗"], "n_miss": tiers["漏"],
        "identified": identified, "id_rate": identified / 45.0,
        "first_offset_median": float(np.median(offs)) if offs else np.nan,
        "delay_median": float(np.median(delays)) if delays else np.nan,
        "delay_max": int(max(delays)) if delays else 0,
        "n_delayed_events": int(sum(1 for d in delays if d > 0)),
        "alarm_days_total": n_alarm,
        "alarm_day_share": n_alarm / n,
        "window_alarm_days": win_cover,
        "false_days_total": f_days,
        "false_days_per_year": f_days / years,
        "false_episodes": f_runs,
        "false_episodes_per_year": f_runs / years,
        "longest_false_episode": f_long,
        "n_revoke": st["n_revoke"], "n_rec3": st["n_rec3"], "n_quiet5": st["n_quiet5"],
        "n_revoke_in_window": st["n_revoke_in_window"],
        "suppressed_hits": len(st["suppressed"]),
        "suppressed_hits_in_window": sup_in,
    })

summary = pd.DataFrame(summary_rows)
matrix = pd.DataFrame(matrix_rows)
episodes = pd.DataFrame(episode_rows)
suppressed_df = pd.DataFrame(suppressed_rows)

# ---------------- G0 对账断言（必须与 v0.13 实用候选一致） ----------------
v8 = v013_sum[v013_sum["policy"] == "P8"].iloc[0]
g0 = summary[summary["variant"] == "G0"].iloc[0]
assert int(g0["identified"]) == int(v8["identified"]) == 45
assert int(g0["n_pre"]) == int(v8["n_pre"]) == 45
assert int(g0["false_days_total"]) == int(v8["false_days_total"]), (g0["false_days_total"], v8["false_days_total"])
assert int(g0["false_episodes"]) == int(v8["false_episodes"]), (g0["false_episodes"], v8["false_episodes"])
assert int(g0["alarm_days_total"]) == int(v8["fire_days_total"])

# ---------------- 选定规则（预登记固定） ----------------
qualified = summary[summary["identified"] == 45].copy()
if len(qualified):
    qualified = qualified.sort_values(
        ["false_days_per_year", "n_pre", "false_episodes_per_year", "cooldown_days"],
        ascending=[True, False, True, True])
    # 规则乙优先的最终并列打破：同前四项时 B 优先
    qualified = qualified.sort_values(
        ["false_days_per_year", "n_pre", "false_episodes_per_year", "cooldown_days", "revocation_rule"],
        ascending=[True, False, True, True, True], kind="mergesort")
    best_id = qualified.iloc[0]["variant"]
    summary["selected"] = np.where(summary["variant"] == best_id, "是", "否")
    selection_note = "合格"
else:
    best_id = summary.sort_values(["identified", "n_pre", "false_days_per_year"],
                                  ascending=[False, False, True]).iloc[0]["variant"]
    summary["selected"] = np.where(summary["variant"] == best_id, "是", "否")
    selection_note = "无合格（治理伤害召回），取伤害最小行仅作描述"

best = summary[summary["variant"] == best_id].iloc[0]

# 被拖延事件明细（选定行）
delayed_detail = matrix[(matrix["variant"] == best_id) &
                        (pd.to_numeric(matrix["delay_vs_raw"], errors="coerce") > 0)]

# ---------------- 输出 ----------------
summary.to_csv(f"{OUT}/regime_v014_governance_summary.csv", index=False, encoding="utf-8-sig")
matrix.to_csv(f"{OUT}/regime_v014_governance_matrix.csv", index=False, encoding="utf-8-sig")
episodes.to_csv(f"{OUT}/regime_v014_governance_episodes.csv", index=False, encoding="utf-8-sig")
suppressed_df.to_csv(f"{OUT}/regime_v014_governance_suppressed.csv", index=False, encoding="utf-8-sig")

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

manifest = {
    "version": "v0.14",
    "title": "误报治理——警报态撤销与冷却期",
    "created": datetime.now(timezone(timedelta(hours=8))).isoformat(),
    "registered": REG_TS,
    "inputs": {
        "regime_v07_split_wide.csv": sha(f"{OUT}/regime_v07_split_wide.csv"),
        "regime_v05_benchmark_daily.csv": sha(f"{OUT}/regime_v05_benchmark_daily.csv"),
        "regime_v012_trigger_event_timing.csv": sha(f"{OUT}/regime_v012_trigger_event_timing.csv"),
        "regime_v013_trigger_policy_summary.csv": sha(f"{OUT}/regime_v013_trigger_policy_summary.csv"),
        "config_regime_trigger_governance_v0.14.toml": sha(f"{BASE}/config/regime_trigger_governance_v0.14.toml"),
    },
    "params": {
        "pre_days": PRE_DAYS, "post_days": POST_DAYS,
        "roll_pct": ROLL_PCT, "min_vol_obs": MIN_VOL_OBS, "min_topo_obs": MIN_TOPO_OBS,
        "trading_days_year": TRADING_DAYS_YEAR, "n_days": n, "n_events": 45,
        "variants": [v[0] for v in VARIANTS],
        "base_policy": "v0.13 P8 原样重建",
    },
    "outputs": {},
    "summary": {
        "selection_note": selection_note,
        "selected_variant": best_id,
        "selected_variant_name": str(best["variant_name"]),
        "selected_identified": int(best["identified"]),
        "selected_n_pre": int(best["n_pre"]),
        "selected_false_days_per_year": float(best["false_days_per_year"]),
        "selected_false_episodes_per_year": float(best["false_episodes_per_year"]),
        "selected_alarm_day_share": float(best["alarm_day_share"]),
        "selected_suppressed_in_window": int(best["suppressed_hits_in_window"]),
        "selected_n_delayed_events": int(best["n_delayed_events"]),
        "delayed_event_ids": [int(x) for x in delayed_detail["event_id"].tolist()],
        "g0_false_days_per_year": float(g0["false_days_per_year"]),
        "g0_false_episodes_per_year": float(g0["false_episodes_per_year"]),
        "g0_alarm_day_share": float(g0["alarm_day_share"]),
        "by_variant": {
            r["variant"]: {
                "identified": int(r["identified"]), "n_pre": int(r["n_pre"]),
                "n_miss": int(r["n_miss"]),
                "false_days_per_year": float(r["false_days_per_year"]),
                "false_episodes_per_year": float(r["false_episodes_per_year"]),
                "alarm_day_share": float(r["alarm_day_share"]),
                "suppressed_hits_in_window": int(r["suppressed_hits_in_window"]),
                "n_delayed_events": int(r["n_delayed_events"]),
            } for _, r in summary.iterrows()
        },
    },
}
for f in ["regime_v014_governance_summary.csv", "regime_v014_governance_matrix.csv",
          "regime_v014_governance_episodes.csv", "regime_v014_governance_suppressed.csv"]:
    manifest["outputs"][f] = sha(f"{OUT}/{f}")
with open(f"{OUT}/regime_v014_manifest.json", "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, ensure_ascii=False, indent=2)

print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
