"""Two READ-ONLY diagnostics requested after the signal-trigger IC matrix.

Q1  Event-level examination of the 42 k=1 clusters (an event study instead of
    392 repeated signal-days), including a randomisation/permutation test and
    an event-time price path.
Q2  Can the N threshold move with the drift?  A pre-registered grid of CAUSAL
    rolling-percentile thresholds (history up to and including t only), plus a
    node-count-scaled control and an explicitly FORBIDDEN look-ahead contrast.

Nothing here is a strategy, a replication, or a confirmatory result.  No
existing output file is modified.  Every cell is disclosed; no threshold is
selected by its IC or return.  Gate 1 stays paused; the 2025 final test is not
read; Gate 2 is not started.

Outputs (all under outputs/):
  xy_event_study.json, xy_event_study_clusters.csv, xy_event_study.png
  xy_adaptive_threshold.json, xy_adaptive_threshold_grid.csv,
  xy_adaptive_threshold.png
"""
from __future__ import annotations

import csv
import json
import math
from datetime import date, datetime
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
FEATURE_CSV = OUT / "xy_corrected_sw193_ifind_peak_features.csv"
WIND_CSV = OUT / "xy_wind_all_a_daily.csv"

EVENT_JSON = OUT / "xy_event_study.json"
EVENT_CSV = OUT / "xy_event_study_clusters.csv"
EVENT_FIG = OUT / "xy_event_study.png"
ADAPT_JSON = OUT / "xy_adaptive_threshold.json"
ADAPT_CSV = OUT / "xy_adaptive_threshold_grid.csv"
ADAPT_FIG = OUT / "xy_adaptive_threshold.png"

START, END = "2015-07-01", "2025-05-30"
HORIZONS = (1, 5, 10, 20, 40)
GAP_DAYS = 10                     # calendar days, identical to prior scripts
BLOCK, N_BOOT, SEED = 20, 1000, 20261108
N_EVENT_BOOT, N_PERM = 10000, 5000
WINDOWS = (60, 120, 250)          # trading days of trailing history
PERCENTILES = (0.05, 0.10, 0.20)
NODE_GAMMAS = (1, 2, 3)
NODE_REF = 100.0                  # early-period node count, k_ref = 1
SEGMENTS = (("2015-2020", "2015", "2020"), ("2021-2025", "2021", "2025"))


# ---------------------------------------------------------------- helpers
def pearson(x: np.ndarray, y: np.ndarray) -> float:
    xc, yc = x - x.mean(), y - y.mean()
    den = math.sqrt(float(xc @ xc) * float(yc @ yc))
    return float(xc @ yc / den) if den > 0 else float("nan")


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    return pearson(rankdata(x), rankdata(y))


def finite_or_none(v):
    if v is None:
        return None
    f = float(v)
    return f if math.isfinite(f) else None


BOOT_DEGENERATE: list[dict] = []


def block_bootstrap_ci(x, y, tag: str, block: int = BLOCK,
                       repetitions: int = N_BOOT, seed: int = SEED):
    n = len(x)
    rng = np.random.default_rng(seed)
    starts_max = n - block + 1
    n_blocks = math.ceil(n / block)
    values = []
    for _ in range(repetitions):
        starts = rng.integers(0, starts_max, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        values.append(pearson(x[idx], y[idx]))
    finite = [v for v in values if math.isfinite(v)]
    bad = len(values) - len(finite)
    if bad:
        BOOT_DEGENERATE.append({"tag": tag, "degenerate_draws": bad,
                                "total_draws": len(values)})
    if len(finite) < 10:
        return [float("nan"), float("nan")]
    return [float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))]


def describe(values: np.ndarray) -> dict:
    v = np.asarray([x for x in values if x is not None and math.isfinite(float(x))],
                   dtype=float)
    if len(v) == 0:
        return {"n": 0}
    return {
        "n": int(len(v)), "mean": float(v.mean()), "median": float(np.median(v)),
        "std_ddof1": float(v.std(ddof=1)) if len(v) > 1 else None,
        "min": float(v.min()), "max": float(v.max()),
        "win_rate": float((v > 0).mean()),
        "q25": float(np.quantile(v, 0.25)), "q75": float(np.quantile(v, 0.75)),
    }


def event_bootstrap_ci(values: np.ndarray, repetitions: int = N_EVENT_BOOT,
                       seed: int = SEED + 7):
    v = np.asarray([x for x in values if x is not None and math.isfinite(float(x))],
                   dtype=float)
    if len(v) < 3:
        return [None, None]
    rng = np.random.default_rng(seed)
    means = v[rng.integers(0, len(v), size=(repetitions, len(v)))].mean(axis=1)
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def read_inputs():
    with FEATURE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        features = [r for r in csv.DictReader(handle) if r["date"] <= END]
    with WIND_CSV.open(encoding="utf-8-sig", newline="") as handle:
        wind_rows = list(csv.DictReader(handle))
    wind = {r["date"]: (float(r["open"]), float(r["close"])) for r in wind_rows}
    missing = [r["date"] for r in features if r["date"] not in wind]
    assert not missing, f"feature dates missing from Wind daily: {missing[:5]}"
    dates = [r["date"] for r in features]
    wind_dates = [r["date"] for r in wind_rows]
    wind_index = {d: i for i, d in enumerate(wind_dates)}
    N = np.asarray([float(r["h2_count"]) for r in features])
    nodes = np.asarray([float(r["n_nodes"]) for r in features])
    op = np.asarray([wind[d][0] for d in dates])
    cl = np.asarray([wind[d][1] for d in dates])
    wop = np.asarray([float(r["open"]) for r in wind_rows])
    return dates, N, nodes, op, cl, wind_dates, wind_index, wop


