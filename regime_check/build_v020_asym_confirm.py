#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.20 非对称类型确认：浅快单日动手、深慢维持两日（先登记后计算）。
用法：
  python build_v020_asym_confirm.py baseline   # 对称规则复算，对 v0.19 逐字段对账，不写文件
  python build_v020_asym_confirm.py asym       # 非对称规则正式计算，写 v0.20 产物
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

MODE = sys.argv[1] if len(sys.argv) > 1 else "asym"
assert MODE in ("baseline", "asym"), MODE

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
CFG_PATH = ROOT / "config" / "regime_asym_confirm_v0.20.toml"
REG_TS = "2026-11-19T00:36:29+08:00"

PRE_DAYS = POST_DAYS = 20
ROLL_PCT = 756
MIN_VOL_OBS = 250
TRADING_DAYS_YEAR = 250
BASELINE_WINDOW = 10
BASELINE_MIN_NONNULL = 8
CURRENT_MIN_FRAC = 0.8
HIST_WINDOW = 756
HIST_MIN_OBS = 120
EXTREME_PCT = 0.85
JUDGMENT_START, JUDGMENT_END = 1, 20
CONFIRM_DAYS = 2          # 深慢确认天数（不变）
SHALLOW_CONFIRM_DAYS = 1  # 浅快确认天数（本实验改动；baseline 模式下也用 2）
TYPE_DEEP_MIN, TYPE_SHALLOW_MAX = 2 / 3, 1 / 3
MAX_CORRECTIONS = 1
P1_SWITCH_OFFSET = 2
POS_DEEP, POS_SHALLOW, POS_BASE = 0.5, 0.8, 1.0
STOP_DEEP, STOP_SHALLOW = 0.20, 0.12
PUT_PREMIUM_RATE, PUT_NOTIONAL, PUT_OTM = 0.015, 0.5, 0.95
REENTRY_DAYS = 20
CATCH_START = -20
FALSE_HOLD_DAYS = 20
REPLAY_START, DATA_END = "2025-04-08", "2026-11-03"

