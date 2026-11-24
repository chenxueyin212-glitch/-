"""v0.3 stage 1: line-separated SHORT-WINDOW summaries only.

Frozen spec: config/regime_split_check_v0.3.toml (draft, D3 pending).
Explicit boundary: NO group statistics, NO significance test, NO verdict.
Stage 2 (primary judgements / report) is BLOCKED until the user decides D3.

Stage 1 does four things, all independent of D3 (which only affects the
event-level sample definition):
  A  audit v0.2 window summaries for reuse (full-point equivalence,
     determinism re-computation on 24 sampled dates, node-count control)
  B  compute the two missing A-line w=10 PHTI state-cloud summaries
  C  compute the never-produced B-line H0 hierarchical-clustering summaries
     (VR H0 finite deaths == Kruskal MST edge weights; checked against ripser)
  D  emit a line-separated wide table (date x A16/A27/B/H0/labels), with
     explicit per-line prefixes so identically named quantities cannot merge.

No pandas import (broken numpy/pandas pairing in this venv). Single process,
one price load, incremental disk writes. All JSON goes through jsonable() so
the v0.2 manifest serialization bug (numpy scalar / NaN) cannot recur.
"""
from __future__ import annotations

import collections
import csv
import json
import math
import sys
import time
import tomllib
import warnings
from pathlib import Path

import numpy as np
from ripser import ripser

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "phti_replication"))
sys.path.insert(0, str(ROOT / "src" / "regime_check"))
warnings.filterwarnings("ignore", message=".*more columns than rows.*")

import build_window_grid_summaries as bg  # noqa: E402

OUT = bg.OUT
CFG_V03 = ROOT / "config" / "regime_split_check_v0.3.toml"
CFG_PHTI = ROOT / "config" / "phti_replication.toml"
W = 10
EPSILONS = (0.4, 0.6, 0.8)
# ripser casts the distance matrix to float32 internally; our Prim runs in
# float64. Cross-implementation tolerance must reflect float32 rounding,
# not the 1e-8 used for same-implementation determinism checks.
RIPSER_FLOAT32_TOL = 1e-6

H0_FIELDS = [
    "n_nodes", "xy_h0_death_mean", "xy_h0_death_median", "xy_h0_death_max",
    "xy_h0_death_p90", "xy_h0_death_cv", "xy_h0_top1_over_rest_median",
    "xy_h0_components_0p4", "xy_h0_components_0p6", "xy_h0_components_0p8",
    "xy_avg_corr_w10", "xy_leading_eig_share_w10",
]


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, bool):
        return bool(o)
    if isinstance(o, int):
        return int(o)
    if isinstance(o, float):
        return float(o) if math.isfinite(o) else None
    if o is None or isinstance(o, str):
        return o
    return str(o)


