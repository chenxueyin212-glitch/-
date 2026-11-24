"""READ-ONLY diagnostic: score the LAST day of each k=1 event cluster.

The user asked what the IC looks like if the signal is placed on the last day
of an event cluster instead of the first day.  There is an unavoidable causal
problem: at the close of the last trigger day, one cannot know it is the last
one until >10 CALENDAR days have passed with no new trigger.  We therefore
compute TWO definitions and never mix them:

  A  "cluster_last"          : retrospective label, s_t = 1[t is a cluster end]
                               LOOK-AHEAD.  Diagnostic only, NOT tradable.
  B  "cluster_last_confirmed": first trading day d with (d - end) > 10 calendar
                               days; the cluster end is knowable at d's close,
                               entry at open d+1.  CAUSAL / executable.

Controls: all N<=1 days, cluster starts, cluster middle days, continuous -N,
and (to cover a second possible reading of the question) the continuous
correlation of -N with forward return WITHIN the 42 last-day subsample.

Nothing here is a strategy, a replication, or a confirmatory result.  No
existing output file is modified.  All cells are disclosed; no cell is chosen
by its IC.  Gate 1 stays paused; the 2025 final test is not read; Gate 2 not
started.

Outputs (all under outputs/):
  xy_cluster_last_day_ic.json, xy_cluster_last_day_ic.csv,
  xy_cluster_last_day_ic.png
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
FEATURE_CSV = OUT / "xy_corrected_sw193_ifind_peak_features.csv"
WIND_CSV = OUT / "xy_wind_all_a_daily.csv"
JSON_OUT = OUT / "xy_cluster_last_day_ic.json"
CSV_OUT = OUT / "xy_cluster_last_day_ic.csv"
FIG_OUT = OUT / "xy_cluster_last_day_ic.png"

START, END = "2015-07-01", "2025-05-30"
HORIZONS = (1, 5, 10, 20, 40)
GAP_DAYS = 10
BLOCK, N_BOOT, SEED = 20, 1000, 20261108
N_EVENT_BOOT, N_PERM_SIMPLE, N_PERM_SPACED = 10000, 5000, 2000


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
        return [None, None]
    return [float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))]


def describe(values) -> dict:
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


def event_bootstrap_ci(values, repetitions: int = N_EVENT_BOOT,
                       seed: int = SEED + 7):
    v = np.asarray([x for x in values if x is not None and math.isfinite(float(x))],
                   dtype=float)
    if len(v) < 3:
        return [None, None]
    rng = np.random.default_rng(seed)
    means = v[rng.integers(0, len(v), size=(repetitions, len(v)))].mean(axis=1)
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def subsample_ic_ci(x, y, seed: int, repetitions: int = N_BOOT):
    """Paired iid bootstrap for a correlation computed inside a tiny subsample."""
    if len(x) < 4:
        return [None, None]
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(repetitions):
        idx = rng.integers(0, len(x), size=len(x))
        v = pearson(x[idx], y[idx])
        if math.isfinite(v):
            values.append(v)
    if len(values) < 10:
        return [None, None]
    return [float(np.quantile(values, 0.025)),
            float(np.quantile(values, 0.975))]


def read_inputs():
    with FEATURE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        features = [r for r in csv.DictReader(handle) if r["date"] <= END]
    with WIND_CSV.open(encoding="utf-8-sig", newline="") as handle:
        wind_rows = list(csv.DictReader(handle))
    wind = {r["date"]: (float(r["open"]), float(r["close"])) for r in wind_rows}
    missing = [r["date"] for r in features if r["date"] not in wind]
    assert not missing, f"feature dates missing from Wind daily: {missing[:5]}"
    dates = [r["date"] for r in features]
    N = np.asarray([float(r["h2_count"]) for r in features])
    nodes = np.asarray([float(r["n_nodes"]) for r in features])
    op = np.asarray([wind[d][0] for d in dates])
    cl = np.asarray([wind[d][1] for d in dates])
    return dates, N, nodes, op, cl


def forward_returns(op, cl, h):
    """Signal at close t -> entry open t+1 -> exit open t+1+h (feature calendar)."""
    n = len(op)
    ro = np.full(n, np.nan)
    ro[:n - h - 1] = op[h + 1:] / op[1:n - h] - 1.0
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


def confirmation_indices(dates, clusters):
    """First trading day strictly more than GAP_DAYS calendar days after a
    cluster end.  Only on this day can an observer know the cluster is over."""
    dts = [datetime.fromisoformat(d).date() for d in dates]
    out = []
    for c in clusters:
        j = c[-1]
        k = j + 1
        while k < len(dates) and (dts[k] - dts[j]).days <= GAP_DAYS:
            k += 1
        out.append(k if k < len(dates) else None)
    return out


def permutation_p(usable_idx, actual_idx, ro20, dates, seed):
    """Two nulls for the statistic 'mean forward-20 return on the signal days'.

    simple_random   : m days drawn uniformly from all usable days.
    circular_shift  : the whole usable forward-return series is rolled by a
                      random offset; signal positions are kept.  This preserves
                      return autocorrelation AND the exact spacing structure of
                      the 42 event days, breaking only signal/return alignment.
                      Same device as the joint max-IC test in the adaptive study.
    """
    m = len(actual_idx)
    actual = float(np.mean(ro20[actual_idx]))
    usable = np.asarray(usable_idx)
    usable_ro = ro20[usable]
    pos = {int(i): p for p, i in enumerate(usable)}
    pos_arr = np.asarray([pos[int(i)] for i in actual_idx])
    n_u = len(usable)
    rng = np.random.default_rng(seed)

    simple = np.empty(N_PERM_SIMPLE)
    for b in range(N_PERM_SIMPLE):
        simple[b] = ro20[rng.choice(usable, size=m, replace=False)].mean()

    shifted = np.empty(N_PERM_SPACED)
    for b in range(N_PERM_SPACED):
        s = int(rng.integers(1, n_u))
        shifted[b] = usable_ro[(pos_arr + s) % n_u].mean()

    def pvals(null):
        if len(null) == 0:
            return {"p_greater": None, "p_two_sided": None, "n_draws": 0,
                    "null_mean": None, "null_sd": None}
        ge = float((null >= actual).mean())
        le = float((null <= actual).mean())
        return {"p_greater": ge, "p_two_sided": float(min(1.0, 2 * min(ge, le))),
                "n_draws": int(len(null)), "null_mean": float(null.mean()),
                "null_sd": float(null.std(ddof=1))}

    return {"actual_mean": actual, "n_signal_days": m,
            "simple_random": pvals(simple), "circular_shift": pvals(shifted)}


def main():
    dates, N, nodes, op, cl = read_inputs()
    n = len(dates)
    report = np.asarray([START <= d <= END for d in dates])
    flag = N <= 1
    clusters = clusters_from_flag(dates, flag, report)
    confirm = confirmation_indices(dates, clusters)
    dts = [datetime.fromisoformat(d).date() for d in dates]

    s_daily = flag.astype(float)
    s_start = np.zeros(n)
    s_last = np.zeros(n)
    s_middle = np.zeros(n)
    s_confirm = np.zeros(n)
    for c, k in zip(clusters, confirm):
        s_start[c[0]] = 1.0
        s_last[c[-1]] = 1.0
        for i in c[1:-1]:
            s_middle[i] = 1.0
        if k is not None:
            s_confirm[k] = 1.0

    signals = {
        "daily_N_le_1": ("all N<=1 days", s_daily),
        "cluster_start": ("first day of each cluster", s_start),
        "cluster_last": ("LAST day of each cluster (retrospective label)", s_last),
        "cluster_middle": ("interior days, neither first nor last", s_middle),
        "cluster_last_confirmed": ("first day >10 cal days after cluster end "
                                   "(causal, executable)", s_confirm),
    }
    fwd = {h: forward_returns(op, cl, h) for h in HORIZONS}
    ro20 = fwd[20]
    usable20 = report & np.isfinite(ro20)

    # ---- IC matrix: five binary signals x five horizons -------------------
    matrix = []
    for h in HORIZONS:
        ro = fwd[h]
        mask = report & np.isfinite(ro)
        y = ro[mask]
        for name, (desc, s) in signals.items():
            x = s[mask]
            on = y[x == 1]
            ci = block_bootstrap_ci(x, y, f"{name}|h{h}")
            matrix.append({
                "signal": name, "description": desc, "horizon_days": h,
                "n_observations": int(mask.sum()),
                "signal_days": int((x == 1).sum()),
                "ic_point_biserial": finite_or_none(pearson(x, y)),
                "ic_spearman": finite_or_none(spearman(x, y)),
                "ci95_lo": ci[0], "ci95_hi": ci[1],
                "crosses_zero": None if ci[0] is None else bool(ci[0] <= 0 <= ci[1]),
                "mean_fwd_on": finite_or_none(on.mean()) if len(on) else None,
                "mean_fwd_off": finite_or_none(y[x == 0].mean()),
                "win_rate_on": finite_or_none((on > 0).mean()) if len(on) else None,
                "look_ahead": name == "cluster_last",
            })
        # continuous -N control on the full panel
        xc = (-N)[mask]
        ci_c = block_bootstrap_ci(xc, y, f"minus_N|h{h}")
        matrix.append({
            "signal": "minus_N", "description": "continuous -N on full panel",
            "horizon_days": h, "n_observations": int(mask.sum()),
            "signal_days": None, "ic_point_biserial": finite_or_none(pearson(xc, y)),
            "ic_spearman": finite_or_none(spearman(xc, y)),
            "ci95_lo": ci_c[0], "ci95_hi": ci_c[1],
            "crosses_zero": None if ci_c[0] is None else bool(ci_c[0] <= 0 <= ci_c[1]),
            "mean_fwd_on": None, "mean_fwd_off": None, "win_rate_on": None,
            "look_ahead": False,
        })

    # ---- second reading: correlation WITHIN the last-day subsample -------
    within = []
    for h in HORIZONS:
        ro = fwd[h]
        m = (s_last == 1) & report & np.isfinite(ro)
        x, y = (-N)[m], ro[m]
        ci_w = subsample_ic_ci(x, y, SEED + 400 + h)
        within.append({
            "horizon_days": h, "n_last_days": int(m.sum()),
            "ic_pearson": finite_or_none(pearson(x, y)),
            "ic_spearman": finite_or_none(spearman(x, y)),
            "ci95_ic_iid_bootstrap": ci_w,
            "crosses_zero": None if ci_w[0] is None else bool(ci_w[0] <= 0 <= ci_w[1]),
            "note": "uses -N, not a 0/1 flag; restricted to the 42 cluster-end "
                    "days; 5 horizons with no multiple-testing correction",
        })

    # ---- per-cluster rows -------------------------------------------------
    cluster_rows = []
    for ci, (c, k) in enumerate(zip(clusters, confirm), 1):
        i, j = c[0], c[-1]
        rec = {
            "event_no": ci,
            "start": dates[i], "end": dates[j],
            "cluster_days": len(c),
            "is_single_day_cluster": len(c) == 1,
            "calendar_span_days": (dts[j] - dts[i]).days,
            "N_at_start": int(N[i]), "N_at_last": int(N[j]),
            "n_nodes_at_last": int(nodes[j]),
            "year_of_last": dates[j][:4],
            "start_fwd20": finite_or_none(ro20[i]) if np.isfinite(ro20[i]) else None,
            "last_fwd20": finite_or_none(ro20[j]) if np.isfinite(ro20[j]) else None,
            "confirm_date": dates[k] if k is not None else None,
            "confirm_lag_trading_days": (k - j) if k is not None else None,
            "confirm_lag_calendar_days": ((dts[k] - dts[j]).days
                                          if k is not None else None),
            "confirm_fwd20": (finite_or_none(ro20[k])
                              if k is not None and np.isfinite(ro20[k]) else None),
        }
        a, b = rec["start_fwd20"], rec["last_fwd20"]
        rec["pair_diff_last_minus_start"] = (b - a) if (a is not None and b is not None) else None
        cluster_rows.append(rec)

    # ---- event-level statistics at h=20 ----------------------------------
    groups = {
        "daily_all_N_le_1": [i for i in range(n) if usable20[i] and s_daily[i] == 1],
        "cluster_start": [c[0] for c in clusters if usable20[c[0]]],
        "cluster_last": [c[-1] for c in clusters if usable20[c[-1]]],
        "cluster_middle": [i for c in clusters for i in c[1:-1] if usable20[i]],
        "cluster_last_confirmed": [k for k in confirm if k is not None and usable20[k]],
        "unconditional": [i for i in range(n) if usable20[i]],
    }
    event_level = {}
    for name, idx in groups.items():
        vals = ro20[idx]
        d = describe(vals)
        d["ci95_mean_iid_bootstrap"] = event_bootstrap_ci(vals)
        d["mean_excess_vs_unconditional"] = (
            d["mean"] - float(ro20[usable20].mean()) if "mean" in d else None)
        event_level[name] = d

    # ---- paired first vs last --------------------------------------------
    pair_clusters = [c for c in clusters
                     if np.isfinite(ro20[c[0]]) and np.isfinite(ro20[c[-1]])]
    pairs = [(ro20[c[0]], ro20[c[-1]]) for c in pair_clusters]
    single_flags = np.asarray([len(c) == 1 for c in pair_clusters])
    first_arr = np.asarray([a for a, _ in pairs])
    last_arr = np.asarray([b for _, b in pairs])
    diff = last_arr - first_arr
    multi = [(a, b) for (a, b), s in zip(pairs, single_flags) if not s]
    m_first = np.asarray([a for a, _ in multi])
    m_last = np.asarray([b for _, b in multi])
    m_diff = m_last - m_first
    paired = {
        "n_pairs": len(pairs),
        "n_single_day_clusters_in_pairs": int(single_flags.sum()),
        "single_day_note": "for a 1-day cluster the first and last day are the "
                           "same date, so the paired difference is exactly 0; "
                           "these pairs dilute the all-pair mean",
        "mean_start": float(first_arr.mean()),
        "mean_last": float(last_arr.mean()),
        "mean_diff_last_minus_start": float(diff.mean()),
        "median_diff": float(np.median(diff)),
        "n_last_better": int((diff > 0).sum()),
        "n_last_worse": int((diff < 0).sum()),
        "n_exactly_equal": int((diff == 0).sum()),
        "ci95_diff_iid_bootstrap": event_bootstrap_ci(diff),
        "pearson_start_vs_last": finite_or_none(pearson(first_arr, last_arr)),
        "spearman_start_vs_last": finite_or_none(spearman(first_arr, last_arr)),
        "multi_day_only": {
            "n_pairs": len(multi),
            "mean_start": float(m_first.mean()),
            "mean_last": float(m_last.mean()),
            "mean_diff_last_minus_start": float(m_diff.mean()),
            "median_diff": float(np.median(m_diff)),
            "n_last_better": int((m_diff > 0).sum()),
            "n_last_worse": int((m_diff < 0).sum()),
            "ci95_diff_iid_bootstrap": event_bootstrap_ci(m_diff),
        },
        "note": "paired by cluster; a positive diff means the last day of the "
                "same event had a higher forward-20 return than the first day",
    }

    # ---- permutation tests ------------------------------------------------
    usable_idx = [i for i in range(n) if usable20[i]]
    perm = {
        "cluster_last": permutation_p(usable_idx, groups["cluster_last"],
                                      ro20, dates, SEED + 301),
        "cluster_start": permutation_p(usable_idx, groups["cluster_start"],
                                       ro20, dates, SEED + 302),
        "cluster_last_confirmed": permutation_p(
            usable_idx, groups["cluster_last_confirmed"], ro20, dates, SEED + 303),
        "method": "statistic = mean forward-20 open-to-open return; "
                  "simple-random null and circular-shift null (preserves both "
                  "return autocorrelation and the 42-day spacing structure)",
    }

    # ---- by year (of cluster end) ----------------------------------------
    by_year = []
    for year in sorted({r["year_of_last"] for r in cluster_rows}):
        vals = [r["last_fwd20"] for r in cluster_rows
                if r["year_of_last"] == year and r["last_fwd20"] is not None]
        by_year.append({"year": year,
                        "n_clusters": sum(1 for r in cluster_rows
                                          if r["year_of_last"] == year),
                        "n_with_fwd20": len(vals),
                        "mean_fwd20": float(np.mean(vals)) if vals else None,
                        "win_rate": float(np.mean(np.asarray(vals) > 0)) if vals else None})

    # ---- overlap / causal audit ------------------------------------------
    last_set = {c[-1] for c in clusters}
    start_set = {c[0] for c in clusters}
    conf_set = {k for k in confirm if k is not None}
    overlap_audit = {
        "n_clusters": len(clusters),
        "n_clusters_with_confirmation_day": len(conf_set),
        "n_clusters_without_confirmation_day": len(clusters) - len(conf_set),
        "confirmation_is_also_a_cluster_start": len(conf_set & start_set),
        "confirmation_is_also_a_cluster_last": len(conf_set & last_set),
        "confirmation_lag_trading_days_min": min(
            (r["confirm_lag_trading_days"] for r in cluster_rows
             if r["confirm_lag_trading_days"] is not None), default=None),
        "confirmation_lag_trading_days_max": max(
            (r["confirm_lag_trading_days"] for r in cluster_rows
             if r["confirm_lag_trading_days"] is not None), default=None),
        "confirmation_lag_calendar_days_min": min(
            (r["confirm_lag_calendar_days"] for r in cluster_rows
             if r["confirm_lag_calendar_days"] is not None), default=None),
        "confirmation_lag_calendar_days_max": max(
            (r["confirm_lag_calendar_days"] for r in cluster_rows
             if r["confirm_lag_calendar_days"] is not None), default=None),
        "note": "a cluster-end label is only knowable at the confirmation day; "
                "the retrospective last-day signal uses future information",
    }

    # ---- figure -----------------------------------------------------------
    names = list(signals.keys())
    colors = {"daily_N_le_1": "#185FA5", "cluster_start": "#0F6E56",
              "cluster_last": "#BA7517", "cluster_middle": "#888780",
              "cluster_last_confirmed": "#993C1D"}
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    ax = axes[0, 0]
    for name in names:
        vals = [next(r["ic_point_biserial"] for r in matrix
                     if r["signal"] == name and r["horizon_days"] == h)
                for h in HORIZONS]
        ax.plot(list(HORIZONS), vals, "o-", color=colors[name], lw=1.6,
                ms=5, label=name)
    ax.axhline(0, color="#5F5E5A", lw=0.8, ls="--")
    ax.set_title("(a) Point-biserial IC by horizon, five signal definitions", fontsize=11)
    ax.set_xlabel("forward horizon h (trading days)")
    ax.set_ylabel("IC (dimensionless)")
    ax.legend(fontsize=8, loc="best")

    ax = axes[0, 1]
    h20 = [r for r in matrix if r["horizon_days"] == 20]
    xs = np.arange(len(h20))
    for i, r in enumerate(h20):
        lo, hi, ic = r["ci95_lo"], r["ci95_hi"], r["ic_point_biserial"]
        c = colors.get(r["signal"], "#534AB7")
        ax.scatter([i], [ic], color=c, s=40, zorder=3)
        if lo is not None and hi is not None:
            ax.plot([i, i], [lo, hi], color=c, lw=2, zorder=2)
        else:
            ax.text(i, ic, " CI undefined", fontsize=7, color=c, rotation=90,
                    va="bottom")
    ax.axhline(0, color="#5F5E5A", lw=0.8, ls="--")
    ax.set_xticks(xs)
    ax.set_xticklabels([r["signal"].replace("cluster_", "cl_") for r in h20],
                       rotation=32, ha="right", fontsize=8)
    ax.set_title("(b) h=20 IC with 95% block-bootstrap interval", fontsize=11)
    ax.set_ylabel("IC (dimensionless)")

    ax = axes[1, 0]
    multi_mask = ~single_flags
    ax.scatter(first_arr[multi_mask] * 100, last_arr[multi_mask] * 100,
               s=34, color="#185FA5", alpha=0.75, edgecolor="none",
               label=f"multi-day clusters (n={int(multi_mask.sum())})")
    ax.scatter(first_arr[single_flags] * 100, last_arr[single_flags] * 100,
               s=34, color="#BA7517", alpha=0.9, edgecolor="none",
               label=f"single-day clusters (n={int(single_flags.sum())})")
    lim = [min(first_arr.min(), last_arr.min()) * 100 - 2,
           max(first_arr.max(), last_arr.max()) * 100 + 2]
    ax.plot(lim, lim, color="#888780", ls="--", lw=1)
    ax.axhline(0, color="#D3D1C7", lw=0.7)
    ax.axvline(0, color="#D3D1C7", lw=0.7)
    ax.set_xlabel("first day: forward-20 return (%)")
    ax.set_ylabel("last day: forward-20 return (%)")
    ax.set_title("(c) Same event, first vs last day (45-degree line)", fontsize=11)
    ax.legend(fontsize=8, loc="best")

    ax = axes[1, 1]
    yrs = [r["year"] for r in by_year]
    means = [(r["mean_fwd20"] or 0) * 100 for r in by_year]
    bars = ax.bar(yrs, means, color=["#BA7517" if m >= 0 else "#1D9E75"
                                     for m in means], edgecolor="none")
    for b, r in zip(bars, by_year):
        ax.text(b.get_x() + b.get_width() / 2,
                b.get_height() + (0.4 if b.get_height() >= 0 else -0.9),
                f"n={r['n_with_fwd20']}", ha="center", fontsize=8)
    ax.axhline(0, color="#5F5E5A", lw=0.8)
    ax.set_ylabel("mean forward-20 return (%)")
    ax.set_title("(d) Cluster-end returns by year", fontsize=11)
    ax.tick_params(axis="x", rotation=40, labelsize=8)
    fig.tight_layout()
    fig.savefig(FIG_OUT, dpi=130)
    plt.close(fig)

    # ---- CSV --------------------------------------------------------------
    fields = list(cluster_rows[0].keys())
    with CSV_OUT.open("w", encoding="utf-8-sig", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=fields)
        w.writeheader()
        for r in cluster_rows:
            w.writerow({k: ("" if r[k] is None else r[k]) for k in fields})

    # ---- JSON -------------------------------------------------------------
    cells = [r for r in matrix if r["crosses_zero"] is False]
    payload = {
        "generated_on": "2026-11-08",
        "status": "exploratory signal-level diagnostic; not a strategy result; "
                  "not out-of-sample; no existing output file modified",
        "question": "IC when the signal is placed on the LAST day of each k=1 "
                    "event cluster, instead of the first day",
        "preregistration": {
            "definitions_fixed_before_viewing_results": True,
            "all_cells_disclosed": True,
            "no_cell_selected_by_ic": True,
            "signal_definitions": [v[0] for v in signals.values()] + ["minus_N"],
            "horizons": list(HORIZONS),
            "bootstrap": {"method": "paired 20-day moving block",
                          "repetitions": N_BOOT, "seed": SEED},
            "permutation": {"simple_random_draws": N_PERM_SIMPLE,
                            "circular_shift_draws": N_PERM_SPACED},
        },
        "causal_warning": {
            "cluster_last": "RETROSPECTIVE / LOOK-AHEAD: whether day t is the "
                            "last trigger of a cluster is only known after >10 "
                            "calendar days with no new trigger. Not tradable.",
            "cluster_last_confirmed": "CAUSAL: on the first trading day d with "
                                      "(d-end)>10 calendar days the end is "
                                      "knowable; entry at open d+1.",
            "ic_h_is_not_a_holding_period": True,
        },
        "data": {
            "feature_file": str(FEATURE_CSV.relative_to(ROOT)),
            "wind_file": str(WIND_CSV.relative_to(ROOT)),
            "rows_after_end_truncation": n,
            "first_feature_date": dates[0], "last_feature_date": dates[-1],
            "report_days": int(report.sum()),
            "usable_h20_days": int(usable20.sum()),
            "n_clusters": len(clusters),
            "n_N_le_1_days": int((report & flag).sum()),
            "forward_return": "open[t+1+h]/open[t+1]-1, feature calendar",
        },
        "cluster_rule": "successive trigger days >10 CALENDAR days apart form "
                        "a new event",
        "ic_matrix": matrix,
        "within_last_day_subsample_minus_N": within,
        "h20_event_level": event_level,
        "paired_first_vs_last": paired,
        "permutation_tests": perm,
        "by_year_of_cluster_end": by_year,
        "clusters": cluster_rows,
        "overlap_audit": overlap_audit,
        "bootstrap_degenerate_draws": BOOT_DEGENERATE,
        "bootstrap_degenerate_total": sum(x["degenerate_draws"]
                                          for x in BOOT_DEGENERATE),
        "interpretation": {
            "n_ic_cells": len(matrix),
            "n_cells_excluding_zero": len(cells),
            "cells_excluding_zero": [f"{r['signal']}@h{r['horizon_days']}" for r in cells],
            "h20_cells_excluding_zero": [r["signal"] for r in h20
                                         if r["crosses_zero"] is False],
            "warning": f"{len(matrix)} cells with no multiple-testing correction; "
                       f"~{0.05 * len(matrix):.1f} false positives expected at 5% "
                       f"under a global null. Bootstrap degeneracy total = "
                       f"{sum(x['degenerate_draws'] for x in BOOT_DEGENERATE)} "
                       f"across {len(BOOT_DEGENERATE)} tagged cells.",
        },
        "limitations": [
            "All in-sample; no 2025 final test read; no out-of-sample split.",
            "The retrospective last-day signal is not executable and must not "
            "be read as a strategy result.",
            "The causal confirmation-day signal changes the economic question: "
            "it trades AFTER the low-hole state has ended, not during it.",
            "N<=1 clusters are concentrated in 2015-2020; late-period coverage "
            "is almost zero for the fixed threshold.",
            "N's exact definition in the original report, Wind daily industry "
            "membership and the fourth-level industry classification are still "
            "unavailable.",
        ],
        "gate_status": "Gate 1 paused; 2025 final test NOT read; Gate 2 NOT started",
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                   allow_nan=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "n_clusters": len(clusters),
        "h20": [(r["signal"], r["signal_days"],
                 None if r["ic_point_biserial"] is None else round(r["ic_point_biserial"], 4),
                 [None if r["ci95_lo"] is None else round(r["ci95_lo"], 4),
                  None if r["ci95_hi"] is None else round(r["ci95_hi"], 4)])
                for r in h20],
        "event_level_mean": {k: (None if "mean" not in v else round(v["mean"], 5))
                             for k, v in event_level.items()},
        "paired": {k: (round(v, 5) if isinstance(v, float) else v)
                   for k, v in paired.items() if k != "note"},
        "perm_p_two_sided": {k: v["simple_random"]["p_two_sided"]
                             for k, v in perm.items() if isinstance(v, dict)},
        "degenerate_total": payload["bootstrap_degenerate_total"],
        "overlap": {k: v for k, v in overlap_audit.items()
                    if k.startswith("n_") or "also" in k},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