FEATURES_7 = [
    ("a16_avg_pair_corr", +1), ("a16_leading_eig_share", +1),
    ("b_industry_average_correlation", +1), ("b_h2_count", -1),
    ("b_h1_count", -1), ("b_h2_landscape_l1", -1),
    ("b_xy_h0_death_mean", -1),
]
FEATURES_10 = FEATURES_7 + [
    ("a16_W_t", +1), ("a16_h0_death_mean", +1), ("a16_h1_count", -1),
]
TYPE_FEATURES = [
    ("a16_window_rms", +1), ("a16_avg_pair_corr", +1),
    ("b_xy_h0_death_mean", -1),
]
ARMS = [
    ("F7K4", "方案一·非对称确认：7项4票", 7, 4),
    ("F10K6", "方案二·非对称确认：10项6票", 10, 6),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ts = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    wide = pd.read_csv(OUT / "regime_v07_split_wide.csv", parse_dates=["date"])
    bench = pd.read_csv(OUT / "regime_v05_benchmark_daily.csv", parse_dates=["date"])
    tim0 = pd.read_csv(OUT / "regime_v012_trigger_event_timing.csv")

    w = wide.merge(bench[["date", "wind_close"]], on="date", how="left").sort_values("date").reset_index(drop=True)
    assert len(w) == 6483 and w["wind_close"].notna().all()
    close = w["wind_close"].to_numpy(dtype=float)
    n = len(w)
    cal = w["date"].dt.strftime("%Y-%m-%d").tolist()
    ret = np.empty(n)
    ret[0] = 0.0
    ret[1:] = close[1:] / close[:-1] - 1.0
    ret_s = pd.Series(ret)

    feat_arr = {}
    for feat, _ in FEATURES_10 + TYPE_FEATURES:
        if feat not in feat_arr:
            feat_arr[feat] = w[feat].to_numpy(dtype=float)

    r5 = ret_s.rolling(5).sum()
    vol20 = ret_s.rolling(20).std()
    vol_p70 = vol20.rolling(ROLL_PCT, min_periods=MIN_VOL_OBS).quantile(0.70)
    roll_max20 = pd.Series(close).rolling(20, min_periods=20).max()
    dd20 = (roll_max20 - close) / roll_max20
    raw_mask = (((r5 <= -0.04).astype(int) + (vol20 > vol_p70).astype(int)
                 + (dd20 >= 0.05).astype(int)) >= 2).to_numpy()

    def build_extreme(feats):
        extreme = {}
        for feat, direction in feats:
            s = feat_arr[feat]
            flag = np.zeros(n, dtype=bool)
            for i in range(n):
                hist = s[max(0, i - HIST_WINDOW):i]
                hist = hist[np.isfinite(hist)]
                if hist.size < HIST_MIN_OBS or not np.isfinite(s[i]):
                    continue
                if direction > 0:
                    flag[i] = s[i] > np.quantile(hist, EXTREME_PCT)
                else:
                    flag[i] = s[i] < np.quantile(hist, 1 - EXTREME_PCT)
            extreme[feat] = flag
        count = np.zeros(n, dtype=int)
        for feat, _ in feats:
            count += extreme[feat].astype(int)
        return count

    ext_by_box = {7: build_extreme(FEATURES_7), 10: build_extreme(FEATURES_10)}

    ev = (tim0[tim0["policy"] == "乙"].drop_duplicates(subset=["event_id"])
          .sort_values("onset").reset_index(drop=True))
    assert len(ev) == 45
    idx_of = {d: i for i, d in enumerate(cal)}
    events = []
    for _, r in ev.iterrows():
        o, e = idx_of[r["onset"]], idx_of[r["event_end"]]
        events.append({"event_id": int(r["event_id"]), "onset": r["onset"],
                       "event_end": r["event_end"], "event_len": int(r["event_len"]),
                       "true_type": r["true_type"], "i0": o, "i1": e, "e_off": e - o})
    events.sort(key=lambda x: x["event_id"])
    in_window_mask = np.zeros(n, dtype=bool)
    for evd in events:
        in_window_mask[max(0, evd["i0"] - PRE_DAYS):min(n - 1, evd["i1"] + POST_DAYS) + 1] = True
    catch_lo_hi = [(max(0, e["i0"] + CATCH_START), e["i1"]) for e in events]
    years = n / TRADING_DAYS_YEAR

    alarm = np.zeros(n, dtype=bool)
    state_on, quiet, cd_left = False, 0, 0
    n_revoke = 0
    for i in range(n):
        hit = bool(raw_mask[i])
        if not state_on:
            if cd_left > 0:
                cd_left -= 1
                continue
            if hit:
                state_on, quiet, alarm[i] = True, 0, True
            continue
        alarm[i] = True
        if hit:
            quiet = 0
            continue
        quiet += 1
        if quiet >= 5:
            state_on, alarm[i], cd_left = False, False, 10
            n_revoke += 1

    def plan_of(kind):
        return (POS_DEEP, STOP_DEEP, True) if kind == "deep" else (POS_SHALLOW, STOP_SHALLOW, False)

    def build_positions(i0, T_off, e_off, switch_list):
        pos = np.full(T_off + 1, POS_BASE)
        put_buys, stopped, stopped_at = [], False, None
        switch_map = {off: kind for off, kind in switch_list}
        kind_now, cur_pos, cur_stop, cur_anchor = None, POS_BASE, None, None
        for t in range(T_off + 1):
            pos[t] = cur_pos
            if (not stopped and cur_stop is not None and cur_anchor is not None
                    and t >= cur_anchor - i0 and t <= e_off):
                if close[i0 + t] / close[cur_anchor] - 1.0 <= -cur_stop:
                    stopped, stopped_at, cur_pos = True, t, 0.0
            if t in switch_map and not stopped:
                kind_now = switch_map[t]
                cur_pos, cur_stop, has_put = plan_of(kind_now)
                cur_anchor = i0 + t
                if has_put:
                    put_buys.append((t, -PUT_NOTIONAL * PUT_PREMIUM_RATE))
        start_val = 0.0 if stopped else (plan_of(kind_now)[0] if kind_now else POS_BASE)
        for j in range(1, REENTRY_DAYS + 1):
            t = e_off + j
            if t <= T_off:
                pos[t] = start_val + (POS_BASE - start_val) * j / REENTRY_DAYS
        return pos, stopped_at, put_buys

    def hedge_flows(i0, T_off, put_buys):
        flows = list(put_buys)
        premium_total = sum(amt for _, amt in put_buys)
        payoff = 0.0
        for off, _ in put_buys:
            s0 = close[i0 + off]
            k = PUT_OTM * s0
            payoff += PUT_NOTIONAL * max(0.0, (k - close[i0 + T_off]) / k)
        flows.append((T_off, payoff))
        return flows, payoff, premium_total

    def maxdd(values):
        peak, dd = -np.inf, 0.0
        for v in values:
            peak = max(peak, v)
            if peak > 0:
                dd = min(dd, v / peak - 1.0)
        return dd * 100.0

    def metrics(i0, T_off, e_off, pos_arr, put_buys):
        flows, payoff, premium_total = hedge_flows(i0, T_off, put_buys)
        flow_map = {}
        for off, amt in flows:
            flow_map[off] = flow_map.get(off, 0.0) + amt
        values = np.full(T_off + 2, np.nan)
        values[0] = 1.0
        for t in range(T_off + 1):
            r = ret[i0 + t] if np.isfinite(ret[i0 + t]) else 0.0
            values[t + 1] = values[t] * (1.0 + pos_arr[t] * r) + flow_map.get(t, 0.0)
        full = (values[T_off + 1] / values[0] - 1.0) * 100.0
        return {"full_cum": full, "maxdd": maxdd(values), "hedge_net": payoff + premium_total}

    def run_judgment(i0, e_off, eligibility, ext_count, n_box, min_votes):
        shallow_days = SHALLOW_CONFIRM_DAYS if MODE == "asym" else CONFIRM_DAYS
        judgments, scores, score_ns = {}, {}, {}
        for k in range(JUDGMENT_START, JUDGMENT_END + 1):
            j = i0 + k
            if j >= n:
                break
            votes = []
            for feat, sgn in TYPE_FEATURES:
                s = feat_arr[feat]
                base = s[max(0, i0 - BASELINE_WINDOW):i0]
                base = base[np.isfinite(base)]
                cur = s[i0:j + 1]
                cur = cur[np.isfinite(cur)]
                if base.size < BASELINE_MIN_NONNULL or cur.size < np.ceil(CURRENT_MIN_FRAC * (k + 1)):
                    continue
                delta = cur.mean() - base.mean()
                votes.append(int((delta > 0) if sgn > 0 else (delta < 0)))
            if len(votes) < 2:
                judgments[k], scores[k] = "数据不足", np.nan
            else:
                type_score = sum(votes) / len(votes)
                scores[k] = type_score
                judgments[k] = ("深慢" if type_score >= TYPE_DEEP_MIN else
                                "浅快" if type_score <= TYPE_SHALLOW_MAX else "无法判定")
            score_ns[k] = int(ext_count[i0 + k])
        switched, first_type, cur_plan = False, None, None
        switch_offsets, corrections_used, last_switch_k = [], 0, None
        for k in range(JUDGMENT_START, JUDGMENT_END + 1):
            if k not in judgments:
                break
            elig = (k < e_off) if eligibility else (k < FALSE_HOLD_DAYS)
            if judgments[k] not in ("深慢", "浅快"):
                confirmed = False
            elif judgments[k] == "浅快":
                confirmed = (k >= shallow_days and score_ns.get(k, 0) >= min_votes and elig)
            else:
                confirmed = (k >= CONFIRM_DAYS and judgments.get(k) == judgments.get(k - 1)
                             and score_ns.get(k, 0) >= min_votes and elig)
            if not switched and confirmed:
                switched, first_type, cur_plan = True, judgments[k], judgments[k]
                switch_offsets.append(k)
                last_switch_k = k
            elif (switched and corrections_used < MAX_CORRECTIONS
                  and (k - 1) > last_switch_k and confirmed and judgments[k] != cur_plan):
                cur_plan = judgments[k]
                corrections_used += 1
                switch_offsets.append(k)
                last_switch_k = k
        return judgments, score_ns, (first_type if switched else "无法判定"), switch_offsets, corrections_used, cur_plan

    def first_hit_ident(mask, evd):
        lo, hi = max(0, evd["i0"] - PRE_DAYS), min(n - 1, evd["i1"] + POST_DAYS)
        seg = mask[lo:hi + 1]
        return lo + int(np.argmax(seg)) if seg.any() else None

    def tier_of(off, e_off):
        return "提前" if off < 0 else ("窗内" if off <= e_off else "损伤窗")

    arm_rows, matrix_rows, all_false_rows = [], [], []
    false_by_arm = {}
    for aid, aname, n_box, min_votes in ARMS:
        ext_count = ext_by_box[n_box]
        tiers = {"提前": 0, "窗内": 0, "损伤窗": 0, "漏": 0}
        arm_matrix = []
        for event_pos, evd in enumerate(events):
            h = first_hit_ident(alarm, evd)
            raw_h = first_hit_ident(raw_mask, evd)
            raw_off = raw_h - evd["i0"] if raw_h is not None else ""
            lo, hi = catch_lo_hi[event_pos]
            fire_idx, fire_off = None, None
            for j in range(lo, hi + 1):
                if alarm[j]:
                    fire_idx, fire_off = j, j - evd["i0"]
                    break
            if h is None:
                tiers["漏"] += 1
                ident_tier, gov_off, delay = "漏", "", ""
            else:
                off = h - evd["i0"]
                ident_tier, gov_off = tier_of(off, evd["e_off"]), off
                tiers[ident_tier] += 1
                delay = off - raw_off if raw_off != "" else ""
            base = {"arm": aid, "arm_name": aname, "n_box": n_box, "min_votes": min_votes,
                    "event_id": evd["event_id"], "onset": evd["onset"], "event_end": evd["event_end"],
                    "true_type": evd["true_type"], "raw_first_offset": raw_off,
                    "gov_first_offset": gov_off, "tier": ident_tier, "delay_vs_raw": delay}
            empty = {**base, "trigger_date": "", "trigger_offset": "", "caught_in_catch": "否",
                     "judged_type": "未触发", "final_plan_type": "未切换", "first_confirm_offset": "",
                     "switch_offs_p4": "", "corrections_p4": 0, "p1_full": "", "p3_full": "",
                     "p4_full": "", "diff_p1_p3": 0.0, "diff_p4_p3": 0.0}
            if fire_idx is None:
                arm_matrix.append(empty)
                continue
            f = fire_idx
            e_off = evd["i1"] - f
            T_off = evd["i1"] + REENTRY_DAYS - f
            if e_off < 0:
                arm_matrix.append({**empty, "trigger_date": cal[f], "trigger_offset": fire_off})
                continue
            assert T_off + f < n
            judgments, score_ns, judged_type, switch_offsets, corrections, cur_plan = run_judgment(
                f, e_off, True, ext_count, n_box, min_votes)
            p1_kind = "deep" if evd["true_type"] == "深慢" else "shallow"
            p1_switch = [(P1_SWITCH_OFFSET, p1_kind)] if P1_SWITCH_OFFSET < e_off else []
            p4_switch = [(off, "deep" if judgments[off] == "深慢" else "shallow") for off in switch_offsets]
            pos1, _, put1 = build_positions(f, T_off, e_off, p1_switch)
            pos4, _, put4 = build_positions(f, T_off, e_off, p4_switch)
            p3_pos = np.full(T_off + 1, POS_BASE)
            m1, m3, m4 = metrics(f, T_off, e_off, pos1, put1), metrics(f, T_off, e_off, p3_pos, []), metrics(f, T_off, e_off, pos4, put4)
            arm_matrix.append({**base, "trigger_date": cal[f], "trigger_offset": fire_off,
                               "caught_in_catch": "是", "judged_type": judged_type,
                               "final_plan_type": cur_plan if switch_offsets else "未切换",
                               "first_confirm_offset": switch_offsets[0] if switch_offsets else "",
                               "switch_offs_p4": "；".join(str(x) for x in switch_offsets),
                               "corrections_p4": corrections, "p1_full": m1["full_cum"],
                               "p3_full": m3["full_cum"], "p4_full": m4["full_cum"],
                               "diff_p1_p3": m1["full_cum"] - m3["full_cum"],
                               "diff_p4_p3": m4["full_cum"] - m3["full_cum"]})
        matrix_rows.extend(arm_matrix)

        false_records = []
        i, f_days = 0, 0
        while i < n:
            if not alarm[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and alarm[j + 1]:
                j += 1
            attributed = any(not (j < lo or i > hi) for lo, hi in catch_lo_hi)
            if not attributed:
                f_days += j - i + 1
                rec = {"arm": aid, "arm_name": aname, "episode_start": cal[i], "episode_end": cal[j],
                       "episode_len": j - i + 1}
                if i - 1 < 0 or i + 40 >= n:
                    rec.update({"status": "随访不足跳过", "judged_type": "", "final_plan_type": "",
                                "first_confirm_offset": "", "corrections": 0, "diff_p4_p3": "", "hedge_net": ""})
                else:
                    e_off_p, T_off_p = FALSE_HOLD_DAYS, FALSE_HOLD_DAYS + REENTRY_DAYS
                    judgments, score_ns, judged_type, switch_offsets, corrections, cur_plan = run_judgment(
                        i, e_off_p, False, ext_count, n_box, min_votes)
                    p4_switch = [(off, "deep" if judgments[off] == "深慢" else "shallow") for off in switch_offsets]
                    pos4, _, put4 = build_positions(i, T_off_p, e_off_p, p4_switch)
                    p3_pos = np.full(T_off_p + 1, POS_BASE)
                    m4, m3 = metrics(i, T_off_p, e_off_p, pos4, put4), metrics(i, T_off_p, e_off_p, p3_pos, [])
                    rec.update({"status": "已评估", "judged_type": judged_type,
                                "final_plan_type": cur_plan if switch_offsets else "未切换",
                                "first_confirm_offset": switch_offsets[0] if switch_offsets else "",
                                "corrections": corrections, "diff_p4_p3": m4["full_cum"] - m3["full_cum"],
                                "hedge_net": m4["hedge_net"]})
                false_records.append(rec)
            i = j + 1
        false_by_arm[aid] = false_records
        all_false_rows.extend(false_records)

        mat = pd.DataFrame(arm_matrix)
        for c in ("diff_p1_p3", "diff_p4_p3"):
            mat[c] = pd.to_numeric(mat[c])
        caught = mat[mat["caught_in_catch"] == "是"]
        switched = mat[mat["judged_type"].isin(["深慢", "浅快"])].copy()
        fm = pd.DataFrame([r for r in false_records if r["status"] == "已评估"])
        if len(fm):
            fm["diff_p4_p3"] = pd.to_numeric(fm["diff_p4_p3"])
            false_total = float(fm["diff_p4_p3"].sum())
            false_activated = int((fm["judged_type"] != "无法判定").sum())
        else:
            false_total, false_activated = 0.0, 0
        sw_diff = pd.to_numeric(switched["diff_p4_p3"]) if len(switched) else pd.Series(dtype=float)
        first_delay = pd.to_numeric(switched["first_confirm_offset"], errors="coerce") if len(switched) else pd.Series(dtype=float)
        first_correct = int((switched["judged_type"] == switched["true_type"]).sum()) if len(switched) else 0
        final_correct = int((switched["final_plan_type"] == switched["true_type"]).sum()) if len(switched) else 0
        top_idx = mat["diff_p4_p3"].idxmax()
        top_value = float(mat.loc[top_idx, "diff_p4_p3"])
        e2e_total = float(mat["diff_p4_p3"].sum())
        arm_rows.append({
            "arm": aid, "arm_name": aname, "n_box": n_box, "min_votes": min_votes,
            "identified": 45 - tiers["漏"], "n_pre": tiers["提前"], "n_in_window": tiers["窗内"],
            "n_damage": tiers["损伤窗"], "n_miss": tiers["漏"], "caught_n": len(caught),
            "trigger_offset_median": float(pd.to_numeric(caught["trigger_offset"]).median()),
            "alarm_day_share": float(alarm.sum()) / n, "false_days_total": f_days,
            "false_days_per_year": f_days / years,
            "false_days_ident_total": int((alarm & ~in_window_mask).sum()),
            "false_days_ident_per_year": int((alarm & ~in_window_mask).sum()) / years,
            "false_episodes": len(false_records), "switched_n": len(switched),
            "corrections_total": int(pd.to_numeric(mat["corrections_p4"]).sum()),
            "first_switch_delay_median": float(first_delay.median()) if len(first_delay) else math.nan,
            "first_switch_delay_q1": float(first_delay.quantile(0.25)) if len(first_delay) else math.nan,
            "first_switch_delay_q3": float(first_delay.quantile(0.75)) if len(first_delay) else math.nan,
            "first_switch_delay_min": float(first_delay.min()) if len(first_delay) else math.nan,
            "first_switch_delay_max": float(first_delay.max()) if len(first_delay) else math.nan,
            "first_type_correct_n": first_correct, "final_type_correct_n": final_correct,
            "first_type_accuracy_switched": first_correct / len(switched) if len(switched) else math.nan,
            "final_type_accuracy_switched": final_correct / len(switched) if len(switched) else math.nan,
            "event_positive_n_switched": int((sw_diff > 0).sum()), "event_negative_n_switched": int((sw_diff < 0).sum()),
            "diff_p4_p3_median_switched": float(sw_diff.median()) if len(sw_diff) else math.nan,
            "diff_p4_p3_median": float(mat["diff_p4_p3"].median()),
            "e2e_p1_p3_total": float(mat["diff_p1_p3"].sum()), "e2e_p4_p3_total": e2e_total,
            "false_cost_total": false_total, "false_activated_n": false_activated,
            "net_reference": e2e_total + false_total,
            "top_positive_event_id": int(mat.loc[top_idx, "event_id"]), "top_positive_event_contribution": top_value,
            "net_without_top_positive_event": e2e_total + false_total - max(0.0, top_value),
            "n_revoke": n_revoke, "gate_pass": "是" if tiers["漏"] == 0 else "否",
        })

    arms_df = pd.DataFrame(arm_rows)
    matrix_df = pd.DataFrame(matrix_rows)
    false_df = pd.DataFrame(all_false_rows)

    # ---------- 告警层不变量：与 v0.19 逐字段一致 ----------
    v19_sum = pd.read_csv(OUT / "regime_v019_c1_completion_summary.csv")
    for aid, _n, _k in [("F7K4", 7, 4), ("F10K6", 10, 6)]:
        new_r = arms_df[arms_df["arm"] == aid].iloc[0]
        old_r = v19_sum[v19_sum["arm"] == aid].iloc[0]
        for col in ["identified", "n_pre", "n_in_window", "n_damage", "n_miss", "caught_n",
                    "false_days_total", "false_episodes", "n_revoke", "alarm_day_share",
                    "false_days_ident_total", "false_days_per_year", "false_days_ident_per_year"]:
            assert same_scalar(new_r[col], old_r[col]), ("alarm-invariant", aid, col, new_r[col], old_r[col])

    def s_or_empty(v):
        return "" if (v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v)) else str(v)

    v19_mat = pd.read_csv(OUT / "regime_v019_c1_completion_event_matrix.csv", encoding="utf-8-sig")
    v19_false = pd.read_csv(OUT / "regime_v019_c1_completion_false_episodes.csv", encoding="utf-8-sig")

    if MODE == "baseline":
        # 对称规则复算必须与 v0.19 全字段一致。
        for aid in ("F7K4", "F10K6"):
            new_m = matrix_df[matrix_df["arm"] == aid].set_index("event_id")
            old_m = v19_mat[v19_mat["arm"] == aid].set_index("event_id")
            assert set(new_m.index) == set(old_m.index)
            for eid in new_m.index:
                for col in ["tier", "trigger_date", "judged_type", "final_plan_type",
                            "switch_offs_p4", "caught_in_catch"]:
                    nv = s_or_empty(new_m.loc[eid, col] if not isinstance(new_m.loc[eid], dict) else new_m.loc[eid, col])
                    ov = s_or_empty(old_m.loc[eid, col])
                    if col == "switch_offs_p4":
                        nv = nv.replace("；", ";")
                        ov = ov.replace("；", ";")
                    assert nv == ov, (aid, eid, col, repr(nv), repr(ov))
                for col in ["trigger_offset", "first_confirm_offset", "diff_p1_p3", "diff_p4_p3",
                            "p1_full", "p3_full", "p4_full", "corrections_p4"]:
                    assert same_scalar(new_m.loc[eid, col], old_m.loc[eid, col]), (aid, eid, col)
            old_f = v19_false[v19_false["arm"] == aid].sort_values("episode_start").reset_index(drop=True)
            new_f = pd.DataFrame(false_by_arm[aid])
            assert len(new_f) == len(old_f)
            for i in range(len(new_f)):
                for col in ["episode_start", "episode_end", "status", "judged_type",
                            "final_plan_type"]:
                    nv, ov = s_or_empty(new_f.iloc[i][col]), s_or_empty(old_f.iloc[i][col])
                    assert nv == ov, (aid, "false", i, col, repr(nv), repr(ov))
                for col in ["diff_p4_p3", "hedge_net", "corrections", "episode_len",
                            "first_confirm_offset"]:
                    assert same_scalar(new_f.iloc[i][col], old_f.iloc[i][col]), (aid, "false", i, col)
        print("baseline 对账通过：两臂 45 事件与误报段全部字段与 v0.19 一致（容差1e-6）")
        return

    # ---------- asym 模式：与 v0.19 的差异表 ----------
    def classify(eid, aid):
        new_m = matrix_df[matrix_df["arm"] == aid].set_index("event_id")
        old_m = v19_mat[v19_mat["arm"] == aid].set_index("event_id")
        nr, orow = new_m.loc[eid], old_m.loc[eid]
        old_sw = s_or_empty(orow["switch_offs_p4"]).replace("；", ";")
        new_sw = s_or_empty(nr["switch_offs_p4"]).replace("；", ";")
        old_sw_on = old_sw != ""
        new_sw_on = new_sw != ""
        if not old_sw_on and not new_sw_on:
            cat = "无变化（均未切换）"
        elif not old_sw_on and new_sw_on:
            cat = "新增切换"
        elif old_sw_on and not new_sw_on:
            cat = "取消切换"
        elif old_sw == new_sw and s_or_empty(nr["final_plan_type"]) == s_or_empty(orow["final_plan_type"]):
            cat = "无变化"
        else:
            old_first = s_or_empty(orow["judged_type"])
            new_first = s_or_empty(nr["judged_type"])
            if old_first != new_first:
                cat = "首判类型变化"
            else:
                old_off = pd.to_numeric(orow["first_confirm_offset"], errors="coerce")
                new_off = pd.to_numeric(nr["first_confirm_offset"], errors="coerce")
                cat = "切换提前" if new_off < old_off else ("切换推迟" if new_off > old_off else "修正路径变化")
        return cat, float(nr["diff_p4_p3"]) - float(orow["diff_p4_p3"]), float(nr["diff_p4_p3"]), float(orow["diff_p4_p3"])

    diff_rows = []
    for aid in ("F7K4", "F10K6"):
        new_m = matrix_df[matrix_df["arm"] == aid].set_index("event_id")
        for eid in new_m.index:
            cat, d, nv, ov = classify(eid, aid)
            if cat.startswith("无变化"):
                continue
            diff_rows.append({"arm": aid, "event_id": eid, "onset": new_m.loc[eid, "onset"],
                              "event_end": new_m.loc[eid, "event_end"], "true_type": new_m.loc[eid, "true_type"],
                              "类别": cat, "旧判型": s_or_empty(new_m.loc[eid, "judged_type"]),
                              "新切换序列": s_or_empty(new_m.loc[eid, "switch_offs_p4"]),
                              "新最终预案": s_or_empty(new_m.loc[eid, "final_plan_type"]),
                              "旧收益差": round(ov, 4), "新收益差": round(nv, 4), "收益差变化": round(d, 4)})
    diff_df = pd.DataFrame(diff_rows)

    # 误报段激活变化
    fa_rows = []
    for aid in ("F7K4", "F10K6"):
        old_f = v19_false[v19_false["arm"] == aid].sort_values("episode_start").reset_index(drop=True)
        new_f = pd.DataFrame(false_by_arm[aid])
        old_act = {s_or_empty(r["episode_start"]): r for _, r in old_f.iterrows()
                   if r["judged_type"] in ("深慢", "浅快")}
        new_act = {r["episode_start"]: r for _, r in new_f.iterrows() if r["judged_type"] in ("深慢", "浅快")}
        for s_start, nr in new_act.items():
            if s_start not in old_act:
                fa_rows.append({"arm": aid, "段首": s_start, "变化": "新增激活",
                                "判型": nr["judged_type"], "确认偏移": nr["first_confirm_offset"],
                                "收益差": round(float(nr["diff_p4_p3"]), 4)})
        for s_start, orow in old_act.items():
            if s_start not in new_act:
                fa_rows.append({"arm": aid, "段首": s_start, "变化": "激活消失",
                                "判型": s_or_empty(orow["judged_type"]), "确认偏移": s_or_empty(orow["first_confirm_offset"]),
                                "收益差": round(float(orow["diff_p4_p3"]), 4)})
        for s_start, nr in new_act.items():
            if s_start in old_act:
                ov = float(old_act[s_start]["diff_p4_p3"]); nv = float(nr["diff_p4_p3"])
                if abs(nv - ov) > 1e-6 or s_or_empty(old_act[s_start]["final_plan_type"]) != s_or_empty(nr["final_plan_type"]):
                    fa_rows.append({"arm": aid, "段首": s_start, "变化": "路径变化",
                                    "判型": nr["judged_type"], "确认偏移": nr["first_confirm_offset"],
                                    "收益差": round(nv, 4)})
    fa_diff_df = pd.DataFrame(fa_rows)

    # 汇总新旧对照
    comp_rows = []
    for aid in ("F7K4", "F10K6"):
        new_r = arms_df[arms_df["arm"] == aid].iloc[0]
        old_r = v19_sum[v19_sum["arm"] == aid].iloc[0]
        comp_rows.append({
            "arm": aid,
            "switched_old": int(old_r["switched_n"]), "switched_new": int(new_r["switched_n"]),
            "delay_median_old": float(old_r["first_switch_delay_median"]), "delay_median_new": float(new_r["first_switch_delay_median"]),
            "type_correct_old": int(old_r["final_type_correct_n"]), "type_correct_new": int(new_r["final_type_correct_n"]),
            "e2e_old": float(old_r["e2e_p4_p3_total"]), "e2e_new": float(new_r["e2e_p4_p3_total"]),
            "fa_activated_old": int(old_r["false_activated_n"]), "fa_activated_new": int(new_r["false_activated_n"]),
            "fa_cost_old": float(old_r["false_cost_total"]), "fa_cost_new": float(new_r["false_cost_total"]),
            "net_old": float(old_r["net_reference"]), "net_new": float(new_r["net_reference"]),
            "net_without_top_old": float(old_r["net_without_top_positive_event"]),
            "net_without_top_new": float(new_r["net_without_top_positive_event"]),
        })
    comp_df = pd.DataFrame(comp_rows)

    # ---------- 验证期重放（复用 v0.18 归因） ----------
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_v018_sealed_validation as v18
    books = v18.build_events(cal)
    total_days = sum(1 for d in cal if REPLAY_START <= d <= DATA_END)
    assert total_days == 381
    replay_years = total_days / 243.0
    replay_rows, replay_summary = [], {}
    for aid, aname, n_box, min_votes in ARMS:
        eps = [r for r in false_by_arm[aid] if REPLAY_START <= r["episode_start"] <= DATA_END]
        eps.sort(key=lambda e: e["episode_start"])
        attributed_ids, layer_hits = set(), {}
        for book_name, book_events in books.items():
            used = set()
            for evd in book_events:
                hit = None
                for i, ep in enumerate(eps):
                    if i in used or ep["episode_end"] < evd["win_start"] or ep["episode_start"] > evd["win_end"]:
                        continue
                    hit = (i, ep)
                    break
                if hit is None:
                    replay_rows.append({"arm": aid, "event_def": evd["def"], "event_id": evd["id"],
                                        "event_start": evd["start"], "event_end": evd["end"], "hit": "漏",
                                        "first_alarm": "", "first_offset_td": "", "offset_clamped": "",
                                        "overlap_days": 0, "timing_bin": "漏",
                                        "judged_type": "", "plan": "", "engine_status": "",
                                        "expected_type": evd["expected_type"]})
                    continue
                i, ep = hit
                used.add(i)
                attributed_ids.add(i)
                first = ep["episode_start"]
                off = v18.td_offset(cal, evd["start"], first)
                tbin = "提前" if first < evd["start"] else ("窗内" if first <= evd["end"] else "损伤窗")
                ov_s, ov_e = max(first, evd["win_start"]), min(ep["episode_end"], evd["win_end"])
                overlap = v18.td_offset(cal, ov_s, ov_e) + 1 if ov_s <= ov_e else 0
                replay_rows.append({"arm": aid, "event_def": evd["def"], "event_id": evd["id"],
                                    "event_start": evd["start"], "event_end": evd["end"], "hit": "命中",
                                    "first_alarm": first, "first_offset_td": off, "offset_clamped": max(off, -20),
                                    "overlap_days": overlap, "timing_bin": tbin,
                                    "judged_type": ep["judged_type"], "plan": ep["final_plan_type"],
                                    "engine_status": ep["status"], "expected_type": evd["expected_type"]})
            layer_hits[book_name] = len(used)
        replay_summary[aid] = {"hit_narrative": layer_hits.get("叙事", 0),
                               "hit_label": layer_hits.get("标签", 0)}
    replay_df = pd.DataFrame(replay_rows)
    for aid in ("F7K4", "F10K6"):
        rs = replay_summary[aid]
        assert rs["hit_narrative"] == 3 and rs["hit_label"] == 3, (aid, rs)

    # ---------- 输出 ----------
    names = {
        "summary": "regime_v020_asym_confirm_summary.csv",
        "events": "regime_v020_asym_confirm_event_matrix.csv",
        "false": "regime_v020_asym_confirm_false_episodes.csv",
        "diff": "regime_v020_asym_confirm_event_diff.csv",
        "replay": "regime_v020_asym_confirm_replay_events.csv",
    }
    arms_df.to_csv(OUT / names["summary"], index=False, encoding="utf-8-sig", float_format="%.6f")
    matrix_df.to_csv(OUT / names["events"], index=False, encoding="utf-8-sig", float_format="%.6f")
    false_df.to_csv(OUT / names["false"], index=False, encoding="utf-8-sig", float_format="%.6f")
    diff_df.to_csv(OUT / names["diff"], index=False, encoding="utf-8-sig", float_format="%.6f")
    replay_df.to_csv(OUT / names["replay"], index=False, encoding="utf-8-sig", float_format="%.6f")
    if len(fa_diff_df):
        fa_diff_df.to_csv(OUT / "regime_v020_asym_confirm_false_activation_diff.csv",
                          index=False, encoding="utf-8-sig", float_format="%.6f")

    css = "body{font-family:Arial,'Microsoft YaHei',sans-serif;max-width:1280px;margin:32px auto;color:#172033;background:#f7f9fc;line-height:1.55}main{background:white;padding:32px;border-radius:12px}h1,h2{color:#183b66}table{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0 28px}th,td{border:1px solid #d9e1ec;padding:7px;text-align:right}th{background:#eaf0f7}td:first-child,th:first-child{text-align:left}.note,.warn{padding:14px 18px;border-radius:8px;margin:14px 0}.note{background:#eaf3ff}.warn{background:#fff4df}.small{font-size:13px;color:#536278}"
    cv = comp_df[["arm", "switched_old", "switched_new", "delay_median_old", "delay_median_new",
                  "type_correct_old", "type_correct_new", "e2e_old", "e2e_new",
                  "fa_activated_old", "fa_activated_new", "fa_cost_old", "fa_cost_new",
                  "net_old", "net_new", "net_without_top_old", "net_without_top_new"]].copy()
    cv.columns = ["臂", "切换数(旧)", "切换数(新)", "延迟中位(旧)", "延迟中位(新)",
                  "终判一致(旧)", "终判一致(新)", "事件侧(旧)", "事件侧(新)",
                  "误报激活(旧)", "误报激活(新)", "误报损益(旧)", "误报损益(新)",
                  "净账(旧)", "净账(新)", "去最大正贡献净账(旧)", "去最大正贡献净账(新)"]
    rv = replay_df[["arm", "event_def", "event_id", "hit", "timing_bin", "judged_type", "plan", "engine_status"]].copy()
    rv.columns = ["臂", "账", "事件", "识别", "分档", "判型", "预案", "引擎状态"]
    diff_view = diff_df if len(diff_df) else pd.DataFrame([{"说明": "无差异事件"}])
    fav = fa_diff_df if len(fa_diff_df) else pd.DataFrame([{"说明": "无差异段"}])
    report = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>非对称类型确认 v0.20</title>",
              f"<style>{css}</style></head><body><main><h1>非对称类型确认：浅快单日动手、深慢维持两日（v0.20）</h1>",
              f"<div class='note'><b>预登记：</b>{REG_TS}；规则改动仅限动手所需的同型连续天数（浅快2→1，深慢不变）；S3、B10、类型3票、确认票门槛、预案与账本全部冻结。对称规则复算已与 v0.19 逐字段对账通过。</div>",
              "<h2>一、新旧对照（两臂）</h2>", cv.round(2).to_html(index=False, escape=True),
              "<h2>二、事件级差异</h2>", diff_view.to_html(index=False, escape=True),
              "<h2>三、误报段激活差异</h2>", fav.to_html(index=False, escape=True),
              "<h2>四、验证期重放（2025-04-08 起，描述性）</h2>", rv.to_html(index=False, escape=True),
              "<div class='warn'><b>证据边界：</b>样本内净账是单位账算术和与反事实上限，不是组合收益率；事件结束日前视偏差和未计一般换手摩擦原样继承；验证期已打开，本轮仅为重用后的描述性重放。本实验不自动改写最终产品；若为否定结果照常保留。</div>",
              "<p class='small'>配置：config/regime_asym_confirm_v0.20.toml；结果：regime_v020_asym_confirm_*。</p></main></body></html>"]
    (OUT / "crisis_asym_confirm_v020_report.html").write_text("".join(report), encoding="utf-8")

    out_files = list(names.values()) + ["regime_v020_asym_confirm_false_activation_diff.csv",
                                        "crisis_asym_confirm_v020_report.html"]
    manifest = {
        "version": "v0.20", "created": ts, "registered": REG_TS, "mode": MODE,
        "config": "config/regime_asym_confirm_v0.20.toml", "config_sha256": sha256_file(CFG_PATH),
        "purpose": "非对称类型确认：浅快单日动手、深慢维持两日；对照 v0.19 冻结基准",
        "rule_change": "浅快动手需 k>=1 单日判浅快+确认票过门槛+资格；深慢维持 k>=2 连续两日同判；类型修正同规则",
        "baseline_check": "对称模式复算与 v0.19 事件矩阵/误报段逐字段一致（本次运行前已通过）",
        "inputs": {f: sha256_file(OUT / f) for f in [
            "regime_v07_split_wide.csv", "regime_v05_benchmark_daily.csv", "regime_v012_trigger_event_timing.csv",
            "regime_v019_c1_completion_summary.csv", "regime_v019_c1_completion_event_matrix.csv",
            "regime_v019_c1_completion_false_episodes.csv"]},
        "outputs": {f: sha256_file(OUT / f) for f in out_files if (OUT / f).exists()},
        "comparison": comp_df.to_dict(orient="records"),
        "replay_summary": replay_summary,
        "boundary": ["样本内描述性反事实，不外推", "净账不是组合收益率", "事件结束日前视偏差与一般摩擦未计原样继承",
                     "告警层不变量与v0.19一致已断言", "不自动改写冻结产品，产品改写须用户拍板"],
    }
    (OUT / "regime_v020_asym_confirm_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"v0.20 asym 计算完成 ({ts})")
    print(comp_df.to_string(index=False))
    print("\n事件级差异：")
    print(diff_df.to_string(index=False) if len(diff_df) else "（无）")
    print("\n误报段激活差异：")
    print(fa_diff_df.to_string(index=False) if len(fa_diff_df) else "（无）")


def same_scalar(a, b, tol=1e-6):
    import math as _m
    def norm(v):
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        if isinstance(v, str):
            return v.strip()
        try:
            f = float(v)
            return None if _m.isnan(f) else f
        except (TypeError, ValueError):
            return str(v).strip()
    na, nb = norm(a), norm(b)
    if na is None and nb is None:
        return True
    if isinstance(na, float) and isinstance(nb, float):
        return abs(na - nb) <= tol
    return na == nb


if __name__ == "__main__":
    main()
