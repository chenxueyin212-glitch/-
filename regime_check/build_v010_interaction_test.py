"""v0.10 Interaction test: financial crisis type × topological response.

Pre-registered in config/regime_interaction_test_v0.10.toml.
Read-only on frozen products.  No v0.5 re-judgement, no performance metrics.
"""

import csv
import json
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
CFG = ROOT / "config" / "regime_interaction_test_v0.10.toml"
SEED = 20261112
N_PERM = 10000
N_BOOT = 5000
TARGET_FDR = 0.10


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def cliffs_delta(x, y):
    """Cliff's delta: P(X>Y) − P(X<Y)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    x, y = x[~np.isnan(x)], y[~np.isnan(y)]
    if not len(x) or not len(y):
        return np.nan
    gt = sum(1 for a in x for b in y if a > b)
    lt = sum(1 for a in x for b in y if a < b)
    return (gt - lt) / (len(x) * len(y))


def perm_test(x, y, rng, n_perm=N_PERM):
    """Two-sided permutation test on median difference."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    x, y = x[~np.isnan(x)], y[~np.isnan(y)]
    if len(x) < 3 or len(y) < 3:
        return np.nan, np.nan
    obs = np.median(x) - np.median(y)
    pooled = np.concatenate([x, y])
    n1 = len(x)
    cnt = 0
    for _ in range(n_perm):
        perm = rng.permutation(pooled)
        d = np.median(perm[:n1]) - np.median(perm[n1:])
        if abs(d) >= abs(obs):
            cnt += 1
    p = (cnt + 1) / (n_perm + 1)
    return obs, p