def dump(name: str, obj) -> None:
    (OUT / name).write_text(
        json.dumps(jsonable(obj), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")


def read_csv(name: str) -> list[dict]:
    with (OUT / name).open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(name: str, fields: list[str], rows: list[dict]) -> None:
    with (OUT / name).open("w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(rows)


# ---------------------------------------------------------------------------
# A. audit v0.2 summaries before reuse
# ---------------------------------------------------------------------------
def stage_a() -> dict:
    v01 = read_csv("xy_corrected_features.csv")
    ref = {r["date"]: r for r in v01}
    dates = sorted(ref)
    grids = {w: {r["date"]: r for r in read_csv(f"regime_win_summaries_xy_{w}.csv")}
             for w in (10, 15, 20, 30)}
    rep = {"n_v0_1_dates": len(dates), "windows_checked": [10, 15, 20, 30]}

    # 1 completeness / finiteness / date coverage
    rep["coverage"] = {}
    for w, g in grids.items():
        bad = 0
        for d, r in g.items():
            for k, v in r.items():
                if k == "date":
                    continue
                if v is None or v == "":
                    bad += 1
                elif not math.isfinite(float(v)):
                    bad += 1
        rep["coverage"][f"w{w}"] = {
            "rows": len(g), "blank_or_nonfinite": bad,
            "date_set_equals_v0_1": set(g) == set(dates)}

    # 2 full-point equivalence w=30 vs v0.1 (not just 24 sampled dates)
    diffs = {k: [] for k in bg.XY_FIELDS}
    for d in dates:
        for k in bg.XY_FIELDS:
            diffs[k].append(abs(float(grids[30][d][k]) - float(ref[d][k])))
    rep["w30_full_equivalence"] = {
        "n_dates": len(dates),
        "max_abs_diff_by_field": {k: float(max(v)) for k, v in diffs.items()},
        "passed": all(max(v) < 1e-8 for v in diffs.values())}

    # 2b diagnose the w=30 discrepancy. v0.2's node_count_control INTENTIONALLY
    #     replaces the v0.1 list with one list shared by all windows, so full
    #     equivalence of control quantities is not expected. Topology fields
    #     must still reproduce v0.1 exactly. Keep the failed check disclosed.
    topology_fields = [
        "h2_count", "h1_count", "h2_landscape_l1", "h1_landscape_l1",
        "max_h2_persistence", "h2_betti_0p4", "h2_betti_0p6", "h2_betti_0p8",
    ]
    inconsistent = collections.Counter()
    nn_bad_dates = []
    for d in dates:
        for k in bg.XY_FIELDS:
            if abs(float(grids[30][d][k]) - float(ref[d][k])) > 1e-8:
                inconsistent[k] += 1
                if k == "n_nodes":
                    nn_bad_dates.append(d)
    eligible_audit = json.loads(
        (OUT / "regime_win_xy_eligible_audit.json").read_text(encoding="utf-8"))
    topo_zero = all(
        rep["w30_full_equivalence"]["max_abs_diff_by_field"][k] == 0.0
        for k in topology_fields)
    rep["w30_discrepancy_diagnosis"] = {
        "n_dates_with_any_diff": len(nn_bad_dates),
        "inconsistent_field_counts": dict(inconsistent),
        "year_distribution": dict(collections.Counter(d[:4] for d in nn_bad_dates)),
        "topology_fields_all_zero": topo_zero,
        "eligible_audit_dropped_columns": eligible_audit["n_dropped_columns"],
        "explanation": "v0.2 node_count_control fixes one eligible list across all "
                       "windows; 40 consecutive 2018 dates lose one column each. "
                       "All 8 topology fields still reproduce v0.1 exactly.",
        "sampled_equivalence_blind_spot": "v0.2's 24-date equivalence check did not "
                                          "cover 2018-03, so it reported a false pass",
        "explained_by_parent_spec": bool(
            topo_zero and len(nn_bad_dates) == eligible_audit["n_dropped_columns"]),
    }

    # 3 node-count control: identical eligible list across all windows
    nn_mismatch = sum(
        1 for d in dates
        if len({grids[w][d]["n_nodes"] for w in grids}) != 1)
    rep["node_count_identical_across_windows"] = {
        "n_mismatch_dates": nn_mismatch, "passed": nn_mismatch == 0}

    # 4 determinism: recompute w=10 on 24 sampled dates with CURRENT code
    old_closes, current_closes, _, all_dates = bg.load_xy_prices()
    pos = {d: i for i, d in enumerate(all_dates)}
    eligible = json.loads((OUT / "regime_win_xy_eligible.json").read_text(encoding="utf-8"))
    sample = dates[::max(1, len(dates) // 24)][:24]
    worst = {k: 0.0 for k in bg.XY_FIELDS}
    for d in sample:
        i = pos[d]
        source = old_closes if d < bg.ERA_SWITCH else current_closes
        wd = all_dates[i - W:i + 1]
        cols = [bg._valid_prices(source.get(c, {}), wd) for c in eligible[d]]
        if any(c is None for c in cols):
            raise RuntimeError(f"determinism sample {d}: ineligible column")
        got = bg.xy_features(np.asarray(cols, dtype=float).T)
        for k in bg.XY_FIELDS:
            worst[k] = max(worst[k], abs(float(got[k]) - float(grids[W][d][k])))
    rep["w10_determinism_24_dates"] = {
        "n_sampled_dates": len(sample),
        "max_abs_diff_by_field": worst,
        "passed": all(v < 1e-8 for v in worst.values())}

    rep["reusable"] = (
        rep["w10_determinism_24_dates"]["passed"]
        and rep["node_count_identical_across_windows"]["passed"]
        and rep["w30_discrepancy_diagnosis"]["explained_by_parent_spec"]
        and all(v["blank_or_nonfinite"] == 0 and v["date_set_equals_v0_1"]
                for v in rep["coverage"].values()))
    rep["reusable_note"] = (
        "w30_full_equivalence.passed stays FALSE and is disclosed in full. It is "
        "not a blocker because v0.2 explicitly replaced the eligible-list rule; "
        "the discrepancy is confined to 40 dates / control quantities, while all "
        "8 topology fields reproduce v0.1 exactly. Amended after stage-1 summary "
        "audit and BEFORE any group, significance or verdict result was seen.")
    return rep


# ---------------------------------------------------------------------------
# B. missing A-line w=10
# ---------------------------------------------------------------------------
def stage_b() -> dict:
    cfg = tomllib.loads(CFG_PHTI.read_text(encoding="utf-8"))
    order = int(cfg["distance"]["order_p"])
    norm = cfg["distance"]["internal_norm"]
    outs = []
    for key in ("p16", "p27"):
        pc = cfg["panels"][key]
        t0 = time.time()
        out = bg.phti_worker(key, W, order, norm, list(pc["codes"]), pc["start"])
        src = OUT / out["csv"]
        dst = OUT / f"regime_v03_phti_{key}_w{W}.csv"
        dst.write_bytes(src.read_bytes())
        rows = read_csv(dst.name)
        n_blank_w = sum(1 for r in rows if not r["W_t"].strip())
        outs.append({"panel": key, "window": W, "order_p": order, "norm": norm,
                     "rows": len(rows), "W_t_blank_warmup": n_blank_w,
                     "W_t_finite": sum(1 for r in rows if r["W_t"].strip()),
                     "rows_with_window": out["rows"], "seconds": round(time.time() - t0, 1),
                     "csv": dst.name,
                     "prior_note": "10 state points < 16/27 industry coordinates; "
                                   "H1 constrained, W2 variance inflated; "
                                   "never compare absolute level with w=60"})
    return {"panels": outs}


# ---------------------------------------------------------------------------
# C. B-line H0 hierarchical clustering summaries
# ---------------------------------------------------------------------------
def prim_edges(distance: np.ndarray) -> np.ndarray:
    """Kruskal MST edge weights == finite H0 deaths of the VR filtration.

    Prim in O(n^2); keeps zero-weight edges (unlike sparse nonzero extraction).
    """
    n = distance.shape[0]
    in_tree = np.zeros(n, dtype=bool)
    in_tree[0] = True
    best = distance[0].copy()
    edges = []
    for _ in range(n - 1):
        cand = np.where(in_tree, np.inf, best)
        j = int(np.argmin(cand))
        edges.append(float(best[j]))
        in_tree[j] = True
        np.minimum(best, distance[j], out=best)
    return np.sort(np.asarray(edges, dtype=float))


def corr_distance(returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bit-identical correlation construction to bg.xy_features."""
    x = np.asarray(returns, dtype=float)
    corr = np.corrcoef(x, rowvar=False)
    corr = np.clip((corr + corr.T) / 2.0, -1.0, 1.0)
    np.fill_diagonal(corr, 1.0)
    dist = np.sqrt(np.maximum(0.0, 2.0 * (1.0 - corr)))
    np.fill_diagonal(dist, 0.0)
    return corr, dist


def h0_features(returns: np.ndarray) -> tuple[dict, np.ndarray, np.ndarray]:
    corr, dist = corr_distance(returns)
    edges = prim_edges(dist)
    assert len(edges) == corr.shape[0] - 1, "MST edge count mismatch"
    n = len(edges)
    med_rest = float(np.median(edges[:-1])) if n > 1 else 0.0
    denom = float(np.mean(edges))
    out = {
        "n_nodes": int(corr.shape[0]),
        "xy_h0_death_mean": float(np.mean(edges)),
        "xy_h0_death_median": float(np.median(edges)),
        "xy_h0_death_max": float(edges[-1]),
        "xy_h0_death_p90": float(np.quantile(edges, 0.9)),
        "xy_h0_death_cv": float(np.std(edges, ddof=1) / denom) if denom > 0 else 0.0,
        "xy_h0_top1_over_rest_median": float(edges[-1] / med_rest) if med_rest > 0 else 0.0,
        "xy_h0_components_0p4": int(1 + np.sum(edges > 0.4)),
        "xy_h0_components_0p6": int(1 + np.sum(edges > 0.6)),
        "xy_h0_components_0p8": int(1 + np.sum(edges > 0.8)),
        "xy_avg_corr_w10": float(np.mean(corr[np.triu_indices(corr.shape[0], k=1)])),
        "xy_leading_eig_share_w10": float(np.linalg.eigvalsh(corr)[-1] / corr.shape[0]),
    }
    return out, dist, edges


def stage_c() -> dict:
    old_closes, current_closes, _, all_dates = bg.load_xy_prices()
    pos = {d: i for i, d in enumerate(all_dates)}
    eligible = json.loads((OUT / "regime_win_xy_eligible.json").read_text(encoding="utf-8"))
    dates = sorted(eligible)
    rep = {"n_dates": len(dates), "nominal_window": W,
           "effective_return_observations": W - 1,
           "fisher_z_se_note": "correlation uses W-1=9 daily returns, "
                               "so SE=1/sqrt(9-3)=0.408; the v0.2 spec's "
                               "1/sqrt(W-3)=0.378 was a nominal-window approximation"}

    # C1 equivalence check: MST edge weights vs ripser H0 finite deaths
    checks = []
    sample = dates[::max(1, len(dates) // 24)][:24]
    for d in sample:
        i = pos[d]
        source = old_closes if d < bg.ERA_SWITCH else current_closes
        wd = all_dates[i - W:i + 1]
        cols = [bg._valid_prices(source.get(c, {}), wd) for c in eligible[d]]
        _, dist, edges = h0_features(np.asarray(cols, dtype=float).T)
        dgms = ripser(dist, distance_matrix=True, maxdim=0, thresh=2.0,
                      coeff=2)["dgms"]
        h0 = np.asarray(dgms[0], dtype=float)
        fin = h0[np.isfinite(h0).all(axis=1)]
        deaths = np.sort(fin[:, 1])
        # ripser drops zero-persistence intervals; Prim keeps zero-weight MST
        # edges. Compare strictly positive edges/deaths only.
        nz_edges = edges[edges > 0]
        nz_deaths = deaths[deaths > 0]
        checks.append({"date": d, "n_edges": len(edges),
                       "n_ripser_finite_deaths": len(deaths),
                       "n_positive_edges": len(nz_edges),
                       "n_positive_deaths": len(nz_deaths),
                       "max_abs_diff": float(np.max(np.abs(nz_deaths - nz_edges)))
                       if len(nz_deaths) == len(nz_edges) else None})
    rep["mst_vs_ripser_h0"] = {
        "n_sampled_dates": len(sample),
        "max_abs_diff": max((c["max_abs_diff"] for c in checks
                             if c["max_abs_diff"] is not None), default=None),
        "count_mismatch": sum(1 for c in checks if c["max_abs_diff"] is None),
        "edge_count_match_all_dates": all(
            c["n_positive_edges"] == c["n_positive_deaths"] for c in checks),
        "tolerance": RIPSER_FLOAT32_TOL,
        "tolerance_reason": "cross-implementation check: ripser float32 distance "
                            "matrix vs our float64 Prim; edge/death counts match "
                            "exactly on every sampled date, residual is float32 "
                            "rounding. Same-implementation determinism in stage A "
                            "keeps the stricter 1e-8.",
        "passed": (all(c["max_abs_diff"] is not None
                       and c["max_abs_diff"] < RIPSER_FLOAT32_TOL for c in checks)
                   and all(c["n_positive_edges"] == c["n_positive_deaths"]
                           for c in checks))}
    if not rep["mst_vs_ripser_h0"]["passed"]:
        dump("regime_v03_stage_c_checks.json", checks)
        raise RuntimeError("MST / ripser H0 equivalence failed; stage C aborted")

    # C2 full pass, single process, one price load
    t0 = time.time()
    rows = []
    for k, d in enumerate(dates):
        i = pos[d]
        source = old_closes if d < bg.ERA_SWITCH else current_closes
        wd = all_dates[i - W:i + 1]
        cols, ok = [], True
        for c in eligible[d]:
            r = bg._valid_prices(source.get(c, {}), wd)
            if r is None:
                ok = False
                break
            cols.append(r)
        if not ok or len(cols) < 4:
            continue
        feat, _, _ = h0_features(np.asarray(cols, dtype=float).T)
        rows.append({"date": d, **feat})
        if (k + 1) % 1000 == 0:
            print(f"   h0 progress {k+1}/{len(dates)} {round(time.time()-t0,1)}s",
                  flush=True)
    write_csv("regime_v03_xy_h0_w10.csv", ["date"] + H0_FIELDS, rows)
    rep["output"] = {"csv": "regime_v03_xy_h0_w10.csv", "rows": len(rows),
                     "seconds": round(time.time() - t0, 1)}

    # C3 cross-check control quantities against the v0.2 w=10 summary
    b10 = {r["date"]: r for r in read_csv("regime_win_summaries_xy_10.csv")}
    h0_by_date = {r["date"]: r for r in rows}
    common = sorted(set(h0_by_date) & set(b10))
    dc = max(abs(float(h0_by_date[d]["xy_avg_corr_w10"])
                 - float(b10[d]["industry_average_correlation"])) for d in common)
    de = max(abs(float(h0_by_date[d]["xy_leading_eig_share_w10"])
                 - float(b10[d]["correlation_leading_eigenvalue_share"]))
             for d in common)
    dn = sum(1 for d in common
             if int(b10[d]["n_nodes"]) != int(h0_by_date[d]["n_nodes"]))
    rep["crosscheck_vs_v0_2_w10"] = {
        "n_common_dates": len(common), "max_abs_avg_corr_diff": float(dc),
        "max_abs_leading_eig_diff": float(de), "n_nodes_mismatch": dn,
        "passed": dc < 1e-8 and de < 1e-8 and dn == 0}
    return rep


# ---------------------------------------------------------------------------
# D. line-separated wide table (no group statistics, no verdict)
# ---------------------------------------------------------------------------
LABEL_COLS = [
    "state_v0_primary", "state_v1_benchmark_sse", "state_v2_B2", "state_v3_C2",
    "state_v4_legacy5pct", "crisis_in", "crisis_in_usable", "crisis_event_id",
    "pre5", "pre10", "pre20", "pre_vol_type", "bull_bear_defined",
    "bear_in_crisis",
]


def stage_d() -> dict:
    labels = {r["date"]: r for r in read_csv("regime_daily_labels.csv")}
    a16 = {r["date"]: r for r in read_csv("regime_v03_phti_p16_w10.csv")}
    a27 = {r["date"]: r for r in read_csv("regime_v03_phti_p27_w10.csv")}
    b10 = {r["date"]: r for r in read_csv("regime_win_summaries_xy_10.csv")}
    h0 = {r["date"]: r for r in read_csv("regime_v03_xy_h0_w10.csv")}
    dates = sorted(set(labels) & set(b10) & set(h0))
    a16_cols = [c for c in next(iter(a16.values())) if c != "date"]
    a27_cols = [c for c in next(iter(a27.values())) if c != "date"]
    b_cols = [c for c in next(iter(b10.values())) if c != "date"]
    # These three are already present in the B-line w=10 summary (and were
    # cross-checked above); keep the wide table free of duplicate column names.
    _dup = {"n_nodes", "xy_avg_corr_w10", "xy_leading_eig_share_w10"}
    h0_cols = [c for c in next(iter(h0.values())) if c != "date" and c not in _dup]
    fields = (["date"] + LABEL_COLS
              + [f"a16_{c}" for c in a16_cols]
              + [f"a27_{c}" for c in a27_cols]
              + [f"b_{c}" for c in b_cols]
              + [f"b_{c}" for c in h0_cols]
              + ["line_a16_present", "line_a27_present"])
    rows = []
    for d in dates:
        r = {"date": d}
        for c in LABEL_COLS:
            r[c] = labels[d].get(c, "")
        for c in a16_cols:
            r[f"a16_{c}"] = a16.get(d, {}).get(c, "")
        for c in a27_cols:
            r[f"a27_{c}"] = a27.get(d, {}).get(c, "")
        for c in b_cols:
            r[f"b_{c}"] = b10[d].get(c, "")
        for c in h0_cols:
            r[f"b_{c}"] = h0[d].get(c, "")
        r["line_a16_present"] = int(d in a16)
        r["line_a27_present"] = int(d in a27)
        rows.append(r)
    write_csv("regime_v03_split_wide.csv", fields, rows)
    return {
        "csv": "regime_v03_split_wide.csv", "rows": len(rows),
        "n_columns": len(fields), "date_min": dates[0], "date_max": dates[-1],
        "a16_coverage": sum(r["line_a16_present"] for r in rows),
        "a27_coverage": sum(r["line_a27_present"] for r in rows),
        "prefix_rule": "a16_/a27_ = PHTI state cloud; b_ = XY correlation network; "
                       "identically named quantities must never be merged",
        "no_group_statistics": True, "no_significance_test": True,
        "no_verdict": True,
    }


def main() -> None:
    spec = tomllib.loads(CFG_V03.read_text(encoding="utf-8"))
    manifest = {
        "spec": "config/regime_split_check_v0.3.toml",
        "stage": 1,
        "d3_status": spec["user_decisions"]["D3_short_events"],
        "main_judgement_blocked": spec["user_decisions"]["D3_short_events"] == "UNDECIDED",
        "performance_evaluated": False, "equity_index_loaded": False,
        "gate1_test_read": False, "overwrite_v0_1_or_v0_2": False,
        "v0_2_xy_grid_recomputed": False,
    }
    t0 = time.time()
    print("[A] audit v0.2 summaries", flush=True)
    manifest["A_audit"] = stage_a()
    print("   reusable:", manifest["A_audit"]["reusable"], flush=True)
    if not manifest["A_audit"]["reusable"]:
        dump("regime_v03_stage1_manifest.json", manifest)
        raise RuntimeError("v0.2 summaries failed audit; stage 1 aborted")

    print("[B] A-line w=10 PHTI summaries", flush=True)
    manifest["B_phti_w10"] = stage_b()
    for p in manifest["B_phti_w10"]["panels"]:
        print("  ", p["panel"], p["rows_with_window"], "windows,",
              p["W_t_finite"], "finite W_t", flush=True)

    print("[C] B-line H0 summaries (MST == VR H0 deaths)", flush=True)
    manifest["C_xy_h0"] = stage_c()
    print("   equivalence:", manifest["C_xy_h0"]["mst_vs_ripser_h0"]["passed"],
          "crosscheck:", manifest["C_xy_h0"]["crosscheck_vs_v0_2_w10"]["passed"],
          flush=True)

    print("[D] line-separated wide table", flush=True)
    manifest["D_wide"] = stage_d()
    print("  ", manifest["D_wide"]["rows"], "rows /",
          manifest["D_wide"]["n_columns"], "cols", flush=True)

    manifest["elapsed_seconds"] = round(time.time() - t0, 1)
    dump("regime_v03_stage1_manifest.json", manifest)
    print("DONE", manifest["elapsed_seconds"], "s", flush=True)


if __name__ == "__main__":
    main()
