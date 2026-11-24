"""v0.8 危机事件拓扑画像分型 —— 纯描述性对账。

读取 v0.7 事件阶段指标与事件概览，计算每事件的拓扑 delta 画像，
按 Ward 层次聚类分组，再与金融定性交叉对照。
不重判推测、不做显著性、不改任何冻结产物。
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
PREFIX = "regime_v08_typology_"

# ---- 特征定义（与预登记一致） ----
A_KEYS = [
    "a16_W_t__mean",
    "a16_h0_death_mean__mean",
    "a16_h1_count__mean",
    "a16_window_rms__mean",
    "a16_avg_pair_corr__mean",
    "a16_leading_eig_share__mean",
]
B_KEYS = [
    "b_h2_count__mean",
    "b_h1_count__mean",
    "b_h2_landscape_l1__mean",
    "b_industry_average_correlation__mean",
    "b_xy_h0_death_mean__mean",
]
ALL_TOPO = A_KEYS + B_KEYS

FIN_KEYS = [
    "crisis_max_dd_pct",
    "n_crisis_days",
    "crisis_cum_pct",
    "post20_cum_pct",
    "onset_avg_pair_corr",
]


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(s):
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main():
    # ---- 读取数据 ----
    phase = read_csv(OUT / "crisis_context_v07_event_phase_metrics.csv")
    overview = read_csv(OUT / "crisis_context_v07_event_overview.csv")
    ov_by_id = {r["event_id"]: r for r in overview}

    # ---- 构建事件级拓扑画像（crisis − pre20 delta） ----
    # 先按 event_id 聚合 phase 表
    events = {}
    for row in phase:
        eid = row["event_id"]
        ph = row["phase"]
        if eid not in events:
            events[eid] = {}
        events[eid][ph] = row

    profiles = []
    for eid, phases in sorted(events.items(), key=lambda x: int(x[0])):
        if "crisis" not in phases or "pre20" not in phases:
            continue
        crisis_row = phases["crisis"]
        pre_row = phases["pre20"]
        ov = ov_by_id.get(eid, {})
        source = ov.get("event_source", "")
        in_judge = ov.get("in_judgement", "0")
        seg = ov.get("segment", "")

        # 外部锚点不入分组
        if source == "外部金融定性危机":
            continue

        delta = {}
        valid = True
        for k in ALL_TOPO:
            c = fnum(crisis_row.get(k))
            p = fnum(pre_row.get(k))
            if c is None or p is None:
                delta[k] = None
            else:
                delta[k] = c - p
        # 至少要有 8 个非空 delta 才入组
        n_valid = sum(1 for v in delta.values() if v is not None)
        if n_valid < 8:
            continue

        fin = {}
        for k in FIN_KEYS:
            fin[k] = fnum(ov.get(k))
        fin["segment"] = seg
        fin["event_source"] = source
        fin["in_judgement"] = in_judge
        fin["event_label"] = ov.get("event_label", "")
        fin["onset"] = ov.get("onset", "")

        profiles.append({
            "event_id": eid,
            "onset": ov.get("onset", ""),
            "segment": seg,
            "event_source": source,
            "in_judgement": in_judge,
            "event_label": ov.get("event_label", ""),
            "delta": delta,
            "fin": fin,
        })

    print(f"入组事件数: {len(profiles)}")

    # ---- 标准化拓扑 delta（z-score） ----
    # 先转成矩阵，缺失用全事件中位数填充（仅用于聚类，不影响原始表）
    topo_matrix = np.full((len(profiles), len(ALL_TOPO)), np.nan)
    for i, p in enumerate(profiles):
        for j, k in enumerate(ALL_TOPO):
            v = p["delta"].get(k)
            if v is not None:
                topo_matrix[i, j] = v

    # 用列中位数填 NaN（仅聚类用）
    col_med = np.nanmedian(topo_matrix, axis=0)
    for j in range(topo_matrix.shape[1]):
        mask = np.isnan(topo_matrix[:, j])
        topo_matrix[mask, j] = col_med[j]

    # z-score
    mu = topo_matrix.mean(axis=0)
    sd = topo_matrix.std(axis=0, ddof=0)
    sd[sd == 0] = 1.0
    Z = (topo_matrix - mu) / sd

    # ---- Ward 层次聚类 ----
    dist = pdist(Z, metric="euclidean")
    Zlink = linkage(dist, method="ward")

    # 轮廓系数选 k
    from scipy.spatial.distance import cdist

    def silhouette(Zmat, labels):
        n = len(labels)
        if len(set(labels)) < 2:
            return -1.0
        D = cdist(Zmat, Zmat, "euclidean")
        sil_vals = []
        for i in range(n):
            same = [j for j in range(n) if labels[j] == labels[i] and j != i]
            if not same:
                sil_vals.append(0.0)
                continue
            a = np.mean(D[i, same])
            b = min(
                np.mean(D[i, [j for j in range(n) if labels[j] == c]])
                for c in set(labels) if c != labels[i]
            )
            sil_vals.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
        return float(np.mean(sil_vals))

    best_k, best_sil, all_sil = 2, -2, {}
    for k in range(2, 9):
        labels = fcluster(Zlink, t=k, criterion="maxclust")
        s = silhouette(Z, labels)
        all_sil[k] = round(s, 4)
        if s > best_sil:
            best_sil, best_k = s, k

    print(f"轮廓系数: {all_sil}  → 最优 k={best_k} (sil={best_sil:.4f})")

    # 各 k 分组
    k_results = {}
    for k in range(3, 7):
        labels = fcluster(Zlink, t=k, criterion="maxclust")
        k_results[k] = labels.tolist()

    labels_main = fcluster(Zlink, t=best_k, criterion="maxclust")

    # ---- 命名聚类 ----
    cluster_names = {}
    for c in sorted(set(labels_main)):
        idx = [i for i, l in enumerate(labels_main) if l == c]
        med_deltas = {}
        for j, k in enumerate(ALL_TOPO):
            med_deltas[k] = float(np.median([topo_matrix[i, j] for i in idx]))
        # 找最极端的 z-score 特征来命名
        zs = {}
        for j, k in enumerate(ALL_TOPO):
            zs[k] = (med_deltas[k] - mu[j]) / sd[j]
        top_feat = max(zs, key=lambda k: abs(zs[k]))
        direction = "升" if zs[top_feat] > 0 else "降"
        short = top_feat.replace("__mean", "").replace("a16_", "状态.").replace("b_", "相关.")
        cluster_names[c] = f"{short}{direction}型"

    print(f"聚类命名: {cluster_names}")

    # ---- 金融画像汇总 ----
    cluster_financial = {}
    for c in sorted(set(labels_main)):
        idx = [i for i, l in enumerate(labels_main) if l == c]
        members = [profiles[i] for i in idx]
        fin_summary = {}
        for k in FIN_KEYS:
            vals = [m["fin"][k] for m in members if m["fin"].get(k) is not None]
            fin_summary[k] = {
                "median": round(float(np.median(vals)), 4) if vals else None,
                "min": round(float(np.min(vals)), 4) if vals else None,
                "max": round(float(np.max(vals)), 4) if vals else None,
            }
        segs = [m["segment"] for m in members]
        fin_summary["n_front"] = segs.count("前段")
        fin_summary["n_back"] = segs.count("后段")
        fin_summary["n_events"] = len(members)
        fin_summary["event_ids"] = [m["event_id"] for m in members]
        fin_summary["onsets"] = [m["onset"] for m in members]
        cluster_financial[c] = fin_summary

    # ---- 金融分型 → 拓扑画像 ----
    # 按严重度三档、速度三档分别看拓扑 delta 中位数
    dd_vals = [p["fin"]["crisis_max_dd_pct"] for p in profiles if p["fin"].get("crisis_max_dd_pct") is not None]
    dd_q33, dd_q67 = np.percentile(dd_vals, [33, 67])
    speed_vals = [p["fin"]["n_crisis_days"] for p in profiles if p["fin"].get("n_crisis_days") is not None]
    sp_q33, sp_q67 = np.percentile(speed_vals, [33, 67])

    def sev_bin(v):
        # crisis_max_dd_pct 是负数（回撤），越小越深
        if v is None:
            return "未知"
        if v <= dd_q33:
            return "深"   # 最负 = 最深回撤
        if v <= dd_q67:
            return "中"
        return "浅"       # 最接近零 = 最浅

    def speed_bin(v):
        if v is None:
            return "未知"
        if v <= sp_q33:
            return "急性"
        if v <= sp_q67:
            return "中速"
        return "慢性"

    financial_topology = {"severity": {}, "speed": {}}
    for cat_name, bin_fn in [("severity", sev_bin), ("speed", speed_bin)]:
        bins = {}
        for p in profiles:
            if cat_name == "severity":
                b = bin_fn(p["fin"].get("crisis_max_dd_pct"))
            else:
                b = bin_fn(p["fin"].get("n_crisis_days"))
            if b not in bins:
                bins[b] = []
            bins[b].append(p)
        for b, members in bins.items():
            topo_med = {}
            for j, k in enumerate(ALL_TOPO):
                vals = [m["delta"][k] for m in members if m["delta"].get(k) is not None]
                topo_med[k] = round(float(np.median(vals)), 6) if vals else None
            financial_topology[cat_name][b] = {
                "n": len(members),
                "event_ids": [m["event_id"] for m in members],
                "topo_delta_median": topo_med,
            }

    # ---- 输出 CSV ----
    # 1. event_profiles.csv
    with (OUT / (PREFIX + "event_profiles.csv")).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        header = ["event_id", "onset", "segment", "event_source", "in_judgement", "event_label",
                  f"cluster_k{best_k}", "cluster_name"]
        header += [f"delta_{k}" for k in ALL_TOPO]
        header += FIN_KEYS
        w.writerow(header)
        for i, p in enumerate(profiles):
            row = [p["event_id"], p["onset"], p["segment"], p["event_source"],
                   p["in_judgement"], p["event_label"],
                   int(labels_main[i]), cluster_names.get(labels_main[i], "")]
            row += [p["delta"].get(k, "") for k in ALL_TOPO]
            row += [p["fin"].get(k, "") for k in FIN_KEYS]
            w.writerow(row)

    # 2. cluster_assignments.csv
    with (OUT / (PREFIX + "cluster_assignments.csv")).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event_id", "onset"] + [f"k={k}" for k in sorted(k_results)] + ["k_optimal", "cluster_name"])
        for i, p in enumerate(profiles):
            row = [p["event_id"], p["onset"]] + [k_results[k][i] for k in sorted(k_results)]
            row += [int(labels_main[i]), cluster_names.get(labels_main[i], "")]
            w.writerow(row)

    # 3. cluster_financial.csv
    with (OUT / (PREFIX + "cluster_financial.csv")).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cluster_id", "cluster_name", "n_events", "n_front", "n_back",
                    "dd_median", "dd_min", "dd_max",
                    "speed_median", "speed_min", "speed_max",
                    "cum_ret_median", "recovery_median", "corr_median",
                    "event_ids", "onsets"])
        for c in sorted(cluster_financial):
            cf = cluster_financial[c]
            w.writerow([
                c, cluster_names.get(c, ""), cf["n_events"], cf["n_front"], cf["n_back"],
                cf["crisis_max_dd_pct"]["median"], cf["crisis_max_dd_pct"]["min"], cf["crisis_max_dd_pct"]["max"],
                cf["n_crisis_days"]["median"], cf["n_crisis_days"]["min"], cf["n_crisis_days"]["max"],
                cf["crisis_cum_pct"]["median"], cf["post20_cum_pct"]["median"], cf["onset_avg_pair_corr"]["median"],
                ";".join(cf["event_ids"]), ";".join(cf["onsets"]),
            ])

    # 4. financial_topology.csv
    with (OUT / (PREFIX + "financial_topology.csv")).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["dimension", "bin", "n_events", "event_ids"] + [f"delta_med_{k}" for k in ALL_TOPO])
        for dim in ["severity", "speed"]:
            for b, info in sorted(financial_topology[dim].items()):
                w.writerow([dim, b, info["n"], ";".join(info["event_ids"])]
                           + [info["topo_delta_median"].get(k, "") for k in ALL_TOPO])

    # 5. cross_tab.csv
    with (OUT / (PREFIX + "cross_tab.csv")).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cluster_id", "cluster_name", "severity_bin", "speed_bin", "n", "event_ids"])
        for c in sorted(cluster_financial):
            members = [profiles[i] for i in range(len(profiles)) if labels_main[i] == c]
            # 按严重度×速度交叉
            combos = {}
            for m in members:
                sb = sev_bin(m["fin"].get("crisis_max_dd_pct"))
                pb = speed_bin(m["fin"].get("n_crisis_days"))
                key = (sb, pb)
                if key not in combos:
                    combos[key] = []
                combos[key].append(m["event_id"])
            for (sb, pb), eids in sorted(combos.items()):
                w.writerow([c, cluster_names.get(c, ""), sb, pb, len(eids), ";".join(eids)])

    # ---- 汇总 JSON ----
    summary = {
        "purpose": "危机事件拓扑画像分型 —— 纯描述性对账",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_events_clustered": len(profiles),
        "silhouette_by_k": all_sil,
        "optimal_k": best_k,
        "optimal_silhouette": round(best_sil, 4),
        "cluster_names": {str(k): v for k, v in cluster_names.items()},
        "cluster_sizes": {str(c): cluster_financial[c]["n_events"] for c in cluster_financial},
        "cluster_financial": {
            str(c): {
                "n": cluster_financial[c]["n_events"],
                "n_front": cluster_financial[c]["n_front"],
                "n_back": cluster_financial[c]["n_back"],
                "dd_median": cluster_financial[c]["crisis_max_dd_pct"]["median"],
                "speed_median": cluster_financial[c]["n_crisis_days"]["median"],
                "recovery_median": cluster_financial[c]["post20_cum_pct"]["median"],
                "corr_median": cluster_financial[c]["onset_avg_pair_corr"]["median"],
                "onsets": cluster_financial[c]["onsets"],
            }
            for c in cluster_financial
        },
        "financial_topology": financial_topology,
        "severity_bins": {"q33": round(float(dd_q33), 2), "q67": round(float(dd_q67), 2)},
        "speed_bins": {"q33": round(float(sp_q33), 1), "q67": round(float(sp_q67), 1)},
        "boundary": [
            "纯描述性对账，不做显著性检验、不做预测",
            "不重判 14 条推测，不改任何冻结产物",
            "不覆盖 v0.1—v0.7 任何产物",
            "不做绩效/IC/命中率/提前量",
            "不读 2025 最终测试集",
            "分组结果不构成「识别出了危机类型」的声称",
            "结论仅限本样本内拓扑画像与金融定性的对应关系",
        ],
    }
    (OUT / (PREFIX + "summary.json")).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n输出完成。k={best_k}, 聚类命名={cluster_names}")
    for c in sorted(cluster_financial):
        cf = cluster_financial[c]
        print(f"  组 {c} ({cluster_names[c]}): {cf['n_events']} 事件, "
              f"前段 {cf['n_front']}/后段 {cf['n_back']}, "
              f"DD 中位 {cf['crisis_max_dd_pct']['median']}, "
              f"速度中位 {cf['n_crisis_days']['median']}, "
              f"恢复中位 {cf['post20_cum_pct']['median']}")


if __name__ == "__main__":
    main()
