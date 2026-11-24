"""Stage B-1: full-date DAILY shape summaries for the PHTI state point cloud.

Frozen spec: config/regime_conjecture_check.toml (v0.1), granularity = daily.
This is a DESCRIPTIVE recomputation of already-defined descriptors over the
full data range; it is NOT a new experiment, NOT a strategy evaluation.

Why needed: outputs/phti_section33_ashare_check.json only has month-end
windows (237 + 128) of a 2-industry point cloud. The conjecture check needs
daily H0/H1 shape summaries of the SAME 16/27-industry state point cloud that
produces W_t, so that "bull / bear / pre-crisis / crisis" labels can be joined.

Reuse: phti_pipeline.load_industry_panel / wasserstein_p / finite_diagram.
One ripser call per window serves both W_t and the shape summaries. W_t is
cross-checked against the archived v0.2 CSV on the overlapping dates.

Units: log returns (same as W_t). delta threshold for component counts is
0.01 (about one 1% daily move), unlike Sect. 3.3 which used percent simple
returns; the difference is documented, not silently mixed.

No equity index return is loaded. No performance / IC / Sharpe is computed.
"""
from __future__ import annotations

import csv
import json
import math
import sys
import tomllib
from pathlib import Path

import numpy as np
from ripser import ripser

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "phti_replication"))

from phti_pipeline import (  # noqa: E402
    finite_diagram, load_industry_panel, sma_causal, wasserstein_p,
)
DB = (ROOT.parent / "a_share_pit" / "tdx_central.db").resolve()
CFG = ROOT / "config" / "phti_replication.toml"
OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

END = "2026-11-03"       # full-date, per user decision; NOT cut at 2024-12-31
WINDOW = 60
DELTA = 0.01
SMA_K = 60

SHAPE_COLS = [
    "h0_death_mean", "h0_death_median", "h0_death_max", "h0_death_cv",
    "h0_top1_over_rest_median", "components_at_delta",
    "h1_count", "h1_birth_mean", "h1_persistence_mean", "h1_persistence_max",
    "window_rms", "window_variance", "avg_pair_corr", "leading_eig_share",
]


def shape_of_window(cloud: np.ndarray, dgms) -> dict:
    """Single 60 x K point cloud: H0/H1 shape + scale/structure controls."""
    h0 = finite_diagram(dgms[0])
    h1 = finite_diagram(dgms[1])
    deaths = np.sort(h0[:, 1]) if len(h0) else np.array([0.0])
    longest = float(deaths[-1])
    rest = deaths[:-1]
    rest_med = float(np.median(rest)) if len(rest) else 0.0
    pers_h1 = h1[:, 1] - h1[:, 0] if len(h1) else np.array([])

    centre = cloud.mean(axis=0)
    rms = float(np.sqrt(np.mean(np.sum((cloud - centre) ** 2, axis=1))))
    var = float(np.var(cloud, axis=0, ddof=1).mean())

    # average pairwise correlation, leading eigenvalue share of covariance
    sd = cloud.std(axis=0, ddof=1)
    good = sd > 1e-12
    if good.sum() >= 2:
        cm = np.corrcoef(cloud[:, good], rowvar=False)
        iu = np.triu_indices(cm.shape[0], k=1)
        avg_corr = float(np.nanmean(cm[iu]))
        eig = np.linalg.eigvalsh(np.cov(cloud[:, good], rowvar=False, ddof=1))
        eig_pos = np.clip(eig, 0.0, None)
        lead = float(eig_pos[-1] / eig_pos.sum()) if eig_pos.sum() > 0 else None
    else:
        avg_corr, lead = None, None

    return {
        "h0_death_mean": float(deaths.mean()),
        "h0_death_median": float(np.median(deaths)),
        "h0_death_max": longest,
        "h0_death_cv": float(deaths.std(ddof=1) / deaths.mean())
        if deaths.mean() > 0 else None,
        "h0_top1_over_rest_median": float(longest / rest_med)
        if rest_med > 0 else None,
        "components_at_delta": int((deaths > DELTA).sum()) + 1,
        "h1_count": int(len(h1)),
        "h1_birth_mean": float(h1[:, 0].mean()) if len(h1) else None,
        "h1_persistence_mean": float(pers_h1.mean()) if len(pers_h1) else None,
        "h1_persistence_max": float(pers_h1.max()) if len(pers_h1) else None,
        "window_rms": rms,
        "window_variance": var,
        "avg_pair_corr": avg_corr,
        "leading_eig_share": lead,
    }


