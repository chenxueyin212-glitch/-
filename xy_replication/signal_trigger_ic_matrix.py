"""Supplementary READ-ONLY diagnostics: when does the signal fire, and what is
the IC of every signal definition at every horizon?

This does not create a strategy, does not select a signal by performance, does
not change any confirmatory result, and does not modify any existing output.
All signal definitions and horizons were fixed before looking at any IC value.
Every cell is disclosed. Same data and causal convention as ic_diagnostics.py.

Outputs:
  xy_signal_trigger_ic_matrix.json / .png
  xy_signal_ic_matrix.csv
  xy_signal_trigger_clusters.csv
  xy_signal_trigger_by_year.csv
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
JSON_OUT = OUT / "xy_signal_trigger_ic_matrix.json"
MATRIX_CSV = OUT / "xy_signal_ic_matrix.csv"
CLUSTER_CSV = OUT / "xy_signal_trigger_clusters.csv"
YEAR_CSV = OUT / "xy_signal_trigger_by_year.csv"
FIG_OUT = OUT / "xy_signal_trigger_ic_matrix.png"

START, END = "2015-07-01", "2025-05-30"
HORIZONS = (1, 5, 10, 20, 40)
BLOCK, N_BOOT, SEED, GAP_DAYS = 20, 1000, 20261108, 10
THRESHOLDS = (0, 1, 2, 3)
CASES = {
    "2020-03": ("2020-03-01", "2020-03-31"),
    "2022-04": ("2022-04-01", "2022-04-30"),
    "2024-02": ("2024-02-01", "2024-02-29"),
    "2025-01": ("2025-01-01", "2025-01-31"),
}
SEGMENTS = (("2015-2020", "2015", "2020"), ("2021-2025", "2021", "2025"))


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    xc, yc = x - x.mean(), y - y.mean()
    den = math.sqrt(float(xc @ xc) * float(yc @ yc))
    return float(xc @ yc / den) if den > 0 else float("nan")


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    return pearson(rankdata(x), rankdata(y))


BOOT_DEGENERATE: list[dict] = []


def block_bootstrap_ci(x: np.ndarray, y: np.ndarray, tag: str = "",
                       block: int = BLOCK, repetitions: int = N_BOOT,
                       seed: int = SEED) -> list[float]:
    """Paired moving-block bootstrap. Degenerate draws (constant signal inside
    the resample, possible for very rare binary signals) are counted and
    disclosed instead of being silently dropped or replaced."""
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
    n_bad = len(values) - len(finite)
    if n_bad:
        BOOT_DEGENERATE.append({"tag": tag, "degenerate_draws": n_bad,
                               "total_draws": len(values),
                               "note": "resample had zero signal variance; Pearson undefined"})
    if len(finite) < 10:
        return [float("nan"), float("nan")]
    return [float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))]


def finite_or_none(v):
    return float(v) if v is not None and math.isfinite(float(v)) else None


def read_inputs():
    with FEATURE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        features = [r for r in csv.DictReader(handle) if r["date"] <= END]
    with WIND_CSV.open(encoding="utf-8-sig", newline="") as handle:
        wind = {r["date"]: (float(r["open"]), float(r["close"]))
                for r in csv.DictReader(handle)}
    missing = [r["date"] for r in features if r["date"] not in wind]
    assert not missing, f"feature dates missing from Wind daily: {missing[:5]}"
    dates = [r["date"] for r in features]
    n_h2 = np.asarray([float(r["h2_count"]) for r in features])
    l2 = np.asarray([float(r["h2_landscape_l1"]) for r in features])
    l1 = np.asarray([float(r["h1_landscape_l1"]) for r in features])
    nodes = np.asarray([float(r["n_nodes"]) for r in features])
    op = np.asarray([wind[d][0] for d in dates])
    cl = np.asarray([wind[d][1] for d in dates])
    return dates, n_h2, l2, l1, nodes, op, cl


def forward_returns(op: np.ndarray, cl: np.ndarray, h: int):
    n = len(op)
    ro = np.full(n, np.nan)
    rc = np.full(n, np.nan)
    if h + 1 < n:
        ro[:n - h - 1] = op[h + 1:] / op[1:n - h] - 1.0
    if h < n:
        rc[:n - h] = cl[h:] / cl[:n - h] - 1.0
    return ro, rc


def cluster_starts(dates, n_h2, threshold: int = 1) -> np.ndarray:
    flag = np.zeros(len(dates), dtype=int)
    prev = None
    for i, d in enumerate(dates):
        if not (START <= d <= END) or n_h2[i] > threshold:
            continue
        cur = datetime.fromisoformat(d).date()
        if prev is None or (cur - prev).days > GAP_DAYS:
            flag[i] = 1
        prev = cur
    return flag


def make_clusters(dates, n_h2, report, threshold):
    idx = [i for i in range(len(dates)) if report[i] and n_h2[i] <= threshold]
    clusters = []
    for i in idx:
        if not clusters or (datetime.fromisoformat(dates[i]).date()
                            - datetime.fromisoformat(dates[clusters[-1][-1]]).date()).days > GAP_DAYS:
            clusters.append([i])
        else:
            clusters[-1].append(i)
    return clusters


def main() -> None:
    dates, N, L2, L1, nodes, op, cl = read_inputs()
    report = np.asarray([START <= d <= END for d in dates])

    signals = [
        ("minus_N", -N, "连续：孔洞数取负"),
        ("minus_log1p_N", -np.log1p(N), "连续：对数压缩（−N 的单调变换）"),
        ("minus_h2_landscape_l1", -L2, "连续：H2 持久景观 L1 取负"),
        ("minus_h1_landscape_l1", -L1, "连续：H1 持久景观 L1 取负"),
        ("binary_N<=0", (N <= 0).astype(float), "二元：仅在 N=0 触发"),
        ("binary_N<=1", (N <= 1).astype(float), "二元：兴业原文阈值"),
        ("binary_N<=2", (N <= 2).astype(float), "二元：放宽阈值"),
        ("binary_N<=3", (N <= 3).astype(float), "二元：进一步放宽"),
        ("binary_N<=1_cluster_start", cluster_starts(dates, N, 1).astype(float),
         "二元：N≤1 且仅每簇第一天"),
        ("minus_n_nodes_CONTROL", -nodes, "对照变量，不是交易信号：行业节点数取负"),
    ]

    fwd = {h: forward_returns(op, cl, h) for h in HORIZONS}
    matrix_rows = []
    for name, s_full, desc in signals:
        for h in HORIZONS:
            ro, _ = fwd[h]
            usable = report & np.isfinite(ro)
            x, y = s_full[usable], ro[usable]
            ic_p, ic_s = pearson(x, y), spearman(x, y)
            ci = block_bootstrap_ci(x, y, f"{name}|h{h}")
            lo, hi = finite_or_none(ci[0]), finite_or_none(ci[1])
            matrix_rows.append({
                "signal": name, "description": desc, "horizon_days": h,
                "n_observations": int(usable.sum()),
                "signal_days": int((x != 0).sum()) if name.startswith("binary") else None,
                "ic_pearson": finite_or_none(ic_p), "ic_spearman": finite_or_none(ic_s),
                "ci95_lo": lo, "ci95_hi": hi,
                "crosses_zero": None if lo is None or hi is None else bool(lo <= 0 <= hi),
                "signal_direction": "positive IC = fewer holes / smaller N predicts higher forward return",
            })

    # segment stability of every signal at h=20
    ro20, _ = fwd[20]
    usable20 = report & np.isfinite(ro20)
    segment_rows = []
    for name, s_full, desc in signals:
        for label, a, b in SEGMENTS:
            m = usable20 & np.asarray([a <= d[:4] <= b for d in dates])
            x, y = s_full[m], ro20[m]
            ci = block_bootstrap_ci(x, y, f"{name}|{label}")
            lo, hi = finite_or_none(ci[0]), finite_or_none(ci[1])
            segment_rows.append({
                "signal": name, "segment": label, "n": int(m.sum()),
                "ic_pearson": finite_or_none(pearson(x, y)), "ci95_lo": lo, "ci95_hi": hi,
                "crosses_zero": None if lo is None or hi is None else bool(lo <= 0 <= hi),
                "signal_days": int((x != 0).sum()) if name.startswith("binary") else None,
            })

    # trigger timing profiles
    trigger_profile = []
    year_rows = []
    years = sorted({d[:4] for d, ok in zip(dates, report) if ok})
    for k in THRESHOLDS:
        clusters = make_clusters(dates, N, report, k)
        lengths = [len(c) for c in clusters]
        signal_days = int(((N <= k) & report).sum())
        trigger_profile.append({
            "threshold_k": k, "report_days": int(report.sum()),
            "signal_days": signal_days, "signal_share": signal_days / int(report.sum()),
            "event_clusters": len(clusters),
            "first_signal_date": dates[clusters[0][0]] if clusters else None,
            "last_signal_date": dates[clusters[-1][-1]] if clusters else None,
            "cluster_length_median": float(np.median(lengths)) if lengths else None,
            "cluster_length_max": int(max(lengths)) if lengths else None,
            "cluster_length_p90": float(np.percentile(lengths, 90)) if lengths else None,
            "definition": "t 日收盘得到 N_t ≤ k 即触发；相邻触发日间隔 >10 个日历日算新簇",
        })
        for yr in years:
            m = report & np.asarray([d.startswith(yr) for d in dates])
            yr_idx = [i for i in range(len(dates)) if m[i] and N[i] <= k]
            yr_clusters = [c for c in clusters if dates[c[0]].startswith(yr)]
            year_rows.append({
                "threshold_k": k, "year": yr, "report_days": int(m.sum()),
                "signal_days": len(yr_idx),
                "signal_share": len(yr_idx) / int(m.sum()) if m.sum() else None,
                "cluster_starts": len(yr_clusters),
                "mean_N": float(N[m].mean()), "median_N": float(np.median(N[m])),
            })

    # full cluster list for the original threshold k=1
    cluster_rows = []
    cl1 = make_clusters(dates, N, report, 1)
    prev_end = None
    for cluster in cl1:
        i = cluster[0]
        j = cluster[-1]
        gap = None
        if prev_end is not None:
            gap = (datetime.fromisoformat(dates[i]).date()
                   - datetime.fromisoformat(dates[prev_end]).date()).days
        idx_next = i + 1
        idx_exit = i + 21
        fwd20_open = (op[idx_exit] / op[idx_next] - 1.0) if idx_exit < len(op) else None
        fwd20_close = (cl[i + 20] / cl[i] - 1.0) if i + 20 < len(cl) else None
        cluster_rows.append({
            "start": dates[i], "end": dates[j], "cluster_days": len(cluster),
            "calendar_gap_from_prev_cluster": gap,
            "N_at_start": int(N[i]), "n_nodes_at_start": int(nodes[i]),
            "entry_date_t_plus_1": dates[idx_next] if idx_next < len(dates) else None,
            "entry_open": float(op[idx_next]) if idx_next < len(op) else None,
            "forward20_open_to_open": float(fwd20_open) if fwd20_open is not None else None,
            "forward20_close_to_close": float(fwd20_close) if fwd20_close is not None else None,
            "year": dates[i][:4],
        })
        prev_end = j

    case_rows = []
    for label, (a, b) in CASES.items():
        hits = [{"date": d, "N": int(N[i])}
                for i, d in enumerate(dates) if report[i] and a <= d <= b and N[i] <= 1]
        case_rows.append({
            "case_month": label, "window": [a, b],
            "N_le_1_days": len(hits), "dates": hits,
            "min_N_in_month": float(N[[i for i, d in enumerate(dates)
                                       if a <= d <= b]].min()) if any(a <= d <= b for d in dates) else None,
        })

    # figure
    names = [name for name, _, _ in signals]
    grid = np.asarray([[np.nan if r["ic_pearson"] is None else r["ic_pearson"]
                        for r in matrix_rows if r["signal"] == name]
                       for name in names])
    fig, axes = plt.subplots(2, 1, figsize=(13.4, 10.4), dpi=160)
    ax = axes[0]
    im = ax.imshow(grid, cmap="coolwarm", vmin=-0.12, vmax=0.12, aspect="auto")
    ax.set_xticks(range(len(HORIZONS)), [f"h={h}" for h in HORIZONS])
    ax.set_yticks(range(len(names)), names, fontsize=8.5)
    for r in range(len(names)):
        for c in range(len(HORIZONS)):
            ax.text(c, r, f"{grid[r, c]:.3f}", ha="center", va="center",
                    fontsize=7.6, color="#1d1d1b")
    ax.set_title("Pearson IC by signal definition and forward horizon (all 50 cells; red = positive)")
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02, label="IC (unitless)")
    ax = axes[1]
    yr = [r["year"] for r in year_rows if r["threshold_k"] == 1]
    days = [r["signal_days"] for r in year_rows if r["threshold_k"] == 1]
    cls = [r["cluster_starts"] for r in year_rows if r["threshold_k"] == 1]
    med = [r["median_N"] for r in year_rows if r["threshold_k"] == 1]
    ax.bar(range(len(yr)), days, color="#E24B4A", alpha=0.75, label="N<=1 signal days")
    ax.plot(range(len(yr)), cls, "o-", color="#185FA5", lw=1.4, ms=4, label="event cluster starts")
    ax.set_xticks(range(len(yr)), yr)
    ax.set_ylabel("days / clusters", color="#444441")
    ax.legend(loc="upper right", fontsize=8)
    ax2 = ax.twinx()
    ax2.plot(range(len(yr)), med, "s--", color="#5F5E5A", lw=1.2, ms=4, label="median N")
    ax2.set_ylabel("median N", color="#5F5E5A")
    ax2.legend(loc="upper left", fontsize=8)
    ax.set_title("When does N<=1 fire? Signal days collapse after 2020 as median N rises")
    fig.tight_layout()
    fig.savefig(FIG_OUT)
    plt.close(fig)

    def write_csv(path, rows):
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    write_csv(MATRIX_CSV, matrix_rows)
    write_csv(CLUSTER_CSV, cluster_rows)
    write_csv(YEAR_CSV, year_rows)

    payload = {
        "generated_on": date.today().isoformat(),
        "status": "supplementary read-only diagnostic; all cells disclosed; no signal selected by IC; not a strategy result; not out-of-sample",
        "preregistration": {
            "signal_definitions_fixed_before_viewing_ic": True,
            "signals": [{"name": n, "description": d} for n, _, d in signals],
            "horizons": list(HORIZONS),
            "cells": len(signals) * len(HORIZONS),
            "rule": "every cell reported; no cell promoted to a headline; no threshold chosen by IC",
            "data_and_causal_convention": "identical to ic_diagnostics.py; t close signal -> t+1 open entry -> open[t+1+h]/open[t+1]-1",
            "uncertainty": {"method": "paired 20-day moving-block bootstrap", "repetitions": N_BOOT, "seed": SEED},
        },
        "trigger_definition": {
            "when_N_is_computed": "after the close of day t, from the trailing 30-day industry return correlation network",
            "trigger_condition": "N_t <= k, with k in {0,1,2,3}; original text uses k=1",
            "earliest_executable_entry": "open of t+1",
            "original_holding": "the original report holds the position for 4 trading days after a trigger",
            "grid_holding_days": [4, 8, 12],
            "IC_horizon_h": "NOT a holding period and NOT a trigger rule; h is only the forward-return window used to score the signal",
            "cluster_rule": "consecutive trigger days separated by more than 10 CALENDAR days form a new event cluster",
            "distinction": "a signal day is not an independent event; 389 daily N<=1 observations correspond to 40-42 clusters",
        },
        "trigger_profile": trigger_profile,
        "case_months": case_rows,
        "bootstrap_degenerate_draws": BOOT_DEGENERATE,
        "bootstrap_note": (
            "For very sparse binary signals some 20-day block bootstrap draws contain no "
            "signal day at all, so Pearson is undefined in that draw. Those draws are "
            "counted and disclosed per cell, and the CI is computed from the finite draws. "
            "A high degenerate count means the CI for that cell is unreliable."
        ),
        "ic_matrix": matrix_rows,
        "h20_segment_ic": segment_rows,
        "cluster_list_N_le_1": cluster_rows,
        "by_year": year_rows,
        "interpretation": {
            "no_significant_cell": "count and list of cells whose 95% block-bootstrap interval excludes zero, if any",
            "caveat": "IC of a binary signal is mechanically shrunk by sqrt(p(1-p)); daily binary IC is inflated by repeated days within one event; all results are in-sample descriptive diagnostics.",
            "gate_status": "Gate 1 paused; 2025 final test not read; Gate 2 not started.",
        },
    }
    cells = [r for r in matrix_rows if r["crosses_zero"] is False]
    degenerate_cells = [r for r in matrix_rows if r["crosses_zero"] is None]
    payload["interpretation"]["no_significant_cell"] = (
        f"{len(cells)} of {len(matrix_rows)} IC cells exclude zero"
        + (": " + ", ".join(f"{r['signal']}@h{r['horizon_days']}" for r in cells) if cells else "")
        + f"; {len(degenerate_cells)} cells have an unreliable bootstrap CI"
    )
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")

    def r4(v):
        return None if v is None else round(v, 4)

    print(json.dumps({
        "cells": len(matrix_rows),
        "cells_excluding_zero": len(cells),
        "degenerate_ci_cells": len(degenerate_cells),
        "bootstrap_degenerate_draws_total": sum(d["degenerate_draws"] for d in BOOT_DEGENERATE),
        "excluded": [(r["signal"], r["horizon_days"], r4(r["ic_pearson"]),
                      [r4(r["ci95_lo"]), r4(r["ci95_hi"])]) for r in cells],
        "h20_by_signal": [(r["signal"], r4(r["ic_pearson"]), r4(r["ic_spearman"]),
                           [r4(r["ci95_lo"]), r4(r["ci95_hi"])])
                          for r in matrix_rows if r["horizon_days"] == 20],
        "trigger_profile": [(r["threshold_k"], r["signal_days"], r["event_clusters"],
                             r["first_signal_date"], r["last_signal_date"])
                            for r in trigger_profile],
        "case_months": [(r["case_month"], r["N_le_1_days"]) for r in case_rows],
        "figure": str(FIG_OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
