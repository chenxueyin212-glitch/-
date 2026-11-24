#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.16 消音治理后的触发器接回端到端损益账本（先登记后计算）
预登记：config/regime_governed_pnl_v0.16.toml（2026-11-14T13:49:02+08:00）

底座掩码 = v0.15 选定行 S3（三中二·回撤换年线）逐字重建；
治理层   = v0.14 警报态状态机逐字复用（撤销甲/乙 × 冷却 0/5/10/20，9 变体 + G0）；
损益引擎 = v0.12 引擎段逐字复用（判定/切换/纠错/预案/止损/认沽/回补/复利/误报段）。
只组合不改规则。无随机数、全流程确定性，验收 = 双跑字节一致。
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
CFG_PATH = ROOT / "config" / "regime_governed_pnl_v0.16.toml"
REG_TS = "2026-11-14T13:49:02+08:00"

# ---- v0.15 信号块参数（冻结）----
PRE_DAYS = 20
POST_DAYS = 20
ROLL_PCT = 756
MIN_VOL_OBS = 250
MIN_TOPO_OBS = 120
TRADING_DAYS_YEAR = 250

# ---- v0.12 引擎参数（冻结，与 v0.11/v0.12 逐字同）----
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

CATCH_START = -20            # 归属窗 [起点−20, 事件结束]（v0.12 同）
FALSE_HOLD_DAYS = 20         # 误报段持有代理（v0.12 同）


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ts = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

    # ---------- 输入（与 v0.15/v0.12 逐字同源）----------
    wide = pd.read_csv(OUT / "regime_v07_split_wide.csv", parse_dates=["date"])
    bench = pd.read_csv(OUT / "regime_v05_benchmark_daily.csv", parse_dates=["date"])
    tim0 = pd.read_csv(OUT / "regime_v012_trigger_event_timing.csv")
    v015_sum = pd.read_csv(OUT / "regime_v015_lightpatch_summary.csv")
    v015_mat = pd.read_csv(OUT / "regime_v015_lightpatch_matrix.csv")
    v012_sum = pd.read_csv(OUT / "regime_v012_trigger_policy_summary.csv")

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

    # 特征数组预取（数值与 run_judgment 内逐字转换等价）
    feat_arr = {}
    for feat, _ in CRISIS_FEATURES + TYPE_FEATURES:
        if feat not in feat_arr:
            feat_arr[feat] = w[feat].to_numpy(dtype=float)

    # ---------- v0.15 信号块（逐字重建）----------
    r3 = ret_s.rolling(3).sum()
    r5 = ret_s.rolling(5).sum()
    vol20 = ret_s.rolling(20).std()
    vol_p70 = vol20.rolling(ROLL_PCT, min_periods=MIN_VOL_OBS).quantile(0.70)
    roll_max20 = pd.Series(close).rolling(20, min_periods=20).max()
    dd20 = (roll_max20 - close) / roll_max20

    S = {}
    S["D2"] = (r5 <= -0.04).to_numpy()
    S["V2"] = (vol20 > vol_p70).to_numpy()
    S["R1"] = (dd20 >= 0.05).to_numpy()

    # 底座掩码 = v0.15 选定行 S3
    raw_mask = ((S["D2"].astype(int) + S["V2"].astype(int) + S["R1"].astype(int)) >= 2)
    assert raw_mask.dtype == bool

    # ---------- 极端状态（v0.12 判定危机确认分用，逐字）----------
    extreme = {}
    for feat, direction in CRISIS_FEATURES:
        s = feat_arr[feat]
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

    # ---------- 45 事件（与 v0.14/v0.15 同）----------
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
    events.sort(key=lambda x: x["event_id"])

    in_window_mask = np.zeros(n, dtype=bool)       # 识别窗 [−20,+20]（触发层统计用）
    for evd in events:
        lo = max(0, evd["i0"] - PRE_DAYS)
        hi = min(n - 1, evd["i1"] + POST_DAYS)
        in_window_mask[lo:hi + 1] = True

    catch_lo_hi = []                                # 归属窗 [−20, 结束]（账本用）
    for evd in events:
        catch_lo_hi.append((max(0, evd["i0"] + CATCH_START), evd["i1"]))

    years = n / TRADING_DAYS_YEAR

    # ---------- v0.14 警报态状态机（逐字）----------
    ma250 = pd.Series(close).rolling(250).mean().to_numpy(dtype=float)

    def govern(mask, rule, cooldown):
        alarm = np.zeros(n, dtype=bool)
        state_on = False
        quiet = 0
        cd_left = 0
        n_rec3 = 0
        n_quiet5 = 0
        n_revoke = 0
        n_revoke_in_window = 0
        suppressed = []
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
                        if not (m3 == m3) or close[k3] < m3:
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
                alarm[i] = False
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
            "n_revoke_in_window": n_revoke_in_window, "suppressed": suppressed,
        }

    VARIANTS = [
        ("G0", "原始（无治理）", None, 0),
        ("A0", "收复静默·无冷却", "A", 0),
        ("A5", "收复静默·冷却五日", "A", 5),
        ("A10", "收复静默·冷却十日", "A", 10),
        ("A20", "收复静默·冷却二十日", "A", 20),
        ("B0", "纯静默·无冷却", "B", 0),
        ("B5", "纯静默·冷却五日", "B", 5),
        ("B10", "纯静默·冷却十日", "B", 10),
        ("B20", "纯静默·冷却二十日", "B", 20),
    ]

    # ---------- v0.12 引擎（逐字）----------
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
        """逐日判定 + 切换/纠错（与 v0.11/v0.12 同；护栏：基线窗负下标不回绕）。"""
        judgments, scores, score_ns, votes_map = {}, {}, {}, {}
        for k in range(JUDGMENT_START, JUDGMENT_END + 1):
            j = i0 + k
            if j >= n:
                break
            votes, valid_names = [], []
            for feat, sgn in TYPE_FEATURES:
                s = feat_arr[feat]
                blo = max(0, i0 - BASELINE_WINDOW)   # 护栏
                base = s[blo:i0]
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

    # ---------- 触发层统计（识别窗三档，v0.13—v0.15 口径）----------
    def tier_of(off, e_off_geo):
        if off < 0:
            return "提前"
        if off <= e_off_geo:
            return "窗内"
        return "损伤窗"

    def first_hit_ident(mask, evd):
        lo = max(0, evd["i0"] - PRE_DAYS)
        hi = min(n - 1, evd["i1"] + POST_DAYS)
        seg = mask[lo:hi + 1]
        if not seg.any():
            return None
        return lo + int(np.argmax(seg))

    # ---------- 逐变体计算 ----------
    summary_rows = []
    matrix_rows = []
    false_rows = []
    alarms = {}

    for vid, vname, rule, cd in VARIANTS:
        if vid == "G0":
            alarm = raw_mask.copy()
            st = {"n_revoke": 0, "n_rec3": 0, "n_quiet5": 0,
                  "n_revoke_in_window": 0, "suppressed": []}
        else:
            alarm, st = govern(raw_mask, rule, cd)
        alarms[vid] = alarm

        tiers = {"提前": 0, "窗内": 0, "损伤窗": 0, "漏": 0}
        ident_offs = []
        for evd in events:
            h = first_hit_ident(alarm, evd)
            raw_h = first_hit_ident(raw_mask, evd)
            raw_off = (raw_h - evd["i0"]) if raw_h is not None else ""

            # 账本时钟：归属窗 [−20, 结束] 内首个警报日
            lo, hi = catch_lo_hi[events.index(evd)]
            fire_idx, fire_off = None, None
            for j in range(lo, hi + 1):
                if alarm[j]:
                    fire_idx, fire_off = j, j - evd["i0"]
                    break

            if h is None:
                tiers["漏"] += 1
                ident_tier = "漏"
                gov_off = ""
                delay = ""
            else:
                off = h - evd["i0"]
                ident_tier = tier_of(off, evd["e_off"])
                tiers[ident_tier] += 1
                ident_offs.append(off)
                gov_off = off
                delay = (off - raw_off) if raw_off != "" else ""

            row_base = {
                "event_id": evd["event_id"], "onset": evd["onset"],
                "event_end": evd["event_end"], "event_len": evd["event_len"],
                "true_type": evd["true_type"],
                "segment": "前段" if evd["onset"] < "2015-01-01" else "后段",
                "variant": vid, "variant_name": vname,
                "revocation_rule": rule or "—", "cooldown_days": cd,
                "raw_first_offset": raw_off,
                "gov_first_offset": gov_off, "tier": ident_tier,
                "delay_vs_raw": delay,
                "n_alarm_days_in_window": int(alarm[max(0, evd["i0"] - PRE_DAYS):
                                                    min(n - 1, evd["i1"] + POST_DAYS) + 1].sum()),
            }

            # ---------- 触发版端到端（v0.12 逐字）----------
            if fire_idx is None:
                matrix_rows.append({
                    **row_base,
                    "trigger_date": "", "trigger_offset": "",
                    "caught_in_catch": "否", "geom_feasible": "否（未触发）",
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
                })
                continue

            f = fire_idx
            e_off = evd["i1"] - f
            T_off = evd["i1"] + REENTRY_DAYS - f
            assert T_off + f < n, (evd["event_id"], cal[f])
            if e_off < 0:
                matrix_rows.append({
                    **row_base,
                    "trigger_date": cal[f], "trigger_offset": fire_off,
                    "caught_in_catch": "是", "geom_feasible": "否（触发晚于事件结束）",
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
                })
                continue

            (judgments, scores, score_ns, votes_map, judged_type,
             switch_offsets, corrections_used, cur_plan) = run_judgment(f, e_off)

            p1_kind = "deep" if evd["true_type"] == "深慢" else "shallow"
            p2_kind = "shallow" if evd["true_type"] == "深慢" else "deep"
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

            matrix_rows.append({
                **row_base,
                "trigger_date": cal[f], "trigger_offset": fire_off,
                "caught_in_catch": "是",
                "geom_feasible": "是" if elig12 else "否（危机窗口过短）",
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
            })

        # ---------- 误报段（v0.12 账本口径）----------
        i = 0
        f_days = 0
        while i < n:
            if not alarm[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and alarm[j + 1]:
                j += 1
            attributed = False
            for (lo, hi) in catch_lo_hi:
                if not (j < lo or i > hi):
                    attributed = True
                    break
            if not attributed:
                f_days += j - i + 1
                g = i
                if g - 1 < 0 or g + 40 >= n:
                    false_rows.append({
                        "variant": vid, "variant_name": vname,
                        "episode_start": cal[g], "episode_end": cal[j],
                        "episode_len": j - i + 1, "status": "随访不足跳过",
                        "judged_type": "", "final_plan_type": "",
                        "first_confirm_offset": "", "corrections": 0,
                        "diff_p4_p3": "", "hedge_net": "",
                    })
                else:
                    e_off_p = FALSE_HOLD_DAYS
                    T_off_p = FALSE_HOLD_DAYS + REENTRY_DAYS
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
                        "variant": vid, "variant_name": vname,
                        "episode_start": cal[g], "episode_end": cal[j],
                        "episode_len": j - i + 1, "status": "已评估",
                        "judged_type": judged_type,
                        "final_plan_type": cur_plan if switch_offsets else "未切换",
                        "first_confirm_offset": switch_offsets[0] if switch_offsets else "",
                        "corrections": corrections_used,
                        "diff_p4_p3": m4["full_cum"] - m3["full_cum"],
                        "hedge_net": m4["hedge_net"],
                    })
            i = j + 1

        # ---------- 汇总行 ----------
        mat_v = pd.DataFrame([r for r in matrix_rows if r["variant"] == vid])
        caught = mat_v[mat_v["caught_in_catch"] == "是"].copy()
        for c in ("diff_p1_p3", "diff_p4_p3", "diff_p1_p2", "diff_p1_p4"):
            mat_v[c] = pd.to_numeric(mat_v[c])
        trig_offs = pd.to_numeric(caught["trigger_offset"], errors="coerce")
        fm = pd.DataFrame([r for r in false_rows if r["variant"] == vid and r["status"] == "已评估"])
        if len(fm):
            fm["diff_p4_p3"] = pd.to_numeric(fm["diff_p4_p3"])
            false_total = float(fm["diff_p4_p3"].sum())
            false_median = float(fm["diff_p4_p3"].median())
            false_activated = int((fm["judged_type"] != "无法判定").sum())
        else:
            false_total = 0.0
            false_median = np.nan
            false_activated = 0
        n_false = sum(1 for r in false_rows if r["variant"] == vid)
        switched = mat_v[mat_v["judged_type"].isin(["深慢", "浅快"])]
        e2e_total = float(mat_v["diff_p4_p3"].sum())
        e2e_p1_total = float(mat_v["diff_p1_p3"].sum())

        # 识别窗口径误报日（[−20,+20] 外命中，v0.13—v0.15 同；描述性对照列，不进净账）
        fm_ident = alarm & ~in_window_mask
        f_days_ident = int(fm_ident.sum())

        summary_rows.append({
            "variant": vid, "variant_name": vname,
            "revocation_rule": rule or "—", "cooldown_days": cd,
            "identified": 45 - tiers["漏"],
            "n_pre": tiers["提前"], "n_in_window": tiers["窗内"],
            "n_damage": tiers["损伤窗"], "n_miss": tiers["漏"],
            "caught_n": int(len(caught)),
            "caught_rate": float(len(caught)) / 45.0,
            "trigger_offset_median": float(trig_offs.median()) if len(trig_offs) else np.nan,
            "n_late_only": tiers["损伤窗"],
            "alarm_day_share": float(alarm.sum()) / n,
            "false_days_total": f_days,
            "false_days_per_year": f_days / years,
            "false_days_ident_total": f_days_ident,
            "false_days_ident_per_year": f_days_ident / years,
            "false_episodes": n_false,
            "false_episodes_per_year": n_false / years,
            "switched_n": int(len(switched)),
            "diff_p1_p3_median": float(mat_v["diff_p1_p3"].median()),
            "diff_p4_p3_median": float(mat_v["diff_p4_p3"].median()),
            "diff_p4_p3_median_triggered": (
                float(pd.to_numeric(caught["diff_p4_p3"]).median()) if len(caught) else np.nan),
            "diff_p4_p3_median_switched": (
                float(pd.to_numeric(switched["diff_p4_p3"]).median()) if len(switched) else np.nan),
            "diff_p1_p2_median": float(mat_v["diff_p1_p2"].median()),
            "diff_p1_p4_median": float(mat_v["diff_p1_p4"].median()),
            "e2e_p1_p3_total": e2e_p1_total,
            "e2e_p4_p3_total": e2e_total,
            "false_cost_total": false_total,
            "false_cost_median": false_median,
            "false_activated_n": false_activated,
            "net_reference": e2e_total + false_total,
        })

    summary = pd.DataFrame(summary_rows)
    matrix = pd.DataFrame(matrix_rows)
    false_df = pd.DataFrame(false_rows)

    # ---------- 对账断言 ----------
    v15 = v015_sum.set_index("policy")
    g0 = summary[summary["variant"] == "G0"].iloc[0]
    s3 = v15.loc["S3"]
    assert int(g0["identified"]) == int(s3["identified"]) == 45
    assert int(g0["n_pre"]) == int(s3["n_pre"]), (g0["n_pre"], s3["n_pre"])
    assert int(g0["n_in_window"]) == int(s3["n_in_window"])
    assert int(g0["n_damage"]) == int(s3["n_damage"])
    assert int(g0["n_miss"]) == int(s3["n_miss"]) == 0
    # G0 首响偏移与 v0.15 矩阵 S3 行一致
    m15 = v015_mat[v015_mat["policy"] == "S3"].set_index("event_id")
    for evd in events:
        eid = evd["event_id"]
        a = matrix[(matrix["variant"] == "G0") & (matrix["event_id"] == eid)].iloc[0]
        b = m15.loc[eid]
        assert str(a["gov_first_offset"]) == str(b["first_hit_offset"]) or (
            pd.to_numeric(a["gov_first_offset"], errors="coerce")
            == pd.to_numeric(b["first_hit_offset"], errors="coerce")), (eid,)
        assert a["tier"] == b["tier"], (eid, a["tier"], b["tier"])

    assert len(matrix) == 45 * len(VARIANTS), len(matrix)

    # ---------- 机械选定（预登记规则）----------
    qualified = summary[summary["identified"] == 45].copy()
    if len(qualified):
        qualified = qualified.sort_values(
            ["net_reference", "false_days_per_year", "cooldown_days"],
            ascending=[False, True, True], kind="mergesort")
        best_id = qualified.iloc[0]["variant"]
        summary["selected"] = np.where(summary["variant"] == best_id, "是", "否")
        selection_note = "合格"
    else:
        cand = summary.sort_values(["identified", "caught_n", "net_reference"],
                                   ascending=[False, False, True])
        best_id = cand.iloc[0]["variant"]
        summary["selected"] = np.where(summary["variant"] == best_id, "是", "否")
        selection_note = "无合格（治理伤害识别），取识别最大行仅作描述"

    best = summary[summary["variant"] == best_id].iloc[0]

    # ---------- 输出 ----------
    summary.to_csv(OUT / "regime_v016_governed_pnl_summary.csv",
                   index=False, encoding="utf-8-sig", float_format="%.6f")
    matrix.to_csv(OUT / "regime_v016_governed_pnl_event_matrix.csv",
                  index=False, encoding="utf-8-sig", float_format="%.6f")
    false_df.to_csv(OUT / "regime_v016_governed_pnl_false_alarm.csv",
                    index=False, encoding="utf-8-sig", float_format="%.6f")

    out_files = [
        "regime_v016_governed_pnl_summary.csv",
        "regime_v016_governed_pnl_event_matrix.csv",
        "regime_v016_governed_pnl_false_alarm.csv",
    ]
    manifest = {
        "version": "v0.16",
        "purpose": "消音治理后的触发器接回端到端损益账本（样本内描述性反事实记账）",
        "created": ts,
        "registered": REG_TS,
        "config": "config/regime_governed_pnl_v0.16.toml",
        "config_sha256": sha256_file(CFG_PATH),
        "inputs": {
            "regime_v07_split_wide.csv": sha256_file(OUT / "regime_v07_split_wide.csv"),
            "regime_v05_benchmark_daily.csv": sha256_file(OUT / "regime_v05_benchmark_daily.csv"),
            "regime_v012_trigger_event_timing.csv": sha256_file(OUT / "regime_v012_trigger_event_timing.csv"),
            "regime_v015_lightpatch_summary.csv": sha256_file(OUT / "regime_v015_lightpatch_summary.csv"),
            "regime_v015_lightpatch_matrix.csv": sha256_file(OUT / "regime_v015_lightpatch_matrix.csv"),
            "regime_v012_trigger_policy_summary.csv": sha256_file(OUT / "regime_v012_trigger_policy_summary.csv"),
        },
        "outputs": {f: sha256_file(OUT / f) for f in out_files},
        "frozen_params": {
            "base_mask": "v0.15 S3 三中二（五日跌四＋波动抬升＋回撤警报）",
            "governance_variants": [v[0] for v in VARIANTS],
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
        "v012_reference": {
            r["policy"]: {
                "caught_n": int(r["caught_n"]),
                "e2e_p4_p3_total": float(r["e2e_p4_p3_total"]),
                "false_cost_total": float(r["false_cost_total"]),
                "net_reference": float(r["net_reference"]),
            } for _, r in v012_sum[v012_sum["policy"].isin(["乙", "丁", "戊"])].iterrows()
        },
        "selection_note": selection_note,
        "selected_variant": best_id,
        "selected_variant_name": str(best["variant_name"]),
        "selected_net_reference": float(best["net_reference"]),
        "selected_e2e_p4_p3_total": float(best["e2e_p4_p3_total"]),
        "selected_false_cost_total": float(best["false_cost_total"]),
        "selected_caught_n": int(best["caught_n"]),
        "selected_false_days_per_year": float(best["false_days_per_year"]),
        "summary": summary.to_dict(orient="records"),
    }
    with open(OUT / "regime_v016_governed_pnl_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("v0.16 计算完成")
    cols_show = ["variant", "identified", "n_pre", "n_in_window", "n_damage",
                 "caught_n", "switched_n", "diff_p4_p3_median_switched",
                 "e2e_p4_p3_total", "false_cost_total", "net_reference",
                 "false_days_per_year", "false_days_ident_per_year",
                 "alarm_day_share", "selected"]
    print(summary[cols_show].to_string(index=False))


if __name__ == "__main__":
    main()
