#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.17 产品栈条件下的拓扑条件增量检验（先登记后计算）
预登记：config/regime_topology_increment_v0.17.toml（2026-11-14T21:52:26+08:00）

层一：警报态条件下 11 个拓扑特征的条件判别（真假警报）与票箱之上的增量面积，并排老标准裸面积。
层二：三臂账本——控制臂 C0（v0.16 选定组合逐字）＋实验臂甲（票箱扩容）＋实验臂乙（拓扑平静撤销）。
只按预登记组合与检验，不反选、不外推、不重判。无随机判定、随机数只进自助（种子 20261114），
验收 = 双跑字节一致 + 控制臂/裸面积双对账。
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def rankdata_avg(a):
    """平均秩（平局取均值），与 scipy.stats.rankdata 默认语义一致；纯 numpy 实现。"""
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    sorted_a = a[order]
    i = 0
    n_a = len(a)
    while i < n_a:
        j = i
        while j + 1 < n_a and sorted_a[j + 1] == sorted_a[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        ranks[order[i:j + 1]] = avg_rank
        i = j + 1
    return ranks

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
CFG_PATH = ROOT / "config" / "regime_topology_increment_v0.17.toml"
REG_TS = "2026-11-14T21:52:26+08:00"

# ---- v0.15 信号块参数（冻结）----
PRE_DAYS = 20
POST_DAYS = 20
ROLL_PCT = 756
MIN_VOL_OBS = 250
MIN_TOPO_OBS = 120
TRADING_DAYS_YEAR = 250

# ---- v0.12 引擎参数（冻结）----
BASELINE_WINDOW = 10
BASELINE_MIN_NONNULL = 8
CURRENT_MIN_FRAC = 0.8
HIST_WINDOW = 756
HIST_MIN_OBS = 120
EXTREME_PCT = 0.85
JUDGMENT_START = 1
JUDGMENT_END = 20
CONFIRM_DAYS = 2
CRISIS_SCORE_MIN_N = 4          # 7 件口径整数门槛（等价 4/7）
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

CATCH_START = -20
FALSE_HOLD_DAYS = 20

CRISIS_FEATURES_7 = [
    ("a16_avg_pair_corr", +1),
    ("a16_leading_eig_share", +1),
    ("b_industry_average_correlation", +1),
    ("b_h2_count", -1),
    ("b_h1_count", -1),
    ("b_h2_landscape_l1", -1),
    ("b_xy_h0_death_mean", -1),
]
CRISIS_FEATURES_10 = CRISIS_FEATURES_7 + [
    ("a16_W_t", +1),
    ("a16_h0_death_mean", +1),
    ("a16_h1_count", -1),
]
TYPE_FEATURES = [
    ("a16_window_rms", +1),
    ("a16_avg_pair_corr", +1),
    ("b_xy_h0_death_mean", -1),
]

# ---- 层一：v0.9 冻结 11 特征（名称、中文、冻结方向）----
FEATURES_11 = [
    ("a16_W_t", "状态点云相邻日持续图距离", +1),
    ("a16_h0_death_mean", "状态点云零维死亡值均值", +1),
    ("a16_h1_count", "状态点云一维环数量", -1),
    ("a16_window_rms", "状态点云窗口均方根", +1),
    ("a16_avg_pair_corr", "状态点云平均两两相关", +1),
    ("a16_leading_eig_share", "状态点云第一特征值占比", +1),
    ("b_h2_count", "相关网络二维空腔数量", -1),
    ("b_h1_count", "相关网络一维环数量", -1),
    ("b_h2_landscape_l1", "相关网络二维景观范数", -1),
    ("b_industry_average_correlation", "相关网络平均相关", +1),
    ("b_xy_h0_death_mean", "相关网络零维死亡值均值", -1),
]

BOOT_B = 2000
BOOT_SEED = 20261114
BLOCK = 20
EARLY_LO, EARLY_HI = -20, 5          # 早期决策窗 [起点−20, 起点+5]
PROX_LO, PROX_HI = -10, -1           # v0.9 邻近日 [−10,−1]
Q1_RULE_AUC = 0.60


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def auc_mw(x, y):
    """曼-惠特尼曲线下面积 P(X>Y)（平局减半）；与 v0.9 同一实现。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    x = x[~np.isnan(x)]
    y = y[~np.isnan(y)]
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return math.nan
    allv = np.concatenate([x, y])
    ranks = rankdata_avg(allv)
    r1 = ranks[:n1].sum()
    return (r1 - n1 * (n1 + 1) / 2.0) / (n1 * n2)


def bh_qvals(pvals):
    """BH-FDR 校正标注。"""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    q = np.empty(m)
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        val = min(prev, p[i] * m / rank)
        q[i] = val
        prev = val
    return q


def zscore(v):
    v = np.asarray(v, dtype=float)
    sd = v.std(ddof=0)
    if sd <= 0 or not np.isfinite(sd):
        return np.zeros_like(v)
    return (v - v.mean()) / sd


def pooled_z(x, y):
    """双类合并标准化（样本内均值标准差）；预登记口径。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    allv = np.concatenate([x, y])
    mu = allv.mean()
    sd = allv.std(ddof=0)
    if sd <= 0 or not np.isfinite(sd):
        return np.zeros_like(x), np.zeros_like(y)
    return (x - mu) / sd, (y - mu) / sd


def comb_auc(vx, fx, vy, fy):
    """票箱分面积、等权合并分面积、增量（合并−票箱）；合并分用双类合并标准化。"""
    a_box = auc_mw(vx, vy)
    zvx, zvy = pooled_z(vx, vy)
    zfx, zfy = pooled_z(fx, fy)
    a_comb = auc_mw(zvx + zfx, zvy + zfy)
    return a_box, a_comb, a_comb - a_box


def main() -> None:
    ts = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

    # ---------- 输入（与 v0.16/v0.9 逐字同源）----------
    wide = pd.read_csv(OUT / "regime_v07_split_wide.csv", parse_dates=["date"])
    bench = pd.read_csv(OUT / "regime_v05_benchmark_daily.csv", parse_dates=["date"])
    tim0 = pd.read_csv(OUT / "regime_v012_trigger_event_timing.csv")
    v016_sum = pd.read_csv(OUT / "regime_v016_governed_pnl_summary.csv")
    v09_q1 = pd.read_csv(OUT / "regime_v09_q1_trigger.csv")

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

    feat_arr = {}
    for feat, _ in CRISIS_FEATURES_10 + TYPE_FEATURES:
        if feat not in feat_arr:
            feat_arr[feat] = w[feat].to_numpy(dtype=float)
    for key, _, _ in FEATURES_11:
        if key not in feat_arr:
            feat_arr[key] = w[key].to_numpy(dtype=float)

    # ---------- v0.15 信号块（逐字重建）----------
    r5 = ret_s.rolling(5).sum()
    vol20 = ret_s.rolling(20).std()
    vol_p70 = vol20.rolling(ROLL_PCT, min_periods=MIN_VOL_OBS).quantile(0.70)
    roll_max20 = pd.Series(close).rolling(20, min_periods=20).max()
    dd20 = (roll_max20 - close) / roll_max20

    S = {}
    S["D2"] = (r5 <= -0.04).to_numpy()
    S["V2"] = (vol20 > vol_p70).to_numpy()
    S["R1"] = (dd20 >= 0.05).to_numpy()
    raw_mask = ((S["D2"].astype(int) + S["V2"].astype(int) + S["R1"].astype(int)) >= 2)

    # ---------- 极端状态（v0.12 判定机逐字；7 件与 10 件两口径）----------
    def build_extreme(feats):
        extreme = {}
        for feat, direction in feats:
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
        count = np.zeros(n, dtype=int)
        for feat, _ in feats:
            count += extreme[feat].astype(int)
        return count

    ext7 = build_extreme(CRISIS_FEATURES_7)
    ext10 = build_extreme(CRISIS_FEATURES_10)

    # ---------- 45 事件（与 v0.16 同源）----------
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

    in_window_mask = np.zeros(n, dtype=bool)
    for evd in events:
        lo = max(0, evd["i0"] - PRE_DAYS)
        hi = min(n - 1, evd["i1"] + POST_DAYS)
        in_window_mask[lo:hi + 1] = True

    catch_lo_hi = []
    for evd in events:
        catch_lo_hi.append((max(0, evd["i0"] + CATCH_START), evd["i1"]))

    years = n / TRADING_DAYS_YEAR

    # ---------- v0.14 警报态状态机（逐字；乙规则 + 预登记规则丙）----------
    ma250 = pd.Series(close).rolling(250).mean().to_numpy(dtype=float)

    def govern(mask, rule, cooldown, ext_calm=None):
        alarm = np.zeros(n, dtype=bool)
        state_on = False
        quiet = 0
        cd_left = 0
        n_rec3 = 0
        n_quiet5 = 0
        n_topo3 = 0
        n_revoke = 0
        n_revoke_in_window = 0
        for i in range(n):
            hit = bool(mask[i])
            if not state_on:
                if cd_left > 0:
                    cd_left -= 1
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
                # 规则乙 + 预登记规则丙（ext_calm 给定时启用；纯静默兜底不变）
                if ext_calm is not None and quiet >= 3 and int(ext_calm[i]) == 0:
                    revoked = True
                    which = "topo3"
                if not revoked and quiet >= 5:
                    revoked = True
                    which = "quiet5"
            if revoked:
                state_on = False
                alarm[i] = False
                cd_left = cooldown
                n_revoke += 1
                if which == "rec3":
                    n_rec3 += 1
                elif which == "topo3":
                    n_topo3 += 1
                else:
                    n_quiet5 += 1
                if in_window_mask[i]:
                    n_revoke_in_window += 1
        return alarm, {
            "n_revoke": n_revoke, "n_rec3": n_rec3, "n_quiet5": n_quiet5,
            "n_topo3": n_topo3, "n_revoke_in_window": n_revoke_in_window,
        }

    alarm_c0, _ = govern(raw_mask, "B", 10)

    # ================================================================
    # 层一：条件判别与增量面积
    # ================================================================
    vote_score = ext7.astype(float) / float(len(CRISIS_FEATURES_7))

    # 样本索引：真警报早期日（归属起点最早者）/ 误报段日 / 常态日 / 邻近日
    events_by_onset = sorted(events, key=lambda x: (x["onset"], x["event_id"]))
    ev_of_day = np.full(n, -1, dtype=int)
    for pos, evd in enumerate(events_by_onset):
        lo = max(0, evd["i0"] + EARLY_LO)
        hi = min(n - 1, evd["i0"] + EARLY_HI)
        for d in range(lo, hi + 1):
            if ev_of_day[d] == -1:
                ev_of_day[d] = pos

    p_idx = np.array([d for d in range(n) if alarm_c0[d] and ev_of_day[d] != -1], dtype=int)
    p_cluster = np.array([int(ev_of_day[d]) for d in p_idx], dtype=int)

    # 误报段（v0.16 归属口径逐字）：连续警报段与任何归属窗不相交
    n_idx_list, n_cluster_list = [], []
    deep_alarm_days = []          # 归属段内但不属早期窗的警报日（描述性）
    seg_id = 0
    i = 0
    while i < n:
        if not alarm_c0[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and alarm_c0[j + 1]:
            j += 1
        attributed = False
        for (lo, hi) in catch_lo_hi:
            if not (j < lo or i > hi):
                attributed = True
                break
        if not attributed:
            for d in range(i, j + 1):
                n_idx_list.append(d)
                n_cluster_list.append(seg_id)
            seg_id += 1
        else:
            for d in range(i, j + 1):
                if ev_of_day[d] == -1:
                    deep_alarm_days.append(d)
        i = j + 1
    n_idx = np.array(n_idx_list, dtype=int)
    n_cluster = np.array(n_cluster_list, dtype=int)
    p_day_cluster = np.full(n, -1, dtype=int)
    for d, c in zip(p_idx, p_cluster):
        p_day_cluster[d] = c
    n_day_cluster = np.full(n, -1, dtype=int)
    for d, c in zip(n_idx, n_cluster):
        n_day_cluster[d] = c

    # 常态日（v0.9 逐字）
    crisis_in = pd.to_numeric(w["crisis_in"], errors="coerce").to_numpy(dtype=float)
    crisis_flag = np.nan_to_num(crisis_in, nan=0.0) > 0
    excl = np.zeros(n, dtype=bool)
    for evd in events:
        lo, hi = max(evd["i0"] - 20, 0), min(evd["i0"] + 31, n)
        excl[lo:hi] = True
    norm_idx = np.array([i2 for i2 in range(n) if (not crisis_flag[i2]) and (not excl[i2])], dtype=int)

    # 邻近日（v0.9 逐字）
    prox_event_idx = []
    for evd in events:
        lo = max(evd["i0"] + PROX_LO, 0)
        hi = evd["i0"] + PROX_HI + 1
        prox_event_idx.append(list(range(lo, hi)))
    prox_unique = np.array(sorted({i2 for idxs in prox_event_idx for i2 in idxs}), dtype=int)

    def pair_vals(fv, vs, idx):
        x = fv[idx]
        y = vs[idx]
        ok = np.isfinite(x) & np.isfinite(y)
        kept = idx[ok]
        return x[ok], y[ok], kept

    def boot_clusters(values_x, values_y, cl_x, cl_y, rng, extra=None, dirn=+1):
        """按簇重抽返回面积序列（及增量序列）。extra=(vote_x, vote_y) 时一并算增量；dirn=冻结方向。"""
        ux = np.unique(cl_x)
        uy = np.unique(cl_y)
        bx = {c: (values_x[cl_x == c], (extra[0][cl_x == c] if extra else None)) for c in ux}
        by = {c: (values_y[cl_y == c], (extra[1][cl_y == c] if extra else None)) for c in uy}
        out_auc = np.empty(BOOT_B)
        out_delta = np.empty(BOOT_B) if extra else None
        for b in range(BOOT_B):
            dx = rng.integers(0, len(ux), len(ux))
            dy = rng.integers(0, len(uy), len(uy))
            xs, ys, vxs, vys = [], [], [], []
            for t in dx:
                vx, vv = bx[ux[t]]
                if len(vx):
                    xs.append(vx)
                    if extra:
                        vxs.append(vv)
            for t in dy:
                vy, vv = by[uy[t]]
                if len(vy):
                    ys.append(vy)
                    if extra:
                        vys.append(vv)
            xb = np.concatenate(xs) if xs else np.array([])
            yb = np.concatenate(ys) if ys else np.array([])
            out_auc[b] = auc_mw(xb, yb)
            if extra:
                pvx = np.concatenate(vxs) if vxs else np.array([])
                pvy = np.concatenate(vys) if vys else np.array([])
                if len(xb) >= 2 and len(yb) >= 2:
                    out_delta[b] = comb_auc(
                        pvx, xb if dirn > 0 else -xb,
                        pvy, yb if dirn > 0 else -yb)[2]
                else:
                    out_delta[b] = math.nan
        return out_auc, out_delta

    def boot_blocks(values_x, values_y, cl_x, rng, extra=None, dirn=+1):
        """正类按事件簇重抽，负类按块重抽。用于真警报对常态。"""
        clusters = {}
        for c in np.unique(cl_x):
            m = cl_x == c
            clusters[c] = (values_x[m], (extra[0][m] if extra else None))
        u = np.unique(cl_x)
        nb = max(1, math.ceil(len(values_y) / BLOCK))
        out_auc = np.empty(BOOT_B)
        out_delta = np.empty(BOOT_B) if extra else None
        for b in range(BOOT_B):
            dx = rng.integers(0, len(u), len(u))
            xs, vxs = [], []
            for t in dx:
                vx, vv = clusters[u[t]]
                if len(vx):
                    xs.append(vx)
                    if extra:
                        vxs.append(vv)
            starts = rng.integers(0, max(len(values_y), 1), nb)
            ys, vys = [], []
            for s0 in starts:
                seg = values_y[s0:s0 + BLOCK]
                ys.append(seg)
                if extra:
                    vys.append(extra[1][s0:s0 + BLOCK])
            xb = np.concatenate(xs) if xs else np.array([])
            yb = np.concatenate([t for t in ys if len(t)]) if ys else np.array([])
            out_auc[b] = auc_mw(xb, yb)
            if extra:
                pvx = np.concatenate(vxs) if vxs else np.array([])
                pvy = np.concatenate([t for t in vys if len(t)]) if vys else np.array([])
                if len(xb) >= 2 and len(yb) >= 2:
                    out_delta[b] = comb_auc(
                        pvx, xb if dirn > 0 else -xb,
                        pvy, yb if dirn > 0 else -yb)[2]
                else:
                    out_delta[b] = math.nan
        return out_auc, out_delta

    def two_tail_p(boot, center):
        boot = boot[np.isfinite(boot)]
        if len(boot) == 0:
            return math.nan
        lo = float(np.mean(boot <= center))
        hi = float(np.mean(boot >= center))
        return min(1.0, 2.0 * min(lo, hi))

    rng = np.random.default_rng(BOOT_SEED)
    layer1_rows = []
    primary_p_dir, primary_p_delta = [], []

    for key, cn, dir_frozen in FEATURES_11:
        fv = feat_arr[key]

        # --- 参照列：老标准裸面积（v0.9 逐字重算）---
        x_p = fv[prox_unique]
        ok_p = x_p[~np.isnan(x_p)]
        x_n = fv[norm_idx]
        ok_n = x_n[~np.isnan(x_n)]
        bare_auc = auc_mw(ok_p, ok_n)
        bare_star = max(bare_auc, 1 - bare_auc) if not math.isnan(bare_auc) else math.nan
        bare_dir = "升" if bare_auc > 0.5 else "降"
        ref = v09_q1[v09_q1["feature"] == key].iloc[0]
        assert abs(bare_auc - float(ref["auc"])) <= 1e-4, (key, bare_auc, ref["auc"])
        assert abs(bare_star - float(ref["auc_star"])) <= 1e-4, (key, bare_star, ref["auc_star"])

        # --- 主对比：真警报早期日 对 假警报日 ---
        xp, vpx, kept_p = pair_vals(fv, vote_score, p_idx)
        yn, vpn, kept_n = pair_vals(fv, vote_score, n_idx)
        raw = auc_mw(xp, yn)
        star = max(raw, 1 - raw) if not math.isnan(raw) else math.nan
        dir_obs = "升" if raw > 0.5 else "降"
        dir_frozen_cn = "升" if dir_frozen > 0 else "降"
        consist = "一致" if dir_obs == dir_frozen_cn else "相反"
        # 定向面积（冻结方向取向）
        directed = raw if dir_frozen > 0 else (1 - raw if not math.isnan(raw) else math.nan)
        # 增量面积（合并分按双类合并标准化）
        auc_box, auc_comb, delta = comb_auc(
            vpx, xp if dir_frozen > 0 else -xp,
            vpn, yn if dir_frozen > 0 else -yn)
        boot_auc, boot_delta = boot_clusters(
            xp, yn, p_day_cluster[kept_p], n_day_cluster[kept_n],
            rng, extra=(vpx, vpn), dirn=dir_frozen)
        ci_lo, ci_hi = (float(np.nanpercentile(boot_auc, 2.5)),
                        float(np.nanpercentile(boot_auc, 97.5)))
        dci_lo, dci_hi = (float(np.nanpercentile(boot_delta, 2.5)),
                          float(np.nanpercentile(boot_delta, 97.5)))
        p_dir = two_tail_p(boot_auc if dir_frozen > 0 else (1 - boot_auc), 0.5)
        p_del = two_tail_p(boot_delta, 0.0)
        primary_p_dir.append(p_dir)
        primary_p_delta.append(p_del)
        verdict_cond = "条件判别成立" if (star >= Q1_RULE_AUC and not (ci_lo <= 0.5 <= ci_hi)) else "无条件判别"
        verdict_delta = "票箱之上有增量" if (not math.isnan(dci_lo) and dci_lo > 0) else "无增量"

        layer1_rows.append({
            "contrast": "主对比·真警报对假警报", "feature": key, "feature_cn": cn,
            "frozen_direction": dir_frozen_cn, "n_pos": int(len(xp)), "n_neg": int(len(yn)),
            "auc_raw": round(raw, 4), "auc_star": round(star, 4),
            "directed_auc": round(directed, 4), "direction_observed": dir_obs,
            "direction_consistency": consist,
            "median_diff": round(float(np.median(xp) - np.median(yn)), 6) if len(xp) and len(yn) else math.nan,
            "mean_diff": round(float(xp.mean() - yn.mean()), 6) if len(xp) and len(yn) else math.nan,
            "ci_low": round(ci_lo, 4), "ci_high": round(ci_hi, 4),
            "auc_box": round(auc_box, 4), "auc_combined": round(auc_comb, 4),
            "delta_auc": round(delta, 4), "delta_ci_low": round(dci_lo, 4),
            "delta_ci_high": round(dci_hi, 4),
            "p_directed": round(p_dir, 4), "p_delta": round(p_del, 4),
            "verdict_cond": verdict_cond, "verdict_delta": verdict_delta,
        })

        # --- 次对比：真警报早期日 对 常态日 ---
        xpn, vpn2, kept_p2 = pair_vals(fv, vote_score, p_idx)
        ynn, vnn, _ = pair_vals(fv, vote_score, norm_idx)
        raw2 = auc_mw(xpn, ynn)
        star2 = max(raw2, 1 - raw2) if not math.isnan(raw2) else math.nan
        auc_box2, auc_comb2, delta2 = comb_auc(
            vpn2, xpn if dir_frozen > 0 else -xpn,
            vnn, ynn if dir_frozen > 0 else -ynn)
        boot_auc2, boot_delta2 = boot_blocks(xpn, ynn, p_day_cluster[kept_p2], rng, extra=(vpn2, vnn), dirn=dir_frozen)
        ci2_lo, ci2_hi = (float(np.nanpercentile(boot_auc2, 2.5)),
                          float(np.nanpercentile(boot_auc2, 97.5)))
        dci2_lo, dci2_hi = (float(np.nanpercentile(boot_delta2, 2.5)),
                            float(np.nanpercentile(boot_delta2, 97.5)))
        layer1_rows.append({
            "contrast": "次对比·真警报对常态", "feature": key, "feature_cn": cn,
            "frozen_direction": dir_frozen_cn, "n_pos": int(len(xpn)), "n_neg": int(len(ynn)),
            "auc_raw": round(raw2, 4), "auc_star": round(star2, 4),
            "directed_auc": round(raw2 if dir_frozen > 0 else 1 - raw2, 4),
            "direction_observed": "升" if raw2 > 0.5 else "降",
            "direction_consistency": "一致" if (("升" if raw2 > 0.5 else "降") == dir_frozen_cn) else "相反",
            "median_diff": round(float(np.median(xpn) - np.median(ynn)), 6) if len(xpn) and len(ynn) else math.nan,
            "mean_diff": round(float(xpn.mean() - ynn.mean()), 6) if len(xpn) and len(ynn) else math.nan,
            "ci_low": round(ci2_lo, 4), "ci_high": round(ci2_hi, 4),
            "auc_box": round(auc_box2, 4),
            "auc_combined": round(auc_comb2, 4),
            "delta_auc": round(delta2, 4), "delta_ci_low": round(dci2_lo, 4),
            "delta_ci_high": round(dci2_hi, 4),
            "p_directed": round(two_tail_p(boot_auc2 if dir_frozen > 0 else (1 - boot_auc2), 0.5), 4),
            "p_delta": round(two_tail_p(boot_delta2, 0.0), 4),
            "verdict_cond": "条件判别成立" if (star2 >= Q1_RULE_AUC and not (ci2_lo <= 0.5 <= ci2_hi)) else "无条件判别",
            "verdict_delta": "票箱之上有增量" if (not math.isnan(dci2_lo) and dci2_lo > 0) else "无增量",
        })

        # --- 参照列：老标准（只点估计）---
        layer1_rows.append({
            "contrast": "参照·老标准邻近对常态", "feature": key, "feature_cn": cn,
            "frozen_direction": dir_frozen_cn,
            "n_pos": int(len(ok_p)), "n_neg": int(len(ok_n)),
            "auc_raw": round(bare_auc, 4), "auc_star": round(bare_star, 4),
            "directed_auc": round(bare_auc if dir_frozen > 0 else 1 - bare_auc, 4),
            "direction_observed": bare_dir,
            "direction_consistency": "一致" if bare_dir == dir_frozen_cn else "相反",
            "median_diff": round(float(np.median(ok_p) - np.median(ok_n)), 6),
            "mean_diff": round(float(ok_p.mean() - ok_n.mean()), 6),
            "ci_low": float(ref["auc_ci_low"]), "ci_high": float(ref["auc_ci_high"]),
            "auc_box": "", "auc_combined": "", "delta_auc": "",
            "delta_ci_low": "", "delta_ci_high": "",
            "p_directed": "", "p_delta": "",
            "verdict_cond": str(ref["verdict"]), "verdict_delta": "—",
        })

    # 票箱分自身两行（主、次对比基线）
    for contrast, idx_p_, idx_n_ in (
            ("主对比·真警报对假警报", p_idx, n_idx),
            ("次对比·真警报对常态", p_idx, norm_idx)):
        vs_p = vote_score[idx_p_]
        vs_n = vote_score[idx_n_]
        a = auc_mw(vs_p, vs_n)
        layer1_rows.append({
            "contrast": contrast, "feature": "__vote_box_score__", "feature_cn": "票箱分（危机确认分）",
            "frozen_direction": "升", "n_pos": int(len(vs_p)), "n_neg": int(len(vs_n)),
            "auc_raw": round(a, 4), "auc_star": round(max(a, 1 - a), 4),
            "directed_auc": round(a, 4), "direction_observed": "升" if a > 0.5 else "降",
            "direction_consistency": "—",
            "median_diff": round(float(np.median(vs_p) - np.median(vs_n)), 6),
            "mean_diff": round(float(vs_p.mean() - vs_n.mean()), 6),
            "ci_low": "", "ci_high": "", "auc_box": round(a, 4),
            "auc_combined": "", "delta_auc": 0.0, "delta_ci_low": "", "delta_ci_high": "",
            "p_directed": "", "p_delta": "", "verdict_cond": "（基线）", "verdict_delta": "（基线）",
        })

    # BH 标注（只主对比 11 特征）
    q_dir = bh_qvals(primary_p_dir)
    q_del = bh_qvals(primary_p_delta)
    k = 0
    for row in layer1_rows:
        if row["contrast"] == "主对比·真警报对假警报" and row["feature"] != "__vote_box_score__":
            row["q_directed"] = round(float(q_dir[k]), 4)
            row["q_delta"] = round(float(q_del[k]), 4)
            k += 1
        else:
            row["q_directed"] = ""
            row["q_delta"] = ""

    l1 = pd.DataFrame(layer1_rows)

    # 深层警报日描述（防平凡分离披露）
    deep_desc = {}
    if deep_alarm_days:
        deep_idx = np.array(deep_alarm_days, dtype=int)
        for key, cn, _ in FEATURES_11:
            v = feat_arr[key][deep_idx]
            v = v[np.isfinite(v)]
            deep_desc[key] = float(np.median(v)) if len(v) else math.nan

    # ================================================================
    # 层二：三臂账本（v0.12 引擎逐字）
    # ================================================================
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

    def run_judgment(i0, e_off, eligibility=True, ext_count=None, n_box=7):
        """逐日判定 + 切换/纠错（v0.12 逐字；分数门槛统一为计数×7 ≥ 4×箱内件数）。"""
        judgments, scores, score_ns, votes_map = {}, {}, {}, {}
        for k in range(JUDGMENT_START, JUDGMENT_END + 1):
            j = i0 + k
            if j >= n:
                break
            votes, valid_names = [], []
            for feat, sgn in TYPE_FEATURES:
                s = feat_arr[feat]
                blo = max(0, i0 - BASELINE_WINDOW)
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
            score_ns[k] = int(ext_count[i0 + k])
            scores[k] = score_ns[k] / float(n_box)
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
                        and score_ns.get(k, 0) * 7 >= CRISIS_SCORE_MIN_N * n_box
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
                        and score_ns.get(k, 0) * 7 >= CRISIS_SCORE_MIN_N * n_box
                        and elig):
                    cur_plan = judgments[k]
                    corrections_used += 1
                    switch_offsets.append(k)
                    last_switch_k = k
        judged_type = first_type if switched else "无法判定"
        return judgments, scores, score_ns, votes_map, judged_type, switch_offsets, corrections_used, cur_plan

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

    ARMS = [
        ("C0", "控制臂（冻结合体）", ext7, 7, None),
        ("C1", "实验臂甲（票箱扩容）", ext10, 10, None),
        ("C2", "实验臂乙（拓扑平静撤销）", ext7, 7, ext7),
    ]

    arm_rows = []
    matrix_rows = []
    false_records = {a[0]: [] for a in ARMS}

    for aid, aname, ext_count, n_box, ext_calm in ARMS:
        # 控制臂与实验臂甲的警报掩码同为 B10（只动判定箱）；实验臂乙加规则丙
        alarm, st = govern(raw_mask, "B", 10, ext_calm=ext_calm)

        tiers = {"提前": 0, "窗内": 0, "损伤窗": 0, "漏": 0}
        for evd in events:
            h = first_hit_ident(alarm, evd)
            raw_h = first_hit_ident(raw_mask, evd)
            raw_off = (raw_h - evd["i0"]) if raw_h is not None else ""
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
                gov_off = off
                delay = (off - raw_off) if raw_off != "" else ""

            row_base = {
                "arm": aid, "arm_name": aname,
                "event_id": evd["event_id"], "onset": evd["onset"],
                "event_end": evd["event_end"], "event_len": evd["event_len"],
                "true_type": evd["true_type"],
                "segment": "前段" if evd["onset"] < "2015-01-01" else "后段",
                "raw_first_offset": raw_off,
                "gov_first_offset": gov_off, "tier": ident_tier,
                "delay_vs_raw": delay,
            }

            if fire_idx is None:
                matrix_rows.append({**row_base,
                    "trigger_date": "", "trigger_offset": "",
                    "caught_in_catch": "否（未触发）",
                    "judged_type": "未触发", "final_plan_type": "未切换",
                    "first_confirm_offset": "", "switch_offs_p4": "",
                    "corrections_p4": 0,
                    "stop_p4": "", "p3_full": "", "p4_full": "",
                    "diff_p1_p3": 0.0, "diff_p4_p3": 0.0,
                    "diff_p1_p2": 0.0, "diff_p1_p4": 0.0,
                    "p1_full": "", "p2_full": ""})
                continue

            f = fire_idx
            e_off = evd["i1"] - f
            T_off = evd["i1"] + REENTRY_DAYS - f
            assert T_off + f < n, (evd["event_id"], cal[f])
            if e_off < 0:
                matrix_rows.append({**row_base,
                    "trigger_date": cal[f], "trigger_offset": fire_off,
                    "caught_in_catch": "否（触发晚于事件结束）",
                    "judged_type": "未触发", "final_plan_type": "未切换",
                    "first_confirm_offset": "", "switch_offs_p4": "",
                    "corrections_p4": 0,
                    "stop_p4": "", "p3_full": "", "p4_full": "",
                    "diff_p1_p3": 0.0, "diff_p4_p3": 0.0,
                    "diff_p1_p2": 0.0, "diff_p1_p4": 0.0,
                    "p1_full": "", "p2_full": ""})
                continue

            (judgments, scores, score_ns, votes_map, judged_type,
             switch_offsets, corrections_used, cur_plan) = run_judgment(
                f, e_off, ext_count=ext_count, n_box=n_box)

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

            m1 = metrics(f, T_off, e_off, pos1, put1)
            m2 = metrics(f, T_off, e_off, pos2, put2)
            m3 = metrics(f, T_off, e_off, p3_pos, [])
            m4 = metrics(f, T_off, e_off, pos4, put4)

            matrix_rows.append({**row_base,
                "trigger_date": cal[f], "trigger_offset": fire_off,
                "caught_in_catch": "是",
                "judged_type": judged_type,
                "final_plan_type": cur_plan if switch_offsets else "未切换",
                "first_confirm_offset": switch_offsets[0] if switch_offsets else "",
                "switch_offs_p4": "；".join(str(x) for x in switch_offsets),
                "corrections_p4": corrections_used,
                "stop_p4": stop4 if stop4 is not None else "",
                "p1_full": m1["full_cum"], "p2_full": m2["full_cum"],
                "p3_full": m3["full_cum"], "p4_full": m4["full_cum"],
                "diff_p1_p3": m1["full_cum"] - m3["full_cum"],
                "diff_p4_p3": m4["full_cum"] - m3["full_cum"],
                "diff_p1_p2": m1["full_cum"] - m2["full_cum"],
                "diff_p1_p4": m1["full_cum"] - m4["full_cum"],
            })

        # 误报段（v0.16 账本口径逐字）
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
                    false_records[aid].append({
                        "episode_start": cal[g], "episode_end": cal[j],
                        "episode_len": j - i + 1, "status": "随访不足跳过",
                        "judged_type": "", "diff_p4_p3": "",
                    })
                else:
                    e_off_p = FALSE_HOLD_DAYS
                    T_off_p = FALSE_HOLD_DAYS + REENTRY_DAYS
                    (judgments, scores, score_ns, votes_map, judged_type,
                     switch_offsets, corrections_used, cur_plan) = run_judgment(
                        g, e_off_p, eligibility=False, ext_count=ext_count, n_box=n_box)
                    p4_switch = [(off, "deep" if judgments[off] == "深慢" else "shallow")
                                 for off in switch_offsets]
                    pos4, _, put4 = build_positions(g, T_off_p, e_off_p, p4_switch)
                    p3_pos = np.full(T_off_p + 1, POS_BASE)
                    m4 = metrics(g, T_off_p, e_off_p, pos4, put4)
                    m3 = metrics(g, T_off_p, e_off_p, p3_pos, [])
                    false_records[aid].append({
                        "episode_start": cal[g], "episode_end": cal[j],
                        "episode_len": j - i + 1, "status": "已评估",
                        "judged_type": judged_type,
                        "diff_p4_p3": m4["full_cum"] - m3["full_cum"],
                    })
            i = j + 1

        # 汇总
        mat_v = pd.DataFrame([r for r in matrix_rows if r["arm"] == aid])
        for c in ("diff_p1_p3", "diff_p4_p3", "diff_p1_p2", "diff_p1_p4"):
            mat_v[c] = pd.to_numeric(mat_v[c])
        caught = mat_v[mat_v["caught_in_catch"] == "是"].copy()
        trig_offs = pd.to_numeric(caught["trigger_offset"], errors="coerce")
        fm = pd.DataFrame([r for r in false_records[aid] if r["status"] == "已评估"])
        if len(fm):
            fm["diff_p4_p3"] = pd.to_numeric(fm["diff_p4_p3"])
            false_total = float(fm["diff_p4_p3"].sum())
            false_median = float(fm["diff_p4_p3"].median())
            false_activated = int((fm["judged_type"] != "无法判定").sum())
        else:
            false_total = 0.0
            false_median = math.nan
            false_activated = 0
        n_false = len(false_records[aid])
        switched = mat_v[mat_v["judged_type"].isin(["深慢", "浅快"])]
        e2e_total = float(mat_v["diff_p4_p3"].sum())
        e2e_p1_total = float(mat_v["diff_p1_p3"].sum())
        fm_ident = alarm & ~in_window_mask
        f_days_ident = int(fm_ident.sum())

        arm_rows.append({
            "arm": aid, "arm_name": aname,
            "identified": 45 - tiers["漏"],
            "n_pre": tiers["提前"], "n_in_window": tiers["窗内"],
            "n_damage": tiers["损伤窗"], "n_miss": tiers["漏"],
            "caught_n": int(len(caught)),
            "trigger_offset_median": float(trig_offs.median()) if len(trig_offs) else math.nan,
            "alarm_day_share": float(alarm.sum()) / n,
            "false_days_total": f_days,
            "false_days_per_year": f_days / years,
            "false_days_ident_total": f_days_ident,
            "false_days_ident_per_year": f_days_ident / years,
            "false_episodes": n_false,
            "switched_n": int(len(switched)),
            "diff_p4_p3_median_switched": (
                float(pd.to_numeric(switched["diff_p4_p3"]).median()) if len(switched) else math.nan),
            "diff_p1_p3_median": float(mat_v["diff_p1_p3"].median()),
            "diff_p4_p3_median": float(mat_v["diff_p4_p3"].median()),
            "e2e_p1_p3_total": e2e_p1_total,
            "e2e_p4_p3_total": e2e_total,
            "false_cost_total": false_total,
            "false_cost_median": false_median,
            "false_activated_n": false_activated,
            "net_reference": e2e_total + false_total,
            "n_revoke": st["n_revoke"], "n_topo3": st.get("n_topo3", 0),
            "gate_pass": "是" if tiers["漏"] == 0 else "否",
        })

    arms_df = pd.DataFrame(arm_rows)
    matrix_df = pd.DataFrame(matrix_rows)

    # ---------- 对账 ----------
    c0 = arms_df[arms_df["arm"] == "C0"].iloc[0]
    v16 = v016_sum[v016_sum["variant"] == "B10"].iloc[0]
    for col in ["identified", "n_pre", "n_in_window", "n_damage", "n_miss",
                "caught_n", "switched_n", "false_days_total"]:
        assert int(c0[col]) == int(v16[col]), (col, c0[col], v16[col])
    for col in ["e2e_p4_p3_total", "false_cost_total", "net_reference",
                "e2e_p1_p3_total", "alarm_day_share", "false_days_per_year"]:
        assert abs(float(c0[col]) - float(v16[col])) <= 1e-6, (col, c0[col], v16[col])

    # 事件级对账（抽核全字段）
    m16 = pd.read_csv(OUT / "regime_v016_governed_pnl_event_matrix.csv")
    m16b = m16[m16["variant"] == "B10"].set_index("event_id")
    mc0 = matrix_df[matrix_df["arm"] == "C0"].set_index("event_id")
    for eid in mc0.index:
        a = mc0.loc[eid]
        b = m16b.loc[eid]
        assert str(a["tier"]) == str(b["tier"]), (eid, a["tier"], b["tier"])
        if str(a["diff_p4_p3"]) not in ("", "nan"):
            assert abs(float(a["diff_p4_p3"]) - float(b["diff_p4_p3"])) <= 1e-6, eid

    # ---------- 机械判读（预登记规则）----------
    verdicts = []
    for _, r in arms_df.iterrows():
        if r["arm"] == "C0":
            verdicts.append("控制臂·对账基准")
            continue
        if r["gate_pass"] != "是":
            verdicts.append("破坏闸门·否决")
        elif float(r["net_reference"]) > float(c0["net_reference"]):
            verdicts.append("可作产品增强件候选")
        else:
            verdicts.append("无净增量")
    arms_df["verdict"] = verdicts

    cond_cnt = int(((l1["contrast"] == "主对比·真警报对假警报") &
                    (l1["verdict_cond"] == "条件判别成立") &
                    (l1["feature"] != "__vote_box_score__")).sum())
    delta_cnt = int(((l1["contrast"] == "主对比·真警报对假警报") &
                     (l1["verdict_delta"] == "票箱之上有增量")).sum())
    bare_mean = float(l1[(l1["contrast"] == "参照·老标准邻近对常态")]["auc_star"].astype(float).mean())
    cond_mean = float(l1[(l1["contrast"] == "主对比·真警报对假警报") &
                         (l1["feature"] != "__vote_box_score__")]["auc_star"].astype(float).mean())
    if cond_cnt >= 1 and delta_cnt >= 1:
        layer1_verdict = "拓扑有产品侧增量·增强件候选"
    elif cond_cnt >= 1:
        layer1_verdict = "看得出真假警报但已被票箱吸收·留科研发现层"
    else:
        layer1_verdict = "警报态条件下无判别信息·科研发现层不进管线"
    old_std_read = ("老标准低估" if cond_mean - bare_mean > 0.02 else
                    "老标准高估" if bare_mean - cond_mean > 0.02 else "老标准与条件相当")

    # ---------- 输出 ----------
    l1.to_csv(OUT / "regime_v017_conditional_auc.csv",
              index=False, encoding="utf-8-sig", float_format="%.6f")
    arms_df.to_csv(OUT / "regime_v017_account_arms.csv",
                   index=False, encoding="utf-8-sig", float_format="%.6f")
    matrix_df.to_csv(OUT / "regime_v017_account_event_matrix.csv",
                     index=False, encoding="utf-8-sig", float_format="%.6f")

    out_files = [
        "regime_v017_conditional_auc.csv",
        "regime_v017_account_arms.csv",
        "regime_v017_account_event_matrix.csv",
    ]
    manifest = {
        "version": "v0.17",
        "purpose": "产品栈条件下的拓扑条件增量检验（样本内描述性）",
        "created": ts,
        "registered": REG_TS,
        "config": "config/regime_topology_increment_v0.17.toml",
        "config_sha256": sha256_file(CFG_PATH),
        "inputs": {
            "regime_v07_split_wide.csv": sha256_file(OUT / "regime_v07_split_wide.csv"),
            "regime_v05_benchmark_daily.csv": sha256_file(OUT / "regime_v05_benchmark_daily.csv"),
            "regime_v012_trigger_event_timing.csv": sha256_file(OUT / "regime_v012_trigger_event_timing.csv"),
            "regime_v016_governed_pnl_summary.csv": sha256_file(OUT / "regime_v016_governed_pnl_summary.csv"),
            "regime_v016_governed_pnl_event_matrix.csv": sha256_file(OUT / "regime_v016_governed_pnl_event_matrix.csv"),
            "regime_v09_q1_trigger.csv": sha256_file(OUT / "regime_v09_q1_trigger.csv"),
        },
        "outputs": {f: sha256_file(OUT / f) for f in out_files},
        "sample": {
            "days": n,
            "events": 45,
            "p_early_alarm_days": int(len(p_idx)),
            "p_events_with_early_days": int(len(np.unique(p_cluster))) if len(p_idx) else 0,
            "n_false_alarm_days": int(len(n_idx)),
            "n_false_segments": int(seg_id),
            "normal_days": int(len(norm_idx)),
            "prox_unique_days": int(len(prox_unique)),
            "deep_alarm_days_descriptive": int(len(deep_alarm_days)),
        },
        "layer1_verdict": layer1_verdict,
        "layer1_cond_discrimination_count": cond_cnt,
        "layer1_delta_count": delta_cnt,
        "old_standard_read": old_std_read,
        "old_standard_bare_mean_auc_star": bare_mean,
        "old_standard_cond_mean_auc_star": cond_mean,
        "deep_alarm_feature_medians": deep_desc,
        "arms": arms_df.to_dict(orient="records"),
        "false_episodes": false_records,
        "boundary": [
            "样本内描述性，不外推、不做实盘宣称",
            "2025 最终测试集封存未读；不重判十四条推测与 v0.5 冻结判定",
            "账本以事件结束日（后视镜）为已知输入的已知不足原样继承，本版不修补",
            "路径一是上限；全样本中位数被未触发/无法判定记 0 拉平，读已切换中位与合计",
            "误报两口径（账本 [−20,结束] vs 识别窗 [−20,+20]）不可混用",
            "层一特征方向冻结于 v0.9 记录（前版冻结发现，非本轮反选）",
        ],
    }
    with open(OUT / "regime_v017_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("v0.17 计算完成")
    print("层一判决：", layer1_verdict, "| 条件判别成立", cond_cnt, "项 | 增量成立", delta_cnt,
          "项 |", old_std_read)
    print("裸均值 %.4f vs 条件均值 %.4f" % (bare_mean, cond_mean))
    cols_show = ["arm", "identified", "n_pre", "n_in_window", "n_damage",
                 "switched_n", "diff_p4_p3_median_switched",
                 "e2e_p4_p3_total", "false_cost_total", "net_reference",
                 "false_days_per_year", "alarm_day_share", "gate_pass", "verdict"]
    print(arms_df[cols_show].to_string(index=False))


if __name__ == "__main__":
    main()
