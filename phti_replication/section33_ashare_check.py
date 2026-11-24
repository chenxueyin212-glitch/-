"""Exploratory check of Baitinger & Flegel (2021), Sect. 3.3, on A-share data.

The paper's Sect. 3.3 compares one quiet and one turbulent 60-day window of
US Financials + Construction daily returns (in percent) and claims three PH
differences:
  (i)   mean H0 length low (quiet) vs high (turbulent)
  (ii)  H0 evolution exponential-shaped (quiet) vs flat (turbulent)
  (iii) H1 features born at larger delta and longer-lived (turbulent)

This script applies the SAME construction to two A-share industry pairs.
Provenance / scope:
  * IN-SAMPLE, exploratory, descriptive only. No equity index is loaded, no
    strategy return / IC / Sharpe / regression is computed, and the sealed
    2025 test is never read.
  * Returns are daily simple returns expressed in percent, mirroring the
    paper's figures (whose axes are "returns in %"). delta = 1 means one
    percentage point, as in the paper's Figs. 2 and 3.
  * Window selection is fixed BEFORE any PH output is inspected: for every
    month-end anchor with a complete 60-day history, compute the mean of the
    two industries' return variances; take the lowest (quiet) and highest
    (turbulent). Full-sample Spearman correlations are reported as well, so
    the conclusion does not rest on two handpicked windows.
  * The two industry pairs are declared in advance and are not swapped after
    looking at results.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from ripser import ripser
from scipy.stats import spearmanr

from phti_pipeline import finite_diagram, load_industry_panel, month_end_indices

ROOT = Path(__file__).resolve().parents[2]
DB = (ROOT.parent / "a_share_pit" / "tdx_central.db").resolve()
OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

END = "2024-12-31"
WINDOW = 60
DELTA_PCT = 1.0

PAIRS = [
    {
        "key": "p16_realestate_steel",
        "codes": ["801180", "801040"],
        "start": "2005-01-04",
        "analogue": "A-share property + cyclical pair, long sample incl. 2008",
    },
    {
        "key": "p27_bank_building",
        "codes": ["801780", "801710"],
        "start": "2014-02-21",
        "analogue": "closest A-share analogue of US Financials + Construction",
    },
]

CORRELATED_COLUMNS = [
    "h0_death_mean", "h0_death_cv", "h0_top1_over_rest_median",
    "components_at_delta_1pct", "h1_count", "h1_birth_mean",
    "h1_persistence_mean", "return_correlation", "cov_eigenvalue_ratio",
]


def variance_pct(r: np.ndarray) -> float:
    return float(np.var(r, axis=0, ddof=1).mean())


def ph_summary(r: np.ndarray) -> dict:
    """PH descriptors of one 60 x 2 return cloud (units: percentage points)."""
    dgms = ripser(r, maxdim=1, metric="euclidean", coeff=2)["dgms"]
    h0 = finite_diagram(dgms[0])
    h1 = finite_diagram(dgms[1])
    deaths = np.sort(h0[:, 1]) if len(h0) else np.array([0.0])
    longest = float(deaths[-1])
    rest = deaths[:-1]
    rest_med = float(np.median(rest)) if len(rest) else 0.0
    pers_h1 = h1[:, 1] - h1[:, 0] if len(h1) else np.array([])
    corr = float(np.corrcoef(r[:, 0], r[:, 1])[0, 1])
    eig = np.linalg.eigvalsh(np.cov(r, rowvar=False, ddof=1))
    return {
        "variance_pct2": variance_pct(r),
        "sd_industry_pct": [float(np.std(r[:, j], ddof=1)) for j in range(2)],
        "return_correlation": corr,
        "cov_eigenvalue_ratio": float(eig[-1] / max(eig[0], 1e-12)),
        "h0_count": int(len(h0)),
        "h0_death_mean": float(deaths.mean()),
        "h0_death_median": float(np.median(deaths)),
        "h0_death_max": longest,
        "h0_death_cv": float(deaths.std(ddof=1) / deaths.mean())
        if deaths.mean() > 0 else None,
        "h0_top1_over_rest_median": float(longest / rest_med)
        if rest_med > 0 else None,
        "components_at_delta_1pct": int((deaths > DELTA_PCT).sum()) + 1,
        "h1_count": int(len(h1)),
        "h1_birth_mean": float(h1[:, 0].mean()) if len(h1) else None,
        "h1_persistence_mean": float(pers_h1.mean()) if len(pers_h1) else None,
        "h1_persistence_max": float(pers_h1.max()) if len(pers_h1) else None,
    }


def spearman_against_variance(rows: list[dict], col: str) -> dict | None:
    var = np.asarray([x["variance_pct2"] for x in rows], dtype=float)
    y = np.asarray([x[col] if x[col] is not None else np.nan for x in rows],
                   dtype=float)
    ok = np.isfinite(y) & np.isfinite(var)
    if ok.sum() < 10:
        return None
    rho, p = spearmanr(var[ok], y[ok])
    return {
        "spearman_rho": float(rho) if math.isfinite(rho) else None,
        "p_value_naive": float(p) if math.isfinite(p) else None,
        "n": int(ok.sum()),
        "warning": "naive p-value; month-end windows overlap and are not independent",
    }


def main() -> None:
    report = {
        "status": "exploratory_in_sample_descriptive_only",
        "paper_section": "3.3 (Figs. 2 and 3)",
        "provenance": "original paper: quiet = lowest 60-day variance month-end "
                      "window in 2006-2008 (2007-05-31), turbulent = highest "
                      "(2008-11-28), US Financials + Construction returns in %; "
                      "this script: same rule over the full A-share development "
                      "period, two predeclared industry pairs",
        "performance_evaluated": False,
        "equity_index_loaded": False,
        "test_2025_read": False,
        "window_days": WINDOW,
        "delta_pct": DELTA_PCT,
        "paper_claims": {
            "i_h0_mean_length": "quiet low, turbulent high",
            "ii_h0_evolution": "quiet exponential-shaped, turbulent flatter",
            "iii_h1": "turbulent born at larger delta and longer-lived",
        },
        "pairs": {},
    }

    for pair in PAIRS:
        panel = load_industry_panel(DB, pair["codes"], pair["start"], END,
                                    name=pair["key"])
        r = panel.simple_returns * 100.0
        dates = list(panel.dates)
        anchors = [i for i in month_end_indices(dates) if i >= WINDOW - 1]
        rows = []
        for i in anchors:
            s = ph_summary(r[i - WINDOW + 1:i + 1])
            s["month_end"] = dates[i]
            rows.append(s)

        var = np.asarray([x["variance_pct2"] for x in rows], dtype=float)
        quiet = dict(rows[int(np.argmin(var))])
        turbulent = dict(rows[int(np.argmax(var))])
        report["pairs"][pair["key"]] = {
            "description": pair["analogue"],
            "codes": pair["codes"],
            "first_date": dates[0],
            "last_date": dates[-1],
            "n_month_end_windows": len(rows),
            "variance_range_pct2": [float(var.min()), float(var.max())],
            "quiet_window": quiet,
            "turbulent_window": turbulent,
            "full_sample_spearman_vs_variance": {
                c: spearman_against_variance(rows, c) for c in CORRELATED_COLUMNS
            },
            "window_rows": rows,
        }

    path = OUT / "phti_section33_ashare_check.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(path),
        "pairs": {
            k: {
                "n_windows": v["n_month_end_windows"],
                "quiet": {"date": v["quiet_window"]["month_end"],
                          "var": round(v["quiet_window"]["variance_pct2"], 4),
                          "h0_mean": round(v["quiet_window"]["h0_death_mean"], 4),
                          "h1_count": v["quiet_window"]["h1_count"]},
                "turbulent": {"date": v["turbulent_window"]["month_end"],
                              "var": round(v["turbulent_window"]["variance_pct2"], 4),
                              "h0_mean": round(v["turbulent_window"]["h0_death_mean"], 4),
                              "h1_count": v["turbulent_window"]["h1_count"]},
            } for k, v in report["pairs"].items()
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
