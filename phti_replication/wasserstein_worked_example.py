"""Concrete worked example: W_p between two adjacent-day persistence diagrams.

Answers "can you actually compute it?" with real A-share data, not a toy:
  * takes two consecutive 60-day state point clouds (16 industry log returns)
  * computes VR H0/H1 persistence diagrams with ripser
  * builds the standard augmented-diagonal (n+m)x(n+m) cost matrix
  * solves the optimal assignment and prints the matched pairs
  * reports W_1, W_2, bottleneck, per-dimension contributions and the total W_2
  * verifies that the upgraded matching rule reproduces the archived v0.1 p=1
    daily W series (i.e. the construction change did not alter the optimum)

No equity index, no strategy return, no IC, no regression, no 2025 test data.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from ripser import ripser

from phti_pipeline import (
    bottleneck_distance, daily_wasserstein, finite_diagram,
    load_industry_panel, wasserstein_details, wasserstein_p,
)

ROOT = Path(__file__).resolve().parents[2]
DB = (ROOT.parent / "a_share_pit" / "tdx_central.db").resolve()
OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

CODES = ["801010", "801030", "801040", "801050", "801080", "801110",
         "801120", "801130", "801140", "801150", "801160", "801170",
         "801180", "801200", "801210", "801230"]
START, DEMO_END = "2005-01-04", "2005-12-31"
WINDOW = 60


def main() -> None:
    panel = load_industry_panel(DB, CODES, START, DEMO_END, name="worked_example")
    r = panel.log_returns
    prev_cloud = r[:WINDOW]
    cur_cloud = r[1:WINDOW + 1]
    prev_dgms = ripser(prev_cloud, maxdim=1, metric="euclidean", coeff=2)["dgms"]
    cur_dgms = ripser(cur_cloud, maxdim=1, metric="euclidean", coeff=2)["dgms"]
    prev = {d: finite_diagram(prev_dgms[i]) for i, d in enumerate(("H0", "H1"))}
    cur = {d: finite_diagram(cur_dgms[i]) for i, d in enumerate(("H0", "H1"))}

    report = {
        "status": "worked_example_only",
        "performance_evaluated": False,
        "equity_index_loaded": False,
        "test_2025_read": False,
        "date_prev": panel.dates[WINDOW - 1],
        "date_cur": panel.dates[WINDOW],
        "window_days": WINDOW,
        "n_industries": len(CODES),
        "matching_rule": "U = A + pi(B); V = B + pi(A); "
                         "c(u,v)=||u-v||_inf^p, projection<->projection = 0; "
                         "linear_sum_assignment (Hungarian/Jonker-Volgenant)",
        "dimensions": {},
    }

    total_w2 = 0.0
    for dim in ("H0", "H1"):
        a, b = prev[dim], cur[dim]
        d1 = wasserstein_details(a, b, 1, "L_inf")
        d2 = wasserstein_details(a, b, 2, "L_inf")
        total_w2 += d2["W_p"]
        pair_kinds: dict[str, int] = {}
        for p in d2["pairs"]:
            key = f"{p['u_kind']} -> {p['v_kind']}"
            pair_kinds[key] = pair_kinds.get(key, 0) + 1
        nonzero = [p for p in d2["pairs"] if p["cost_p"] > 1e-15]
        report["dimensions"][dim] = {
            "n_points_prev": int(len(a)),
            "n_points_cur": int(len(b)),
            "augmented_matrix": d2["augmented_matrix"],
            "W_1": wasserstein_p(a, b, 1, "L_inf"),
            "W_2": d2["W_p"],
            "sum_cost_p2": d2["total_cost_p"],
            "bottleneck": bottleneck_distance(a, b),
            "n_matched_pairs": len(d2["pairs"]),
            "n_nonzero_cost_pairs": len(nonzero),
            "pair_kinds": pair_kinds,
            "sample_pairs": sorted(nonzero, key=lambda x: -x["cost_p"])[:8],
        }
    report["total_W_2_H0_plus_H1"] = total_w2

    # Equivalence check: full Kerber construction must reproduce archived v0.1 p=1.
    legacy_csv = OUT / "phti_daily_w_p16_v0.1.csv"
    legacy: dict[str, float] = {}
    if legacy_csv.exists():
        with legacy_csv.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row["W_t"]:
                    legacy[row["date"]] = float(row["W_t"])
    recomputed = daily_wasserstein(r[:WINDOW + 5], window=WINDOW,
                                   order=1, internal_norm="L_inf")
    diffs = []
    for k in range(WINDOW, WINDOW + 5):
        d = panel.dates[k]
        if d in legacy:
            diffs.append({"date": d, "v0_1_W": legacy[d],
                          "recomputed_p1": float(recomputed[k]),
                          "abs_diff": abs(float(recomputed[k]) - legacy[d])})
    report["v0_1_p1_equivalence"] = {
        "description": "upgraded full bipartite matching vs archived v0.1 "
                       "own-projection shortcut, both at p=1",
        "n_compared": len(diffs),
        "max_abs_diff": max((x["abs_diff"] for x in diffs), default=None),
        "passed": bool(diffs) and max(x["abs_diff"] for x in diffs) < 1e-9,
        "rows": diffs,
    }

    path = OUT / "phti_wasserstein_worked_example.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(path),
        "dates": [report["date_prev"], report["date_cur"]],
        "dimensions": {
            k: {"n_prev": v["n_points_prev"], "n_cur": v["n_points_cur"],
                "W_1": round(v["W_1"], 8), "W_2": round(v["W_2"], 8)}
            for k, v in report["dimensions"].items()
        },
        "total_W_2": round(total_w2, 8),
        "v0_1_equivalence": report["v0_1_p1_equivalence"]["passed"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
