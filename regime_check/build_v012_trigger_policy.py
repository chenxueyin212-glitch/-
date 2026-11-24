#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.12 触发层政策对比：区间检测 / 混合用 与 事件＋价格确认
预登记：config/regime_trigger_policy_v0.12.toml（先登记后计算）

只读 v0.5—v0.11 冻结产物；无随机数；确定性输出。
判定机 / 预案 / 止损 / 认沽 / 回补 / 复利与 build_v011_counterfactual.py 同规则，
仅时钟原点（第 0 天）换为触发日。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
CFG_PATH = ROOT / "config" / "regime_trigger_policy_v0.12.toml"

# ---- 冻结参数（与 v0.11 完全一致，不反选）----
BASELINE_WINDOW = 10
BASELINE_MIN_NONNULL = 8
CURRENT_MIN_FRAC = 0.8
HIST_WINDOW = 756
HIST_MIN_OBS = 120
EXTREME_PCT = 0.85
JUDGMENT_START = 1
JUDGMENT_END = 20
CONFIRM_DAYS = 2
CRISIS_SCORE_MIN_N = 4
TYPE_DEEP_MIN = 2 / 3
TYPE_SHALLOW_MAX = 1 / 3
MAX_CORRECTIONS = 1
P1_SWITCH_OFFSET = 2

POS_DEEP = 0.5
POS_SHALLOW = 0.8
POS_BASE = 1.0
STOP_DEEP = 0.20
STOP_SHALLOW = 0.12
STOP_BASE_SENS = 0.08
PUT_PREMIUM_RATE = 0.015
PUT_NOTIONAL = 0.5
PUT_OTM = 0.95
REENTRY_DAYS = 20

CRISIS_FEATURES = [
    ("a16_avg_pair_corr", +1),
    ("a16_leading_eig_share", +1),
    ("b_industry_average_correlation", +1),
    ("b_h2_count", -1),
    ("b_h1_count", -1),
    ("b_h2_landscape_l1", -1),
    ("b_xy_h0_death_mean", -1),
]
TYPE_FEATURES = [
    ("a16_window_rms", +1),
    ("a16_avg_pair_corr", +1),
    ("b_xy_h0_death_mean", -1),
]

