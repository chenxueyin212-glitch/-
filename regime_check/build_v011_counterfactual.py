#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.11 产品二核心验证：四路径反事实损益
预登记：config/regime_product2_counterfactual_v0.11.toml（先登记后计算）

只读 v0.5—v0.10 冻结产物；无随机数；确定性输出。
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
CFG_PATH = ROOT / "config" / "regime_product2_counterfactual_v0.11.toml"

# ---- 冻结参数（全部来自预登记，不反选）----
BASELINE_WINDOW = 10          # 判定基线窗（第 0 天前 10 个交易日）
BASELINE_MIN_NONNULL = 8
CURRENT_MIN_FRAC = 0.8
HIST_WINDOW = 756             # 滚动 3 年
HIST_MIN_OBS = 120
EXTREME_PCT = 0.85
JUDGMENT_START = 1
JUDGMENT_END = 20
CONFIRM_DAYS = 2              # 连续同向确认天数
CRISIS_SCORE_MIN_N = 4        # 4/7
TYPE_DEEP_MIN = 2 / 3
TYPE_SHALLOW_MAX = 1 / 3
MAX_CORRECTIONS = 1
P1_SWITCH_OFFSET = 2          # 路径一/二在第 2 个交易日收盘切换

POS_DEEP = 0.5
POS_SHALLOW = 0.8
POS_BASE = 1.0
STOP_DEEP = 0.20
STOP_SHALLOW = 0.12
STOP_BASE_SENS = 0.08         # P3b 敏感性
PUT_PREMIUM_RATE = 0.015      # 名义 0.5 的 1.5%（主口径）
PUT_PREMIUM_SENS = (0.01, 0.02)  # 权利金率稳健性对照（只报数字）
PUT_NOTIONAL = 0.5
PUT_OTM = 0.95
REENTRY_DAYS = 20