def forward_returns(op, cl, h):
    """Main convention (identical to ic_diagnostics.py / signal_trigger_ic_matrix.py):
    signal at close t -> entry at open t+1 -> exit at open t+1+h, where t+1 is
    the NEXT ROW OF THE FEATURE CALENDAR."""
    n = len(op)
    ro = np.full(n, np.nan)
    rc = np.full(n, np.nan)
    ro[:n - h - 1] = op[h + 1:] / op[1:n - h] - 1.0
    rc[:n - h] = cl[h:] / cl[:n - h] - 1.0
    return ro, rc


def forward_returns_wind_calendar(dates, wind_index, wop, h):
    """Sensitivity: use the FULL Wind trading calendar for t+1 and t+1+h."""
    n = len(dates)
    ro = np.full(n, np.nan)
    for i, d in enumerate(dates):
        j = wind_index[d]
        a, b = j + 1, j + 1 + h
        if b < len(wop):
            ro[i] = wop[b] / wop[a] - 1.0
    return ro


def clusters_from_flag(dates, flag, report):
    idx = [i for i in range(len(dates)) if report[i] and flag[i]]
    dts = [datetime.fromisoformat(d).date() for d in dates]
    clusters = []
    for i in idx:
        if not clusters or (dts[i] - dts[clusters[-1][-1]]).days > GAP_DAYS:
            clusters.append([i])
        else:
            clusters[-1].append(i)
    return clusters


def cluster_start_flag(dates, flag, report):
    out = np.zeros(len(dates), dtype=float)
    for c in clusters_from_flag(dates, flag, report):
        out[c[0]] = 1.0
    return out


def causal_midrank_percentile(series: np.ndarray, window: int) -> np.ndarray:
    """ECDF mid-rank of series[t] inside the TRAILING window [t-W+1, t].

    Only information available at the close of t is used. Ties are split with
    the 0.5 convention so that a discrete integer series does not produce a
    spuriously huge trigger rate. Undefined (NaN) before the window is full.
    """
    out = np.full(len(series), np.nan)
    for t in range(window - 1, len(series)):
        w = series[t - window + 1:t + 1]
        cur = series[t]
        less = int(np.count_nonzero(w < cur))
        equal = int(np.count_nonzero(w == cur))
        out[t] = (less + 0.5 * equal) / window
    return out


