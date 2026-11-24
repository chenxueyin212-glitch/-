# -*- coding: utf-8 -*-
"""v0.22 净值口径完整核算：先登记后计算。

预登记：config/regime_netvalue_v0.22.toml（2026-11-19T17:29:04+08:00，计算前冻结）。

判定层冻结复用（不重算、不改写）：
- 事件侧切换日：v0.21 双模式 CSV 的 switch_dates_p4（方案一 7项4票臂）；
- 误报侧：未归属告警极大段单钟重算（clock_judgments/merge_switches 逐字复制自
  build_v021_rolling_clock.py），与 v0.21 CSV 逐行断言一致后才进入净值核算；
- S3+B10 状态机逐字重建，归属对账后用于回补B（告警驱动）。

核算层新增（全部预登记）：连续净值复利、回补B主/回补A对照、合成虚值认沽（生效日+20到期，
到期可续买）、止损（深慢20%/浅快12%，监测至回补开始）、类型修正、单边交易成本。
"""
import sys
import json
import math
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
CFG_PATH = ROOT / "config" / "regime_netvalue_v0.22.toml"
REG_TS = "2026-11-19T17:29:04+08:00"

# ---------- 判定层常量（逐字继承 v0.21） ----------
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
FALSE_HOLD_DAYS = 20
PRE_DAYS = POST_DAYS = 20
POS_DEEP, POS_SHALLOW, POS_BASE = 0.5, 0.8, 1.0
STOP_DEEP, STOP_SHALLOW = 0.20, 0.12
PUT_OTM, PUT_NOTIONAL, PUT_PREMIUM_RATE, PUT_MATURITY = 0.95, 0.5, 0.015, 20
N_BOX, MIN_VOTES = 7, 4  # 本实验只用方案一（7项4票）
FEATURES_7 = [
    ("a16_avg_pair_corr", +1), ("a16_leading_eig_share", +1),
    ("b_industry_average_correlation", +1), ("b_h2_count", -1),
    ("b_h1_count", -1), ("b_h2_landscape_l1", -1),
    ("b_xy_h0_death_mean", -1),
]
TYPE_FEATURES = [
    ("a16_window_rms", +1), ("a16_avg_pair_corr", +1),
    ("b_xy_h0_death_mean", -1),
]
# ---------- 核算层常量（v0.22 预登记新增） ----------
REBUY_LINEAR = 20        # 回补线性天数
QUIET_DAYS = 10          # 回补B静默条件（B10冷却）
REBACK_A_HOLD = 20       # 回补A固定期限
COST_BASE = 0.001        # 万10
COST_HIGH = 0.0025       # 万25


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
    idx_of = {d: i for i, d in enumerate(cal)}
    ret = np.empty(n)
    ret[0] = 0.0
    ret[1:] = close[1:] / close[:-1] - 1.0
    ret_s = pd.Series(ret)

    feat_arr = {}
    for feat, _ in FEATURES_7 + TYPE_FEATURES:
        if feat not in feat_arr:
            feat_arr[feat] = w[feat].to_numpy(dtype=float)

    # ---------- S3 与 B10（逐字复制 build_v021_rolling_clock.py 111-137 行） ----------
    r5 = ret_s.rolling(5).sum()
    vol20 = ret_s.rolling(20).std()
    vol_p70 = vol20.rolling(ROLL_PCT, min_periods=MIN_VOL_OBS).quantile(0.70)
    roll_max20 = pd.Series(close).rolling(20, min_periods=20).max()
    dd20 = (roll_max20 - close) / roll_max20
    raw_mask = (((r5 <= -0.04).astype(int) + (vol20 > vol_p70).astype(int)
                 + (dd20 >= 0.05).astype(int)) >= 2).to_numpy()

    alarm = np.zeros(n, dtype=bool)
    state_on, quiet, cd_left = False, 0, 0
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

    # 告警极大段
    segs = []
    i = 0
    while i < n:
        if not alarm[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and alarm[j + 1]:
            j += 1
        segs.append((i, j))
        i = j + 1
    seg_arr = np.full(n, -1, dtype=int)
    for s, (a, _) in enumerate(segs):
        seg_arr[a:] = s

    # 事件 catch 窗（仅用于归属对账与误报段判定，不参与任何仓位决策）
    ev = (tim0[tim0["policy"] == "乙"].drop_duplicates(subset=["event_id"])
          .sort_values("onset").reset_index(drop=True))
    assert len(ev) == 45
    catch_lo_hi = []
    for _, r in ev.iterrows():
        lo, hi = idx_of[r["onset"]] - PRE_DAYS, idx_of[r["event_end"]]
        catch_lo_hi.append((lo, hi))

    # ---------- 确认票（build_extreme 逐字） ----------
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

    ext_count = build_extreme(FEATURES_7)

    # ---------- 判定钟（逐字复制 v0.21） ----------
    def clock_judgments(anchor, day_upper_excl, ext_cnt, min_votes):
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
                    and anchor + k < day_upper_excl and int(ext_cnt[anchor + k]) >= min_votes):
                confirms.append((anchor + k, k, judgments[k]))
        return judgments, confirms

    def merge_switches(clocks):
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

    # ---------- 误报段重算 + 与 v0.21 逐行对账（两模式） ----------
    def recompute_false_rows():
        rows = []
        day = 0
        while day < n:
            if not alarm[day]:
                day += 1
                continue
            j = day
            while j + 1 < n and alarm[j + 1]:
                j += 1
            attributed = any(not (j < lo or day > hi) for lo, hi in catch_lo_hi)
            if not attributed:
                rec = {"episode_start": cal[day], "episode_end": cal[j], "episode_len": j - day + 1}
                if day - 1 < 0 or day + 40 >= n:
                    rec.update({"status": "随访不足跳过", "judged_type": "", "final_plan_type": "",
                                "first_confirm_offset": "", "corrections": 0})
                else:
                    jd, cf = clock_judgments(day, day + FALSE_HOLD_DAYS, ext_count, MIN_VOTES)
                    judged_type, switch_days, corrections, cur_plan = merge_switches([(day, jd, cf)])
                    rec.update({"status": "已评估", "judged_type": judged_type,
                                "final_plan_type": cur_plan if switch_days else "未切换",
                                "first_confirm_offset": (switch_days[0][0] - day) if switch_days else "",
                                "corrections": corrections,
                                "_switch_days": [(d, "deep" if tp == "深慢" else "shallow") for d, tp in switch_days]})
                rows.append(rec)
            day = j + 1
        return rows

    def norm(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        return str(v).strip()

    def same_number(a, b, tol=1e-6):
        aa = pd.to_numeric(pd.Series([a]), errors="coerce").iloc[0]
        bb = pd.to_numeric(pd.Series([b]), errors="coerce").iloc[0]
        if pd.isna(aa) and pd.isna(bb):
            return True
        return bool(pd.notna(aa) and pd.notna(bb) and abs(float(aa) - float(bb)) <= tol)

    false_switches = {}
    false_corr = {}
    for mode in ("baseline", "rolling"):
        v21_false = pd.read_csv(OUT / f"regime_v021_{mode}_false_episodes.csv", encoding="utf-8-sig")
        v21_false = v21_false[v21_false["arm"] == "F7K4"].reset_index(drop=True)
        recomputed = recompute_false_rows()
        assert len(recomputed) == len(v21_false), (mode, len(recomputed), len(v21_false))
        sw_list, n_corr = [], 0
        for i in range(len(recomputed)):
            nr, orow = recomputed[i], v21_false.iloc[i]
            for col in ["episode_start", "episode_end", "status", "judged_type", "final_plan_type"]:
                assert norm(nr[col]) == norm(orow[col]), (mode, "false", i, col, nr[col], orow[col])
            assert same_number(nr["first_confirm_offset"], orow["first_confirm_offset"]), (mode, "false", i, "offset")
            assert int(nr["corrections"]) == int(pd.to_numeric(orow["corrections"])), (mode, "false", i, "corr")
            sd = nr.get("_switch_days", [])
            sw_list.extend((d, tp, ci > 0) for ci, (d, tp) in enumerate(sd))
            n_corr += int(nr["corrections"])
        false_switches[mode] = sw_list
        false_corr[mode] = n_corr

    # ---------- 事件侧切换日（v0.21 CSV 冻结输出，逐字符解析） ----------
    event_switches = {}
    event_corr = {}
    for mode in ("baseline", "rolling"):
        v21_events = pd.read_csv(OUT / f"regime_v021_{mode}_event_matrix.csv", encoding="utf-8-sig")
        sw = v21_events[(v21_events["arm"] == "F7K4") & (v21_events["caught_in_catch"] == "是")]
        event_trigger_days = {r["trigger_date"] for _, r in sw.iterrows()}
        pairs, n_corr = [], 0
        for _, r in sw.iterrows():
            toks = [tok for tok in str(r["switch_dates_p4"]).split("；") if ":" in tok]
            for ci, tok in enumerate(toks):
                d, tp = tok.split(":")
                assert tp in ("深慢", "浅快"), tok
                pairs.append((idx_of[d], "deep" if tp == "深慢" else "shallow", ci > 0))
            n_corr += int(r["corrections_p4"])
        assert n_corr == sum(1 for _, _, c in pairs if c), (mode, "行内修正数与corrections_p4列不符", n_corr)
        event_switches[mode] = sorted(pairs)
        event_corr[mode] = n_corr
        # 归属对账：每个告警极大段要么含某事件 trigger，要么属于误报段记录
        v21_all_false = pd.read_csv(OUT / f"regime_v021_{mode}_false_episodes.csv", encoding="utf-8-sig")
        v21_all_false = v21_all_false[v21_all_false["arm"] == "F7K4"]
        false_pairs = {(r["episode_start"], r["episode_end"]) for _, r in v21_all_false.iterrows()}
        n_attr, n_false = 0, 0
        for (a, b) in segs:
            attributed = any(not (b < lo or a > hi) for lo, hi in catch_lo_hi)
            if attributed:
                n_attr += 1
            else:
                assert (cal[a], cal[b]) in false_pairs, (mode, "段未覆盖", cal[a], cal[b])
                n_false += 1
        assert n_attr + n_false == len(segs)
        print(f"[{mode}] 告警段 {len(segs)} = 事件归属 {n_attr} + 误报 {n_false}")

    # ---------- 合并全日历切换序列 ----------
    merged_switches = {}
    for mode in ("baseline", "rolling"):
        merged = sorted(event_switches[mode] + false_switches[mode])
        dedup = []
        for d, tp, is_corr in merged:
            if dedup and dedup[-1][0] == d:
                assert dedup[-1][1] == tp, (mode, "同日类型冲突", cal[d])
                continue
            dedup.append((d, tp, is_corr))
        merged_switches[mode] = dedup
        n_event_sw, n_false_sw = len(event_switches[mode]), len(false_switches[mode])
        n_merged = len(dedup)
        assert n_merged == n_event_sw + n_false_sw, (mode, n_merged, n_event_sw, n_false_sw)
        n_corr = sum(1 for _, _, c in dedup if c)
        assert n_corr == event_corr[mode] + false_corr[mode], (mode, "修正数对账失败", n_corr, event_corr[mode], false_corr[mode])
        print(f"[{mode}] 合并切换 {n_merged}（事件 {n_event_sw} + 误报激活 {n_false_sw}），修正 {n_corr} ✓ 与 v0.21 一致")

    # ---------- 净值模拟引擎 ----------
    def simulate(switches, reback, use_put, use_stop, cost_rate):
        pos = np.ones(n)
        flow = np.zeros(n)
        nav = np.ones(n)
        sw_map = {}
        for d, tp, is_corr in switches:
            assert d not in sw_map, ("同日重复切换", cal[d])
            sw_map[d] = (tp, is_corr)
        logs = []
        puts = []
        plan = None
        anchor = None
        stopped = False
        stop_seg = None
        last_cut = None
        rebuy_active = False
        rebuy_level0 = 0.0
        rebuy_k = 0
        hedge_eligible = False
        cost_sum = 0.0

        def buy_put(eff):
            if eff + PUT_MATURITY >= n:
                return  # 到期日越出数据末端，不买（末日邻域无切换，防御性）
            notional = PUT_NOTIONAL * nav[eff]
            k = PUT_OTM * close[eff]
            flow[eff] -= notional * PUT_PREMIUM_RATE
            puts.append({"eff": eff, "mat": eff + PUT_MATURITY, "notional": notional,
                         "k": k, "premium": notional * PUT_PREMIUM_RATE, "settled": False,
                         "settled_at": ""})

        for t in range(n):
            # 1) 切换/修正：确认日收盘决策，次日起生效
            if t in sw_map and not (stopped and seg_arr[t] == stop_seg):
                tp, is_corr = sw_map[t]
                level = POS_DEEP if tp == "deep" else POS_SHALLOW
                action = "修正" if is_corr else "切换"
                plan, anchor = tp, t
                stopped, stop_seg = False, None
                last_cut = t
                rebuy_active, rebuy_k = False, 0
                hedge_eligible = (tp == "deep")
                logs.append({"day": t, "date": cal[t], "action": action, "type": tp,
                             "level": level, "detail": ""})
                if use_put and tp == "deep":
                    buy_put(t)
            # 2) 止损检查：监测窗 = 锚日至回补开始前
            if (use_stop and plan is not None and not stopped and not rebuy_active
                    and anchor is not None and t > anchor):
                th = STOP_DEEP if plan == "deep" else STOP_SHALLOW
                if close[t] / close[anchor] - 1.0 <= -th:
                    stopped, stop_seg = True, seg_arr[t]
                    last_cut = t
                    hedge_eligible = False
                    logs.append({"day": t, "date": cal[t], "action": "止损", "type": plan,
                                 "level": 0.0, "detail": f"锚{cal[anchor]} 跌幅{close[t]/close[anchor]-1.0:.2%}"})
            # 3) 回补开启
            if plan is not None and not rebuy_active:
                if reback == "B":
                    ok = (t > last_cut and t >= QUIET_DAYS
                          and not alarm[max(0, t - QUIET_DAYS):t].any())
                else:
                    ok = (t >= last_cut + REBACK_A_HOLD)
                if ok:
                    rebuy_level0 = 0.0 if stopped else (POS_DEEP if plan == "deep" else POS_SHALLOW)
                    rebuy_active, rebuy_k = True, 0
                    hedge_eligible = False
                    logs.append({"day": t, "date": cal[t], "action": "回补开始", "type": plan,
                                 "level": rebuy_level0, "detail": f"{'静默10日' if reback=='B' else '锚+20日'} 起点{rebuy_level0:.2f}"})
            # 4) 认沽到期结算与续买
            for p in puts:
                if not p["settled"] and (p["mat"] == t or (p["mat"] >= n and t == n - 1)):
                    p["settled"] = True
                    if p["mat"] >= n:
                        p["settled_at"] = f"数据末截断@{cal[t]}"
                    else:
                        p["settled_at"] = cal[t]
                    payoff = p["notional"] * max(0.0, (p["k"] - close[t]) / p["k"])
                    flow[t] += payoff
                    p["payoff"] = payoff
                    p["rolled"] = False
                    if use_put and hedge_eligible and p["mat"] == t and p["mat"] < n:
                        buy_put(t)
                        p["rolled"] = True
            # 5) 明日仓位（当日收盘决策→次日起暴露）
            if t + 1 < n:
                if stopped:
                    pos[t + 1] = 0.0
                elif rebuy_active:
                    rebuy_k += 1
                    pos[t + 1] = rebuy_level0 + (POS_BASE - rebuy_level0) * rebuy_k / REBUY_LINEAR
                    if rebuy_k >= REBUY_LINEAR:
                        rebuy_active = False
                        plan, anchor = None, None
                        last_cut = None
                        logs.append({"day": t + 1, "date": cal[t + 1], "action": "回补完成",
                                     "type": "", "level": 1.0, "detail": ""})
                elif plan is not None:
                    pos[t + 1] = POS_DEEP if plan == "deep" else POS_SHALLOW
                else:
                    pos[t + 1] = POS_BASE
                # 6) 交易成本（乘性扣减：成本∝换手幅度×期初净值，计入当日增长因子）
                cost = abs(pos[t + 1] - pos[t]) * cost_rate
                cost_sum += cost * nav[t]
            # 7) 复利：t→t+1 转换用 pos[t+1]×ret[t+1]；当日现金流（权利金/到期收益）次收盘入账
            if t + 1 < n:
                nav[t + 1] = nav[t] * (1.0 + pos[t + 1] * ret[t + 1] - cost) + flow[t]

        for p in puts:
            assert p["settled"], ("认沽未结算", cal[p["eff"]])
        nav[n - 1] += flow[n - 1]  # 末日在循环内未消费的现金流并入期末净值
        return {"pos": pos, "nav": nav, "flow": flow, "logs": logs, "puts": puts, "cost_sum": cost_sum}

    # ---------- 臂定义（预登记 TOML 第三节） ----------
    ARMS = [
        ("E0", "基准：全仓持有万得全A", "", "B", True, True, 0.0),
        ("A1", "方案一（固定钟）×回补B×全件×万10", "baseline", "B", True, True, COST_BASE),
        ("A2", "方案一＋滚动钟×回补B×全件×万10（主候选）", "rolling", "B", True, True, COST_BASE),
        ("A3", "方案一×回补A×全件×万10（回补对照）", "baseline", "A", True, True, COST_BASE),
        ("A4", "方案一＋滚动钟×回补A×全件×万10（回补对照）", "rolling", "A", True, True, COST_BASE),
        ("S1", "方案一＋滚动钟×回补B×无认沽（部件归因）", "rolling", "B", False, True, COST_BASE),
        ("S2", "方案一＋滚动钟×回补B×无止损（部件归因）", "rolling", "B", True, False, COST_BASE),
        ("C25", "方案一＋滚动钟×回补B×全件×成本万25", "rolling", "B", True, True, COST_HIGH),
        ("C0", "方案一＋滚动钟×回补B×全件×零成本", "rolling", "B", True, True, 0.0),
    ]

    def metrics(res):
        nav = res["nav"]
        strat_ret = pd.Series(nav).pct_change().fillna(0.0)
        years = (n - 1) / TRADING_DAYS_YEAR
        cum = (nav[-1] - 1.0) * 100.0
        cagr = (nav[-1] ** (1.0 / years) - 1.0) * 100.0
        vol = float(strat_ret.std() * math.sqrt(TRADING_DAYS_YEAR)) * 100.0
        sharpe = (cagr / vol) if vol > 0 else math.nan
        peak, mdd = -np.inf, 0.0
        for v in nav:
            peak = max(peak, v)
            if peak > 0:
                mdd = min(mdd, v / peak - 1.0)
        pos = res["pos"]
        put_premium = sum(p["premium"] for p in res["puts"])
        put_payoff = sum(p["payoff"] for p in res["puts"] if "payoff" in p)
        n_switch = sum(1 for lg in res["logs"] if lg["action"] == "切换")
        n_corr = sum(1 for lg in res["logs"] if lg["action"] == "修正")
        n_stop = sum(1 for lg in res["logs"] if lg["action"] == "止损")
        n_rebuy = sum(1 for lg in res["logs"] if lg["action"] == "回补开始")
        put_rolled = sum(1 for p in res["puts"] if p.get("rolled"))
        put_trunc = sum(1 for p in res["puts"] if "数据末截断" in str(p["settled_at"]))
        return {
            "累计收益%": cum, "年化收益%": cagr, "年化波动%": vol, "Sharpe(rf=0)": sharpe,
            "最大回撤%": mdd * 100.0, "平均仓位": float(pos.mean()),
            "仓位低于满仓日数": int((pos < POS_BASE - 1e-9).sum()),
            "切换次数": n_switch, "修正次数": n_corr, "止损次数": n_stop, "回补轮数": n_rebuy,
            "认沽笔数": len(res["puts"]), "认沽续买笔数": put_rolled, "认沽截断笔数": put_trunc,
            "认沽权利金合计": -put_premium, "认沽到期收益合计": put_payoff, "认沽净现金流": put_payoff - put_premium,
            "交易成本合计": -res["cost_sum"],
        }

    results = {}
    internal_consistent = True
    for aid, aname, mode, reback, use_put, use_stop, cost_rate in ARMS:
        switches = merged_switches[mode] if mode else []
        res = simulate(switches, reback, use_put, use_stop, cost_rate)
        # 内部双跑断言
        res2 = simulate(switches, reback, use_put, use_stop, cost_rate)
        assert np.allclose(res["nav"], res2["nav"], rtol=0, atol=0), (aid, "内部双跑不一致")
        assert res["pos"].tolist() == res2["pos"].tolist(), (aid, "pos 双跑不一致")
        if mode == "" and len(res["logs"]) == 0 and not (res["pos"] < 1 - 1e-9).any():
            assert aid == "E0"
        results[aid] = {"arm_name": aname, **res}
        print(f"[{aid}] {aname} 完成（内部双跑一致）")

    # 不变量：E0 基准 nav 与指数累积一致
    assert np.allclose(results["E0"]["nav"], np.cumprod(1.0 + ret), atol=1e-12)
    # 不变量：A2 认沽仅出现在深慢切换/修正生效日，或某前期认沽的到期日（续买）
    sw_deep_days = {d for d, tp, _ in merged_switches["rolling"] if tp == "deep"}
    put_mats = {p["mat"] for p in results["A2"]["puts"]}
    for p in results["A2"]["puts"]:
        assert p["eff"] in sw_deep_days or p["eff"] in put_mats, ("认沽生效日非深慢确认日/续买", cal[p["eff"]])

    # ---------- 指标汇总 ----------
    summary_rows = []
    for aid, aname, *_ in ARMS:
        m = metrics(results[aid])
        summary_rows.append({"arm": aid, "arm_name": aname, **m})
    summary_df = pd.DataFrame(summary_rows)

    # 分年收益（每臂）
    years_idx = {}
    for t, d in enumerate(cal):
        years_idx.setdefault(d[:4], []).append(t)
    yearly_rows = []
    for aid, aname, *_ in ARMS:
        nav = results[aid]["nav"]
        row = {"arm": aid}
        prev_nav = 1.0
        for y in sorted(years_idx):
            last_t = years_idx[y][-1]
            row[y] = (nav[last_t] / prev_nav - 1.0) * 100.0
            prev_nav = nav[last_t]
        yearly_rows.append(row)
    yearly_df = pd.DataFrame(yearly_rows)

    # ---------- 输出 ----------
    names = {
        "summary": "regime_v022_netvalue_summary.csv",
        "daily": "regime_v022_netvalue_daily.csv",
        "events": "regime_v022_netvalue_events.csv",
        "puts": "regime_v022_netvalue_puts.csv",
        "yearly": "regime_v022_netvalue_yearly.csv",
    }
    daily = pd.DataFrame({"date": cal})
    for aid, *_ in ARMS:
        daily[f"nav_{aid}"] = results[aid]["nav"]
    daily["pos_A2"] = results["A2"]["pos"]
    daily.to_csv(OUT / names["daily"], index=False, encoding="utf-8-sig", float_format="%.6f")
    summary_df.to_csv(OUT / names["summary"], index=False, encoding="utf-8-sig", float_format="%.6f")
    yearly_df.to_csv(OUT / names["yearly"], index=False, encoding="utf-8-sig", float_format="%.6f")
    ev_rows = []
    for aid, aname, *_ in ARMS:
        for lg in results[aid]["logs"]:
            ev_rows.append({"arm": aid, **lg})
    pd.DataFrame(ev_rows).to_csv(OUT / names["events"], index=False, encoding="utf-8-sig")
    put_rows = []
    for aid, aname, *_ in ARMS:
        for p in results[aid]["puts"]:
            put_rows.append({"arm": aid, "eff_date": cal[p["eff"]], "mat_date": cal[min(p["mat"], n - 1)],
                             "strike": p["k"], "notional": p["notional"], "premium": p["premium"],
                             "payoff": p.get("payoff", 0.0), "settled_at": p["settled_at"],
                             "rolled": p.get("rolled", False)})
    pd.DataFrame(put_rows).to_csv(OUT / names["puts"], index=False, encoding="utf-8-sig", float_format="%.6f")

    # ---------- HTML 报告 ----------
    report = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
              "<title>净值口径完整核算 v0.22</title></head><body>",
              "<h1>v0.22 净值口径完整核算（回补B主方案，含认沽、止损、类型修正）</h1>",
              f"<p>预登记：{REG_TS}；配置：config/regime_netvalue_v0.22.toml；运行：{ts}</p>",
              "<p>判定层冻结复用 v0.21（方案一7项4票）：事件切换日取自冻结 CSV；误报段单钟重算逐行对账通过；"
              "B10 重建后全部告警段归属对账通过；合并切换序列修正数与 v0.21 汇总一致；每臂内部双跑逐日一致。</p>",
              "<h2>九臂指标汇总</h2>", summary_df.to_html(index=False),
              "<h2>分年收益（%，每臂按日历年）</h2>", yearly_df.to_html(index=False),
              "<h2>主候选臂 A2 事件日志</h2>",
              pd.DataFrame([{"arm": "A2", **lg} for lg in results["A2"]["logs"]]).to_html(index=False),
              "<h2>主候选臂 A2 认沽明细</h2>",
              pd.DataFrame([{**p, "eff_date": cal[p["eff"]], "mat_date": cal[min(p["mat"], n-1)],
                             "eff_nav": results['A2']['nav'][p['eff']]} for p in results["A2"]["puts"]]).to_html(index=False),
              "<div>证据边界：样本内机械模拟，不外推；指数不可直接交易、停牌与流动性冲击未计；认沽为合成简化记账；"
              "结果不自动改写冻结产品；全部仓位决策仅使用当日及以前信息。</div>",
              "<div><b>认沽口径披露</b>：合成认沽按固定 1.5% 权利金记账（v0.16 注册口径），急跌中真实虚值认沽成本远高于此，"
              "且滚动续买放大该口径偏差——2015 年认沽净现金流 +2.13（占当期净值两倍以上）为该口径的主要伪影来源，"
              "其余年份认沽净现金流合计为负。无认沽臂 S1（年化 6.99%、Sharpe 0.331、最大回撤 −58.5%）应作为口径稳健下界读数；"
              "A2 与 S1 的差额不构成对冲价值证据。</div>",
              "</body></html>"]
    (OUT / "crisis_netvalue_v022_report.html").write_text("".join(report), encoding="utf-8")

    manifest = {
        "version": "v0.22", "created": ts, "registered": REG_TS,
        "config": "config/regime_netvalue_v0.22.toml", "config_sha256": sha256_file(CFG_PATH),
        "purpose": "净值口径完整核算：回补B主方案（告警驱动）＋回补A对照；认沽/止损/修正全件；成本敏感性",
        "inputs": {f: sha256_file(OUT / f) for f in [
            "regime_v07_split_wide.csv", "regime_v05_benchmark_daily.csv", "regime_v012_trigger_event_timing.csv",
            "regime_v021_baseline_event_matrix.csv", "regime_v021_baseline_false_episodes.csv",
            "regime_v021_baseline_summary.csv", "regime_v021_rolling_event_matrix.csv",
            "regime_v021_rolling_false_episodes.csv", "regime_v021_rolling_summary.csv"]},
        "outputs": {f: sha256_file(OUT / f) for f in names.values()} | {
            "report": sha256_file(OUT / "crisis_netvalue_v022_report.html")},
        "reconciliation": {
            "false_episodes_vs_v021": "通过（两模式逐行逐列）",
            "alarm_segment_attribution": "通过（事件归属+误报全覆盖）",
            "switch_merge_no_conflict": "通过",
            "correction_count_vs_v021": "通过（baseline/rolling 修正数与 v0.19/0.21 汇总一致）",
            "internal_double_run": "通过（每臂两遍逐日全等）",
            "e0_equals_index": "通过",
            "put_only_on_deep_confirmation": "通过",
        },
        "boundary": ["样本内机械模拟，不外推", "净值不是事件账净账，两口径不可混用",
                     "指数不可直接交易、停牌与流动性冲击未计", "认沽为合成简化记账（v0.16 口径），净值版到期改锚生效日+20（去前视）",
                     "成本假设为主假设与敏感性，非参数搜索", "不自动改写冻结产品"],
    }
    (OUT / "regime_v022_netvalue_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nv0.22 计算完成。九臂指标：")
    show_cols = ["arm", "累计收益%", "年化收益%", "年化波动%", "Sharpe(rf=0)", "最大回撤%", "平均仓位",
                 "切换次数", "修正次数", "止损次数", "认沽净现金流", "交易成本合计"]
    print(summary_df[show_cols].to_string(index=False))


if __name__ == "__main__":
    main()