COST_FN = 7.57   # 假阴：真深慢判浅快（漏砍仓）
COST_FP = 6.16   # 假阳：真浅快判深慢（误砍仓）

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
    ("a16_window_rms", +1),          # Δ>0 → 深慢票
    ("a16_avg_pair_corr", +1),       # Δ>0 → 深慢票
    ("b_xy_h0_death_mean", -1),      # Δ<0 → 深慢票
]


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

    # 开盘/成交额来自事件日级窗口（逐事件去重后写入日历）
    for _, row in ew.iterrows():
        i = idx_of.get(row["date"])
        if i is None:
            continue
        if pd.notna(row["open"]) and pd.isna(openp.iat[i]):
            openp.iat[i] = float(row["open"])
        if pd.notna(row["amount_yi"]) and pd.isna(amount.iat[i]):
            amount.iat[i] = float(row["amount_yi"])

    # ---------- 极端状态（滚动 3 年分位，方向感知）----------
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

    # ---------- 区间检测轨（3 中 2）----------
    r5 = np.full(n, np.nan)
    r5[5:] = close[5:] / close[:-5] - 1.0
    vol20 = pd.Series(ret).rolling(20, min_periods=15).std(ddof=1).to_numpy()
    ma250 = pd.Series(close).rolling(250, min_periods=250).mean().to_numpy()

    interval_flags = np.zeros(n, dtype=int)  # 命中条数
    interval_detail = [None] * n
    for i in range(n):
        hit = []
        if np.isfinite(r5[i]) and r5[i] <= -0.06:
            hit.append("5日累计急跌")
        lo = max(0, i - HIST_WINDOW)
        vhist = vol20[lo:i]
        vhist = vhist[np.isfinite(vhist)]
        if np.isfinite(vol20[i]) and vhist.size >= HIST_MIN_OBS:
            if vol20[i] > np.quantile(vhist, 0.80):
                hit.append("波动突变")
        if np.isfinite(ma250[i]) and close[i] < ma250[i]:
            hit.append("均线破位")
        interval_flags[i] = len(hit)
        interval_detail[i] = "、".join(hit) if hit else ""

    # ---------- 逐事件 ----------
    ev_rows = []
    timeline_rows = []
    audit_rows = []
    confusion_events = []  # 真型 × 判型对账

    prof_by_id = {int(r["event_id"]): r for _, r in prof.iterrows()}

    for event_id, grp in ew.groupby("event_id"):
        event_id = int(event_id)
        if event_id not in prof_by_id:
            continue  # 外部锚点 18/19 不进
        pr = prof_by_id[event_id]
        onset = str(grp["event_onset"].iloc[0])
        end_d = str(grp["event_end"].iloc[0])
        event_len = int(grp["event_len"].iloc[0])
        assert str(pr["onset"]) == onset, (event_id, pr["onset"], onset)
        true_type = "深慢" if int(pr["cluster_k2"]) == 1 else "浅快"

        i0 = idx_of[onset]
        ie = idx_of[end_d]
        e_off = ie - i0              # 事件结束日相对第 0 天的偏移
        T_off = e_off + REENTRY_DAYS  # 全程窗口末偏移
        assert T_off + i0 < n, (event_id, cal[i0 + T_off])
        assert e_off == event_len - 1, (event_id, e_off, event_len)

        # ===== 触发审计 =====
        # 价格确认：窗 [onset-2, onset]
        pc_days = []
        for off in (-2, -1, 0):
            j = i0 + off
            if j - 1 < 0:
                continue
            rules = []
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
                        rules.append("②跳空达标但放量不足")
                elif gap <= -0.015:
                    rules.append("②跳空达标但均量历史不足")
            if j - 5 >= 0:
                r5j = close[j] / close[j - 5] - 1.0
                if r5j <= -0.06:
                    rules.append("③5日累计≤−6%")
            hit_real = [x for x in rules if "不足" not in x]
            pc_days.append((off, cal[j], hit_real, rules))
        pc_hit_offs = [off for off, _, hit, _ in pc_days if hit]
        pc_first = min(pc_hit_offs) if pc_hit_offs else None
        pc_confirmed = pc_first is not None
        pc_lead = -pc_first if pc_confirmed else None  # >0 表示起点前已确认

        # 区间检测轨：窗 [onset-20, onset+10]
        iv_first_off, iv_first_day, iv_first_detail = None, None, ""
        for off in range(-20, 11):
            j = i0 + off
            if j < 0 or j >= n:
                continue
            if interval_flags[j] >= 2:
                iv_first_off, iv_first_day, iv_first_detail = off, cal[j], interval_detail[j]
                break
        # 拓扑警戒：窗 [onset-30, onset]
        topo_first_off, topo_first_day = None, None
        for off in range(-30, 1):
            j = i0 + off
            if j < 0:
                continue
            if extreme_count[j] >= 4:
                topo_first_off, topo_first_day = off, cal[j]
                break

        audit_rows.append({
            "event_id": event_id,
            "onset": onset,
            "event_end": end_d,
            "true_type": true_type,
            "pc_confirmed": "是" if pc_confirmed else "否（实盘需区间检测轨）",
            "pc_first_offset": pc_first if pc_confirmed else "",
            "pc_first_day": (pc_days[[d[0] for d in pc_days].index(pc_first)][1]
                             if pc_confirmed else ""),
            "pc_rules": ("；".join(next(t for o, _, t, _ in pc_days if o == pc_first))
                         if pc_confirmed else ""),
            "pc_onset_rules": ("；".join(next(t for o, _, t, _ in pc_days if o == 0)) or "无"),
            "interval_first_offset": iv_first_off if iv_first_off is not None else "",
            "interval_first_day": iv_first_day or "",
            "interval_first_detail": iv_first_detail,
            "interval_delay_vs_onset": iv_first_off if iv_first_off is not None else "",
            "topo_warn_first_offset": topo_first_off if topo_first_off is not None else "",
            "topo_warn_first_day": topo_first_day or "",
            "topo_warn_lead": (-topo_first_off) if topo_first_off is not None else "",
        })

        # ===== 逐日判定 =====
        judgments = {}   # k -> 深慢/浅快/无法判定/数据不足
        scores = {}      # k -> 危机确认分（分数）
        score_ns = {}    # k -> 危机确认分（极端项数，整数比较用）
        votes_map = {}
        for k in range(JUDGMENT_START, JUDGMENT_END + 1):
            j = i0 + k
            if j >= n:
                break
            votes = []
            valid_names = []
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

        # 确认切换（同一类型连续 2 日 + 确认日极端项数 ≥ 4 + 确认日 < 事件结束日）
        switched = False
        first_type = None
        switch_offsets = []
        corrections_used = 0
        cur_plan = None
        last_switch_k = None
        for k in range(JUDGMENT_START, JUDGMENT_END + 1):
            if k not in judgments:
                break
            if not switched:
                if (k >= CONFIRM_DAYS and judgments.get(k) == judgments.get(k - 1)
                        and judgments[k] in ("深慢", "浅快")
                        and score_ns.get(k, 0) >= CRISIS_SCORE_MIN_N
                        and k < e_off):
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
                        and k < e_off):
                    cur_plan = judgments[k]
                    corrections_used += 1
                    switch_offsets.append(k)
                    last_switch_k = k
        judged_type = first_type if switched else "无法判定"

        # ===== 四路径仓位序列 =====
        # 偏移 t ∈ [0, T_off]；pos[t] 作用于 t 日收益。
        # 切换在 t=s 收盘执行（锚＝当日收盘），新仓位自 t=s+1 起计损益。
        def plan_of(kind):
            if kind == "deep":
                return POS_DEEP, STOP_DEEP, True
            return POS_SHALLOW, STOP_SHALLOW, False

        def build_positions(switch_list, base_stop=None):
            """switch_list: [(off, kind)] 按时间顺序。
            返回 (pos 数组(长 T_off+1), 止损触发偏移或空, 认沽买点列表)。
            认沽买点: [(off, 权利金现金流)]（主口径 1.5%）。
            """
            pos = np.full(T_off + 1, POS_BASE)
            put_buys = []      # (off, premium_flow)
            stopped = False
            stopped_at = None

            # 基线敏感性止损（P3b，自第 0 日收盘锚定；回补期不监测）
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

            # 主路径：显式逐日生成
            switch_map = {off: kind for off, kind in switch_list}
            kind_now = None
            cur_pos = POS_BASE
            cur_stop = None
            cur_anchor = None
            for t in range(0, T_off + 1):
                # t 日收益按进入 t 日时的仓位计（t=0 为满仓；切换日当日仍是旧仓位）
                pos[t] = cur_pos
                # 止损监测（t 收盘；锚＝切换日收盘；只监测至事件结束日）
                if (not stopped and cur_stop is not None and cur_anchor is not None
                        and t >= (cur_anchor - i0) and t <= e_off):
                    cum = close[i0 + t] / close[cur_anchor] - 1.0
                    if cum <= -cur_stop:
                        stopped = True
                        stopped_at = t
                        cur_pos = 0.0
                # 切换在 t 收盘生效 → 新仓位自 t+1 起；止损后不因切换恢复
                if t in switch_map and not stopped:
                    kind_now = switch_map[t]
                    plan_pos, stop_th, has_put = plan_of(kind_now)
                    cur_pos = plan_pos
                    cur_stop = stop_th
                    cur_anchor = i0 + t
                    if has_put:
                        put_buys.append((t, -PUT_NOTIONAL * PUT_PREMIUM_RATE))
            # 回补：事件结束日起 20 日线性回补（止损后从 0 起；回补期不受止损监测）
            start_val = 0.0 if stopped else (plan_of(kind_now)[0] if kind_now else POS_BASE)
            for j in range(1, REENTRY_DAYS + 1):
                t = e_off + j
                if t <= T_off:
                    pos[t] = start_val + (POS_BASE - start_val) * j / REENTRY_DAYS
            return pos, stopped_at, put_buys

        def hedge_flows(put_buys, premium_rate):
            """把买点列表换成现金流：权利金（买点当日）＋到期收益（事件结束+20 日）。
            premium_rate 传 None 时沿用买点自带现金流（主口径）。
            """
            if premium_rate is None:
                flows = [(off, amt) for off, amt in put_buys]
                premium_total = sum(amt for _, amt in put_buys)
            else:
                flows = [(off, -PUT_NOTIONAL * premium_rate) for off, _ in put_buys]
                premium_total = -PUT_NOTIONAL * premium_rate * len(put_buys)
            payoff = 0.0
            for off, _ in put_buys:
                s0 = close[i0 + off]
                K = PUT_OTM * s0
                sT = close[i0 + T_off]
                payoff += PUT_NOTIONAL * max(0.0, (K - sT) / K)
            flows.append((T_off, payoff))
            return flows, payoff, premium_total

        # P1 / P2（第 2 个交易日收盘切换；至少留 1 个危机内生效日）
        p1_kind = "deep" if true_type == "深慢" else "shallow"
        p2_kind = "shallow" if true_type == "深慢" else "deep"
        elig12 = (P1_SWITCH_OFFSET < e_off)
        p1_switch = [(P1_SWITCH_OFFSET, p1_kind)] if elig12 else []
        p2_switch = [(P1_SWITCH_OFFSET, p2_kind)] if elig12 else []
        # P4（逐日判定的切换与纠错）
        p4_switch = []
        for off in switch_offsets:
            kind = "deep" if judgments[off] == "深慢" else "shallow"
            p4_switch.append((off, kind))
        # P3 / P3b
        p3_pos = np.full(T_off + 1, POS_BASE)
        p3b_pos, p3b_stopped, _ = build_positions([], base_stop=STOP_BASE_SENS)

        pos1, stop1, put1 = build_positions(p1_switch)
        pos2, stop2, put2 = build_positions(p2_switch)
        pos4, stop4, put4 = build_positions(p4_switch)

        # ===== 损益复利 =====
        def run_pnl(pos_arr, flows):
            V = np.full(T_off + 2, np.nan)
            V[0] = 1.0
            flow_map = {}
            for off, amt in flows:
                flow_map[off] = flow_map.get(off, 0.0) + amt
            for t in range(0, T_off + 1):
                r = ret[i0 + t] if np.isfinite(ret[i0 + t]) else 0.0
                v = V[t] * (1.0 + pos_arr[t] * r) + flow_map.get(t, 0.0)
                V[t + 1] = v
            return V  # V[T_off+1] 为最终

        def maxdd(V):
            peak = -np.inf
            dd = 0.0
            for v in V:
                if v > peak:
                    peak = v
                if peak > 0:
                    dd = min(dd, v / peak - 1.0)
            return dd * 100.0

        def metrics(pos_arr, put_buys, premium_rate=None):
            flows, payoff, premium_total = hedge_flows(put_buys, premium_rate)
            V = run_pnl(pos_arr, flows)
            full = (V[T_off + 1] / V[0] - 1.0) * 100.0
            crisis = (V[e_off + 1] / V[0] - 1.0) * 100.0
            post = (V[T_off + 1] / V[e_off + 1] - 1.0) * 100.0
            hedge_net = payoff + premium_total  # 正＝净收入，负＝净成本
            return {
                "crisis_cum": crisis,
                "post20_cum": post,
                "full_cum": full,
                "maxdd": maxdd(V),
                "hedge_net": hedge_net,
            }, V

        m1, V1 = metrics(pos1, put1)
        m2, V2 = metrics(pos2, put2)
        m3, V3 = metrics(p3_pos, [])
        m4, V4 = metrics(pos4, put4)
        m3b, _ = metrics(p3b_pos, [])
        # 权利金率稳健性对照（只报数字，不改主口径）
        m1_s = {r: metrics(pos1, put1, premium_rate=r)[0]["full_cum"]
                for r in PUT_PREMIUM_SENS}
        m4_s = {r: metrics(pos4, put4, premium_rate=r)[0]["full_cum"]
                for r in PUT_PREMIUM_SENS}

        ev_rows.append({
            "event_id": event_id,
            "onset": onset,
            "event_end": end_d,
            "event_len": event_len,
            "true_type": true_type,
            "judged_type": judged_type,
            "final_plan_type": cur_plan if switched else "未切换",
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
            "p1_full_prem10": m1_s[0.01], "p1_full_prem20": m1_s[0.02],
            "p4_full_prem10": m4_s[0.01], "p4_full_prem20": m4_s[0.02],
            "diff_p1_p3": m1["full_cum"] - m3["full_cum"],
            "diff_p4_p3": m4["full_cum"] - m3["full_cum"],
            "diff_p1_p2": m1["full_cum"] - m2["full_cum"],
            "diff_p1_p4": m1["full_cum"] - m4["full_cum"],
            "segment": "前段" if onset < "2015-01-01" else "后段",
        })

        confusion_events.append({
            "event_id": event_id,
            "true_type": true_type,
            "judged_type": judged_type,
            "p1_minus_p4_full": m1["full_cum"] - m4["full_cum"],
            "p1_full": m1["full_cum"],
            "p4_full": m4["full_cum"],
            "segment": "前段" if onset < "2015-01-01" else "后段",
            "eligible_p12": elig12,
        })

        # ===== 逐日时间线 =====
        def plan_label_at(t):
            if stop4 is not None and t > stop4 and t <= e_off:
                return "止损后空仓"
            active = None
            for off in switch_offsets:
                if t > off:
                    active = judgments.get(off)
            if active == "深慢":
                return "深慢预案"
            if active == "浅快":
                return "浅快预案"
            return "基线"

        for t in range(0, T_off + 1):
            k = t
            votes, valid_names, tscore = votes_map.get(k, ([], [], np.nan))
            timeline_rows.append({
                "event_id": event_id,
                "date": cal[i0 + t],
                "offset": t,
                "ret_pct": (ret[i0 + t] * 100.0) if np.isfinite(ret[i0 + t]) else np.nan,
                "in_crisis": "是" if t <= e_off else "否",
                "judgment": judgments.get(k, "") if JUDGMENT_START <= k <= JUDGMENT_END else "",
                "crisis_score": scores.get(k, np.nan) if JUDGMENT_START <= k <= JUDGMENT_END else np.nan,
                "n_extreme": int(extreme_count[i0 + t]),
                "type_score": tscore if JUDGMENT_START <= k <= JUDGMENT_END else np.nan,
                "valid_features": "；".join(valid_names) if votes else "",
                "plan_p4": plan_label_at(t),
                "pos_p1": pos1[t], "pos_p2": pos2[t], "pos_p3": p3_pos[t], "pos_p4": pos4[t],
                "V_p1": V1[t + 1], "V_p2": V2[t + 1], "V_p3": V3[t + 1], "V_p4": V4[t + 1],
            })

    ev = pd.DataFrame(ev_rows).sort_values("event_id").reset_index(drop=True)
    tl = pd.DataFrame(timeline_rows)
    aud = pd.DataFrame(audit_rows).sort_values("event_id").reset_index(drop=True)
    cf = pd.DataFrame(confusion_events)

    # ===== 混淆矩阵与误判代价 =====
    conf_rows = []
    for t_type in ("深慢", "浅快"):
        for j_type in ("深慢", "浅快", "无法判定"):
            sel = cf[(cf["true_type"] == t_type) & (cf["judged_type"] == j_type)]
            conf_rows.append({
                "true_type": t_type,
                "judged_type": j_type,
                "n": len(sel),
                "realized_cost_median": (sel["p1_minus_p4_full"].median() if len(sel) else np.nan),
                "realized_cost_mean": (sel["p1_minus_p4_full"].mean() if len(sel) else np.nan),
                "event_ids": "；".join(str(x) for x in sel["event_id"].tolist()),
            })
    conf = pd.DataFrame(conf_rows)

    n_total = len(cf)
    n_deep = int((cf["true_type"] == "深慢").sum())
    n_shallow = int((cf["true_type"] == "浅快").sum())
    assert n_total == 45, n_total
    assert n_deep == 15 and n_shallow == 30, (n_deep, n_shallow)
    n_fn = int(((cf["true_type"] == "深慢") & (cf["judged_type"] == "浅快")).sum())
    n_fp = int(((cf["true_type"] == "浅快") & (cf["judged_type"] == "深慢")).sum())
    exp_cost = (n_fn * COST_FN + n_fp * COST_FP) / n_total if n_total else np.nan
    base_all_shallow = n_deep * COST_FN / n_total if n_total else np.nan
    base_all_deep = n_shallow * COST_FP / n_total if n_total else np.nan

    cf_test = cf[cf["segment"] == "后段"]
    n_t = len(cf_test)
    fn_t = int(((cf_test["true_type"] == "深慢") & (cf_test["judged_type"] == "浅快")).sum())
    fp_t = int(((cf_test["true_type"] == "浅快") & (cf_test["judged_type"] == "深慢")).sum())
    deep_t = int((cf_test["true_type"] == "深慢").sum())
    shallow_t = int((cf_test["true_type"] == "浅快").sum())

    summary = {
        "n_events": n_total,
        "n_deep": n_deep,
        "n_shallow": n_shallow,
        "eligible_p12": int((ev["eligible_p12"] == "是").sum()),
        "p4_switched": int((cf["judged_type"] != "无法判定").sum()),
        "p4_corrections_total": int(ev["corrections_p4"].sum()),
        "diff_p1_p3_median": float(ev["diff_p1_p3"].median()),
        "diff_p4_p3_median": float(ev["diff_p4_p3"].median()),
        "diff_p1_p2_median": float(ev["diff_p1_p2"].median()),
        "diff_p1_p4_median": float(ev["diff_p1_p4"].median()),
        "fn": n_fn, "fp": n_fp,
        "exp_cost_full": float(exp_cost),
        "base_all_shallow_full": float(base_all_shallow),
        "base_all_deep_full": float(base_all_deep),
        "exp_cost_test": float((fn_t * COST_FN + fp_t * COST_FP) / n_t) if n_t else None,
        "base_all_shallow_test": float(deep_t * COST_FN / n_t) if n_t else None,
        "base_all_deep_test": float(shallow_t * COST_FP / n_t) if n_t else None,
        "p1_full_prem10_median": float(ev["p1_full_prem10"].median()),
        "p1_full_prem20_median": float(ev["p1_full_prem20"].median()),
        "p4_full_prem10_median": float(ev["p4_full_prem10"].median()),
        "p4_full_prem20_median": float(ev["p4_full_prem20"].median()),
    }
    for seg in ("前段", "后段"):
        s = ev[ev["segment"] == seg]
        summary[f"diff_p1_p3_median_{seg}"] = float(s["diff_p1_p3"].median())
        summary[f"diff_p4_p3_median_{seg}"] = float(s["diff_p4_p3"].median())
        summary[f"diff_p1_p2_median_{seg}"] = float(s["diff_p1_p2"].median())
    for tt in ("深慢", "浅快"):
        s = ev[ev["true_type"] == tt]
        summary[f"diff_p1_p3_median_{tt}"] = float(s["diff_p1_p3"].median())
        summary[f"diff_p4_p3_median_{tt}"] = float(s["diff_p4_p3"].median())
        summary[f"diff_p1_p2_median_{tt}"] = float(s["diff_p1_p2"].median())

    # ===== 输出 =====
    ev.to_csv(OUT / "regime_v011_counterfactual_event_pnl.csv",
              index=False, encoding="utf-8-sig", float_format="%.6f")
    tl.to_csv(OUT / "regime_v011_counterfactual_daily_timeline.csv",
              index=False, encoding="utf-8-sig", float_format="%.6f")
    conf.to_csv(OUT / "regime_v011_counterfactual_confusion.csv",
                index=False, encoding="utf-8-sig", float_format="%.6f")
    aud.to_csv(OUT / "regime_v011_trigger_audit.csv",
               index=False, encoding="utf-8-sig", float_format="%.6f")

    out_files = [
        "regime_v011_counterfactual_event_pnl.csv",
        "regime_v011_counterfactual_daily_timeline.csv",
        "regime_v011_counterfactual_confusion.csv",
        "regime_v011_trigger_audit.csv",
    ]
    manifest = {
        "version": "v0.11",
        "purpose": "产品二核心验证：四路径反事实损益（样本内反事实记账，回测结论是实盘的上限）",
        "created": ts,
        "config": "config/regime_product2_counterfactual_v0.11.toml",
        "config_sha256": sha256_file(CFG_PATH),
        "inputs": {
            "regime_v07_split_wide.csv": sha256_file(OUT / "regime_v07_split_wide.csv"),
            "regime_v05_benchmark_daily.csv": sha256_file(OUT / "regime_v05_benchmark_daily.csv"),
            "regime_v08_typology_event_profiles.csv": sha256_file(OUT / "regime_v08_typology_event_profiles.csv"),
            "crisis_context_v07_event_windows.csv": sha256_file(OUT / "crisis_context_v07_event_windows.csv"),
        },
        "outputs": {f: sha256_file(OUT / f) for f in out_files},
        "frozen_params": {
            "pos_deep": POS_DEEP, "pos_shallow": POS_SHALLOW,
            "stop_deep": STOP_DEEP, "stop_shallow": STOP_SHALLOW,
            "put_premium_rate": PUT_PREMIUM_RATE, "put_otm": PUT_OTM,
            "put_premium_sensitivity": list(PUT_PREMIUM_SENS),
            "p1_switch_offset": P1_SWITCH_OFFSET,
            "judgment_window": [JUDGMENT_START, JUDGMENT_END],
            "confirm_days": CONFIRM_DAYS,
            "crisis_score_min": "4/7（整数极端项数比较）",
            "type_vote_directions": "第十版样本内方向（尺度/正相关→深慢票，零维死亡值/负向→深慢票）",
            "switch_effective": "确认日收盘切换（成交锚＝当日收盘），新仓位自次一交易日起计损益",
            "switch_eligibility": "确认日偏移 < 事件结束日偏移（严格小于，至少留 1 个在危机内的生效日）；该资格同样约束路径一/二",
            "correction_pair": "纠错的连续两日必须都晚于最近一次切换日",
            "stop_anchor": "预案止损锚定切换日收盘；触发后仓位归零至事件结束日；不因切换而恢复；纠错时以纠正日收盘重新锚定",
            "reentry": "事件结束日起 20 交易日线性回补至满仓；回补期不受止损监测",
            "p3b_anchor": "基线敏感性止损自第 0 日收盘锚定，监测至事件结束日",
            "hedge_accounting": "权利金于买点当日扣减；到期收益（事件结束+20 交易日）计入当日现金流；均不复利",
        },
        "summary": summary,
    }
    with open(OUT / "regime_v011_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("v0.11 计算完成")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
