#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v0.9：危机拓扑状态的日级检测与实时分类（只读分析）。

预登记：config/regime_daylevel_detection_v0.9.toml
输入：outputs/regime_v07_split_wide.csv + outputs/regime_v08_typology_event_profiles.csv
输出：regime_v09_q1_trigger.csv / regime_v09_q2_lag_curve.csv /
      regime_v09_q2_confusion_k5.csv / regime_v09_q3_power.csv / regime_v09_manifest.json

红线：不重判十四条推测、不做绩效、不改冻结产物、不读 2025 最终测试集。
"""
import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import norm, rankdata

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
SEED = 20261112
B = 2000
BLOCK = 20
PRIMARY_K = 5
SPLIT_DATE = "2015-01-01"

FEATURES = [
    ("a16_W_t", "状态点云相邻日持续图距离"),
    ("a16_h0_death_mean", "状态点云零维死亡值均值"),
    ("a16_h1_count", "状态点云一维环数量"),
    ("a16_window_rms", "状态点云窗口均方根"),
    ("a16_avg_pair_corr", "状态点云平均两两相关"),
    ("a16_leading_eig_share", "状态点云第一特征值占比"),
    ("b_h2_count", "相关网络二维空腔数量"),
    ("b_h1_count", "相关网络一维环数量"),
    ("b_h2_landscape_l1", "相关网络二维景观范数"),
    ("b_industry_average_correlation", "相关网络平均相关"),
    ("b_xy_h0_death_mean", "相关网络零维死亡值均值"),
]
FEAT_KEYS = [k for k, _ in FEATURES]
FEAT_CN = dict(FEATURES)

CL_STATE = "状态.window_rms升型"      # 状态扩张型，15 事件
CL_CORR = "相关.xy_h0_death_mean升型"  # 相关重构型，30 事件
COST_FN = 7.57   # 状态扩张型误判为相关重构型（假阴）代价
COST_FP = 6.16   # 相关重构型误判为状态扩张型（假阳）代价


def read_csv_dict(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def to_float(s):
    if s is None or s == "":
        return math.nan
    try:
        return float(s)
    except ValueError:
        return math.nan


def auc_mw(x, y):
    """曼-惠特尼曲线下面积 P(X > Y)（含平局减半）。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    x = x[~np.isnan(x)]
    y = y[~np.isnan(y)]
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return math.nan
    allv = np.concatenate([x, y])
    ranks = rankdata(allv)
    r1 = ranks[:n1].sum()
    return (r1 - n1 * (n1 + 1) / 2.0) / (n1 * n2)


def youden_threshold(x_state, x_corr):
    """训练段选约登指数最大阈值；正类=状态扩张型（值越大越像状态扩张）。"""
    xs = np.asarray(x_state, dtype=float)
    xc = np.asarray(x_corr, dtype=float)
    xs = xs[~np.isnan(xs)]
    xc = xc[~np.isnan(xc)]
    if len(xs) == 0 or len(xc) == 0:
        return math.nan, math.nan
    cands = np.unique(np.concatenate([xs, xc]))
    best_j, best_t = -np.inf, cands[0]
    for t in cands:
        tpr = (xs >= t).mean()
        fpr = (xc >= t).mean()
        j = tpr - fpr
        if j > best_j:
            best_j, best_t = j, t
    return float(best_t), float(best_j)