# ---------------------------------------------------------------- Q1
def event_study(dates, N, nodes, op, cl, wind_index, wop):
    report = np.asarray([START <= d <= END for d in dates])
    flag = N <= 1
    clusters = clusters_from_flag(dates, flag, report)
    fwd = {h: forward_returns(op, cl, h) for h in HORIZONS}
    ro20, rc20 = fwd[20]
    usable20 = report & np.isfinite(ro20)
    date_objs = [datetime.fromisoformat(d).date() for d in dates]

    rows = []
    for ci, c in enumerate(clusters, 1):
        i, j = c[0], c[-1]
        gap = None
        if ci > 1:
            gap = (date_objs[i] - date_objs[clusters[ci - 2][-1]]).days
        rec = {
            "event_no": ci, "start": dates[i], "end": dates[j],
            "cluster_days": len(c),
            "calendar_span_days": (date_objs[j] - date_objs[i]).days,
            "calendar_gap_from_prev_cluster": gap,
            "N_at_start": int(N[i]), "n_nodes_at_start": int(nodes[i]),
            "entry_date_t_plus_1": dates[i + 1] if i + 1 < len(dates) else None,
            "entry_open": float(op[i + 1]) if i + 1 < len(dates) else None,
            "year": dates[i][:4],
        }
        for h in HORIZONS:
            ro, rc = fwd[h]
            rec[f"fwd{h}_open"] = finite_or_none(ro[i]) if i < len(ro) else None
            rec[f"fwd{h}_close"] = finite_or_none(rc[i]) if i < len(rc) else None
        rows.append(rec)

    # three aggregation conventions -------------------------------------
    daily_idx = [i for i in range(len(dates)) if report[i] and flag[i] and np.isfinite(ro20[i])]
    daily_vals = ro20[daily_idx]
    per_cluster_means = []
    for c in clusters:
        vals = [ro20[i] for i in c if np.isfinite(ro20[i])]
        if vals:
            per_cluster_means.append(float(np.mean(vals)))
    start_idx = [c[0] for c in clusters if np.isfinite(ro20[c[0]])]
    start_vals = ro20[start_idx]
    unconditional = ro20[usable20]

    agg = {
        "daily_all_signal_days": describe(daily_vals),
        "cluster_equal_weighted": describe(np.asarray(per_cluster_means)),
        "cluster_start_only": describe(start_vals),
        "unconditional_all_report_days": describe(unconditional),
    }
    agg["cluster_start_only"]["ci95_mean_iid_bootstrap"] = event_bootstrap_ci(start_vals)
    agg["daily_all_signal_days"]["ci95_mean_iid_bootstrap"] = event_bootstrap_ci(daily_vals)
    agg["cluster_equal_weighted"]["ci95_mean_iid_bootstrap"] = event_bootstrap_ci(
        np.asarray(per_cluster_means))

    # event-window overlap disclosure for h=20 -----------------------------
    overlap_pairs = 0
    for a in range(len(start_idx)):
        for b in range(a + 1, len(start_idx)):
            if abs(start_idx[b] - start_idx[a]) <= 20:
                overlap_pairs += 1

    # permutation tests ---------------------------------------------------
    rng = np.random.default_rng(SEED + 101)
    pool = np.asarray([i for i in range(len(dates)) if usable20[i]], dtype=int)
    n_ev = len(start_vals)
    actual = float(start_vals.mean())
    simple = np.empty(N_PERM)
    for b in range(N_PERM):
        pick = rng.choice(pool, size=n_ev, replace=False)
        simple[b] = ro20[pick].mean()

    matched, attempts = [], 0
    while len(matched) < N_PERM and attempts < N_PERM * 4:
        attempts += 1
        cand = np.sort(rng.choice(pool, size=min(len(pool), n_ev * 30), replace=False))
        chosen, last = [], None
        for i in cand:
            if last is None or (date_objs[i] - last).days > GAP_DAYS:
                chosen.append(i)
                last = date_objs[i]
                if len(chosen) == n_ev:
                    break
        if len(chosen) == n_ev:
            matched.append(float(ro20[np.asarray(chosen)].mean()))
    matched = np.asarray(matched)
    hist_counts, hist_edges = np.histogram(simple, bins=60)
    perm = {
        "actual_event_mean": actual,
        "simple_random_histogram": {
            "counts": [int(v) for v in hist_counts],
            "bin_edges": [float(v) for v in hist_edges],
            "note": "the actual 5000 permutation draws, not a reconstructed density",
        },
        "simple_random": {
            "repetitions": N_PERM, "null_mean": float(simple.mean()),
            "null_sd": float(simple.std(ddof=1)),
            "p_one_sided_ge": float((simple >= actual).mean()),
            "p_two_sided": float(2 * min((simple >= actual).mean(),
                                         (simple <= actual).mean())),
            "null_q025": float(np.quantile(simple, 0.025)),
            "null_q975": float(np.quantile(simple, 0.975)),
        },
        "gap_matched_random": {
            "repetitions": len(matched), "draw_attempts": attempts,
            "null_mean": float(matched.mean()) if len(matched) else None,
            "null_sd": float(matched.std(ddof=1)) if len(matched) > 1 else None,
            "p_one_sided_ge": float((matched >= actual).mean()) if len(matched) else None,
            "p_two_sided": float(2 * min((matched >= actual).mean(),
                                         (matched <= actual).mean())) if len(matched) else None,
            "note": "random 42 start days constrained to >10 calendar days apart, "
                    "matching the cluster rule; still not a full time-series "
                    "block permutation",
        },
    }

    # event-time path -----------------------------------------------------
    path_j = list(range(-20, 41))
    paths = []
    for c in clusters:
        i = c[0]
        base_i = i + 1
        if base_i >= len(op):
            continue
        p = []
        usable = True
        for jj in path_j:
            k = base_i + jj
            if k < 0 or k >= len(op):
                usable = False
                break
            p.append(op[k] / op[base_i] - 1.0)
        if usable:
            paths.append(p)
    mean_path = np.asarray(paths).mean(axis=0) if paths else np.asarray([])

    # by-year and correlations -------------------------------------------
    by_year = []
    for yr in sorted({r["year"] for r in rows}):
        sub = [r for r in rows if r["year"] == yr and r["fwd20_open"] is not None]
        by_year.append({
            "year": yr, "events": len([r for r in rows if r["year"] == yr]),
            "events_with_fwd20": len(sub),
            "mean_fwd20": float(np.mean([r["fwd20_open"] for r in sub])) if sub else None,
            "win_rate_fwd20": float(np.mean([r["fwd20_open"] > 0 for r in sub])) if sub else None,
        })

    lens = np.asarray([r["cluster_days"] for r in rows if r["fwd20_open"] is not None])
    rets = np.asarray([r["fwd20_open"] for r in rows if r["fwd20_open"] is not None])
    nstart = np.asarray([r["N_at_start"] for r in rows if r["fwd20_open"] is not None])
    corrs = {
        "spearman_cluster_length_vs_fwd20": finite_or_none(spearman(lens, rets)),
        "spearman_N_at_start_vs_fwd20": finite_or_none(spearman(nstart, rets)),
    }

    # reconcile with the earlier N=0 cluster-start result (-1.26%) ----------
    k0_clusters = clusters_from_flag(dates, N <= 0, report)
    k0_vals = np.asarray([ro20[c[0]] for c in k0_clusters
                          if np.isfinite(ro20[c[0]])])
    n0_vals = np.asarray([r["fwd20_open"] for r in rows
                          if r["fwd20_open"] is not None and r["N_at_start"] == 0])
    n1_vals = np.asarray([r["fwd20_open"] for r in rows
                          if r["fwd20_open"] is not None and r["N_at_start"] == 1])
    start_decomp = {
        "k0_all_cluster_starts": describe(k0_vals),
        "k1_starts_with_N0_at_start": describe(n0_vals),
        "k1_starts_with_N1_at_start": describe(n1_vals),
        "note": "Earlier 2x2 audit reported about -1.26% for the 35 k=0 cluster "
                "starts. This event study uses k=1 (42 clusters), whose starts "
                "include N=1 days and whose cluster boundaries differ. The two "
                "numbers describe different samples, not a contradiction."
    }

    # calendar audit -------------------------------------------------------
    ro20_wind = forward_returns_wind_calendar(dates, wind_index, wop, 20)
    m = usable20 & np.isfinite(ro20_wind)
    diff = np.abs(ro20[m] - ro20_wind[m])
    calendar_audit = {
        "feature_aligned_days": len(dates),
        "wind_trading_days": len(wind_index),
        "wind_only_days": sorted(set(wind_index) - set(dates)),
        "n_wind_only_days": len(set(wind_index) - set(dates)),
        "comparable_days": int(m.sum()),
        "mean_abs_diff_fwd20": float(diff.mean()),
        "max_abs_diff_fwd20": float(diff.max()),
        "corr_between_calendars": finite_or_none(pearson(ro20[m], ro20_wind[m])),
        "ic_feature_calendar": finite_or_none(pearson(-N[m], ro20[m])),
        "ic_wind_calendar": finite_or_none(pearson(-N[m], ro20_wind[m])),
        "note": "Main results use the FEATURE calendar, identical to all prior "
                "diagnostics. The Wind-calendar column is a sensitivity check only.",
    }

    return {
        "generated_on": str(date.today()),
        "status": "exploratory read-only event study; not a strategy result; "
                  "not out-of-sample; not a replication",
        "question": "If we examine the 42 k=1 events instead of 392 signal-days, "
                    "what does the evidence look like?",
        "definition": {
            "signal": "t close: N_t <= 1", "entry": "open of t+1 (feature calendar)",
            "cluster_rule": "successive trigger days >10 CALENDAR days apart form a new event",
            "forward_return": "open[t+1+h]/open[t+1]-1",
            "horizons": list(HORIZONS),
            "report_days": int(report.sum()),
            "signal_days": int((flag & report).sum()),
            "event_clusters": len(clusters),
        },
        "aggregation_conventions": agg,
        "daily_vs_event_lift": {
            "daily_mean_minus_unconditional": float(daily_vals.mean() - unconditional.mean()),
            "cluster_equal_mean_minus_unconditional": float(
                np.mean(per_cluster_means) - unconditional.mean()),
            "cluster_start_mean_minus_unconditional": float(actual - unconditional.mean()),
            "daily_mean_minus_cluster_start_mean": float(daily_vals.mean() - actual),
        },
        "event_boot_note": "i.i.d. bootstrap over events; overlapping 20-day forward "
                           "windows make this interval somewhat too narrow",
        "overlapping_h20_event_pairs": overlap_pairs,
        "overlapping_h20_event_pairs_out_of": len(start_idx) * (len(start_idx) - 1) // 2,
        "permutation_test": perm,
        "event_time_path": {
            "j_from_entry": path_j,
            "mean_relative_open_path": [finite_or_none(v) for v in mean_path],
            "n_events_in_path": len(paths),
            "definition": "mean of open[entry+j]/open[entry]-1 over event clusters; "
                          "NOT a tradable return, used only to show the shape",
        },
        "by_year": by_year,
        "cluster_correlations": corrs,
        "k0_vs_k1_start_decomposition": start_decomp,
        "calendar_audit": calendar_audit,
        "events": rows,
        "gate_status": "Gate 1 paused; 2025 final test not read; Gate 2 not started.",
    }, rows


