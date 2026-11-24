"""Qualitative relation study + preregistered exploratory parameter grid.

Scope (fixed BEFORE any strategy performance was viewed):
  * benchmark: Wind 881001.WI daily (primary) and SW A-index 801003 (proxy);
  * features: corrected v1.2, 30-day window topology (window NOT recomputed);
  * signal  : finite H2 interval count N <= k, k in {0,1,2,3};
  * holding : hold in {4,8,12} feature days, strict-open execution;
  * period  : 2015-07-01..2025-05-30, each period starts flat;
  * cost    : 0.001 per side, forced flat at period end.
All 4 x 3 x 2 = 24 cells are reported. No cell is selected as "the result";
the grid maximum is labelled an in-sample upper bound with selection bias.

This is exploratory evidence about parameter sensitivity, NOT a replication
of Table 1/2, NOT an out-of-sample result, and NOT Gate 1/2 work.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest import metric  # noqa: E402  (identical execution/metric definition)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
FEATURE_CSV = OUT / "xy_corrected_sw193_ifind_peak_features.csv"
WIND_CSV = OUT / "xy_wind_all_a_daily.csv"
PROXY_DB = OUT / "xy_replication_data.db"
JSON_OUT = OUT / "xy_qualitative_parameter_study.json"
EVENT_CSV = OUT / "xy_qualitative_events.csv"
GRID_CSV = OUT / "xy_parameter_grid.csv"
FIG_EVENTS = OUT / "xy_qualitative_h2_events.png"
FIG_GRID = OUT / "xy_parameter_grid_equity.png"

START, END = "2015-07-01", "2025-05-30"
THRESHOLDS = (0, 1, 2, 3)
HOLDS = (4, 8, 12)
COST = 0.001
GAP_DAYS = 10
LOOKBACK, LOOKAHEAD = 20, 20

ORIGINAL_TABLE1 = {"annual_return": 0.1287, "annual_volatility": 0.1333,
                   "return_risk_ratio": 0.97, "max_drawdown": -0.1634,
                   "annual_two_sided_turnover": 15.04,
                   "benchmark_annual_return": 0.0069,
                   "benchmark_annual_volatility": 0.2273,
                   "benchmark_max_drawdown": -0.4068}
ORIGINAL_TABLE2 = {"annual_return": 0.1097, "annual_volatility": 0.1149,
                   "return_risk_ratio": 0.95, "max_drawdown": -0.1227,
                   "annual_two_sided_turnover": 11.25,
                   "benchmark_annual_return": 0.0396,
                   "benchmark_annual_volatility": 0.2004,
                   "benchmark_max_drawdown": -0.3717}


def read_features() -> list[dict]:
    with FEATURE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for r in rows:
        for key in ("h2_count", "n_nodes"):
            r[key] = int(r[key])
        for key in ("h2_landscape_l1", "industry_average_correlation",
                    "correlation_leading_eigenvalue_share"):
            r[key] = float(r[key])
    return rows


def read_wind() -> dict[str, tuple[float, float]]:
    with WIND_CSV.open(encoding="utf-8", newline="") as handle:
        return {r["date"]: (float(r["open"]), float(r["close"]))
                for r in csv.DictReader(handle)}


def read_proxy() -> dict[str, tuple[float, float]]:
    con = sqlite3.connect(f"file:{PROXY_DB}?mode=ro", uri=True)
    rows = con.execute("SELECT date,open,close FROM benchmark_daily WHERE code='801003'").fetchall()
    con.close()
    return {d: (float(o), float(c)) for d, o, c in rows}


def as_date(text: str) -> date:
    return datetime.fromisoformat(text).date()


def event_analysis(rows: list[dict], prices: dict[str, tuple[float, float]],
                   threshold: int) -> tuple[list[dict], dict]:
    dates = [r["date"] for r in rows]
    close = np.asarray([prices[d][1] for d in dates])
    h2 = np.asarray([r["h2_count"] for r in rows])
    signal_idx = [i for i in range(len(rows)) if START <= dates[i] <= END and h2[i] <= threshold]
    clusters: list[list[int]] = []
    for i in signal_idx:
        if not clusters or (as_date(dates[i]) - as_date(dates[clusters[-1][-1]])).days > GAP_DAYS:
            clusters.append([i])
        else:
            clusters[-1].append(i)

    events = []
    for cluster in clusters:
        t = cluster[0]
        prior = float(close[t] / close[t - LOOKBACK] - 1.0) if t >= LOOKBACK else None
        nxt = float(close[t + LOOKAHEAD] / close[t] - 1.0) if t + LOOKAHEAD < len(rows) else None
        window = close[max(0, t - 250):t + 1]
        drawdown = float(close[t] / window.max() - 1.0)
        prior_h2 = h2[max(0, t - 60):t + 1]
        events.append({
            "start": dates[t], "end": dates[cluster[-1]], "cluster_days": len(cluster),
            "h2_at_start": int(h2[t]), "n_nodes": rows[t]["n_nodes"],
            "prior20_benchmark_return": prior,
            "next20_benchmark_return": nxt,
            "drawdown_vs_prior250_high": drawdown,
            "h2_max_prior60": int(prior_h2.max()),
            "industry_average_correlation": rows[t]["industry_average_correlation"],
            "leading_eigenvalue_share": rows[t]["correlation_leading_eigenvalue_share"],
        })

    report_idx = [i for i, d in enumerate(dates) if START <= d <= END and i + LOOKAHEAD < len(rows)]
    unconditional = np.asarray([close[i + LOOKAHEAD] / close[i] - 1.0 for i in report_idx])
    conditional = np.asarray([e["next20_benchmark_return"] for e in events
                              if e["next20_benchmark_return"] is not None])
    prior = np.asarray([e["prior20_benchmark_return"] for e in events
                        if e["prior20_benchmark_return"] is not None])
    corr = np.asarray([e["industry_average_correlation"] for e in events])
    eig = np.asarray([e["leading_eigenvalue_share"] for e in events])
    report_rows = [rows[i] for i in report_idx]
    summary = {
        "threshold": threshold,
        "signal_days": len(signal_idx),
        "report_days": sum(START <= d <= END for d in dates),
        "signal_day_share": len(signal_idx) / max(1, sum(START <= d <= END for d in dates)),
        "event_clusters": len(clusters),
        "events_with_prior20": len(prior),
        "prior20_negative_share": float((prior < 0).mean()),
        "prior20_mean": float(prior.mean()),
        "events_with_next20": len(conditional),
        "next20_positive_share": float((conditional > 0).mean()),
        "next20_mean": float(conditional.mean()),
        "next20_median": float(np.median(conditional)),
        "unconditional_next20_positive_share": float((unconditional > 0).mean()),
        "unconditional_next20_mean": float(unconditional.mean()),
        "unconditional_next20_median": float(np.median(unconditional)),
        "mean_industry_average_correlation_on_events": float(corr.mean()),
        "mean_industry_average_correlation_all": float(np.mean([r["industry_average_correlation"] for r in report_rows])),
        "mean_leading_eigenvalue_share_on_events": float(eig.mean()),
        "mean_leading_eigenvalue_share_all": float(np.mean([r["correlation_leading_eigenvalue_share"] for r in report_rows])),
    }
    return events, summary


def run_grid(rows: list[dict], prices: dict[str, tuple[float, float]],
             benchmark_name: str) -> tuple[list[dict], dict[str, list[dict]]]:
    dates = [r["date"] for r in rows]
    date_array = np.asarray(dates)
    close = np.asarray([prices[d][1] for d in dates])
    open_ = np.asarray([prices[d][0] for d in dates])
    h2 = np.asarray([r["h2_count"] for r in rows])
    n = len(rows)
    results, equities = [], {}
    for k in THRESHOLDS:
        signal = h2 <= k
        for hold in HOLDS:
            interval_dates, asset_returns, sources = [], [], []
            for end in range(1, n):
                start = end - 1
                if start - hold < 0:
                    continue
                interval_dates.append(dates[end])
                asset_returns.append(float(open_[end] / open_[end - 1] - 1.0))
                sources.append(np.arange(start - hold, start))
            if not interval_dates:
                raise RuntimeError("no return intervals")
            interval_dates = np.asarray(interval_dates)
            asset_returns = np.asarray(asset_returns)
            period_signal = signal & (date_array >= START) & (date_array <= END)
            positions = np.asarray([period_signal[s].any() for s in sources], dtype=int)
            idx = np.flatnonzero((interval_dates >= START) & (interval_dates <= END))
            p = positions[idx].copy()
            r = asset_returns[idx].copy()
            previous = np.concatenate([[0], p[:-1]])
            c = np.abs(p - previous) * COST
            if len(p) and p[-1] == 1:
                c[-1] += COST
            stats, daily = metric(interval_dates[idx], r, p, c)
            key = f"k{k}_h{hold}"
            row = {"benchmark": benchmark_name, "k": k, "hold_days": hold,
                   "raw_signal_days": int(signal.sum()),
                   "raw_signal_share": float(signal[(date_array >= START) & (date_array <= END)].mean()),
                   **{field: stats[field] for field in (
                       "n_return_days", "total_return", "annual_return", "annual_volatility",
                       "return_risk_ratio", "max_drawdown", "annual_two_sided_turnover",
                       "exposure", "n_entries", "benchmark_annual_return",
                       "benchmark_annual_volatility", "benchmark_max_drawdown")}}
            results.append(row)
            equities[key] = daily
    return results, equities


def draw_events(rows: list[dict], prices: dict[str, tuple[float, float]],
                events: list[dict], target: Path) -> None:
    dates = [r["date"] for r in rows]
    idx = [i for i, d in enumerate(dates) if START <= d <= END]
    x = [datetime.fromisoformat(dates[i]).date() for i in idx]
    h2 = [rows[i]["h2_count"] for i in idx]
    close = [prices[dates[i]][1] for i in idx]
    event_dates = {e["start"] for e in events}
    fig, axes = plt.subplots(2, 1, figsize=(13.6, 8.2), dpi=160)
    ax = axes[0]
    ax.plot(x, h2, color="#174a7c", lw=0.9, label="H2 finite intervals (daily)")
    ax.axhline(1, color="#c74343", lw=0.9, ls="--", label="N=1 threshold")
    ax.scatter([datetime.fromisoformat(d).date() for d in event_dates],
               [rows[dates.index(d)]["h2_count"] for d in sorted(event_dates)],
               color="#c74343", s=14, zorder=3, label="N<=1 event start")
    ax.set_ylabel("H2 count")
    ax.set_title("Corrected v1.2: sparse-hole events and Wind All-A index")
    ax.legend(loc="upper left", fontsize=8)
    ax2 = ax.twinx()
    ax2.plot(x, close, color="#a0a8b4", lw=0.8, alpha=0.85)
    ax2.set_ylabel("881001.WI close (grey)")
    ax = axes[1]
    pairs = [(e["prior20_benchmark_return"], e["next20_benchmark_return"])
             for e in events if e["prior20_benchmark_return"] is not None
             and e["next20_benchmark_return"] is not None]
    px = [a for a, _ in pairs]
    py = [b for _, b in pairs]
    ax.axhline(0, color="#999", lw=0.8)
    ax.axvline(0, color="#999", lw=0.8)
    ax.scatter(px, py, color="#2457a7", s=26, alpha=0.8)
    ax.set_xlabel("Prior 20-feature-day benchmark return")
    ax.set_ylabel("Next 20-feature-day benchmark return")
    ax.set_title("Event-level descriptive check: oversold before vs rebound after (no costs, no strategy)")
    fig.tight_layout()
    fig.savefig(target)
    plt.close(fig)


def draw_grid(equities: dict[str, list[dict]], grid: list[dict], target: Path) -> None:
    primary = [r for r in grid if r["benchmark"] == "881001.WI"]
    best = max(primary, key=lambda r: r["annual_return"])
    best_key = f"k{best['k']}_h{best['hold_days']}"
    dates = [datetime.fromisoformat(d["date"]).date() for d in equities[best_key]]
    fig, axes = plt.subplots(2, 1, figsize=(13.6, 8.2), dpi=160, sharex=True,
                             gridspec_kw={"height_ratios": [3, 1]})
    colors = {0: "#6b8fb3", 1: "#2457a7", 2: "#a56a09", 3: "#8a6ea8"}
    for r in primary:
        key = f"k{r['k']}_h{r['hold_days']}"
        eq = [d["strategy_equity_net"] for d in equities[key]]
        axes[0].plot(dates, eq, color=colors[r["k"]], lw=0.8, alpha=0.45)
    eq = [d["strategy_equity_net"] for d in equities[best_key]]
    axes[0].plot(dates, eq, color="#111", lw=1.7,
                 label=f"grid max: k={best['k']}, hold={best['hold_days']} (selection-biased)")
    axes[0].set_ylabel("net equity (start=1)")
    axes[0].set_title("Preregistered 12-cell grid, Wind 881001.WI, strict open, costs included")
    axes[0].legend(loc="upper left", fontsize=8)
    pos = [d["position"] for d in equities[best_key]]
    axes[1].fill_between(dates, 0, pos, step="mid", color="#2457a7", alpha=0.55)
    axes[1].set_ylabel("position")
    axes[1].set_xlabel("Grid-max cell exposure (entries = %d)" % best["n_entries"])
    fig.tight_layout()
    fig.savefig(target)
    plt.close(fig)


def main() -> None:
    # Wind daily ends on 2025-05-30; the corrected feature file continues to
    # 2026-11-03. Restrict the analysis grid to the reported backtest window,
    # so no price is missing and no post-report date leaks into any cell.
    rows = [r for r in read_features() if r["date"] <= END]
    wind = read_wind()
    proxy = read_proxy()
    missing_wind = [r["date"] for r in rows if r["date"] not in wind]
    missing_proxy = [r["date"] for r in rows if r["date"] not in proxy]
    assert not missing_wind and not missing_proxy, (missing_wind[:3], missing_proxy[:3])

    events, event_summary = event_analysis(rows, wind, 1)
    events0, event_summary0 = event_analysis(rows, wind, 0)

    grid, equities = run_grid(rows, wind, "881001.WI")
    proxy_grid, _ = run_grid(rows, proxy, "801003.SW")
    all_grid = grid + proxy_grid
    with GRID_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_grid[0]))
        writer.writeheader()
        writer.writerows(all_grid)
    with EVENT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(events[0]))
        writer.writeheader()
        writer.writerows(events)

    best = max(grid, key=lambda r: r["annual_return"])
    worst = min(grid, key=lambda r: r["annual_return"])
    best_daily = equities[f"k{best['k']}_h{best['hold_days']}"]
    by_year: dict[str, list[int]] = {}
    for item in best_daily:
        by_year.setdefault(item["date"][:4], []).append(int(item["position"]))
    exposure_by_year = {y: float(np.mean(v)) for y, v in sorted(by_year.items())}
    flat_mid = [d for d in best_daily if "2021-01-01" <= d["date"] <= "2023-12-31"]
    ref = ORIGINAL_TABLE1
    draw_events(rows, wind, events, FIG_EVENTS)
    draw_grid(equities, grid, FIG_GRID)

    report = {
        "generated_on": date.today().isoformat(),
        "status": "exploratory; preregistered grid; not a replication result; not out-of-sample",
        "preregistration": {
            "grid_fixed_before_viewing_any_strategy_performance": True,
            "what_was_seen_before_fixing_grid": "only feature-level signal frequencies (N<=1 = 392/2391 report days); no cell performance",
            "thresholds": list(THRESHOLDS), "hold_days": list(HOLDS),
            "cells": len(THRESHOLDS) * len(HOLDS) * 2,
            "window_days": 30,
            "window_note": "30-day topology window unchanged; recomputing 20/40-day VR topology would be a separate experiment and would further expand researcher degrees of freedom",
            "execution": "strict open, identical to backtest.py::metric / signal_source",
            "period": [START, END], "cost_per_side": COST,
            "selection_rule": "none; every cell is disclosed and no cell is promoted to a headline result",
        },
        "data": {
            "features": "outputs/xy_corrected_sw193_ifind_peak_features.csv (v1.2), truncated at 2025-05-30 for this analysis",
            "primary_benchmark": "outputs/xy_wind_all_a_daily.csv (881001.WI daily, 3012 rows)",
            "proxy_benchmark": "xy_replication_data.db benchmark_daily code=801003",
            "daily_benchmark_status": "Wind All-A daily now available; monthly-only limitation applies only to earlier figure-background work",
        },
        "event_analysis": {"N_le_1": event_summary, "N_eq_0": event_summary0,
                           "events": events},
        "grid": all_grid,
        "grid_max": {
            **{key: best[key] for key in ("benchmark", "k", "hold_days", "annual_return",
                                          "annual_volatility", "max_drawdown", "exposure",
                                          "n_entries", "annual_two_sided_turnover")},
            "warning": "In-sample maximum over 12 cells on the same 2015-07..2025-05 window; contains selection bias and must not be quoted as strategy performance or replication evidence.",
            "exposure_by_year": exposure_by_year,
            "exposure_2021_2023": float(np.mean([d["position"] for d in flat_mid])),
            "step_shape_note": "The local best cell also has a step-like equity curve, but with 62 entries versus about 8-10 major jumps visible in Figure 15/16, and it is almost entirely flat during 2021-2023 while the original figures show conspicuous jumps in those years. Similar-looking step shapes therefore do not imply identical signal timing.",
        },
        "grid_min": {"k": worst["k"], "hold_days": worst["hold_days"],
                     "annual_return": worst["annual_return"]},
        "original_reference_from_screenshots": {
            "table1_sw2_2015_07_2025_05": ORIGINAL_TABLE1,
            "table2_wind_level4_2016_01_2025_05": ORIGINAL_TABLE2,
            "figure15_visible_steps_estimate": "about 8-10 discrete jumps separated by long flat plateaus (image reading only)",
            "note": "Numbers transcribed from user-supplied screenshots, not a Wind export or an original daily series; table2 uses Wind level-4 industries, which this project does not have.",
        },
        "provenance": {
            "from_original_text": [
                "When 2-dimensional holes are extremely few, the market 'seems' to correspond to a potential rebound (explicitly qualitative wording).",
                "Extreme signals are rare; once a rebound occurs it tends to persist briefly, hence the long signal is extended for e.g. 4 trading days.",
                "Table 1 / Table 2 / Figure 15 / Figure 16 statistics and step-like equity shapes are visible in the screenshots.",
            ],
            "local_observation": [
                "N<=1 occupies 16.39% of report feature days and forms 42 event clusters; this is far from 'rare' in the local reconstruction.",
                "Event-level prior/next 20-day benchmark returns, correlation structure and drawdown statistics are in event_analysis.",
                "All 24 grid cells and the full equity curves are disclosed; the grid maximum is selection-biased.",
            ],
            "our_inference_not_confirmed_by_original": [
                "A possible mechanism is that broad sell-offs synchronise industry returns, raising average correlation / leading eigenvalue share and collapsing high-dimensional VR holes; the original visible text does not state this mechanism.",
                "Parameters can move annualised return numbers but cannot manufacture the original's sparse-signal, step-like equity structure; a numeric match would therefore not establish replication.",
            ],
            "not_claimed": [
                "Wind level-4 industry panel reproduced (we do not have it)",
                "XY Wind daily industry membership or return details obtained",
                "N definition confirmed by the original authors",
                "Any out-of-sample or Gate 1/2 conclusion",
            ],
        },
        "gate_status": "Gate 1 paused; 2025 final test not read; Gate 2 not started.",
    }
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")
    print({
        "json": str(JSON_OUT), "grid_cells": len(all_grid),
        "event_clusters": event_summary["event_clusters"],
        "signal_share": round(event_summary["signal_day_share"], 4),
        "grid_max": {"k": best["k"], "hold": best["hold_days"],
                     "annual_return": round(best["annual_return"], 4),
                     "max_drawdown": round(best["max_drawdown"], 4),
                     "entries": best["n_entries"]},
        "grid_min_annual_return": round(worst["annual_return"], 4),
        "table1_annual_return_reference": ref["annual_return"],
        "figures": [str(FIG_EVENTS), str(FIG_GRID)],
    })


if __name__ == "__main__":
    main()