def rho1(v):
    """滞后 1 自相关（有效样本量折算用）。"""
    v = np.asarray(v, dtype=float)
    v = v[~np.isnan(v)]
    if len(v) < 5:
        return 0.0
    a, b = v[:-1], v[1:]
    m = ~(np.isnan(a) | np.isnan(b))
    a, b = a[m], b[m]
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def n_eff(n_raw, r):
    if n_raw <= 1:
        return float(max(n_raw, 1))
    r = max(min(r, 0.99), -0.5)
    return float(min(n_raw, max(1.0, n_raw * (1 - r) / (1 + r))))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    rng = np.random.default_rng(SEED)
    wide = read_csv_dict(OUT / "regime_v07_split_wide.csv")
    events = read_csv_dict(OUT / "regime_v08_typology_event_profiles.csv")
    assert len(wide) == 6483, len(wide)
    assert len(events) == 45, len(events)

    dates = [r["date"] for r in wide]
    idx_of = {d: i for i, d in enumerate(dates)}
    n_days = len(wide)

    cols = {k: np.array([to_float(r.get(k)) for r in wide]) for k in FEAT_KEYS}
    crisis_in = np.array([to_float(r.get("crisis_in")) for r in wide])
    crisis_flag = np.nan_to_num(crisis_in, nan=0.0) > 0

    # 事件索引与分组
    ev_rows = []
    for e in events:
        onset = e["onset"]
        assert onset in idx_of, onset
        ev_rows.append({
            "event_id": e["event_id"],
            "onset": onset,
            "i0": idx_of[onset],
            "cluster": e["cluster_name"],
            "is_state": e["cluster_name"] == CL_STATE,
        })
    n_state = sum(r["is_state"] for r in ev_rows)
    n_corr = len(ev_rows) - n_state
    assert n_state == 15 and n_corr == 30, (n_state, n_corr)

    # ------------------------------------------------------------
    # 问题一：危机邻近日 [-10,-1] vs 常态日
    # ------------------------------------------------------------
    prox_event_idx = []   # 每事件的邻近日索引（裁剪到日历内）
    for r in ev_rows:
        lo, hi = r["i0"] - 10, r["i0"]  # [i0-10, i0-1]
        lo = max(lo, 0)
        idxs = list(range(lo, hi))
        prox_event_idx.append(idxs)
    prox_unique = sorted({i for idxs in prox_event_idx for i in idxs})

    excl = np.zeros(n_days, dtype=bool)   # 常态日排除：任一事件 [-20,+30]
    for r in ev_rows:
        lo, hi = max(r["i0"] - 20, 0), min(r["i0"] + 31, n_days)
        excl[lo:hi] = True
    norm_idx = [i for i in range(n_days) if (not crisis_flag[i]) and (not excl[i])]
    norm_idx_arr = np.array(norm_idx)

    q1_rows = []
    for key in FEAT_KEYS:
        v = cols[key]
        prox_vals = v[prox_unique]
        norm_vals = v[norm_idx_arr]
        ok_p = prox_vals[~np.isnan(prox_vals)]
        ok_n = norm_vals[~np.isnan(norm_vals)]
        auc = auc_mw(ok_p, ok_n)
        auc_star = max(auc, 1 - auc) if not math.isnan(auc) else math.nan
        direction = "升" if auc > 0.5 else "降"
        med_d = float(np.median(ok_p) - np.median(ok_n)) if len(ok_p) and len(ok_n) else math.nan
        mean_d = float(ok_p.mean() - ok_n.mean()) if len(ok_p) and len(ok_n) else math.nan

        # 事件簇自助（邻近日按事件重抽）+ 常态日块自助
        per_ev_vals = []
        for idxs in prox_event_idx:
            pv = v[np.array(idxs)] if idxs else np.array([])
            per_ev_vals.append(pv[~np.isnan(pv)] if len(pv) else pv)
        n_ev = len(per_ev_vals)
        n_norm = len(ok_n)
        n_blocks = max(1, math.ceil(n_norm / BLOCK))
        boot_auc = np.empty(B)
        for b in range(B):
            ev_draw = rng.integers(0, n_ev, n_ev)
            parts = [per_ev_vals[i] for i in ev_draw if len(per_ev_vals[i])]
            xp = np.concatenate(parts) if parts else np.array([])
            starts = rng.integers(0, max(n_norm, 1), n_blocks)
            nb_parts = [ok_n[s:s + BLOCK] for s in starts]
            xn = np.concatenate(nb_parts) if nb_parts else np.array([])
            boot_auc[b] = auc_mw(xp, xn)
        boot_auc = boot_auc[~np.isnan(boot_auc)]
        ci_lo, ci_hi = (float(np.percentile(boot_auc, 2.5)),
                        float(np.percentile(boot_auc, 97.5))) if len(boot_auc) else (math.nan, math.nan)
        verdict = "有区分度" if (auc_star >= 0.60 and (ci_lo > 0.5 or ci_hi < 0.5)) else "无区分度"
        q1_rows.append({
            "feature": key, "feature_cn": FEAT_CN[key],
            "n_prox": len(ok_p), "n_norm": len(ok_n),
            "auc": round(auc, 4), "auc_star": round(auc_star, 4),
            "direction": direction,
            "median_diff": round(med_d, 6), "mean_diff": round(mean_d, 6),
            "auc_ci_low": round(ci_lo, 4), "auc_ci_high": round(ci_hi, 4),
            "verdict": verdict,
        })

    # ------------------------------------------------------------
    # 问题二：as-of 变化量 d(k)，两类判别滞后曲线 + k=5 混淆/代价
    # ------------------------------------------------------------
    base_lo_off, base_hi_off = -10, 0  # [i0-10, i0-1]

    def asof_d(ev, key, k):
        v = cols[key]
        base = v[ev["i0"] + base_lo_off: ev["i0"] + base_hi_off]
        base = base[~np.isnan(base)]
        if len(base) < 8:
            return math.nan
        cur = v[ev["i0"]: ev["i0"] + k + 1]
        cur = cur[~np.isnan(cur)]
        need = math.ceil(0.8 * (k + 1))
        if len(cur) < need:
            return math.nan
        return float(cur.mean() - base.mean())

    lag_rows = []
    d_store = {}  # (key,k) -> (state_vals, corr_vals)
    for key in FEAT_KEYS:
        for k in range(16):
            ds, dc = [], []
            for ev in ev_rows:
                d = asof_d(ev, key, k)
                if math.isnan(d):
                    continue
                (ds if ev["is_state"] else dc).append(d)
            d_store[(key, k)] = (ds, dc)
            auc = auc_mw(ds, dc)
            # 事件级类别内重抽自助
            bs, bc = np.array(ds, float), np.array(dc, float)
            boot = np.empty(B)
            for b in range(B):
                xs = bs[rng.integers(0, len(bs), len(bs))] if len(bs) else bs
                xc = bc[rng.integers(0, len(bc), len(bc))] if len(bc) else bc
                boot[b] = auc_mw(xs, xc)
            boot = boot[~np.isnan(boot)]
            ci_lo, ci_hi = (float(np.percentile(boot, 2.5)),
                            float(np.percentile(boot, 97.5))) if len(boot) else (math.nan, math.nan)
            lag_rows.append({
                "feature": key, "feature_cn": FEAT_CN[key], "k": k,
                "n_state": len(ds), "n_corr": len(dc),
                "auc": round(auc, 4), "auc_ci_low": round(ci_lo, 4), "auc_ci_high": round(ci_hi, 4),
            })

    # k=5 时间切分混淆与代价
    conf_rows = []
    for key in FEAT_KEYS:
        train_s, train_c, test_s, test_c = [], [], [], []
        for ev in ev_rows:
            d = asof_d(ev, key, PRIMARY_K)
            if math.isnan(d):
                continue
            if ev["onset"] < SPLIT_DATE:
                (train_s if ev["is_state"] else train_c).append(d)
            else:
                (test_s if ev["is_state"] else test_c).append(d)
        thr, j_stat = youden_threshold(train_s, train_c)
        if math.isnan(thr):
            continue
        tp = sum(1 for d in test_s if d >= thr)   # 状态扩张判为状态扩张
        fn = sum(1 for d in test_s if d < thr)    # 漏判（假阴）
        fp = sum(1 for d in test_c if d >= thr)   # 误判（假阳）
        tn = sum(1 for d in test_c if d < thr)
        n_test = tp + fn + fp + tn
        cost = (fn * COST_FN + fp * COST_FP) / n_test if n_test else math.nan
        base_corr = COST_FN * (tp + fn) / n_test if n_test else math.nan   # 全判相关重构
        base_state = COST_FP * (fp + tn) / n_test if n_test else math.nan  # 全判状态扩张
        base_min = min(base_corr, base_state)
        auc5 = auc_mw(*(d_store[(key, PRIMARY_K)]))
        verdict = "有实时分类价值" if (auc5 >= 0.70 and cost < base_min) else "无"
        conf_rows.append({
            "feature": key, "feature_cn": FEAT_CN[key],
            "train_n": len(train_s) + len(train_c), "test_n": n_test,
            "train_state": len(train_s), "train_corr": len(train_c),
            "test_state": len(test_s), "test_corr": len(test_c),
            "threshold": round(thr, 6), "youden_j": round(j_stat, 4),
            "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "expected_cost": round(cost, 4),
            "baseline_cost": round(base_min, 4),
            "auc_k5": round(auc5, 4),
            "verdict": verdict,
        })

    # ------------------------------------------------------------
    # 问题三：功效边界
    # ------------------------------------------------------------
    z_a = float(norm.ppf(1 - 0.05 / (2 * 11)))   # 双侧 α=0.05/11
    z_b = float(norm.ppf(0.8))
    power_rows = []
    for key in FEAT_KEYS:
        v = cols[key]
        # 日级：邻近日 / 常态日
        prox_series = np.concatenate([v[np.array(i)] for i in prox_event_idx if i])
        prox_series = prox_series[~np.isnan(prox_series)]
        norm_series = v[norm_idx_arr]
        norm_series = norm_series[~np.isnan(norm_series)]
        # 事件级：k=5 变化量
        ds, dc = d_store[(key, PRIMARY_K)]
        for level, s1, s2 in (
            ("危机邻近日 对 常态日（日级）", prox_series, norm_series),
            ("状态扩张型 对 相关重构型（事件级，k=5）", np.array(ds, float), np.array(dc, float)),
        ):
            n1r, n2r = len(s1), len(s2)
            r1, r2 = rho1(s1), rho1(s2)
            n1e, n2e = n_eff(n1r, r1), n_eff(n2r, r2)
            d_mde = (z_a + z_b) * math.sqrt(1 / n1e + 1 / n2e)
            auc_mde = float(norm.cdf(d_mde / math.sqrt(2)))
            power_rows.append({
                "level": level, "feature": key, "feature_cn": FEAT_CN[key],
                "n1_raw": n1r, "n2_raw": n2r,
                "rho1_1": round(r1, 4), "rho1_2": round(r2, 4),
                "n1_eff": round(n1e, 1), "n2_eff": round(n2e, 1),
                "mde_cohen_d": round(d_mde, 4),
                "mde_auc_equiv": round(auc_mde, 4),
            })

    # ------------------------------------------------------------
    # 写产物
    # ------------------------------------------------------------
    def dump(name, rows):
        p = OUT / name
        with p.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        return p

    files = [
        dump("regime_v09_q1_trigger.csv", q1_rows),
        dump("regime_v09_q2_lag_curve.csv", lag_rows),
        dump("regime_v09_q2_confusion_k5.csv", conf_rows),
        dump("regime_v09_q3_power.csv", power_rows),
    ]

    q1_sig = [r["feature"] for r in q1_rows if r["verdict"] == "有区分度"]
    q2_sig = [r["feature"] for r in conf_rows if r["verdict"] == "有实时分类价值"]
    manifest = {
        "purpose": "v0.9 危机拓扑状态的日级检测与实时分类（只读，样本内描述性）",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": "src/regime_check/build_v09_daylevel_detection.py",
        "preregistration": "config/regime_daylevel_detection_v0.9.toml",
        "inputs": {
            "wide_table": "outputs/regime_v07_split_wide.csv",
            "event_profiles": "outputs/regime_v08_typology_event_profiles.csv",
        },
        "sample": {
            "days": n_days,
            "events": len(ev_rows),
            "state_expansion": n_state,
            "correlation_reconstruction": n_corr,
            "proximate_days_unique": len(prox_unique),
            "normal_days": len(norm_idx),
            "train_events": sum(1 for e in ev_rows if e["onset"] < SPLIT_DATE),
            "test_events": sum(1 for e in ev_rows if e["onset"] >= SPLIT_DATE),
        },
        "settings": {
            "seed": SEED, "bootstrap_B": B, "block_length": BLOCK,
            "primary_k": PRIMARY_K, "split_date": SPLIT_DATE,
            "cost_fn": COST_FN, "cost_fp": COST_FP,
            "q1_rule": "AUC*≥0.60 且自助95%区间不覆盖0.50",
            "q2_rule": "k=5 AUC≥0.70 且测试期望代价<最优常数基线",
        },
        "summary": {
            "q1_features_with_discrimination": q1_sig,
            "q1_count": len(q1_sig),
            "q2_features_with_value": q2_sig,
            "q2_count": len(q2_sig),
        },
        "boundary": [
            "只读分析；未改任何冻结产物、未重判十四条推测、未做绩效或仓位阈值反选",
            "问题二的两类标签来自全样本聚类（v0.8），时间切分只约束分类器参数，非完全样本外",
            "全部为样本内描述性对账，不得外推为预警绩效",
            "2025 最终测试集未读取；第一道闸门仍暂停；第二道闸门未启动",
        ],
        "files": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in files},
    }
    mp = OUT / "regime_v09_manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台摘要
    print("=== 问题一：触发器（危机前 10 日 vs 常态日）===")
    for r in q1_rows:
        print(f"  {r['feature']:<36s} AUC*={r['auc_star']:.3f} {r['direction']} "
              f"[{r['auc_ci_low']:.3f},{r['auc_ci_high']:.3f}] → {r['verdict']}")
    print(f"  小计：{len(q1_sig)}/11 有区分度")
    print("=== 问题二：k=5 实时分类（时间切分 2015-01-01）===")
    for r in conf_rows:
        print(f"  {r['feature']:<36s} AUC={r['auc_k5']:.3f} 代价={r['expected_cost']:.3f}"
              f"(基线{r['baseline_cost']:.3f}) FN={r['fn']} FP={r['fp']} → {r['verdict']}")
    print(f"  小计：{len(q2_sig)}/11 有实时分类价值")
    print("=== 问题二：判别滞后曲线（AUC 峰值 k）===")
    for key in FEAT_KEYS:
        ks = [r for r in lag_rows if r["feature"] == key]
        best = max(ks, key=lambda r: r["auc"] if not math.isnan(r["auc"]) else -1)
        k05 = [r for r in ks if r["k"] == 5][0]
        print(f"  {key:<36s} 峰值 k={best['k']:>2d} AUC={best['auc']:.3f} | k=5 AUC={k05['auc']:.3f}")
    print("=== 问题三：最小可检测效应（摘要）===")
    for r in power_rows:
        if r["level"].startswith("状态扩张"):
            print(f"  事件级 {r['feature']:<36s} n_eff={r['n1_eff']:.0f}/{r['n2_eff']:.0f} "
                  f"MDE d={r['mde_cohen_d']:.2f} (AUC≈{r['mde_auc_equiv']:.3f})")
    print("Done.")


if __name__ == "__main__":
    main()
