# -*- coding: utf-8 -*-
"""v0.21 滚动判定钟（告警段级多钟）候选实验：先登记后计算。

用法：
  python build_v021_rolling_clock.py baseline   # 禁用滚动（仅钟一），逐字段复现 v0.19 —— 实现自检
  python build_v021_rolling_clock.py rolling    # 正式实验臂：每段一钟，时间序合并确认

唯一改动点：事件级判定从「归属窗内首个告警日开一次 20 日钟」改为
「每个与归属窗有交集的告警极大段各开一钟（锚=段在窗内首日），确认日按交易日合并」。
误报段、重放、识别、S3、B10、预案、单位账全部与 v0.19 逐字相同。
"""
import sys
import json
import math
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

MODE = sys.argv[1] if len(sys.argv) > 1 else "rolling"
assert MODE in ("baseline", "rolling"), MODE

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
CFG_PATH = ROOT / "config" / "regime_rolling_clock_v0.21.toml"
REG_TS = "2026-11-19T01:08:09+08:00"

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
CONFIRM_DAYS = 2
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
    ("F7K4", "原产品C0：7项4票", 7, 4),
    ("F10K4", "同绝对票数扩容：10项4票", 10, 4),
    ("F7K5", "次要敏感性：7项5票", 7, 5),
    ("F10K5", "次要敏感性：10项5票", 10, 5),
    ("F7K6", "原七项加严：7项6票", 7, 6),
    ("F10K6", "原C1打包臂：10项6票", 10, 6),
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
    v19_events = pd.read_csv(OUT / "regime_v019_c1_completion_event_matrix.csv", encoding="utf-8-sig")
    v19_false = pd.read_csv(OUT / "regime_v019_c1_completion_false_episodes.csv", encoding="utf-8-sig")
    v19_summary = pd.read_csv(OUT / "regime_v019_c1_completion_summary.csv", encoding="utf-8-sig")
    v19_replay = pd.read_csv(OUT / "regime_v019_c1_completion_replay_events.csv", encoding="utf-8-sig")

    w = wide.merge(bench[["date", "wind_close"]], on="date", how="left").sort_values("date").reset_index(drop=True)
    assert len(w) == 6483 and w["wind_close"].notna().all()
    close = w["wind_close"].to_numpy(dtype=float)
    n = len(w)
    cal = w["date"].dt.strftime("%Y-%m-%d").tolist()
    idx_of = {d: i for i, d in enumerate(cal)}
    ret = np.empty(n)
    ret[0] = 0.0
    ret[1:] = close[1:] / close[:-1] - 1.0
    ret_s = pd.Series(ret)

    feat_arr = {}
    for feat, _ in FEATURES_10 + TYPE_FEATURES:
        if feat not in feat_arr:
            feat_arr[feat] = w[feat].to_numpy(dtype=float)

    # S3 与 B10：与 v0.15/v0.17/v0.19 执行实现逐字同源。
    r5 = ret_s.rolling(5).sum()
    vol20 = ret_s.rolling(20).std()
    vol_p70 = vol20.rolling(ROLL_PCT, min_periods=MIN_VOL_OBS).quantile(0.70)
    roll_max20 = pd.Series(close).rolling(20, min_periods=20).max()
    dd20 = (roll_max20 - close) / roll_max20
    raw_mask = (((r5 <= -0.04).astype(int) + (vol20 > vol_p70).astype(int)
                 + (dd20 >= 0.05).astype(int)) >= 2).to_numpy()

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
    events = []
    for _, r in ev.iterrows():
        o, e = idx_of[r["onset"]], idx_of[r["event_end"]]
        events.append({"event_id": int(r["event_id"]), "onset": r["onset"],
                       "event_end": r["event_end"], "true_type": r["true_type"],
                       "i0": o, "i1": e, "e_off": e - o})
    events.sort(key=lambda x: x["event_id"])
    in_window_mask = np.zeros(n, dtype=bool)
    for evd in events:
        in_window_mask[max(0, evd["i0"] - PRE_DAYS):min(n - 1, evd["i1"] + POST_DAYS) + 1] = True
    catch_lo_hi = [(max(0, e["i0"] + CATCH_START), e["i1"]) for e in events]
    years = n / TRADING_DAYS_YEAR

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

    # ---------- 判定钟：v0.21 唯一改动点 ----------
    def clock_judgments(anchor, day_upper_excl, ext_count, min_votes):
        """锚点起 20 日钟。返回 judgments{k:型} 与确认日列表 [(day, k, 型)]。
        确认=钟内 k>=2 且与前一日同型且属深慢/浅快，且该日确认票达标，且该日 < day_upper_excl。"""
        judgments = {}
        for k in range(JUDGMENT_START, JUDGMENT_END + 1):
            j = anchor + k
            if j >= n:
                break
            votes = []
            for feat, sgn in TYPE_FEATURES:
                s = feat_arr[feat]
                base = s[max(0, anchor - BASELINE_WINDOW):anchor]
                base = base[np.isfinite(base)]
                cur = s[anchor:j + 1]
                cur = cur[np.isfinite(cur)]
                if base.size < BASELINE_MIN_NONNULL or cur.size < np.ceil(CURRENT_MIN_FRAC * (k + 1)):
                    continue
                delta = cur.mean() - base.mean()
                votes.append(int((delta > 0) if sgn > 0 else (delta < 0)))
            if len(votes) < 2:
                judgments[k] = "数据不足"
            else:
                type_score = sum(votes) / len(votes)
                judgments[k] = ("深慢" if type_score >= TYPE_DEEP_MIN else
                                "浅快" if type_score <= TYPE_SHALLOW_MAX else "无法判定")
        confirms = []
        for k in range(CONFIRM_DAYS, JUDGMENT_END + 1):
            if k not in judgments or (k - 1) not in judgments:
                continue
            if (judgments[k] == judgments[k - 1] and judgments[k] in ("深慢", "浅快")
                    and anchor + k < day_upper_excl and int(ext_count[anchor + k]) >= min_votes):
                confirms.append((anchor + k, k, judgments[k]))
        return judgments, confirms

    def merge_switches(clocks):
        """clocks = [(anchor, judgments, confirms)]（锚点升序）。
        时间序合并（同日按锚点先后），产出 v0.19 同构的切换状态机结果。
        单钟情形与 v0.19 run_judgment 的切换逻辑逐字等价。"""
        all_conf = sorted(((day, ci, k, tp) for ci, (a, jd, cf) in enumerate(clocks)
                           for (day, k, tp) in cf), key=lambda x: (x[0], x[1]))
        switched, first_type, cur_plan = False, None, None
        switch_days, corrections_used, last_day = [], 0, None
        for day, ci, k, tp in all_conf:
            if not switched:
                switched, first_type, cur_plan = True, tp, tp
                switch_days.append((day, tp))
                last_day = day
            elif corrections_used < MAX_CORRECTIONS and day >= last_day + 2 and tp != cur_plan:
                cur_plan = tp
                corrections_used += 1
                switch_days.append((day, tp))
                last_day = day
        return (first_type if switched else "无法判定"), switch_days, corrections_used, cur_plan

    def first_hit_ident(mask, evd):
        lo, hi = max(0, evd["i0"] - PRE_DAYS), min(n - 1, evd["i1"] + POST_DAYS)
        seg = mask[lo:hi + 1]
        return lo + int(np.argmax(seg)) if seg.any() else None

    def tier_of(off, e_off):
        return "提前" if off < 0 else ("窗内" if off <= e_off else "损伤窗")

    # ---------- 主循环 ----------
    arm_rows, matrix_rows, all_false_rows = [], [], []
    false_by_arm = {}
    rolling_diff_rows = []
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
                     "p4_full": "", "diff_p1_p3": 0.0, "diff_p4_p3": 0.0,
                     "n_clocks": 0, "clock_anchor_dates": "", "switch_dates_p4": ""}
            if fire_idx is None:
                arm_matrix.append(empty)
                continue
            f = fire_idx
            e_off = evd["i1"] - f
            T_off = evd["i1"] + REENTRY_DAYS - f
            if e_off < 0:
                arm_matrix.append({**empty, "trigger_date": cal[f], "trigger_offset": fire_off,
                                   "n_clocks": 0})
                continue
            assert T_off + f < n
            # —— v0.21 唯一改动：枚举归属窗内的告警极大段，每段一钟 ——
            seg_list = []
            i = lo
            while i <= hi:
                if alarm[i]:
                    j = i
                    while j + 1 <= hi and alarm[j + 1]:
                        j += 1
                    seg_list.append((i, j))
                    i = j + 1
                else:
                    i += 1
            anchors = [a for a, b in seg_list]
            assert anchors[0] == f, (evd["event_id"], anchors, f)
            if MODE == "baseline":
                anchors_use = [f]
            else:
                anchors_use = anchors
            clocks = []
            for a in anchors_use:
                jd, cf = clock_judgments(a, evd["i1"], ext_count, min_votes)
                clocks.append((a, jd, cf))
            judged_type, switch_days, corrections, cur_plan = merge_switches(clocks)
            switch_offsets = [day - f for day, tp in switch_days]
            p1_kind = "deep" if evd["true_type"] == "深慢" else "shallow"
            p1_switch = [(P1_SWITCH_OFFSET, p1_kind)] if P1_SWITCH_OFFSET < e_off else []
            p4_switch = [(day - f, "deep" if tp == "深慢" else "shallow") for day, tp in switch_days]
            pos1, _, put1 = build_positions(f, T_off, e_off, p1_switch)
            pos4, _, put4 = build_positions(f, T_off, e_off, p4_switch)
            p3_pos = np.full(T_off + 1, POS_BASE)
            m1, m3, m4 = (metrics(f, T_off, e_off, pos1, put1),
                          metrics(f, T_off, e_off, p3_pos, []),
                          metrics(f, T_off, e_off, pos4, put4))
            arm_matrix.append({**base, "trigger_date": cal[f], "trigger_offset": fire_off,
                               "caught_in_catch": "是", "judged_type": judged_type,
                               "final_plan_type": cur_plan if switch_days else "未切换",
                               "first_confirm_offset": switch_offsets[0] if switch_offsets else "",
                               "switch_offs_p4": "；".join(str(x) for x in switch_offsets),
                               "corrections_p4": corrections, "p1_full": m1["full_cum"],
                               "p3_full": m3["full_cum"], "p4_full": m4["full_cum"],
                               "diff_p1_p3": m1["full_cum"] - m3["full_cum"],
                               "diff_p4_p3": m4["full_cum"] - m3["full_cum"],
                               "n_clocks": len(anchors_use),
                               "clock_anchor_dates": "；".join(cal[a] for a in anchors_use),
                               "switch_dates_p4": "；".join(f"{cal[d]}:{tp}" for d, tp in switch_days)})
        matrix_rows.extend(arm_matrix)

        # 误报段：与 v0.19 逐字相同（一段一钟，本实验不改其结构）。
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
                    jd, cf = clock_judgments(i, i + FALSE_HOLD_DAYS, ext_count, min_votes)
                    judged_type, switch_days, corrections, cur_plan = merge_switches([(i, jd, cf)])
                    p4_switch = [(day - i, "deep" if tp == "深慢" else "shallow") for day, tp in switch_days]
                    T_off_p = FALSE_HOLD_DAYS + REENTRY_DAYS
                    pos4, _, put4 = build_positions(i, T_off_p, FALSE_HOLD_DAYS, p4_switch)
                    p3_pos = np.full(T_off_p + 1, POS_BASE)
                    m4, m3 = metrics(i, T_off_p, FALSE_HOLD_DAYS, pos4, put4), metrics(i, T_off_p, FALSE_HOLD_DAYS, p3_pos, [])
                    rec.update({"status": "已评估", "judged_type": judged_type,
                                "final_plan_type": cur_plan if switch_days else "未切换",
                                "first_confirm_offset": (switch_days[0][0] - i) if switch_days else "",
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
    c0 = arms_df[arms_df["arm"] == "F7K4"].iloc[0]
    arms_df["delta_net_vs_c0"] = arms_df["net_reference"] - float(c0["net_reference"])

    invariant_cols = ["identified", "n_pre", "n_in_window", "n_damage", "n_miss", "caught_n", "alarm_day_share",
                      "false_days_total", "false_days_ident_total", "false_episodes"]
    for col in invariant_cols:
        assert arms_df[col].nunique() == 1, (col, arms_df[["arm", col]].to_dict("records"))

    # ---------- 与 v0.19 冻结产物的对账 ----------
    def norm(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        return str(v).strip()

    def same_number(a, b, tol=1e-6):
        aa, bb = pd.to_numeric(pd.Series([a]), errors="coerce").iloc[0], pd.to_numeric(pd.Series([b]), errors="coerce").iloc[0]
        if pd.isna(aa) and pd.isna(bb):
            return True
        return bool(pd.notna(aa) and pd.notna(bb) and abs(float(aa) - float(bb)) <= tol)

    v19_schema_cols = ["onset", "event_end", "true_type", "raw_first_offset", "gov_first_offset",
                       "tier", "delay_vs_raw", "trigger_date", "trigger_offset", "caught_in_catch",
                       "judged_type", "final_plan_type", "first_confirm_offset", "switch_offs_p4",
                       "corrections_p4", "diff_p1_p3", "diff_p4_p3"]
    n_identical_rows, n_changed_rows = 0, 0
    for aid, _, _, _ in ARMS:
        new_m = matrix_df[matrix_df["arm"] == aid].set_index("event_id")
        old_m = v19_events[v19_events["arm"] == aid].set_index("event_id")
        assert set(new_m.index) == set(old_m.index)
        for eid in new_m.index:
            ncols = new_m.loc[eid]
            ocols = old_m.loc[eid]
            identical = True
            for col in v19_schema_cols:
                if col in ("diff_p1_p3", "diff_p4_p3", "first_confirm_offset", "trigger_offset",
                           "raw_first_offset", "gov_first_offset", "delay_vs_raw", "corrections_p4"):
                    if not same_number(ncols[col], ocols[col]):
                        identical = False
                        break
                else:
                    if norm(ncols[col]) != norm(ocols[col]):
                        identical = False
                        break
            if ncols["n_clocks"] <= 1:
                assert identical, (aid, eid, "单钟事件行必须与v0.19一致")
            if identical:
                n_identical_rows += 1
            else:
                n_changed_rows += 1
                rolling_diff_rows.append({
                    "arm": aid, "event_id": int(eid),
                        "onset": ncols["onset"], "true_type": ncols["true_type"],
                        "old_judged": norm(ocols["judged_type"]), "new_judged": norm(ncols["judged_type"]),
                        "old_final": norm(ocols["final_plan_type"]), "new_final": norm(ncols["final_plan_type"]),
                        "old_first_off": norm(ocols["first_confirm_offset"]), "new_first_off": norm(ncols["first_confirm_offset"]),
                        "old_diff": float(ocols["diff_p4_p3"]) if pd.notna(ocols["diff_p4_p3"]) else 0.0,
                        "new_diff": float(ncols["diff_p4_p3"]),
                        "n_clocks": int(ncols["n_clocks"]),
                        "clock_anchors": norm(ncols["clock_anchor_dates"]),
                        "switch_dates": norm(ncols["switch_dates_p4"]),
                    })
        # 误报段：任何模式都必须与 v0.19 逐行逐列一致
        new_f = pd.DataFrame(false_by_arm[aid])
        old_f = v19_false[v19_false["arm"] == aid].reset_index(drop=True)
        assert len(new_f) == len(old_f), (aid, len(new_f), len(old_f))
        for i in range(len(new_f)):
            for col in ["episode_start", "episode_end", "status", "judged_type", "final_plan_type"]:
                assert norm(new_f.iloc[i][col]) == norm(old_f.iloc[i][col]), (aid, "false", i, col)
            for col in ["diff_p4_p3", "hedge_net", "first_confirm_offset", "corrections"]:
                assert same_number(new_f.iloc[i][col], old_f.iloc[i][col]), (aid, "false", i, col)
        # 汇总识别口径列：任何模式都必须与 v0.19 一致
        new_s = arms_df[arms_df["arm"] == aid].iloc[0]
        old_s = v19_summary[v19_summary["arm"] == aid].iloc[0]
        for col in ["identified", "n_pre", "n_in_window", "n_damage", "n_miss", "caught_n",
                    "false_days_total", "false_episodes", "false_activated_n"]:
            assert int(new_s[col]) == int(old_s[col]), (aid, col)
        for col in ["alarm_day_share", "false_days_per_year", "false_cost_total"]:
            assert abs(float(new_s[col]) - float(old_s[col])) <= 1e-6, (aid, col)

    if MODE == "baseline":
        # baseline：六臂全部事件行、汇总数值列也必须与 v0.19 一致
        for aid, _, _, _ in ARMS:
            new_m = matrix_df[matrix_df["arm"] == aid].set_index("event_id")
            old_m = v19_events[v19_events["arm"] == aid].set_index("event_id")
            for eid in new_m.index:
                for col in v19_schema_cols:
                    if col in ("diff_p1_p3", "diff_p4_p3", "first_confirm_offset", "trigger_offset",
                               "raw_first_offset", "gov_first_offset", "delay_vs_raw", "corrections_p4"):
                        assert same_number(new_m.loc[eid, col], old_m.loc[eid, col]), (aid, eid, col)
                    else:
                        assert norm(new_m.loc[eid, col]) == norm(old_m.loc[eid, col]), (aid, eid, col)
            new_s = arms_df[arms_df["arm"] == aid].iloc[0]
            old_s = v19_summary[v19_summary["arm"] == aid].iloc[0]
            for col in ["switched_n", "first_type_correct_n", "final_type_correct_n", "corrections_total",
                        "false_activated_n"]:
                assert int(new_s[col]) == int(old_s[col]), (aid, col, new_s[col], old_s[col])
            for col in ["e2e_p4_p3_total", "e2e_p1_p3_total", "net_reference", "first_switch_delay_median"]:
                assert same_number(new_s[col], old_s[col]), (aid, col, new_s[col], old_s[col])

    # ---------- 2×2 主析因（机械披露）----------
    by_arm = arms_df.set_index("arm")
    decomp_rows = []
    for metric, label in [("e2e_p4_p3_total", "事件侧全程收益差合计"),
                          ("false_cost_total", "误报段损益差"), ("net_reference", "净账合计"),
                          ("switched_n", "实际切换事件数"), ("false_activated_n", "误报激活段数")]:
        c00, c10 = float(by_arm.loc["F7K4", metric]), float(by_arm.loc["F10K4", metric])
        c01, c11 = float(by_arm.loc["F7K6", metric]), float(by_arm.loc["F10K6", metric])
        decomp_rows.append({"metric": metric, "metric_cn": label, "F7K4": c00, "F10K4": c10,
                            "F7K6": c01, "F10K6": c11})
    decomp_df = pd.DataFrame(decomp_rows)

    # ---------- 验证期重放（与 v0.19 逐字相同；因误报段不变，结果必须逐行一致）----------
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_v018_sealed_validation as v18
    books = v18.build_events(cal)
    total_days = sum(1 for d in cal if REPLAY_START <= d <= DATA_END)
    assert total_days == 381, total_days
    replay_years = total_days / 243.0
    win_days = {d for evs in books.values() for ev in evs for d in cal if ev["win_start"] <= d <= ev["win_end"]}
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
                                        "first_alarm": "", "first_offset_td": "", "offset_clamped": "", "overlap_days": 0, "timing_bin": "漏",
                                        "judged_type": "", "plan": "", "engine_status": "", "expected_type": evd["expected_type"]})
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
        false_eps, assoc_eps = [], []
        for i, ep in enumerate(eps):
            intersects = any(not (ep["episode_end"] < evd["win_start"] or ep["episode_start"] > evd["win_end"])
                             for evs in books.values() for evd in evs)
            if intersects and i not in attributed_ids:
                assoc_eps.append(ep)
            elif not intersects:
                false_eps.append(ep)
        fa_out_days, fa_out_days_2026 = 0, 0
        for ep in false_eps:
            for d in cal:
                if ep["episode_start"] <= d <= ep["episode_end"] and d not in win_days:
                    fa_out_days += 1
                    if d >= "2026-01-01":
                        fa_out_days_2026 += 1
        evaluated_false = [e for e in false_eps if e["status"] == "已评估"]
        replay_summary[aid] = {
            "n_episodes": len(eps), "hit_narrative": layer_hits.get("叙事", 0),
            "hit_label": layer_hits.get("标签", 0), "n_false_episodes": len(false_eps),
            "false_days_episodes": sum(e["episode_len"] for e in false_eps),
            "false_days_outside_event_windows": fa_out_days,
            "false_days_per_year_outside": fa_out_days / replay_years,
            "false_days_outside_2026": fa_out_days_2026, "n_assoc_episodes": len(assoc_eps),
            "assoc_days": sum(e["episode_len"] for e in assoc_eps),
            "false_activated_n": sum(e["judged_type"] != "无法判定" for e in evaluated_false),
            "false_proxy_cost_evaluated": sum(float(e["diff_p4_p3"]) for e in evaluated_false),
            "alarm_days_total": sum(e["episode_len"] for e in eps), "replay_days": total_days,
        }
    replay_df = pd.DataFrame(replay_rows)
    rc0 = replay_summary["F7K4"]
    assert rc0["hit_narrative"] == 3 and rc0["hit_label"] == 3
    assert rc0["false_days_outside_event_windows"] == 6 and rc0["false_days_outside_2026"] == 0
    # 重放逐行对账 v0.19
    for aid, _, _, _ in ARMS:
        new_r = replay_df[replay_df["arm"] == aid].reset_index(drop=True)
        old_r = v19_replay[v19_replay["arm"] == aid].reset_index(drop=True)
        assert len(new_r) == len(old_r), (aid, len(new_r), len(old_r))
        for i in range(len(new_r)):
            for col in ["event_def", "event_id", "hit", "first_alarm", "timing_bin", "judged_type",
                        "plan", "engine_status"]:
                assert norm(new_r.iloc[i][col]) == norm(old_r.iloc[i][col]), (aid, "replay", i, col)
            for col in ["first_offset_td", "offset_clamped", "overlap_days"]:
                assert same_number(new_r.iloc[i][col], old_r.iloc[i][col]), (aid, "replay", i, col)

    # ---------- 输出 ----------
    suffix = "baseline" if MODE == "baseline" else "rolling"
    names = {
        "summary": f"regime_v021_{suffix}_summary.csv",
        "events": f"regime_v021_{suffix}_event_matrix.csv",
        "false": f"regime_v021_{suffix}_false_episodes.csv",
        "decomp": f"regime_v021_{suffix}_decomposition.csv",
        "replay": f"regime_v021_{suffix}_replay_events.csv",
        "diff": f"regime_v021_{suffix}_event_diff_vs_v019.csv",
    }
    arms_df.to_csv(OUT / names["summary"], index=False, encoding="utf-8-sig", float_format="%.6f")
    matrix_df.to_csv(OUT / names["events"], index=False, encoding="utf-8-sig", float_format="%.6f")
    false_df.to_csv(OUT / names["false"], index=False, encoding="utf-8-sig", float_format="%.6f")
    decomp_df.to_csv(OUT / names["decomp"], index=False, encoding="utf-8-sig", float_format="%.6f")
    replay_df.to_csv(OUT / names["replay"], index=False, encoding="utf-8-sig", float_format="%.6f")
    pd.DataFrame(rolling_diff_rows).to_csv(OUT / names["diff"], index=False, encoding="utf-8-sig", float_format="%.6f")

    report = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
              f"<title>滚动判定钟 v0.21（{MODE}）</title></head><body>",
              f"<h1>v0.21 滚动判定钟（告警段级多钟）——{MODE} 模式</h1>",
              f"<p>预登记：{REG_TS}；配置：config/regime_rolling_clock_v0.21.toml；运行：{ts}</p>",
              f"<p>事件行：与 v0.19 一致 {n_identical_rows} 行 / 变动 {n_changed_rows} 行（单钟事件行已断言与 v0.19 一致；误报段与重放逐行一致断言全部通过）。</p>",
              "<h2>六臂汇总</h2>", arms_df.to_html(index=False),
              "<h2>与 v0.19 的事件级差异（F7K4 与 F10K6）</h2>",
              pd.DataFrame(rolling_diff_rows).to_html(index=False) if rolling_diff_rows else "<p>无差异</p>",
              "<h2>验证期重放摘要</h2>", pd.DataFrame([{"arm": k, **v} for k, v in replay_summary.items()]).to_html(index=False),
              "<div>证据边界：样本内描述性对账，不外推；净账为单位账算术和，非组合收益率；事件结束日前视与一般摩擦未计；本实验不自动改写冻结产品。</div>",
              "</body></html>"]
    (OUT / f"crisis_rolling_clock_v021_{suffix}_report.html").write_text("".join(report), encoding="utf-8")

    manifest = {
        "version": "v0.21", "mode": MODE, "created": ts, "registered": REG_TS,
        "config": "config/regime_rolling_clock_v0.21.toml", "config_sha256": sha256_file(CFG_PATH),
        "purpose": "滚动判定钟（告警段级多钟）候选实验",
        "inputs": {f: sha256_file(OUT / f) for f in [
            "regime_v07_split_wide.csv", "regime_v05_benchmark_daily.csv", "regime_v012_trigger_event_timing.csv",
            "regime_v019_c1_completion_event_matrix.csv", "regime_v019_c1_completion_false_episodes.csv",
            "regime_v019_c1_completion_summary.csv", "regime_v019_c1_completion_replay_events.csv"]},
        "code_dependencies": {
            "config/regime_sealed_validation_v0.18.toml": sha256_file(ROOT / "config" / "regime_sealed_validation_v0.18.toml"),
            "src/regime_check/build_v018_sealed_validation.py": sha256_file(ROOT / "src" / "regime_check" / "build_v018_sealed_validation.py"),
        },
        "outputs": {f: sha256_file(OUT / f) for f in names.values()},
        "arms": arms_df.to_dict(orient="records"),
        "reconciliation": {
            "baseline_vs_v019": ("通过（全六臂事件行+汇总数值列）" if MODE == "baseline" else "不适用"),
            "single_clock_events_vs_v019": "通过",
            "false_episodes_vs_v019": "通过（逐行逐列）",
            "replay_vs_v019": "通过（逐行逐列）",
            "identification_cols_vs_v019": "通过",
        },
        "diff_rows_vs_v019": rolling_diff_rows,
        "validation_replay": replay_summary,
        "boundary": ["样本内描述性反事实，不外推", "净账不是组合收益率", "事件结束日前视偏差与一般摩擦未计原样继承",
                     "主误报账沿用全日历扫描含验证日历；重放不得与主净账相加", "不自动改写冻结产品"],
    }
    (OUT / f"regime_v021_{suffix}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"v0.21 [{MODE}] 计算完成")
    print(f"事件行 vs v0.19：一致 {n_identical_rows}，变动 {n_changed_rows}")
    print(arms_df[["arm", "switched_n", "first_type_correct_n", "final_type_correct_n", "corrections_total",
                   "e2e_p4_p3_total", "false_activated_n", "false_cost_total", "net_reference"]].to_string(index=False))
    if rolling_diff_rows:
        print("\n事件级差异：")
        print(pd.DataFrame(rolling_diff_rows).to_string(index=False))


if __name__ == "__main__":
    main()