def boot_ci(x, y, rng, n_boot=N_BOOT):
    """Bootstrap 95% CI for median difference."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    x, y = x[~np.isnan(x)], y[~np.isnan(y)]
    if len(x) < 3 or len(y) < 3:
        return np.nan, np.nan
    diffs = []
    for _ in range(n_boot):
        xb = rng.choice(x, size=len(x), replace=True)
        yb = rng.choice(y, size=len(y), replace=True)
        diffs.append(np.median(xb) - np.median(yb))
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def bh_fdr(pvals, target=TARGET_FDR):
    """Benjamini-Hochberg FDR.  Returns list of booleans (rejected)."""
    n = len(pvals)
    order = sorted(range(n), key=lambda i: pvals[i])
    rejected = [False] * n
    max_k = 0
    for rank, idx in enumerate(order, 1):
        if pvals[idx] <= rank / n * target:
            max_k = rank
    for rank, idx in enumerate(order, 1):
        if rank <= max_k:
            rejected[idx] = True
    return rejected


def main():
    rng = np.random.default_rng(SEED)

    # ── Load event profiles ──
    profiles = read_csv(OUT / "regime_v08_typology_event_profiles.csv")
    assert len(profiles) == 45

    # ── Extract financial features for clustering ──
    FIN_KEYS = ["crisis_max_dd_pct", "n_crisis_days", "post20_cum_pct"]
    events = []
    for r in profiles:
        vals = []
        for k in FIN_KEYS:
            try:
                vals.append(float(r[k]))
            except (ValueError, KeyError):
                vals = None
                break
        if vals is None:
            continue
        events.append({
            "event_id": r["event_id"],
            "onset": r["onset"],
            "segment": r["segment"],
            "old_cluster": r["cluster_name"],
            "fin": np.array(vals),
            "deltas": {
                "C01": float(r.get("delta_a16_window_rms__mean", "nan")),
                "C03": float(r.get("delta_a16_avg_pair_corr__mean", "nan")),
                "C04": float(r.get("delta_a16_leading_eig_share__mean", "nan")),
                "C05": float(r.get("delta_a16_h1_count__mean", "nan")),
                "C06": float(r.get("delta_b_h2_count__mean", "nan")),
                "C07": float(r.get("delta_b_h1_count__mean", "nan")),
                "C08": float(r.get("delta_a16_W_t__mean", "nan")),
                "C09": float(r.get("delta_b_xy_h0_death_mean__mean", "nan")),
            },
        })

    print(f"events with complete financial features: {len(events)}/45")
    assert len(events) == 45

    # ── Standardize financial features and Ward cluster k=2 ──
    F = np.array([e["fin"] for e in events])
    Fz = (F - F.mean(0)) / (F.std(0, ddof=1) + 1e-10)
    Z = linkage(Fz, method="ward")
    lab = fcluster(Z, 2, criterion="maxclust") - 1

    # Label groups so group 0 = deeper/slower (more negative dd), group 1 = shallower
    g0_dd = np.median([events[i]["fin"][0] for i in range(len(events)) if lab[i] == 0])
    g1_dd = np.median([events[i]["fin"][1 - 1] for i in range(len(events)) if lab[i] == 1])
    # Actually use index 0 of fin which is dd
    g0_dd = np.median([events[i]["fin"][0] for i in range(len(events)) if lab[i] == 0])
    g1_dd = np.median([events[i]["fin"][0] for i in range(len(events)) if lab[i] == 1])
    if g0_dd > g1_dd:  # swap so group 0 has more negative dd (deeper crisis)
        lab = 1 - lab

    for i, e in enumerate(events):
        e["fin_cluster"] = int(lab[i])
        e["fin_cluster_name"] = "深慢型" if lab[i] == 0 else "浅快型"

    # ── Clustering summary ──
    cl_rows = []
    for cid in [0, 1]:
        members = [e for e in events if e["fin_cluster"] == cid]
        name = "深慢型" if cid == 0 else "浅快型"
        dd_vals = [e["fin"][0] for e in members]
        sp_vals = [e["fin"][1] for e in members]
        rc_vals = [e["fin"][2] for e in members]
        # agreement with old topological clustering
        old_s = sum(1 for e in members if "window_rms" in e["old_cluster"])
        old_c = len(members) - old_s
        cl_rows.append({
            "fin_cluster": name,
            "n_events": len(members),
            "dd_median": round(float(np.median(dd_vals)), 2),
            "speed_median": round(float(np.median(sp_vals)), 1),
            "recovery_median": round(float(np.median(rc_vals)), 2),
            "old_scale_type": old_s,
            "old_corr_type": old_c,
            "event_ids": ";".join(e["event_id"] for e in members),
        })

    write_csv(OUT / "regime_v010_interaction_clustering.csv", cl_rows,
              ["fin_cluster", "n_events", "dd_median", "speed_median",
               "recovery_median", "old_scale_type", "old_corr_type", "event_ids"])

    print(f"\n=== Financial clustering ===")
    for r in cl_rows:
        print(f"  {r['fin_cluster']}: n={r['n_events']}  dd={r['dd_median']}%  "
              f"speed={r['speed_median']}d  recovery={r['recovery_median']}%")
        print(f"    old typology: 尺度扩张={r['old_scale_type']}  相关重构={r['old_corr_type']}")

    # agreement rate
    agree = 0
    for e in events:
        old_is_scale = "window_rms" in e["old_cluster"]
        fin_is_deep = e["fin_cluster"] == 0
        if old_is_scale == fin_is_deep:
            agree += 1
    print(f"  agreement with topological clustering: {agree}/{len(events)} = {agree/len(events):.1%}")

    # ── Interaction tests ──
    CONJ_DESC = {
        "C01": "尺度摘要（均方根）变化量",
        "C03": "平均两两相关变化量",
        "C04": "第一特征值占比变化量",
        "C05": "状态点云一维环数量变化量",
        "C06": "相关网络二维空腔数量变化量",
        "C07": "相关网络一维环数量变化量",
        "C08": "持续图相邻日距离变化量",
        "C09": "相关网络零维死亡均值变化量",
    }

    results = []
    for cid in ["C01", "C03", "C04", "C05", "C06", "C07", "C08", "C09"]:
        x0 = [e["deltas"][cid] for e in events if e["fin_cluster"] == 0 and not np.isnan(e["deltas"][cid])]
        x1 = [e["deltas"][cid] for e in events if e["fin_cluster"] == 1 and not np.isnan(e["deltas"][cid])]

        med_diff, p = perm_test(x0, x1, rng)
        ci_lo, ci_hi = boot_ci(x0, x1, rng)
        cd = cliffs_delta(x0, x1)

        results.append({
            "conjecture": cid,
            "description": CONJ_DESC[cid],
            "n_deep": len(x0),
            "n_shallow": len(x1),
            "median_deep": round(float(np.median(x0)), 5) if x0 else "nan",
            "median_shallow": round(float(np.median(x1)), 5) if x1 else "nan",
            "median_diff": round(float(med_diff), 5),
            "cliffs_delta": round(float(cd), 3),
            "ci_lo": round(float(ci_lo), 5),
            "ci_hi": round(float(ci_hi), 5),
            "p_value": round(float(p), 5),
            "bonferroni_sig": "是" if p < 0.05 / 8 else "否",
        })

    # BH-FDR
    pvals = [r["p_value"] for r in results]
    rejected = bh_fdr(pvals)
    for i, r in enumerate(results):
        r["bh_fdr_sig"] = "是" if rejected[i] else "否"

    results.sort(key=lambda r: r["p_value"])

    write_csv(OUT / "regime_v010_interaction_test_results.csv", results,
              ["conjecture", "description", "n_deep", "n_shallow",
               "median_deep", "median_shallow", "median_diff",
               "cliffs_delta", "ci_lo", "ci_hi", "p_value",
               "bonferroni_sig", "bh_fdr_sig"])

    print(f"\n=== Interaction tests (8 conjectures) ===")
    print(f"{'ID':>4s} {'feature':<30s} {'deep_med':>10s} {'shallow_med':>10s} "
          f"{'diff':>10s} {'Cliff':>7s} {'p':>8s} {'BH':>4s} {'Bonf':>5s}")
    print("-" * 100)
    for r in results:
        print(f"{r['conjecture']:>4s} {r['description']:<30s} "
              f"{r['median_deep']:>10.4f} {r['median_shallow']:>10.4f} "
              f"{r['median_diff']:>10.4f} {r['cliffs_delta']:>7.3f} "
              f"{r['p_value']:>8.5f} {r['bh_fdr_sig']:>4s} {r['bonferroni_sig']:>5s}")

    n_bh = sum(1 for r in results if r["bh_fdr_sig"] == "是")
    n_bonf = sum(1 for r in results if r["bonferroni_sig"] == "是")
    print(f"\nBH-FDR (q<0.10) survivors: {n_bh}/8")
    print(f"Bonferroni (p<0.00625) survivors: {n_bonf}/8")

    # ── Direction analysis (which type shows which direction) ──
    print(f"\n=== Direction by type ===")
    for r in results:
        d_med = float(r["median_deep"])
        s_med = float(r["median_shallow"])
        d_dir = "↑" if d_med > 0 else ("↓" if d_med < 0 else "→")
        s_dir = "↑" if s_med > 0 else ("↓" if s_med < 0 else "→")
        conflict = "⚠️" if d_dir != s_dir else ""
        print(f"  {r['conjecture']} {r['description']:<30s} "
              f"深慢型 {d_dir}  浅快型 {s_dir}  {conflict}")

    # ── Manifest ──
    manifest = {
        "purpose": "金融危机类型 × 拓扑响应的交互效应检验（v0.10）",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": "src/regime_check/build_v010_interaction_test.py",
        "pre_registration": "config/regime_interaction_test_v0.10.toml",
        "seed": SEED,
        "n_permutations": N_PERM,
        "n_bootstrap": N_BOOT,
        "clustering_features": FIN_KEYS,
        "n_events": len(events),
        "clustering_agreement_with_v08": f"{agree}/{len(events)}",
        "test_results_summary": {
            "n_tests": 8,
            "bh_fdr_survivors": n_bh,
            "bonferroni_survivors": n_bonf,
        },
        "boundary": [
            "分型用金融特征、检验用拓扑特征——特征集不重叠，打破循环论证",
            "交互检验（两组是否不同），不做组内单侧检验",
            "不重判 v0.5 的 14 条正式判定",
            "不做绩效、信息系数、夏普比率、精确率召回率曲线下面积、仓位、阈值反选",
            "不读取 2025 最终测试集",
            "不改 config/study.toml 或任何冻结产物",
            "纯样本内描述性对账，不得外推",
        ],
    }

    # file hashes
    files = {}
    for name in ["regime_v010_interaction_clustering.csv",
                 "regime_v010_interaction_test_results.csv"]:
        p = OUT / name
        files[name] = {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "size": p.stat().st_size,
        }
    manifest["files"] = files

    with open(OUT / "regime_v010_interaction_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nManifest written. Done.")


if __name__ == "__main__":
    main()