# ---------------------------------------------------------------- Q2
def adaptive_threshold_study(dates, N, nodes, op, cl):
    report = np.asarray([START <= d <= END for d in dates])
    fwd = {h: forward_returns(op, cl, h)[0] for h in HORIZONS}
    ro20 = fwd[20]
    usable20 = report & np.isfinite(ro20)
    unconditional = ro20[usable20]
    uncond_mean = float(unconditional.mean())
    uncond_win = float((unconditional > 0).mean())
    year_arr = np.asarray([d[:4] for d in dates])

    # drift attribution (why node-scaling alone cannot work) ---------------
    drift = {"segment_stats": []}
    for label, a, b in (("all-report", "0000", "9999"),) + SEGMENTS:
        m = report & (year_arr >= a) & (year_arr <= b)
        drift["segment_stats"].append({
            "segment": label, "n": int(m.sum()),
            "mean_N": float(N[m].mean()), "median_N": float(np.median(N[m])),
            "mean_n_nodes": float(nodes[m].mean()),
            "corr_N_vs_nodes": finite_or_none(pearson(N[m], nodes[m])),
        })
    drift["by_year"] = []
    for yr in sorted(set(year_arr[report])):
        m = report & (year_arr == yr)
        drift["by_year"].append({
            "year": yr, "mean_N": float(N[m].mean()),
            "median_N": float(np.median(N[m])),
            "mean_n_nodes": float(nodes[m].mean()),
            "share_N_le_1": float((N[m] <= 1).mean()),
        })

    # build the pre-registered signal grid --------------------------------
    pct_N = {W: causal_midrank_percentile(N, W) for W in WINDOWS}
    pct_NN = {W: causal_midrank_percentile(N / nodes, W) for W in WINDOWS}
    specs = []
    for family, table in (("roll_N", pct_N), ("roll_N_per_node", pct_NN)):
        for W in WINDOWS:
            for p in PERCENTILES:
                sig = (table[W] <= p).astype(float)
                sig[~np.isfinite(table[W])] = 0.0
                specs.append({
                    "name": f"{family}_W{W}_p{p:g}", "family": family,
                    "window_days": W, "percentile": p, "signal": sig,
                    "status": "preregistered",
                })
    specs.append({
        "name": "fixed_N<=1_BASELINE", "family": "fixed", "window_days": None,
        "percentile": None, "signal": (N <= 1).astype(float),
        "status": "baseline",
    })

    # node-count-scaled thresholds (the user's literal first idea) --------
    node_scaled = []
    for gamma in NODE_GAMMAS:
        k_t = (nodes / NODE_REF) ** gamma
        sig = (N <= k_t).astype(float)
        later = report & (year_arr >= "2021") & (sig > 0) & np.isfinite(ro20)
        node_scaled.append({
            "gamma": gamma, "threshold_at_100_nodes": 1.0,
            "threshold_at_127_nodes": float((127.0 / NODE_REF) ** gamma),
            "signal_days_report": int((report & (sig > 0)).sum()),
            "trigger_share_report": float((report & (sig > 0)).sum() / report.sum()),
            "signal_days_2021_2025": int(later.sum()),
            "mean_fwd20_on_signal": float(ro20[report & (sig > 0) & np.isfinite(ro20)].mean())
            if (report & (sig > 0) & np.isfinite(ro20)).any() else None,
        })

    grid_rows = []
    for spec in specs:
        sig = spec["signal"]
        name = spec["name"]
        trig = report & (sig > 0)
        clusters = clusters_from_flag(dates, sig, report)
        starts = np.asarray([c[0] for c in clusters], dtype=int)
        starts_valid = [i for i in starts if np.isfinite(ro20[i])]
        ev_vals = ro20[starts_valid] if starts_valid else np.asarray([])
        on_vals = ro20[trig & np.isfinite(ro20)]

        row = {
            "name": name, "family": spec["family"], "status": spec["status"],
            "window_days": spec["window_days"], "percentile": spec["percentile"],
            "signal_days_report": int(trig.sum()),
            "trigger_share_report": float(trig.sum() / report.sum()),
            "event_clusters": len(clusters),
            "event_starts_with_fwd20": len(starts_valid),
            "signal_days_2021_2025": int((trig & (year_arr >= "2021")).sum()),
            "event_clusters_2021_2025": len([c for c in clusters
                                            if dates[c[0]][:4] >= "2021"]),
            "last_trigger_date": dates[int(np.where(trig)[0][-1])] if trig.any() else None,
            "mean_fwd20_on_signal": float(on_vals.mean()) if len(on_vals) else None,
            "win_rate_fwd20_on_signal": float((on_vals > 0).mean()) if len(on_vals) else None,
            "lift_vs_unconditional": float(on_vals.mean() - uncond_mean) if len(on_vals) else None,
            "mean_fwd20_on_event_starts": float(ev_vals.mean()) if len(ev_vals) else None,
            "win_rate_fwd20_on_event_starts": float((ev_vals > 0).mean()) if len(ev_vals) else None,
        }
        for h in HORIZONS:
            y = fwd[h]
            m = report & np.isfinite(y)
            row[f"ic_h{h}"] = finite_or_none(pearson(sig[m], y[m]))
        ci = block_bootstrap_ci(sig[usable20], ro20[usable20], f"{name}|h20")
        row["ci95_h20_lo"] = finite_or_none(ci[0])
        row["ci95_h20_hi"] = finite_or_none(ci[1])
        row["ci95_h20_crosses_zero"] = (None if row["ci95_h20_lo"] is None
                                        else bool(row["ci95_h20_lo"] <= 0 <= row["ci95_h20_hi"]))
        row["ic_h20_spearman"] = finite_or_none(spearman(sig[usable20], ro20[usable20]))
        row["by_year_trigger_share"] = {
            yr: float((trig & (year_arr == yr)).sum() / (report & (year_arr == yr)).sum())
            for yr in sorted(set(year_arr[report]))
        }
        grid_rows.append(row)

    # FORBIDDEN look-ahead contrast ---------------------------------------
    N_report = N[report]
    lookahead = []
    for p in PERCENTILES:
        q = float(np.quantile(N_report, p))
        sig = (N <= q).astype(float)
        m = report & np.isfinite(ro20)
        on = ro20[m & (sig > 0)]
        lookahead.append({
            "percentile": p, "full_sample_quantile_of_N": q,
            "signal_days_report": int((m & (sig > 0)).sum()),
            "ic_h20": finite_or_none(pearson(sig[m], ro20[m])),
            "mean_fwd20_on_signal": float(on.mean()) if len(on) else None,
            "status": "FORBIDDEN_LOOKAHEAD_ILLUSTRATION_DO_NOT_USE",
            "reason": "the quantile uses N from the entire 2015-2025 report "
                      "period, including dates AFTER t; this leaks future "
                      "information and would not be implementable in live use",
        })

    # family-wise max-statistic test: can the two non-crossing cells be called
    # a discovery, or are they what 18 simultaneous tests produce by chance?
    prereg_specs = [s for s in specs if s["status"] == "preregistered"]
    sig_mat = np.column_stack([s["signal"][usable20] for s in prereg_specs])
    yy = ro20[usable20]
    nn = len(yy)
    sigc = sig_mat - sig_mat.mean(axis=0)
    ssd = np.sqrt((sigc ** 2).sum(axis=0))
    yc0 = yy - yy.mean()
    ysd = math.sqrt(float(yc0 @ yc0))
    obs = (sigc.T @ yc0) / (ssd * ysd)
    obs_max = float(np.nanmax(obs))
    argmax = prereg_specs[int(np.nanargmax(obs))]["name"]
    rng_j = np.random.default_rng(SEED + 211)
    n_joint = 2000
    null_max = np.empty(n_joint)
    for b in range(n_joint):
        shift = int(rng_j.integers(1, nn))
        ysc = np.roll(yy, shift) - yy.mean()
        null_max[b] = np.nanmax((sigc.T @ ysc) / (ssd * math.sqrt(float(ysc @ ysc))))
    joint = {
        "method": "random circular shift of the whole forward-return series; "
                  "preserves return autocorrelation and the correlation structure "
                  "among the 18 signals, but breaks signal/return alignment. "
                  "Max-IC across all cells controls family-wise error.",
        "repetitions": n_joint, "seed": SEED + 211,
        "n_cells": len(prereg_specs),
        "observed_max_ic": obs_max, "observed_argmax_cell": argmax,
        "null_max_mean": float(null_max.mean()),
        "null_max_q95": float(np.quantile(null_max, 0.95)),
        "p_family_wise": float((null_max >= obs_max).mean()),
        "bonferroni_alpha_per_cell": 0.05 / len(prereg_specs),
        "limitation": "circular shifting leaves a seam at the wrap point; it is a "
                      "diagnostic, not a formal proof of no effect",
    }

    prereg = {
        "grid_fixed_before_viewing_results": True,
        "causal_rule": "signal_t = 1[ midrank_ECDF(N_t | N_{t-W+1..t}) <= p ]; "
                       "no value after t is ever used; warm-up uses 2012-12-31 "
                       "onward feature history, so the whole report period is covered",
        "ties": "midrank (less + 0.5*equal)/W avoids tie-inflated trigger rates",
        "families": ["causal rolling percentile of N",
                     "causal rolling percentile of N/n_nodes (size-normalised control)"],
        "windows": list(WINDOWS), "percentiles": list(PERCENTILES),
        "n_preregistered_cells": 18, "baseline_cells": 1,
        "horizons": list(HORIZONS),
        "bootstrap": {"method": "paired 20-day moving-block", "repetitions": N_BOOT,
                      "seed": SEED, "only_h20": True},
        "selection_rule": "every cell reported; no threshold or window chosen by IC "
                          "or return; no headline promotion of any cell",
        "unconditional_mean_fwd20": uncond_mean,
        "unconditional_win_rate_fwd20": uncond_win,
        "usable_h20_days": int(usable20.sum()),
    }
    return {
        "generated_on": str(date.today()),
        "status": "exploratory read-only diagnostic; not a strategy, not a "
                  "replication, not out-of-sample, not a confirmatory result",
        "question": "If N drifts upward, can the threshold move with it?",
        "preregistration": prereg,
        "drift_attribution": drift,
        "node_count_scaled_control": node_scaled,
        "grid": grid_rows,
        "joint_max_statistic_test": joint,
        "forbidden_lookahead_contrast": lookahead,
        "bootstrap_degenerate_draws": BOOT_DEGENERATE,
        "interpretation": {
            "semantic_cost": "A rolling low-percentile rule means 'N is low relative "
                             "to its own recent history', NOT 'there are almost no H2 "
                             "holes'. It is no longer a replication of the original "
                             "absolute N<=1 rule.",
            "adaptation_lag": "After a persistent upward jump in N, a rolling window "
                              "needs up to W days to rebuild its baseline; during that "
                              "time the signal is silent.",
            "coverage_vs_validity": "Restoring late-period triggers only fixes coverage. "
                                    "It does not restore the original topological meaning "
                                    "and does not by itself create predictive validity.",
            "multiple_comparison": "18 preregistered cells x multiple horizons; no "
                                   "family-wise correction; any isolated interval that "
                                   "excludes zero must not be called a discovery.",
            "in_sample_only": "The rule is fitted to the full in-sample history of N; "
                              "an honest out-of-sample test would require the rule and "
                              "its parameters to be frozen before the test period.",
        },
        "gate_status": "Gate 1 paused; 2025 final test not read; Gate 2 not started.",
    }, grid_rows, pct_N


