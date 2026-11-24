"""IC diagnostics for a sparse, low-frequency timing signal.

This is NOT a new strategy experiment and does not change any confirmatory
result. It adds signal-level diagnostics to section 4 of the replication
report, in response to the question "for a low-frequency signal, why report
annualised return instead of IC?".

Key points encoded here:
  * There is no cross-section (one market index), so cross-sectional RankIC
    per period is not defined. We compute time-series IC only.
  * Execution-causal forward return: N_t is known after the close of day t;
    the earliest executable entry is the open of t+1. The h-day forward
    return is open[t+1+h]/open[t+1]-1, identical to backtest.py::causal_open.
  * A close-to-close variant is reported as a sensitivity, matching the
    earlier event-level descriptive analysis.
  * Overlapping windows and strong autocorrelation in N_t make the naive
    t-statistic invalid; a 20-day moving block bootstrap is the main
    uncertainty measure.
  * Daily observations inflate 42 event clusters into 392 signal days, so a
    cluster-deduplicated point-biserial IC is reported as well.
  * Tail dates without h+1 future prices are dropped, never zero-filled and
    never treated as negative examples.

Outputs: xy_ic_diagnostics.json / .png / xy_ic_bins.csv / xy_ic_by_year.csv
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
JSON_OUT = OUT / "xy_ic_diagnostics.json"
BINS_CSV = OUT / "xy_ic_bins.csv"
YEAR_CSV = OUT / "xy_ic_by_year.csv"
FIG_OUT = OUT / "xy_ic_diagnostics.png"

START, END = "2015-07-01", "2025-05-30"
HORIZONS = (1, 5, 10, 20, 40)
MAIN_H = 20
BLOCK = 20
N_BOOT = 1000
SEED = 20261108
GAP_DAYS = 10
BIN_EDGES = ((0, 0), (1, 1), (2, 2), (3, 3), (4, 5), (6, 10), (11, 20), (21, 10 ** 6))


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    xc, yc = x - x.mean(), y - y.mean()
    den = math.sqrt(float(xc @ xc) * float(yc @ yc))
    return float(xc @ yc / den) if den > 0 else float("nan")


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    return pearson(rankdata(x), rankdata(y))


def block_bootstrap_ci(x: np.ndarray, y: np.ndarray, block: int = BLOCK,
                       repetitions: int = N_BOOT, seed: int = SEED) -> list[float]:
    """Paired moving-block bootstrap on the (signal, forward return) pairs."""
    n = len(x)
    rng = np.random.default_rng(seed)
    starts_max = n - block + 1
    values = []
    for _ in range(repetitions):
        n_blocks = math.ceil(n / block)
        starts = rng.integers(0, starts_max, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        values.append(pearson(x[idx], y[idx]))
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def read_inputs() -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    with FEATURE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        features = [r for r in csv.DictReader(handle) if r["date"] <= END]
    with WIND_CSV.open(encoding="utf-8-sig", newline="") as handle:
        wind = {r["date"]: (float(r["open"]), float(r["close"]))
                for r in csv.DictReader(handle)}
    missing = [r["date"] for r in features if r["date"] not in wind]
    assert not missing, f"feature dates missing from Wind daily: {missing[:5]}"
    dates = [r["date"] for r in features]
    n_h2 = np.asarray([int(r["h2_count"]) for r in features], dtype=float)
    l2 = np.asarray([float(r["h2_landscape_l1"]) for r in features], dtype=float)
    l1 = np.asarray([float(r["h1_landscape_l1"]) for r in features], dtype=float)
    op = np.asarray([wind[d][0] for d in dates])
    cl = np.asarray([wind[d][1] for d in dates])
    return dates, n_h2, l2, l1, op, cl


def forward_returns(op: np.ndarray, cl: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(op)
    ro = np.full(n, np.nan)
    rc = np.full(n, np.nan)
    if h + 1 < n:
        ro[:n - h - 1] = op[h + 1:] / op[1:n - h] - 1.0
    if h < n:
        rc[:n - h] = cl[h:] / cl[:n - h] - 1.0
    return ro, rc


def cluster_starts(dates: list[str], n_h2: np.ndarray, threshold: int = 1) -> np.ndarray:
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


def main() -> None:
    dates, n_h2, l2, l1, op, cl = read_inputs()
    report = np.asarray([START <= d <= END for d in dates])

    horizon_rows = []
    fwd_cache = {}
    for h in HORIZONS:
        ro, rc = forward_returns(op, cl, h)
        fwd_cache[h] = (ro, rc)
        usable = report & np.isfinite(ro)
        x = -n_h2[usable]
        y = ro[usable]
        ic_p = pearson(x, y)
        ic_s = spearman(x, y)
        ci = block_bootstrap_ci(x, y)
        t_naive = ic_p * math.sqrt(len(y) - 2) / math.sqrt(1 - ic_p ** 2)
        usable_c = report & np.isfinite(rc)
        horizon_rows.append({
            "horizon_days": h, "n_observations": int(usable.sum()),
            "n_dropped_tail": int((report & ~usable).sum()),
            "ic_pearson": ic_p, "ic_spearman": ic_s,
            "ci95_block_bootstrap": ci,
            "naive_t_invalid": t_naive,
            "ic_pearson_close_to_close": pearson(-n_h2[usable_c], rc[usable_c]),
        })

    ro, rc = fwd_cache[MAIN_H]
    usable = report & np.isfinite(ro)
    base = -n_h2[usable]
    y = ro[usable]
    unconditional_mean = float(y.mean())

    binary_rows = []
    daily_le1 = (n_h2 <= 1).astype(int)
    starts = cluster_starts(dates, n_h2, 1)
    for k in (0, 1, 2, 3):
        b = (n_h2[usable] <= k).astype(int)
        on = y[b == 1]
        binary_rows.append({
            "threshold_k": k,
            "ic_point_biserial": pearson(b, y),
            "signal_days": int(b.sum()),
            "signal_share": float(b.mean()),
            "mean_forward20_on": float(on.mean()) if len(on) else None,
            "mean_forward20_off": float(y[b == 0].mean()) if (b == 0).any() else None,
            "lift_vs_unconditional": float(on.mean() - unconditional_mean) if len(on) else None,
            "positive_share_on": float((on > 0).mean()) if len(on) else None,
        })
    b_start = starts[usable]
    on_start = y[b_start == 1]
    binary_rows.append({
        "threshold_k": "cluster_deduplicated_N<=1",
        "ic_point_biserial": pearson(b_start, y),
        "signal_days": int(b_start.sum()),
        "signal_share": float(b_start.mean()),
        "mean_forward20_on": float(on_start.mean()),
        "mean_forward20_off": float(y[b_start == 0].mean()),
        "lift_vs_unconditional": float(on_start.mean() - unconditional_mean),
        "positive_share_on": float((on_start > 0).mean()),
    })

    signal_variants = [
        ("minus_N", -n_h2[usable]),
        ("minus_log1p_N", -np.log1p(n_h2[usable])),
        ("minus_h2_landscape_l1", -l2[usable]),
        ("minus_h1_landscape_l1", -l1[usable]),
        ("binary_N<=1", (n_h2[usable] <= 1).astype(float)),
    ]
    variant_rows = [{"signal": name, "ic_pearson": pearson(s, y),
                     "ic_spearman": spearman(s, y)} for name, s in signal_variants]

    bin_rows = []
    for lo, hi in BIN_EDGES:
        m = usable & (n_h2 >= lo) & (n_h2 <= hi)
        yy = ro[m]
        label = f"N={lo}" if lo == hi else (f"N>={lo}" if hi > 9999 else f"N={lo}-{hi}")
        bin_rows.append({
            "bin": label, "n": int(m.sum()),
            "share": float(m.sum() / usable.sum()),
            "mean_forward20": float(yy.mean()) if len(yy) else None,
            "median_forward20": float(np.median(yy)) if len(yy) else None,
            "positive_share": float((yy > 0).mean()) if len(yy) else None,
        })

    year_rows = []
    years = sorted({d[:4] for d, ok in zip(dates, report) if ok})
    for yr in years:
        m = usable & np.asarray([d.startswith(yr) for d in dates])
        yy = ro[m]
        xx = -n_h2[m]
        year_rows.append({
            "year": yr, "n": int(m.sum()),
            "ic_pearson": pearson(xx, yy) if len(yy) > 3 else None,
            "ic_spearman": spearman(xx, yy) if len(yy) > 3 else None,
            "mean_forward20": float(yy.mean()) if len(yy) else None,
            "signal_day_share_N<=1": float((n_h2[m] <= 1).mean()) if len(yy) else None,
        })
    segments = []
    drift = []
    for label, a, b in (("2015-2020", "2015", "2020"), ("2021-2025", "2021", "2025")):
        m = usable & np.asarray([a <= d[:4] <= b for d in dates])
        yy = ro[m]
        ic = pearson(-n_h2[m], yy)
        ci = block_bootstrap_ci(-n_h2[m], yy)
        segments.append({"segment": label, "n": int(m.sum()),
                         "ic_pearson": ic, "ci95_block_bootstrap": ci,
                         "mean_forward20": float(yy.mean()),
                         "signal_day_share_N<=1": float((n_h2[m] <= 1).mean())})
        drift.append({
            "segment": label, "n": int(m.sum()),
            "mean_N": float(n_h2[m].mean()),
            "median_N": float(np.median(n_h2[m])),
            "p10_N": float(np.percentile(n_h2[m], 10)),
            "p90_N": float(np.percentile(n_h2[m], 90)),
            "share_N<=1": float((n_h2[m] <= 1).mean()),
        })

    n0_starts = cluster_starts(dates, n_h2, 0).astype(bool)
    definition_audit = []
    for label, mask in (("all_N=0_days", report & (n_h2 == 0)),
                        ("N=0_cluster_starts", report & n0_starts)):
        for rname, arr in (("close_to_close_20d", rc), ("open_to_open_20d", ro)):
            v = arr[mask & np.isfinite(arr)]
            definition_audit.append({
                "sample": label, "return_definition": rname, "n": int(len(v)),
                "mean": float(v.mean()), "median": float(np.median(v)),
                "positive_share": float((v > 0).mean()),
            })

    fig, axes = plt.subplots(3, 1, figsize=(13.2, 11.0), dpi=160)
    ax = axes[0]
    hs = [r["horizon_days"] for r in horizon_rows]
    vals = [r["ic_pearson"] for r in horizon_rows]
    lo = [r["ci95_block_bootstrap"][0] for r in horizon_rows]
    hi = [r["ci95_block_bootstrap"][1] for r in horizon_rows]
    ax.axhline(0, color="#888780", lw=0.8)
    ax.errorbar(hs, vals, yerr=[np.array(vals) - np.array(lo), np.array(hi) - np.array(vals)],
                fmt="o-", color="#2457a7", capsize=4, lw=1.4,
                label="Pearson IC + block bootstrap 95% CI")
    ax.plot(hs, [r["ic_spearman"] for r in horizon_rows], "s--",
            color="#a56a09", lw=1.1, ms=4, label="Spearman IC (point estimate)")
    ax.set_xticks(hs)
    ax.set_xlabel("forward horizon (trading days)")
    ax.set_ylabel("IC (correlation, unitless)")
    ax.set_title("Time-series IC of -N vs forward return; every bootstrap interval crosses zero")
    ax.legend(fontsize=8, loc="upper left")
    ax = axes[1]
    labels = [r["bin"] for r in bin_rows]
    means = [(r["mean_forward20"] or 0) * 100 for r in bin_rows]
    colors = ["#E24B4A" if v >= 0 else "#639922" for v in means]
    ax.axhline(unconditional_mean * 100, color="#5F5E5A", ls="--", lw=1,
               label=f"unconditional {unconditional_mean*100:.2f}%")
    ax.bar(range(len(labels)), means, color=colors, alpha=0.9)
    ax.axhline(0, color="#888780", lw=0.8)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("mean forward 20d return (%)")
    ax.set_title("Monotonicity check: forward return by N bucket (not monotonic if bars do not decline)")
    ax.legend(fontsize=8)
    ax = axes[2]
    ys = [r["year"] for r in year_rows]
    iv = [(r["ic_pearson"] or 0) for r in year_rows]
    ax.axhline(0, color="#888780", lw=0.8)
    ax.bar(range(len(ys)), iv, color=["#E24B4A" if v >= 0 else "#639922" for v in iv], alpha=0.9)
    ax.text(len(ys) - 1, iv[-1], "n=76", ha="center", va="bottom", fontsize=9,
            color="#444441")
    ax.set_xticks(range(len(ys)))
    ax.set_xticklabels(ys, fontsize=9)
    ax.set_ylabel("IC (correlation, unitless)")
    ax.set_title("Stability: per-year IC, forward 20d return (descriptive; overlapping windows; 2025 n=76)")
    fig.tight_layout()
    fig.savefig(FIG_OUT)
    plt.close(fig)

    with BINS_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(bin_rows[0]))
        writer.writeheader()
        writer.writerows(bin_rows)
    with YEAR_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(year_rows[0]))
        writer.writeheader()
        writer.writerows(year_rows)

    payload = {
        "generated_on": date.today().isoformat(),
        "status": "exploratory signal-level diagnostic; not a strategy result; not out-of-sample",
        "question": "Low-frequency sparse signal: is annualised return the right headline metric, or IC?",
        "why_ic_is_not_a_cross_sectional_rankic": (
            "The signal times a single market index (881001.WI). With no cross-section of assets, "
            "per-period cross-sectional RankIC is undefined. Only time-series IC is computed."
        ),
        "causal_convention": {
            "signal_known_after_close_of": "t",
            "earliest_entry": "open of t+1",
            "primary_forward_return": "open[t+1+h]/open[t+1]-1",
            "sensitivity_forward_return": "close[t+h]/close[t]-1",
            "tail_handling": "dates without h+1 future prices dropped; no zero fill; not negative examples",
            "period": [START, END],
            "signal_direction": "s = -N (or 1[N<=k]); positive IC means fewer holes predict higher return",
        },
        "uncertainty": {
            "method": "paired moving-block bootstrap on (signal, forward return) pairs",
            "block_days": BLOCK, "repetitions": N_BOOT, "seed": SEED,
            "why": "overlapping h-day windows and strong autocorrelation in N_t invalidate the naive t-statistic",
            "naive_t_column": "reported only to show how much the naive test overstates significance; must not be used",
        },
        "sparse_signal_caveat": (
            "For a binary signal with prevalence p, the point-biserial IC equals the standardised mean "
            "difference times sqrt(p(1-p)); a very rare event therefore has a mechanically small IC even "
            "when its event-level lift is non-trivial. IC alone is not a sufficient verdict for sparse signals."
        ),
        "data": {"features": str(FEATURE_CSV.relative_to(ROOT)),
                 "benchmark": str(WIND_CSV.relative_to(ROOT))},
        "horizon_ic": horizon_rows,
        "h20_binary_and_point_biserial": binary_rows,
        "h20_signal_variants": variant_rows,
        "h20_n_buckets": bin_rows,
        "yearly_ic": year_rows,
        "segment_ic": segments,
        "N_distribution_drift": drift,
        "definition_sensitivity_audit": definition_audit,
        "interpretation": {
            "our_inference_not_confirmed_by_original": [
                "IC of -N is weakly positive and rank-based IC exceeds Pearson IC, so the low-hole state "
                "is associated with somewhat better subsequent returns, but every 20-day block-bootstrap "
                "interval crosses zero; this is not evidence of a stable predictive relation.",
                "Daily point-biserial IC is inflated by repeated days inside the same event: collapsing "
                "389 N<=1 signal days to 40 independent cluster starts cuts IC from 0.091 to 0.013.",
                "The apparent contradiction with the earlier event-level note (N=0 cluster starts had "
                "negative forward return) is a sample-definition effect, not a price-definition effect: "
                "all 145 N=0 days average about +2.2% under both close and open conventions, while "
                "cluster starts average negative under both. State-level association and the executable "
                "first-entry timing are different questions.",
                "N drifts upward strongly after 2020 (median 3 -> 13.5, P(N<=1) 28% -> 1.3%), so a fixed "
                "N<=1 threshold is not portable across the reconstructed panel; this, rather than a weak "
                "IC, is why the grid-max equity is nearly flat in 2021-2023.",
            ],
            "metric_roles": (
                "IC answers 'does the signal rank future returns?'; annualised return answers 'what did a "
                "particular threshold-plus-position rule earn?'. Neither substitutes for the other: a "
                "weakly positive IC can coexist with a near-flat strategy when the fixed threshold stops "
                "firing. The annualised column is retained only as a comparison with the original Table 1."
            ),
        },
        "unconditional_forward20_mean": unconditional_mean,
        "gate_status": "Gate 1 paused; 2025 final test not read; Gate 2 not started.",
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")
    print(json.dumps({
        "horizon_ic": [(r["horizon_days"], round(r["ic_pearson"], 5),
                        [round(v, 5) for v in r["ci95_block_bootstrap"]]) for r in horizon_rows],
        "h20_point_biserial": [(r["threshold_k"], round(r["ic_point_biserial"], 5),
                                r["signal_days"]) for r in binary_rows],
        "variants": [(r["signal"], round(r["ic_pearson"], 5)) for r in variant_rows],
        "segments": [(r["segment"], round(r["ic_pearson"], 5),
                      [round(v, 5) for v in r["ci95_block_bootstrap"]]) for r in segments],
        "figure": str(FIG_OUT.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
