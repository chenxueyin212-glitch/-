"""Engineering acceptance for the A-share PHTI replication line (v0.2, p=2).

STRICTLY READ-ONLY with respect to performance: this script loads industry
prices and builds the causal indicator series, but never loads an equity index,
never joins a market return, and never computes any return/IC/Sharpe/regression.

Outputs (v0.2, versioned filenames; v0.1 artifacts are preserved untouched):
  outputs/phti_engineering_acceptance_v0.2.json
  outputs/phti_daily_w_{panel}_v0.2.csv
  outputs/phti_monthly_signals_{panel}_v0.2.csv
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import tomllib
from datetime import date
from pathlib import Path

import numpy as np

from phti_pipeline import (
    build_monthly_signals, daily_wasserstein, load_industry_panel,
    month_end_indices, sma_causal, wasserstein_self_test,
)

ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = ROOT / "config" / "phti_replication.toml"
OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)
VERSION_SUFFIX = "v0.2"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(x: np.ndarray) -> dict:
    v = x[np.isfinite(x)]
    return {
        "n_finite": int(len(v)),
        "n_nan": int(np.isnan(x).sum()),
        "min": None if len(v) == 0 else float(v.min()),
        "max": None if len(v) == 0 else float(v.max()),
        "mean": None if len(v) == 0 else float(v.mean()),
        "std": None if len(v) == 0 else float(v.std(ddof=1)),
        "n_zero": int((v == 0).sum()),
        "all_nonnegative": bool((v >= 0).all()) if len(v) else None,
        # indicator-only diagnostics; NOT performance
        "is_constant": bool(len(v) > 0 and np.ptp(v) == 0),
    }


def legacy_p1_equivalence(panel, window: int, norm: str) -> dict:
    """The upgraded full bipartite matching must reproduce archived v0.1 p=1 W."""
    legacy_csv = OUT / "phti_daily_w_p16_v0.1.csv"
    legacy: dict[str, float] = {}
    if legacy_csv.exists():
        with legacy_csv.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row["W_t"]:
                    legacy[row["date"]] = float(row["W_t"])
    recomputed = daily_wasserstein(panel.log_returns[:window + 5],
                                   window=window, order=1, internal_norm=norm)
    diffs = []
    for k in range(window, window + 5):
        d = panel.dates[k]
        if d in legacy:
            diffs.append(abs(float(recomputed[k]) - legacy[d]))
    return {
        "description": "full Kerber bipartite matching (p=1) vs archived v0.1 "
                       "own-projection shortcut; verifies matching-rule upgrade "
                       "did not change the optimum",
        "n_compared": len(diffs),
        "max_abs_diff": max(diffs) if diffs else None,
        "passed": bool(diffs) and max(diffs) < 1e-9,
    }


def main() -> None:
    cfg = tomllib.loads(CFG_PATH.read_text(encoding="utf-8"))
    db = (CFG_PATH.parent.parent / cfg["data"]["db"]).resolve()
    start, end = cfg["data"]["start"], cfg["data"]["end"]
    window = int(cfg["pointcloud"]["window_days"])
    sma_k = int(cfg["signal"]["sma_days"])
    history = int(cfg["signal"]["history_month_ends"])
    order = int(cfg["distance"]["order_p"])
    norm = cfg["distance"]["internal_norm"]

    self_tests = wasserstein_self_test()
    assert all(c["pass"] for c in self_tests), "Wasserstein unit tests failed"

    report: dict = {
        "protocol_version": cfg["protocol"]["version"],
        "status": "engineering_acceptance_only",
        "performance_evaluated": False,
        "equity_index_loaded": False,
        "market_return_joined": False,
        "oof_or_2025_test_read": False,
        "gate_status": cfg["protocol"]["gate_status"],
        "config_path": str(CFG_PATH),
        "config_sha256": digest(CFG_PATH),
        "version_history": cfg["protocol"]["version_history"],
        "database": str(db),
        "development_window": {"start": start, "end": end,
                               "test_start": cfg["time_boundary"]["test_start"],
                               "test_status": cfg["time_boundary"]["test_status"]},
        "distance_unit_tests": self_tests,
        "distance_configuration": {
            "order_p": order, "internal_norm": norm,
            "lag_h": int(cfg["distance"]["lag_h"]),
            "combine_dimensions": cfg["distance"]["combine_dimensions"],
            "diagonal_augmentation": bool(cfg["distance"]["diagonal_augmentation"]),
            "diagonal_cost": cfg["distance"]["diagonal_cost"],
            "assignment": cfg["distance"]["assignment"],
            "matching_rule": "U=A+pi(B), V=B+pi(A); c(u,v)=||u-v||_inf^p; "
                             "projection<->projection cost 0; "
                             "min-cost perfect matching by linear_sum_assignment",
            "essential_class": cfg["distance"]["essential_class"],
            "note": "paper Eq.(8) uses L_inf but never states p; "
                    "p=2 specified by user on 2026-11-08 BEFORE any performance "
                    "result; p=1 kept as declared sensitivity",
        },
        "panels": {},
        "causality_checks": {},
        "determinism_check": {},
        "v0_1_p1_equivalence": {},
        "outputs": [],
        "interpretation": (
            "Indicator pipeline built and validated at p=2. No strategy "
            "performance, IC, regression or backtest has been computed. Formal "
            "evaluation is blocked pending user confirmation of panel / "
            "equity+cash / sealed-test boundary."
        ),
    }

    for key in ("p16", "p27"):
        pc = cfg["panels"][key]
        codes = list(pc["codes"])
        p_start = max(start, pc["start"])
        panel = load_industry_panel(db, codes, p_start, end, name=key)
        assert panel.log_returns.shape == (len(panel.dates), len(codes))
        assert np.isfinite(panel.log_returns).all()
        assert max(panel.dates) <= end, "2025+ data leaked into development acceptance"

        w = daily_wasserstein(panel.log_returns, window=window,
                              order=order, internal_norm=norm)
        sm = sma_causal(w, sma_k)
        signals = build_monthly_signals(panel.dates, sm, history=history)

        daily_csv = OUT / f"phti_daily_w_{key}_{VERSION_SUFFIX}.csv"
        with daily_csv.open("w", newline="", encoding="utf-8-sig") as f:
            wr = csv.writer(f)
            wr.writerow(["date", "W_t", "SMA60_W_t"])
            for d, a, b in zip(panel.dates, w, sm):
                wr.writerow([d, "" if not math.isfinite(a) else f"{a:.12g}",
                             "" if not math.isfinite(b) else f"{b:.12g}"])
        monthly_csv = OUT / f"phti_monthly_signals_{key}_{VERSION_SUFFIX}.csv"
        with monthly_csv.open("w", newline="", encoding="utf-8-sig") as f:
            wr = csv.writer(f)
            wr.writerow(["signal_date", "applies_to_month", "phti_sma60",
                         "midrank_in_60_month_ends", "quintile",
                         "w_worst_case_protection_pct", "w_flexible_exposure_pct",
                         "w_flexible_levered_pct"])
            for s in signals:
                wr.writerow([s.signal_date, s.applies_to_month, f"{s.phti:.12g}",
                             f"{s.midrank:.6f}", s.quintile,
                             s.w_wcp, s.w_fe, s.w_fel])

        # ---- assertions that only concern engineering correctness ----
        finite_w = w[np.isfinite(w)]
        assert len(finite_w) > 0 and (finite_w >= 0).all()
        first_w = int(np.flatnonzero(np.isfinite(w))[0])
        first_sma = int(np.flatnonzero(np.isfinite(sm))[0])
        assert first_w == window, (key, "first W index", first_w)
        assert first_sma == window + sma_k - 1, (key, "first SMA index", first_sma)

        me_all = month_end_indices(panel.dates)
        me_valid = [i for i in me_all if np.isfinite(sm[i])]
        assert len(me_valid) >= history, (key, "not enough month ends")
        me_by_month: dict[str, int] = {}
        for i in me_all:
            me_by_month[panel.dates[i][:7]] = i
        assert all(i == me_by_month[panel.dates[i][:7]] for i in me_valid)

        bad = []
        for s in signals:
            y, m = int(s.applies_to_month[:4]), int(s.applies_to_month[5:7])
            if s.signal_date >= date(y, m, 1).isoformat():
                bad.append(s.signal_date)
        assert not bad, (key, "look-ahead signals", bad[:5])
        assert {s.quintile for s in signals} <= {1, 2, 3, 4, 5}

        qdist = {q: sum(1 for s in signals if s.quintile == q)
                 for q in range(1, 6)}

        report["panels"][key] = {
            "role": pc["role"],
            "n_industries": len(codes),
            "aligned_trading_days": len(panel.dates),
            "first_date": panel.dates[0],
            "last_date": panel.dates[-1],
            "n_month_ends_with_sma": len(me_valid),
            "first_month_end_with_sma": panel.dates[me_valid[0]],
            "first_signal_date": signals[0].signal_date if signals else None,
            "first_applied_month": signals[0].applies_to_month if signals else None,
            "last_signal_date": signals[-1].signal_date if signals else None,
            "last_applied_month": signals[-1].applies_to_month if signals else None,
            "n_monthly_signals": len(signals),
            "quintile_counts": qdist,
            "daily_W": describe(w),
            "smoothed_W": describe(sm),
            "warmup_checks": {
                "first_finite_W_index": first_w,
                "expected_first_finite_W_index": window,
                "first_finite_SMA_index": first_sma,
                "expected_first_finite_SMA_index": window + sma_k - 1,
                "passed": True,
            },
            "files": {"daily_indicator": daily_csv.name,
                      "monthly_signals": monthly_csv.name},
        }
        report["causality_checks"][key] = {
            "all_signal_dates_precede_applied_month": True,
            "n_violations": 0,
            "quintile_window": "inclusive current month, 60 month-end values",
            "example": [
                {"signal_date": s.signal_date, "applies_to_month": s.applies_to_month,
                 "quintile": s.quintile, "w_wcp_pct": s.w_wcp}
                for s in signals[:3]
            ],
        }
        report["outputs"].extend([daily_csv.name, monthly_csv.name])

        if key == "p16":
            recomputed = daily_wasserstein(panel.log_returns[:window + 3],
                                           window=window, order=order,
                                           internal_norm=norm)
            original = w[:window + 3]
            same = bool(np.array_equal(np.nan_to_num(recomputed, nan=-1.0),
                                       np.nan_to_num(original, nan=-1.0)))
            report["determinism_check"] = {
                "method": "recompute first 3 comparable windows, compare bit-exact",
                "passed": same,
                "sample_values": [float(x) for x in recomputed[window:window + 3]],
            }
            assert same, "non-deterministic W computation"
            report["v0_1_p1_equivalence"] = legacy_p1_equivalence(panel, window, norm)
            assert report["v0_1_p1_equivalence"]["passed"], \
                "matching-rule upgrade changed the p=1 optimum"

    json_out = OUT / f"phti_engineering_acceptance_{VERSION_SUFFIX}.json"
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                   allow_nan=False) + "\n", encoding="utf-8")
    report["outputs"].append(json_out.name)
    print(json.dumps({
        "json": str(json_out),
        "protocol_version": report["protocol_version"],
        "order_p": order,
        "panels": {k: {
            "days": v["aligned_trading_days"],
            "monthly_signals": v["n_monthly_signals"],
            "first_signal": v["first_signal_date"],
            "last_signal": v["last_signal_date"],
            "W_finite": v["daily_W"]["n_finite"],
            "quintile_counts": v["quintile_counts"],
        } for k, v in report["panels"].items()},
        "unit_tests": len(self_tests),
        "determinism": report["determinism_check"]["passed"],
        "v0_1_p1_equivalence": report["v0_1_p1_equivalence"]["passed"],
        "performance_evaluated": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