# ---------------------------------------------------------------- figures
def figure_events(payload, rows):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    red, green, blue, grey = "#c0392b", "#1e8449", "#2c5f8a", "#7f8c8d"

    ax = axes[0, 0]
    vals = [r["fwd20_open"] for r in rows]
    xv = np.arange(1, len(vals) + 1)
    ax.bar(xv, [0 if v is None else v for v in vals],
           color=[grey if v is None else (red if v > 0 else green) for v in vals],
           width=0.8)
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_title("(a) 42 events: forward 20d open-to-open return", fontsize=11)
    ax.set_xlabel("event no. (chronological)")
    ax.set_ylabel("return")
    ax.grid(alpha=0.25)

    ax = axes[0, 1]
    p = payload["event_time_path"]
    ax.plot(p["j_from_entry"], p["mean_relative_open_path"], color=blue, lw=2,
            label="mean event path (n=%d)" % p["n_events_in_path"])
    ax.axhline(0, color="#333", lw=0.8)
    ax.axvline(0, color=grey, ls="--", lw=1, label="entry (j=0)")
    ax.set_title("(b) Event-time mean price path (not a tradable return)", fontsize=11)
    ax.set_xlabel("trading days from entry open")
    ax.set_ylabel("open[j]/open[entry] - 1")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    ax = axes[1, 0]
    hist = payload["permutation_test"]["simple_random_histogram"]
    edges = np.asarray(hist["bin_edges"])
    centers = (edges[:-1] + edges[1:]) / 2
    ax.bar(centers, hist["counts"], width=edges[1] - edges[0],
           color="#b8c6d1", edgecolor="none",
           label="5000 actual random-42 draws")
    ax.axvline(payload["permutation_test"]["actual_event_mean"], color=red, lw=2,
               label="actual event mean")
    ax.set_title("(c) Permutation null vs actual event mean", fontsize=11)
    ax.set_xlabel("mean forward 20d return")
    ax.set_ylabel("frequency")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    ax = axes[1, 1]
    agg = payload["aggregation_conventions"]
    labels = ["daily\n392 days", "cluster-equal\n42 clusters", "event start\n40 events",
              "unconditional\n2370 days"]
    means = [agg["daily_all_signal_days"]["mean"],
             agg["cluster_equal_weighted"]["mean"],
             agg["cluster_start_only"]["mean"],
             agg["unconditional_all_report_days"]["mean"]]
    colors = [blue, "#8e6bbf", red, grey]
    ax.bar(labels, means, color=colors)
    ax.axhline(0, color="#333", lw=0.8)
    for i, v in enumerate(means):
        ax.text(i, v + (0.0008 if v >= 0 else -0.0018), f"{v:+.2%}",
                ha="center", fontsize=9)
    ax.set_title("(d) Same signal, three aggregation conventions", fontsize=11)
    ax.set_ylabel("mean forward 20d return")
    ax.grid(alpha=0.25, axis="y")

    fig.suptitle("Q1  Event-level examination of k=1 triggers (in-sample diagnostic)",
                 fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(EVENT_FIG, dpi=130, bbox_inches="tight")
    plt.close(fig)


def figure_adaptive(payload, dates, N, nodes, pct_N):
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9))
    red, green, blue, grey, orange = "#c0392b", "#1e8449", "#2c5f8a", "#7f8c8d", "#d98c1f"
    report = np.asarray([START <= d <= END for d in dates])
    idx = np.where(report)[0]
    x = np.arange(len(idx))

    ax = axes[0, 0]
    ax.plot(x, N[idx], color=blue, lw=0.8, label="N (H2 finite intervals)")
    ax.plot(x, np.convolve(N[idx], np.ones(20) / 20, mode="same"), color=red,
            lw=1.6, label="N, 20d mean")
    ax.set_ylabel("N", color=blue)
    ax2 = ax.twinx()
    ax2.plot(x, nodes[idx], color=grey, lw=1.0, alpha=0.8, label="n_nodes")
    ax2.set_ylabel("n_nodes", color=grey)
    ax.set_title("(a) N drift is NOT explained by node count", fontsize=11)
    ax.grid(alpha=0.25)
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [ln.get_label() for ln in lines], fontsize=8, loc="upper left")
    ax.set_xlabel("report-period trading day")

    ax = axes[0, 1]
    grid = [r for r in payload["grid"] if r["status"] == "preregistered"]
    names = [r["name"].replace("roll_", "").replace("_per_node", "/node") for r in grid]
    ics = [r["ic_h20"] for r in grid]
    los = [r["ci95_h20_lo"] for r in grid]
    his = [r["ci95_h20_hi"] for r in grid]
    ypos = np.arange(len(grid))
    cols = [blue if r["family"] == "roll_N" else orange for r in grid]
    ax.barh(ypos, ics, color=cols, height=0.65)
    for i, (lo, hi) in enumerate(zip(los, his)):
        if lo is not None and hi is not None:
            ax.plot([lo, hi], [i, i], color="#333", lw=1)
    ax.axvline(0, color="#333", lw=0.8)
    base = next(r for r in payload["grid"] if r["status"] == "baseline")
    ax.axvline(base["ic_h20"], color=red, ls="--", lw=1.2,
               label=f"fixed N<=1 baseline IC={base['ic_h20']:.4f}")
    ax.set_yticks(ypos)
    ax.set_yticklabels(names, fontsize=7)
    ax.set_title("(b) h=20 IC of all 18 preregistered cells (95% block-bootstrap CI)",
                 fontsize=11)
    ax.set_xlabel("Pearson IC (dimensionless)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25, axis="x")

    ax = axes[1, 0]
    yrs = sorted({d[:4] for d, ok in zip(dates, report) if ok})
    base = next(r for r in payload["grid"] if r["status"] == "baseline")
    pick = next(r for r in payload["grid"] if r["name"] == "roll_N_W120_p0.1")
    ax.plot(yrs, [base["by_year_trigger_share"][y] for y in yrs], "o-",
            color=red, label="fixed N<=1")
    ax.plot(yrs, [pick["by_year_trigger_share"][y] for y in yrs], "s-",
            color=blue, label="causal roll N, W=120, p=10%")
    ax.set_title("(c) Trigger share by calendar year", fontsize=11)
    ax.set_ylabel("share of report days with signal")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    ax.tick_params(axis="x", rotation=45, labelsize=8)

    ax = axes[1, 1]
    late = [r["signal_days_2021_2025"] for r in grid]
    ax.barh(np.arange(len(grid)), late,
            color=[blue if r["family"] == "roll_N" else orange for r in grid], height=0.65)
    ax.axvline(base["signal_days_2021_2025"], color=red, ls="--", lw=1.2,
               label=f"fixed N<=1: {base['signal_days_2021_2025']} days")
    ax.set_yticks(np.arange(len(grid)))
    ax.set_yticklabels(names, fontsize=7)
    ax.set_title("(d) 2021-2025 trigger days: does the moving threshold restore coverage?",
                 fontsize=11)
    ax.set_xlabel("signal days in 2021-2025")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25, axis="x")

    fig.suptitle("Q2  Causal moving thresholds for drifting N (in-sample diagnostic)",
                 fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(ADAPT_FIG, dpi=130, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- main
def main() -> None:
    dates, N, nodes, op, cl, wind_dates, wind_index, wop = read_inputs()
    ev, ev_rows = event_study(dates, N, nodes, op, cl, wind_index, wop)
    EVENT_JSON.write_text(json.dumps(ev, ensure_ascii=False, indent=2,
                                     allow_nan=False) + "\n", encoding="utf-8")
    ev_fields = ["event_no", "start", "end", "cluster_days", "calendar_span_days",
                 "calendar_gap_from_prev_cluster", "N_at_start", "n_nodes_at_start",
                 "entry_date_t_plus_1", "entry_open", "year"]
    for h in HORIZONS:
        ev_fields += [f"fwd{h}_open", f"fwd{h}_close"]
    with EVENT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=ev_fields)
        wr.writeheader()
        for r in ev_rows:
            wr.writerow({k: r.get(k) for k in ev_fields})
    figure_events(ev, ev_rows)

    ad, ad_rows, pct_N = adaptive_threshold_study(dates, N, nodes, op, cl)
    ADAPT_JSON.write_text(json.dumps(ad, ensure_ascii=False, indent=2,
                                     allow_nan=False) + "\n", encoding="utf-8")
    grid_fields = ["name", "family", "status", "window_days", "percentile",
                   "signal_days_report", "trigger_share_report", "event_clusters",
                   "event_starts_with_fwd20", "signal_days_2021_2025",
                   "event_clusters_2021_2025", "last_trigger_date",
                   "mean_fwd20_on_signal", "win_rate_fwd20_on_signal",
                   "lift_vs_unconditional", "mean_fwd20_on_event_starts",
                   "win_rate_fwd20_on_event_starts"] + \
                  [f"ic_h{h}" for h in HORIZONS] + \
                  ["ci95_h20_lo", "ci95_h20_hi", "ci95_h20_crosses_zero",
                   "ic_h20_spearman"]
    with ADAPT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=grid_fields)
        wr.writeheader()
        for r in ad_rows:
            wr.writerow({k: r.get(k) for k in grid_fields})
    figure_adaptive(ad, dates, N, nodes, pct_N)

    print(json.dumps({
        "events": len(ev_rows),
        "daily_mean_h20": round(ev["aggregation_conventions"]["daily_all_signal_days"]["mean"], 6),
        "cluster_equal_mean_h20": round(ev["aggregation_conventions"]["cluster_equal_weighted"]["mean"], 6),
        "event_start_mean_h20": round(ev["aggregation_conventions"]["cluster_start_only"]["mean"], 6),
        "unconditional_mean_h20": round(ev["aggregation_conventions"]["unconditional_all_report_days"]["mean"], 6),
        "event_start_ci": ev["aggregation_conventions"]["cluster_start_only"]["ci95_mean_iid_bootstrap"],
        "perm_p_two_sided": ev["permutation_test"]["simple_random"]["p_two_sided"],
        "grid_cells": len(ad_rows),
        "prereg_h20_ic_range": [round(min(r["ic_h20"] for r in ad_rows
                                          if r["status"] == "preregistered"), 4),
                                round(max(r["ic_h20"] for r in ad_rows
                                          if r["status"] == "preregistered"), 4)],
        "prereg_h20_ci_excluding_zero": [r["name"] for r in ad_rows
                                         if r["status"] == "preregistered"
                                         and r["ci95_h20_crosses_zero"] is False],
        "baseline_late_days": next(r["signal_days_2021_2025"] for r in ad_rows
                                   if r["status"] == "baseline"),
        "node_scaled_late_days": [r["signal_days_2021_2025"] for r in ad["node_count_scaled_control"]],
        "corr_N_nodes_2021_2025": next(s["corr_N_vs_nodes"] for s in ad["drift_attribution"]["segment_stats"]
                                       if s["segment"] == "2021-2025"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