def main() -> None:
    cfg = tomllib.loads(CFG.read_text(encoding="utf-8"))
    order = int(cfg["distance"]["order_p"])
    norm = cfg["distance"]["internal_norm"]
    report = {
        "status": "daily_descriptive_recompute_for_conjecture_check",
        "spec": "config/regime_conjecture_check.toml v0.1",
        "end": END,
        "window_days": WINDOW,
        "delta_threshold_log_return": DELTA,
        "units": "daily log returns (same as W_t); Sect.3.3 used percent simple returns",
        "performance_evaluated": False,
        "equity_index_loaded": False,
        "gate1_test_read": False,
        "panels": {},
    }

    for key in ("p16", "p27"):
        pc = cfg["panels"][key]
        panel = load_industry_panel(DB, list(pc["codes"]), pc["start"], END,
                                    name=key)
        r = panel.log_returns
        dates = list(panel.dates)
        n = len(dates)
        W = np.full(n, np.nan)
        rows: list[dict] = []
        prev = None
        for t in range(WINDOW - 1, n):
            cloud = r[t - WINDOW + 1: t + 1]
            dgms = ripser(cloud, maxdim=1, metric="euclidean", coeff=2)["dgms"]
            cur = (finite_diagram(dgms[0]), finite_diagram(dgms[1]))
            if prev is not None:
                W[t] = (wasserstein_p(prev[0], cur[0], order, norm)
                        + wasserstein_p(prev[1], cur[1], order, norm))
            prev = cur
            s = shape_of_window(cloud, dgms)
            s["date"] = dates[t]
            rows.append(s)

        sma = sma_causal(W, SMA_K)
        by_date = {x["date"]: x for x in rows}
        csv_path = OUT / f"regime_daily_ph_{key}.csv"
        cols = ["date", "W_t", "SMA60_W_t"] + SHAPE_COLS
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for i, d in enumerate(dates):
                s = by_date.get(d)
                def fmt(v):
                    return "" if v is None or (isinstance(v, float)
                                               and not math.isfinite(v)) else v
                w.writerow([d, fmt(W[i]), fmt(sma[i])]
                           + [fmt(s[c]) if s else "" for c in SHAPE_COLS])

        # cross-check W_t against the archived v0.2 engineering acceptance
        legacy_path = OUT / f"phti_daily_w_{key}_v0.2.csv"
        date_to_i = {d: i for i, d in enumerate(dates)}
        diffs = []
        if legacy_path.exists():
            with legacy_path.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    if not row["W_t"]:
                        continue
                    i = date_to_i.get(row["date"], -1)
                    if i >= 0 and math.isfinite(W[i]):
                        diffs.append(abs(W[i] - float(row["W_t"])))
        check = {
            "n_overlap_compared": len(diffs),
            "max_abs_diff_vs_v0_2": float(max(diffs)) if diffs else None,
            "passed": bool(bool(diffs) and max(diffs) < 1e-10),
        }

        report["panels"][key] = {
            "n_days": n,
            "first_date": dates[0],
            "last_date": dates[-1],
            "n_windows_with_W": int(np.isfinite(W).sum()),
            "csv": csv_path.name,
            "W_t_v0_2_crosscheck": check,
            "n_days_after_2024_12_31": sum(1 for d in dates if d > "2024-12-31"),
        }
        print(key, report["panels"][key])

    out = OUT / "regime_daily_ph_summaries.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                              allow_nan=False) + "\n", encoding="utf-8")
    print("meta:", out)


if __name__ == "__main__":
    main()