# ---- v0.12 新参数（预登记冻结）----
CATCH_START = -20                # 归属窗 [起点−20, 事件结束]
PC_FROZEN_WINDOW = (-2, 0)       # 甲
PC_EXT_WINDOW = (-2, 5)          # 甲延
FALSE_HOLD_DAYS = 20             # 误报段事件结束代理
POLICIES = ["甲", "甲延", "乙", "丙", "丁", "戊"]
FALSE_POLICIES = ["乙", "丙", "丁", "戊"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ts = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

    # ---------- 读取冻结产物 ----------
    wide = pd.read_csv(OUT / "regime_v07_split_wide.csv")
    wide["date"] = wide["date"].astype(str)
    wide = wide.sort_values("date").reset_index(drop=True)

    bench = pd.read_csv(OUT / "regime_v05_benchmark_daily.csv")
    bench["date"] = bench["date"].astype(str)
    bench = bench.sort_values("date").reset_index(drop=True)

    prof = pd.read_csv(OUT / "regime_v08_typology_event_profiles.csv")
    prof["onset"] = prof["onset"].astype(str)

    ew = pd.read_csv(
        OUT / "crisis_context_v07_event_windows.csv",
        usecols=["event_id", "event_onset", "event_end", "event_len", "date",
                 "offset_from_onset", "open", "amount_yi"],
    )
    ew["date"] = ew["date"].astype(str)
    ew["event_onset"] = ew["event_onset"].astype(str)
    ew["event_end"] = ew["event_end"].astype(str)

    v011_ev = pd.read_csv(OUT / "regime_v011_counterfactual_event_pnl.csv")

    assert len(wide) == 6483, len(wide)
    assert len(bench) == 6483, len(bench)
    assert (wide["date"].values == bench["date"].values).all(), "宽表与基准日历不一致"

    cal = wide["date"].tolist()
    idx_of = {d: i for i, d in enumerate(cal)}
    n = len(cal)

    close = bench["wind_close"].to_numpy(float)
    ret = np.full(n, np.nan)
    ret[1:] = close[1:] / close[:-1] - 1.0
    amount = pd.Series(np.nan, index=range(n))
    openp = pd.Series(np.nan, index=range(n))
    for _, row in ew.iterrows():
        i = idx_of.get(row["date"])
        if i is None:
            continue
        if pd.notna(row["open"]) and pd.isna(openp.iat[i]):
            openp.iat[i] = float(row["open"])
        if pd.notna(row["amount_yi"]) and pd.isna(amount.iat[i]):
            amount.iat[i] = float(row["amount_yi"])

    # ---------- 极端状态（与 v0.11 同）----------
    extreme = {}
    for feat, direction in CRISIS_FEATURES:
        s = wide[feat].to_numpy(float)
        flag = np.zeros(n, dtype=bool)
        for i in range(n):
            lo = max(0, i - HIST_WINDOW)
            hist = s[lo:i]
            hist = hist[np.isfinite(hist)]
            if hist.size < HIST_MIN_OBS or not np.isfinite(s[i]):
                continue
            if direction > 0:
                flag[i] = s[i] > np.quantile(hist, EXTREME_PCT)
            else:
                flag[i] = s[i] < np.quantile(hist, 1 - EXTREME_PCT)
        extreme[feat] = flag
    extreme_count = np.zeros(n, dtype=int)
    for feat, _ in CRISIS_FEATURES:
        extreme_count += extreme[feat].astype(int)

    # ---------- 区间检测轨（与 v0.11 同）----------
    r5 = np.full(n, np.nan)
    r5[5:] = close[5:] / close[:-5] - 1.0
    vol20 = pd.Series(ret).rolling(20, min_periods=15).std(ddof=1).to_numpy()
    ma250 = pd.Series(close).rolling(250, min_periods=250).mean().to_numpy()

    interval_flags = np.zeros(n, dtype=int)
    for i in range(n):
        hit = 0
        if np.isfinite(r5[i]) and r5[i] <= -0.06:
            hit += 1
        lo = max(0, i - HIST_WINDOW)
        vhist = vol20[lo:i]
        vhist = vhist[np.isfinite(vhist)]
        if np.isfinite(vol20[i]) and vhist.size >= HIST_MIN_OBS:
            if vol20[i] > np.quantile(vhist, 0.80):
                hit += 1
        if np.isfinite(ma250[i]) and close[i] < ma250[i]:
            hit += 1
        interval_flags[i] = hit

    # ---------- 价格确认子规则（与 v0.11 同，逐日可判）----------
    def pc_rules_at(j: int):
        """返回 (真实命中子规则列表, 全部说明列表)；j 为日历下标。"""
        rules, notes = [], []
        if j - 1 < 0:
            return rules, ["历史不足"]
        rj = ret[j]
        if np.isfinite(rj) and rj <= -0.025:
            rules.append("①单日跌幅≤−2.5%")
        if np.isfinite(openp.iat[j]) and np.isfinite(close[j - 1]):
            gap = openp.iat[j] / close[j - 1] - 1.0
            lo = max(0, j - 20)
            ahist = amount.to_numpy()[lo:j]
            ahist = ahist[np.isfinite(ahist)]
            if gap <= -0.015 and ahist.size >= 15:
                if np.isfinite(amount.iat[j]) and amount.iat[j] >= 1.5 * ahist.mean():
                    rules.append("②跳空≤−1.5%且量≥1.5倍")
                else:
                    notes.append("②跳空达标但放量不足")
            elif gap <= -0.015:
                notes.append("②跳空达标但均量历史不足")
        if j - 5 >= 0:
            r5j = close[j] / close[j - 5] - 1.0
            if r5j <= -0.06:
                rules.append("③5日累计≤−6%")
        return rules, notes

    # ---------- 六政策触发掩码 ----------
    fire_乙 = interval_flags >= 2
    fire_丙 = extreme_count >= 4
    fire_甲 = np.zeros(n, dtype=bool)
    fire_甲延 = np.zeros(n, dtype=bool)

    prof_by_id = {int(r["event_id"]): r for _, r in prof.iterrows()}
    events = []
    for event_id, grp in ew.groupby("event_id"):
        event_id = int(event_id)
        if event_id not in prof_by_id:
            continue
        pr = prof_by_id[event_id]
        onset = str(grp["event_onset"].iloc[0])
        end_d = str(grp["event_end"].iloc[0])
        event_len = int(grp["event_len"].iloc[0])
        assert str(pr["onset"]) == onset
        events.append({
            "event_id": event_id, "onset": onset, "event_end": end_d,
            "event_len": event_len,
            "true_type": "深慢" if int(pr["cluster_k2"]) == 1 else "浅快",
            "i0": idx_of[onset], "ie": idx_of[end_d],
        })
    events.sort(key=lambda e: e["event_id"])
    assert len(events) == 45, len(events)

    # 甲/甲延掩码（仅事件价格确认窗内）
    for ev in events:
        i0 = ev["i0"]
        for off in range(PC_FROZEN_WINDOW[0], PC_FROZEN_WINDOW[1] + 1):
            j = i0 + off
            if 0 <= j < n:
                rules, _ = pc_rules_at(j)
                if rules:
                    fire_甲[j] = True
        for off in range(PC_EXT_WINDOW[0], PC_EXT_WINDOW[1] + 1):
            j = i0 + off
            if 0 <= j < n:
                rules, _ = pc_rules_at(j)
                if rules:
                    fire_甲延[j] = True

    fire_masks = {
        "甲": fire_甲,
        "甲延": fire_甲延,
        "乙": fire_乙,
        "丙": fire_丙,
        "丁": fire_甲延 | fire_乙 | fire_丙,
        "戊": fire_乙 | fire_丙,
    }

    # ---------- 引擎函数（与 v0.11 同规则，参数化时钟原点）----------
    def plan_of(kind):
        if kind == "deep":
            return POS_DEEP, STOP_DEEP, True
        return POS_SHALLOW, STOP_SHALLOW, False

    def build_positions(i0, T_off, e_off, switch_list, base_stop=None):
        pos = np.full(T_off + 1, POS_BASE)
        put_buys = []
        stopped = False
        stopped_at = None

        if base_stop is not None:
            anchor = close[i0]
            for t in range(0, min(e_off, T_off) + 1):
                cum = close[i0 + t] / anchor - 1.0
                if cum <= -base_stop:
                    stopped = True
                    stopped_at = t
                    break
            if stopped and stopped_at is not None:
                for t in range(stopped_at + 1, min(e_off, T_off) + 1):
                    pos[t] = 0.0
                for j in range(1, REENTRY_DAYS + 1):
                    t = e_off + j
                    if t <= T_off:
                        pos[t] = POS_BASE * j / REENTRY_DAYS
            return pos, stopped_at, put_buys

        switch_map = {off: kind for off, kind in switch_list}
        kind_now = None
        cur_pos = POS_BASE
        cur_stop = None
        cur_anchor = None
        for t in range(0, T_off + 1):
            pos[t] = cur_pos
            if (not stopped and cur_stop is not None and cur_anchor is not None
                    and t >= (cur_anchor - i0) and t <= e_off):
                cum = close[i0 + t] / close[cur_anchor] - 1.0
                if cum <= -cur_stop:
                    stopped = True
                    stopped_at = t
                    cur_pos = 0.0
            if t in switch_map and not stopped:
                kind_now = switch_map[t]
                plan_pos, stop_th, has_put = plan_of(kind_now)
                cur_pos = plan_pos
                cur_stop = stop_th
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
        flows = [(off, amt) for off, amt in put_buys]
        premium_total = sum(amt for _, amt in put_buys)
        payoff = 0.0
        for off, _ in put_buys:
            s0 = close[i0 + off]
            K = PUT_OTM * s0
            sT = close[i0 + T_off]
            payoff += PUT_NOTIONAL * max(0.0, (K - sT) / K)
        flows.append((T_off, payoff))
        return flows, payoff, premium_total

    def run_pnl(i0, T_off, pos_arr, flows):
        V = np.full(T_off + 2, np.nan)
        V[0] = 1.0
        flow_map = {}
        for off, amt in flows:
            flow_map[off] = flow_map.get(off, 0.0) + amt
        for t in range(0, T_off + 1):
            r = ret[i0 + t] if np.isfinite(ret[i0 + t]) else 0.0
            v = V[t] * (1.0 + pos_arr[t] * r) + flow_map.get(t, 0.0)
            V[t + 1] = v
        return V

    def maxdd(V):
        peak = -np.inf
        dd = 0.0
        for v in V:
            if v > peak:
                peak = v
            if peak > 0:
                dd = min(dd, v / peak - 1.0)
        return dd * 100.0

    def metrics(i0, T_off, e_off, pos_arr, put_buys):
        flows, payoff, premium_total = hedge_flows(i0, T_off, put_buys)
        V = run_pnl(i0, T_off, pos_arr, flows)
        full = (V[T_off + 1] / V[0] - 1.0) * 100.0
        crisis = (V[e_off + 1] / V[0] - 1.0) * 100.0
        post = (V[T_off + 1] / V[e_off + 1] - 1.0) * 100.0
        return {
            "crisis_cum": crisis, "post20_cum": post, "full_cum": full,
            "maxdd": maxdd(V), "hedge_net": payoff + premium_total,
        }

    def run_judgment(i0, e_off, eligibility=True):
        """逐日判定 + 切换/纠错（与 v0.11 同）。
        eligibility=False 时去掉『确认日 < 事件结束』约束（误报段口径）。"""
        judgments, scores, score_ns, votes_map = {}, {}, {}, {}
        for k in range(JUDGMENT_START, JUDGMENT_END + 1):
            j = i0 + k
            if j >= n:
                break
            votes, valid_names = [], []
            for feat, sgn in TYPE_FEATURES:
                s = wide[feat].to_numpy(float)
                base = s[i0 - BASELINE_WINDOW:i0]
                base = base[np.isfinite(base)]
                cur = s[i0:j + 1]
                cur = cur[np.isfinite(cur)]
                if base.size < BASELINE_MIN_NONNULL:
                    continue
                if cur.size < np.ceil(CURRENT_MIN_FRAC * (k + 1)):
                    continue
                delta = cur.mean() - base.mean()
                deep_vote = (delta > 0) if sgn > 0 else (delta < 0)
                votes.append(1 if deep_vote else 0)
                valid_names.append(feat)
            n_valid = len(votes)
            if n_valid < 2:
                judgments[k] = "数据不足"
                type_score = np.nan
            else:
                type_score = sum(votes) / n_valid
                if type_score >= TYPE_DEEP_MIN:
                    judgments[k] = "深慢"
                elif type_score <= TYPE_SHALLOW_MAX:
                    judgments[k] = "浅快"
                else:
                    judgments[k] = "无法判定"
            score_ns[k] = int(extreme_count[i0 + k])
            scores[k] = score_ns[k] / len(CRISIS_FEATURES)
            votes_map[k] = (votes, valid_names, type_score)

        switched = False
        first_type = None
        switch_offsets = []
        corrections_used = 0
        cur_plan = None
        last_switch_k = None
        for k in range(JUDGMENT_START, JUDGMENT_END + 1):
            if k not in judgments:
                break
            elig = (k < e_off) if eligibility else (k < FALSE_HOLD_DAYS)
            if not switched:
                if (k >= CONFIRM_DAYS and judgments.get(k) == judgments.get(k - 1)
                        and judgments[k] in ("深慢", "浅快")
                        and score_ns.get(k, 0) >= CRISIS_SCORE_MIN_N
                        and elig):
                    switched = True
                    first_type = judgments[k]
                    cur_plan = judgments[k]
                    switch_offsets.append(k)
                    last_switch_k = k
            else:
                if (corrections_used < MAX_CORRECTIONS
                        and k >= CONFIRM_DAYS and (k - 1) > last_switch_k
                        and judgments.get(k) == judgments.get(k - 1)
                        and judgments[k] in ("深慢", "浅快")
                        and judgments[k] != cur_plan
                        and score_ns.get(k, 0) >= CRISIS_SCORE_MIN_N
                        and elig):
                    cur_plan = judgments[k]
                    corrections_used += 1
                    switch_offsets.append(k)
                    last_switch_k = k
        judged_type = first_type if switched else "无法判定"
        return judgments, scores, score_ns, votes_map, judged_type, switch_offsets, corrections_used, cur_plan

    # ---------- 逐事件 × 六政策：触发时点 ----------
    timing_rows = []
    endtoend_rows = []
    catch_index = []  # (i0-CATCH_START .. ie) 下标集合，误报归属用

    for ev in events:
        i0, ie = ev["i0"], ev["ie"]
        lo, hi = i0 + CATCH_START, ie
        catch_index.append((lo, hi))
        for policy in POLICIES:
            mask = fire_masks[policy]
            fire_idx, fire_off = None, None
            for j in range(max(0, lo), hi + 1):
                if mask[j]:
                    fire_idx, fire_off = j, j - i0
                    break
            e_off_geo = ie - i0  # 事件结束偏移（相对起点）
            geom_ok = (fire_off is not None and fire_off + P1_SWITCH_OFFSET < e_off_geo)
            timing_rows.append({
                "event_id": ev["event_id"], "onset": ev["onset"],
                "event_end": ev["event_end"], "event_len": ev["event_len"],
                "true_type": ev["true_type"], "policy": policy,
                "caught": "是" if fire_idx is not None else "否",
                "trigger_date": cal[fire_idx] if fire_idx is not None else "",
                "trigger_offset": fire_off if fire_off is not None else "",
                "geom_feasible": "是" if geom_ok else "否",
            })

            # ---------- 触发版端到端 ----------
            if fire_idx is None:
                endtoend_rows.append({
                    "event_id": ev["event_id"], "onset": ev["onset"],
                    "event_end": ev["event_end"], "event_len": ev["event_len"],
                    "true_type": ev["true_type"], "policy": policy,
                    "trigger_date": "", "trigger_offset": "",
                    "judged_type": "未触发", "final_plan_type": "未切换",
                    "first_confirm_offset": "", "switch_offs_p4": "",
                    "corrections_p4": 0, "eligible_p12": "否（未触发）",
                    "stop_p1": "", "stop_p2": "", "stop_p4": "",
                    "p1_crisis": "", "p1_post": "", "p1_full": "", "p1_maxdd": "",
                    "p1_hedge_net": "",
                    "p2_crisis": "", "p2_post": "", "p2_full": "", "p2_maxdd": "",
                    "p2_hedge_net": "",
                    "p3_crisis": "", "p3_post": "", "p3_full": "", "p3_maxdd": "",
                    "p4_crisis": "", "p4_post": "", "p4_full": "", "p4_maxdd": "",
                    "p4_hedge_net": "",
                    "p3b_full": "", "p3b_maxdd": "",
                    "diff_p1_p3": 0.0, "diff_p4_p3": 0.0,
                    "diff_p1_p2": 0.0, "diff_p1_p4": 0.0,
                    "segment": "前段" if ev["onset"] < "2015-01-01" else "后段",
                })
                continue

            f = fire_idx
            e_off = ie - f                      # 事件结束相对触发日
            T_off = ie + REENTRY_DAYS - f       # 全程窗末相对触发日
            assert T_off + f < n, (ev["event_id"], cal[f])
            if e_off < 0:
                # 触发日晚于事件结束（归属窗含事件结束日，正常不会发生）
                endtoend_rows.append({
                    "event_id": ev["event_id"], "onset": ev["onset"],
                    "event_end": ev["event_end"], "event_len": ev["event_len"],
                    "true_type": ev["true_type"], "policy": policy,
                    "trigger_date": cal[f], "trigger_offset": fire_off,
                    "judged_type": "未触发", "final_plan_type": "未切换",
                    "first_confirm_offset": "", "switch_offs_p4": "",
                    "corrections_p4": 0, "eligible_p12": "否（触发晚于事件结束）",
                    "stop_p1": "", "stop_p2": "", "stop_p4": "",
                    "p1_crisis": "", "p1_post": "", "p1_full": "", "p1_maxdd": "",
                    "p1_hedge_net": "",
                    "p2_crisis": "", "p2_post": "", "p2_full": "", "p2_maxdd": "",
                    "p2_hedge_net": "",
                    "p3_crisis": "", "p3_post": "", "p3_full": "", "p3_maxdd": "",
                    "p4_crisis": "", "p4_post": "", "p4_full": "", "p4_maxdd": "",
                    "p4_hedge_net": "",
                    "p3b_full": "", "p3b_maxdd": "",
                    "diff_p1_p3": 0.0, "diff_p4_p3": 0.0,
                    "diff_p1_p2": 0.0, "diff_p1_p4": 0.0,
                    "segment": "前段" if ev["onset"] < "2015-01-01" else "后段",
                })
                continue

            (judgments, scores, score_ns, votes_map, judged_type,
             switch_offsets, corrections_used, cur_plan) = run_judgment(f, e_off)

            p1_kind = "deep" if ev["true_type"] == "深慢" else "shallow"
            p2_kind = "shallow" if ev["true_type"] == "深慢" else "deep"
            elig12 = (P1_SWITCH_OFFSET < e_off)
            p1_switch = [(P1_SWITCH_OFFSET, p1_kind)] if elig12 else []
            p2_switch = [(P1_SWITCH_OFFSET, p2_kind)] if elig12 else []
            p4_switch = [(off, "deep" if judgments[off] == "深慢" else "shallow")
                         for off in switch_offsets]

            pos1, stop1, put1 = build_positions(f, T_off, e_off, p1_switch)
            pos2, stop2, put2 = build_positions(f, T_off, e_off, p2_switch)
            pos4, stop4, put4 = build_positions(f, T_off, e_off, p4_switch)
            p3_pos = np.full(T_off + 1, POS_BASE)
            p3b_pos, _, _ = build_positions(f, T_off, e_off, [], base_stop=STOP_BASE_SENS)

            m1 = metrics(f, T_off, e_off, pos1, put1)
            m2 = metrics(f, T_off, e_off, pos2, put2)
            m3 = metrics(f, T_off, e_off, p3_pos, [])
            m4 = metrics(f, T_off, e_off, pos4, put4)
            m3b = metrics(f, T_off, e_off, p3b_pos, [])

            endtoend_rows.append({
                "event_id": ev["event_id"], "onset": ev["onset"],
                "event_end": ev["event_end"], "event_len": ev["event_len"],
                "true_type": ev["true_type"], "policy": policy,
                "trigger_date": cal[f], "trigger_offset": fire_off,
                "judged_type": judged_type,
                "final_plan_type": cur_plan if switch_offsets else "未切换",
                "first_confirm_offset": switch_offsets[0] if switch_offsets else "",
                "switch_offs_p4": "；".join(str(x) for x in switch_offsets),
                "corrections_p4": corrections_used,
                "eligible_p12": "是" if elig12 else "否（危机窗口过短）",
                "stop_p1": stop1 if stop1 is not None else "",
                "stop_p2": stop2 if stop2 is not None else "",
                "stop_p4": stop4 if stop4 is not None else "",
                "p1_crisis": m1["crisis_cum"], "p1_post": m1["post20_cum"],
                "p1_full": m1["full_cum"], "p1_maxdd": m1["maxdd"],
                "p1_hedge_net": m1["hedge_net"],
                "p2_crisis": m2["crisis_cum"], "p2_post": m2["post20_cum"],
                "p2_full": m2["full_cum"], "p2_maxdd": m2["maxdd"],
                "p2_hedge_net": m2["hedge_net"],
                "p3_crisis": m3["crisis_cum"], "p3_post": m3["post20_cum"],
                "p3_full": m3["full_cum"], "p3_maxdd": m3["maxdd"],
                "p4_crisis": m4["crisis_cum"], "p4_post": m4["post20_cum"],
                "p4_full": m4["full_cum"], "p4_maxdd": m4["maxdd"],
                "p4_hedge_net": m4["hedge_net"],
                "p3b_full": m3b["full_cum"], "p3b_maxdd": m3b["maxdd"],
                "diff_p1_p3": m1["full_cum"] - m3["full_cum"],
                "diff_p4_p3": m4["full_cum"] - m3["full_cum"],
                "diff_p1_p2": m1["full_cum"] - m2["full_cum"],
                "diff_p1_p4": m1["full_cum"] - m4["full_cum"],
                "segment": "前段" if ev["onset"] < "2015-01-01" else "后段",
            })

    timing = pd.DataFrame(timing_rows)
    e2e = pd.DataFrame(endtoend_rows)

    # ---------- 误报段评估 ----------
    false_rows = []
    for policy in FALSE_POLICIES:
        mask = fire_masks[policy]
        i = 0
        while i < n:
            if not mask[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            # 归属判定：与任何事件归属窗相交？
            attributed = False
            for (lo, hi) in catch_index:
                if not (j < lo or i > hi):
                    attributed = True
                    break
            if not attributed:
                g = i  # 段首命中日 = 第 0 天
                if g - 1 < 0 or g + 40 >= n:
                    false_rows.append({
                        "policy": policy, "episode_start": cal[g], "episode_end": cal[j],
                        "episode_len": j - i + 1, "status": "随访不足跳过",
                        "judged_type": "", "final_plan_type": "",
                        "first_confirm_offset": "", "corrections": 0,
                        "diff_p4_p3": "", "hedge_net": "",
                    })
                else:
                    e_off_p = FALSE_HOLD_DAYS
                    T_off_p = FALSE_HOLD_DAYS + REENTRY_DAYS  # 40
                    (judgments, scores, score_ns, votes_map, judged_type,
                     switch_offsets, corrections_used, cur_plan) = run_judgment(
                        g, e_off_p, eligibility=False)
                    p4_switch = [(off, "deep" if judgments[off] == "深慢" else "shallow")
                                 for off in switch_offsets]
                    pos4, _, put4 = build_positions(g, T_off_p, e_off_p, p4_switch)
                    p3_pos = np.full(T_off_p + 1, POS_BASE)
                    m4 = metrics(g, T_off_p, e_off_p, pos4, put4)
                    m3 = metrics(g, T_off_p, e_off_p, p3_pos, [])
                    false_rows.append({
                        "policy": policy, "episode_start": cal[g], "episode_end": cal[j],
                        "episode_len": j - i + 1, "status": "已评估",
                        "judged_type": judged_type,
                        "final_plan_type": cur_plan if switch_offsets else "未切换",
                        "first_confirm_offset": switch_offsets[0] if switch_offsets else "",
                        "corrections": corrections_used,
                        "diff_p4_p3": m4["full_cum"] - m3["full_cum"],
                        "hedge_net": m4["hedge_net"],
                    })
            i = j + 1
    false_df = pd.DataFrame(false_rows)

    # ---------- 六政策汇总 ----------
    v011_p1_p3 = float(v011_ev["diff_p1_p3"].median())
    v011_p4_p3 = float(v011_ev["diff_p4_p3"].median())
    v011_p1_p2 = float(v011_ev["diff_p1_p2"].median())
    v011_p1_p3_total = float(v011_ev["diff_p1_p3"].sum())
    v011_p4_p3_total = float(v011_ev["diff_p4_p3"].sum())
    years = n / 250.0

    summary_rows = []
    for policy in POLICIES:
        tm = timing[timing["policy"] == policy]
        em = e2e[e2e["policy"] == policy]
        caught = em[em["judged_type"] != "未触发"].copy()
        for c in ("diff_p1_p3", "diff_p4_p3", "diff_p1_p2", "diff_p1_p4"):
            em[c] = pd.to_numeric(em[c])
        offs = pd.to_numeric(tm.loc[tm["caught"] == "是", "trigger_offset"], errors="coerce")
        fm = false_df[(false_df["policy"] == policy) & (false_df["status"] == "已评估")].copy()
        if len(fm):
            fm["diff_p4_p3"] = pd.to_numeric(fm["diff_p4_p3"])
            false_total = float(fm["diff_p4_p3"].sum())
            false_median = float(fm["diff_p4_p3"].median())
            false_activated = int((fm["judged_type"] != "无法判定").sum())
        else:
            false_total = np.nan
            false_median = np.nan
            false_activated = 0
        n_false = int((false_df["policy"] == policy).sum()) if policy in FALSE_POLICIES else 0
        n_false_eval = len(fm)
        e2e_total = float(em["diff_p4_p3"].sum())
        e2e_p1_total = float(em["diff_p1_p3"].sum())
        switched = em[em["judged_type"].isin(["深慢", "浅快"])]
        summary_rows.append({
            "policy": policy,
            "caught_n": int((tm["caught"] == "是").sum()),
            "caught_rate": float((tm["caught"] == "是").mean()),
            "trigger_offset_median": float(offs.median()) if len(offs) else np.nan,
            "trigger_offset_q1": float(offs.quantile(0.25)) if len(offs) else np.nan,
            "trigger_offset_q3": float(offs.quantile(0.75)) if len(offs) else np.nan,
            "geom_feasible_n": int((tm["geom_feasible"] == "是").sum()),
            "switched_n": int(len(switched)),
            "diff_p1_p3_median": float(em["diff_p1_p3"].median()),
            "diff_p4_p3_median": float(em["diff_p4_p3"].median()),
            "diff_p1_p3_median_triggered": (
                float(pd.to_numeric(caught["diff_p1_p3"]).median()) if len(caught) else np.nan),
            "diff_p4_p3_median_triggered": (
                float(pd.to_numeric(caught["diff_p4_p3"]).median()) if len(caught) else np.nan),
            "diff_p4_p3_median_switched": (
                float(pd.to_numeric(switched["diff_p4_p3"]).median()) if len(switched) else np.nan),
            "diff_p1_p2_median": float(em["diff_p1_p2"].median()),
            "diff_p1_p4_median": float(em["diff_p1_p4"].median()),
            "e2e_p1_p3_total": e2e_p1_total,
            "e2e_p4_p3_total": e2e_total,
            "detect_discount_p4": v011_p4_p3 - float(em["diff_p4_p3"].median()),
            "detect_discount_p1": v011_p1_p3 - float(em["diff_p1_p3"].median()),
            "false_episodes_n": n_false,
            "false_episodes_evaluated": n_false_eval,
            "false_episodes_per_year": (n_false / years) if policy in FALSE_POLICIES else np.nan,
            "false_activated_n": false_activated,
            "false_cost_total": false_total,
            "false_cost_median": false_median,
            "false_cost_per_year": (false_total / years) if policy in FALSE_POLICIES else np.nan,
            "net_reference": (e2e_total + false_total) if policy in FALSE_POLICIES else np.nan,
        })
    summary = pd.DataFrame(summary_rows)

    # ---------- 校验 ----------
    assert len(timing) == 45 * 6, len(timing)
    assert len(e2e) == 45 * 6, len(e2e)
    for policy in POLICIES:
        em = e2e[e2e["policy"] == policy]
        assert len(em) == 45, policy

    # ---------- 输出 ----------
    timing.to_csv(OUT / "regime_v012_trigger_event_timing.csv",
                  index=False, encoding="utf-8-sig", float_format="%.6f")
    false_df.to_csv(OUT / "regime_v012_trigger_false_alarm.csv",
                    index=False, encoding="utf-8-sig", float_format="%.6f")
    e2e.to_csv(OUT / "regime_v012_endtoend_event_pnl.csv",
               index=False, encoding="utf-8-sig", float_format="%.6f")
    summary.to_csv(OUT / "regime_v012_trigger_policy_summary.csv",
                   index=False, encoding="utf-8-sig", float_format="%.6f")

    out_files = [
        "regime_v012_trigger_event_timing.csv",
        "regime_v012_trigger_false_alarm.csv",
        "regime_v012_endtoend_event_pnl.csv",
        "regime_v012_trigger_policy_summary.csv",
    ]
    manifest = {
        "version": "v0.12",
        "purpose": "触发层政策对比：区间检测 / 混合用 与 事件＋价格确认（样本内描述性对账）",
        "created": ts,
        "config": "config/regime_trigger_policy_v0.12.toml",
        "config_sha256": sha256_file(CFG_PATH),
        "inputs": {
            "regime_v07_split_wide.csv": sha256_file(OUT / "regime_v07_split_wide.csv"),
            "regime_v05_benchmark_daily.csv": sha256_file(OUT / "regime_v05_benchmark_daily.csv"),
            "regime_v08_typology_event_profiles.csv": sha256_file(OUT / "regime_v08_typology_event_profiles.csv"),
            "crisis_context_v07_event_windows.csv": sha256_file(OUT / "crisis_context_v07_event_windows.csv"),
            "regime_v011_counterfactual_event_pnl.csv": sha256_file(OUT / "regime_v011_counterfactual_event_pnl.csv"),
        },
        "outputs": {f: sha256_file(OUT / f) for f in out_files},
        "frozen_params": {
            "policies": {p: "见预登记 [policies]" for p in POLICIES},
            "pc_frozen_window": list(PC_FROZEN_WINDOW),
            "pc_ext_window": list(PC_EXT_WINDOW),
            "catch_window": f"[起点{CATCH_START}, 事件结束]",
            "false_hold_days": FALSE_HOLD_DAYS,
            "judgment_window": [JUDGMENT_START, JUDGMENT_END],
            "confirm_days": CONFIRM_DAYS,
            "crisis_score_min": "4/7",
            "p1_switch_offset": P1_SWITCH_OFFSET,
            "pos_deep": POS_DEEP, "pos_shallow": POS_SHALLOW,
            "stop_deep": STOP_DEEP, "stop_shallow": STOP_SHALLOW,
            "put_premium_rate": PUT_PREMIUM_RATE,
            "reentry_days": REENTRY_DAYS,
        },
        "v011_reference": {
            "diff_p1_p3_median_known_onset": v011_p1_p3,
            "diff_p4_p3_median_known_onset": v011_p4_p3,
            "diff_p1_p2_median_known_onset": v011_p1_p2,
            "diff_p1_p3_total_known_onset": v011_p1_p3_total,
            "diff_p4_p3_total_known_onset": v011_p4_p3_total,
        },
        "sign_note": "误报代价合计与误报段损益差均为带符号（负 = 流失）；参考净账 = 事件侧合计 + 误报段合计（带符号相加）",
        "summary": summary.to_dict(orient="records"),
    }
    with open(OUT / "regime_v012_trigger_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("v0.12 计算完成")
    print(summary.to_string(index=False))
    print()
    print("v0.11 已知起点对照：P1−P3 中位 = %.3f，P4−P3 中位 = %.3f" % (v011_p1_p3, v011_p4_p3))


if __name__ == "__main__":
    main()
