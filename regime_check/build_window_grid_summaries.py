"""v0.2 window-scale sensitivity: recompute DAILY summaries over a window grid.

Frozen spec: config/regime_window_sensitivity_v0.2.toml (frozen before ANY v0.2
group result was seen). Parent v0.1 results are NOT overwritten.

Two independent point clouds, both shortened:
  xy_network  : correlation-distance VR, window in {10,15,20,30} (30 = v0.1)
  phti_p16/p27: state point cloud VR + adjacent-diagram W2, window in {20,30,40,60}
                (60 = v0.1); SMA fixed at 60 and NOT used as a primary statistic.

Node-count control (xy): for each trading day the eligible industry list is
computed from the v0.1 30-day rule, then intersected over ALL four windows so
that any column missing / zero-variance in a short window is dropped for every
window on that day. This isolates window length from the known N drift (3->14).

Explicitly NOT done: equity index returns, performance/IC/Sharpe, positions,
Gate 1 frozen 2025 test set, Gate 2, or any change to v0.1 verdicts.
"""
from __future__ import annotations

import csv
import gc
import json
import math
import sqlite3
import sys
import time
import tomllib
import warnings
from pathlib import Path

import numpy as np
from ripser import ripser

# Short PHTI windows have fewer rows than industry columns; VR is still
# well-defined, ripser only emits a transposition hint. Silence the noise.
warnings.filterwarnings("ignore", message=".*more columns than rows.*")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "phti_replication"))
sys.path.insert(0, str(ROOT / "src" / "regime_check"))

from src.xy_replication.fetch_sw2014_corrected import CODES as SW2014  # noqa: E402
from src.xy_replication.topology import betti_at, exact_landscape_l1  # noqa: E402
from phti_pipeline import (  # noqa: E402
    finite_diagram, load_industry_panel, wasserstein_p,
)
from build_daily_ph_summaries import DELTA, SHAPE_COLS, shape_of_window  # noqa: E402

OUT = ROOT / "outputs"
CFG_V02 = ROOT / "config" / "regime_window_sensitivity_v0.2.toml"
CFG_PHTI = ROOT / "config" / "phti_replication.toml"
DB = (ROOT.parent / "a_share_pit" / "tdx_central.db").resolve()
OLD_DB = OUT / "xy_sw2014_corrected_data.db"
CURRENT_DB = OUT / "xy_replication_data.db"
ERA_SWITCH = "2021-12-13"
END = "2026-11-03"

XY_FIELDS = [
    "n_nodes", "h2_count", "h1_count", "h2_landscape_l1", "h1_landscape_l1",
    "industry_average_correlation", "correlation_leading_eigenvalue_share",
    "max_h2_persistence", "h2_betti_0p4", "h2_betti_0p6", "h2_betti_0p8",
]
EPSILONS = (0.4, 0.6, 0.8)


# ---------------------------------------------------------------------------
# xy: parameterised copy of topology.network_features (v0.1 logic, only the
# hard-coded shape[0]==30 assertion is generalised). w=30 must reproduce v0.1.
# ---------------------------------------------------------------------------
def xy_features(returns: np.ndarray) -> dict:
    x = np.asarray(returns, dtype=float)
    if x.ndim != 2 or x.shape[0] < 5 or x.shape[1] < 4:
        raise ValueError("相关网络输入维度不足")
    if not np.isfinite(x).all() or np.any(np.std(x, axis=0, ddof=1) <= 0):
        raise ValueError("相关网络输入含NaN/Inf或零波动行业")
    corr = np.corrcoef(x, rowvar=False)
    corr = np.clip((corr + corr.T) / 2.0, -1.0, 1.0)
    np.fill_diagonal(corr, 1.0)
    distance = np.sqrt(np.maximum(0.0, 2.0 * (1.0 - corr)))
    np.fill_diagonal(distance, 0.0)
    dgms = ripser(distance, distance_matrix=True, maxdim=2, thresh=2.0,
                  coeff=2, do_cocycles=False)["dgms"]
    if len(dgms) != 3:
        raise RuntimeError("ripser未返回H0/H1/H2")
    h2 = np.asarray(dgms[2], dtype=float)
    h2_finite = h2[np.isfinite(h2).all(axis=1)] if h2.size else h2
    eigenvalues = np.linalg.eigvalsh(corr)
    upper = corr[np.triu_indices(corr.shape[0], k=1)]
    out = {
        "n_nodes": int(corr.shape[0]),
        "h2_count": int(len(h2_finite)),
        "h1_count": int(len(dgms[1])),
        "h2_landscape_l1": exact_landscape_l1(h2),
        "h1_landscape_l1": exact_landscape_l1(dgms[1]),
        "industry_average_correlation": float(np.mean(upper)),
        "correlation_leading_eigenvalue_share": float(eigenvalues[-1] / corr.shape[0]),
        "max_h2_persistence": float(np.max(h2_finite[:, 1] - h2_finite[:, 0]))
        if len(h2_finite) else 0.0,
    }
    for eps in EPSILONS:
        out[f"h2_betti_{str(eps).replace('.', 'p')}"] = betti_at(h2, float(eps))
    return out


def load_xy_prices():
    old = sqlite3.connect(f"file:{OLD_DB}?mode=ro", uri=True)
    old_closes = {r[0]: dict(old.execute(
        "SELECT date,close FROM sw2014_daily WHERE code=?", (r[0],)))
        for r in old.execute("SELECT code FROM sw2014_meta")}
    old.close()
    cur = sqlite3.connect(f"file:{CURRENT_DB}?mode=ro", uri=True)
    current_codes = {r[0] for r in cur.execute(
        "SELECT code FROM sw2_meta WHERE parent IS NOT 'SW2014 legacy supplement'")}
    if len(current_codes) != 131:
        raise RuntimeError(f"当前快照代码数异常: {len(current_codes)}")
    current_closes = {c: dict(cur.execute(
        "SELECT date,close FROM sw2_daily WHERE code=?", (c,)))
        for c in current_codes}
    dates = [r[0] for r in cur.execute(
        "SELECT date FROM benchmark_daily WHERE code='801003' ORDER BY date")]
    cur.close()
    return old_closes, current_closes, current_codes, dates


def _valid_prices(series: dict, window_dates: list[str]) -> np.ndarray | None:
    ps = [series.get(d) for d in window_dates]
    if any(p is None or p <= 0 for p in ps):
        return None
    a = np.asarray(ps, dtype=float)
    r = a[1:] / a[:-1] - 1.0
    return r if np.std(r, ddof=1) > 0 else None


def build_eligible(windows: list[int]) -> dict:
    """Base list = v0.1 30-day rule; final list = intersection over all windows."""
    old_closes, current_closes, current_codes, dates = load_xy_prices()
    pos = {d: i for i, d in enumerate(dates)}
    with (OUT / "xy_corrected_features.csv").open(encoding="utf-8-sig") as f:
        v01 = {r["date"]: int(r["n_nodes"]) for r in csv.DictReader(f)}
    candidates = [d for d in dates if d >= "2012-12-31" and pos[d] >= 30]
    eligible, audit = {}, {"n_dates": len(candidates), "n_base_match_v0_1": 0,
                           "n_base_mismatch": 0, "n_dropped_days": 0,
                           "n_dropped_columns": 0, "examples": []}
    for d in candidates:
        i = pos[d]
        source = old_closes if d < ERA_SWITCH else current_closes
        codes = SW2014 if d < ERA_SWITCH else current_codes
        base = set()
        for c in sorted(codes):
            if _valid_prices(source.get(c, {}), dates[i - 30:i + 1]) is not None:
                base.add(c)
        if len(base) == v01.get(d):
            audit["n_base_match_v0_1"] += 1
        else:
            audit["n_base_mismatch"] += 1
            if len(audit["examples"]) < 5:
                audit["examples"].append({"date": d, "base": len(base), "v0_1": v01.get(d)})
        final = set(base)
        for w in windows:
            wd = dates[i - w:i + 1]
            for c in list(final):
                if _valid_prices(source.get(c, {}), wd) is None:
                    final.discard(c)
        audit["n_dropped_columns"] += len(base) - len(final)
        if len(final) < 4:
            audit["n_dropped_days"] += 1
            continue
        eligible[d] = sorted(final)
    (OUT / "regime_win_xy_eligible.json").write_text(
        json.dumps(eligible, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "regime_win_xy_eligible_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"dates": candidates, "audit": audit}


def xy_all_windows(windows: list[int]) -> list[dict]:
    """Single process, ONE price load, all windows in the same date loop.

    Spawning one process per window exhausted the ~1.1 GB of free RAM (each
    worker reloaded the full price tables); threads give no speed-up because
    ripser holds the GIL. This keeps memory at one copy and shares the frozen
    eligible list across windows.
    """
    eligible = json.loads((OUT / "regime_win_xy_eligible.json").read_text(encoding="utf-8"))
    old_closes, current_closes, _, dates = load_xy_prices()
    pos = {d: i for i, d in enumerate(dates)}
    rows_by_w = {w: [] for w in windows}
    started = time.time()
    for k, d in enumerate(sorted(eligible)):
        i = pos[d]
        source = old_closes if d < ERA_SWITCH else current_closes
        codes = eligible[d]
        for w in windows:
            wd = dates[i - w:i + 1]
            cols, ok = [], True
            for c in codes:
                r = _valid_prices(source.get(c, {}), wd)
                if r is None:      # should not happen after the intersection
                    ok = False
                    break
                cols.append(r)
            if not ok or len(cols) < 4:
                continue
            feat = xy_features(np.asarray(cols, dtype=float).T)
            rows_by_w[w].append({"date": d, **{c: feat[c] for c in XY_FIELDS}})
        if (k + 1) % 500 == 0:
            print(f"   xy progress {k+1}/{len(eligible)} "
                  f"{round(time.time()-started,1)}s", flush=True)

    results = []
    for w in windows:
        rows = rows_by_w[w]
        path = OUT / f"regime_win_summaries_xy_{w}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=["date"] + XY_FIELDS)
            wr.writeheader()
            wr.writerows(rows)
        results.append({
            "window": w, "rows": len(rows), "csv": path.name,
            "seconds": round(time.time() - started, 1),
            "n_nodes_min": min(r["n_nodes"] for r in rows) if rows else None,
            "n_nodes_max": max(r["n_nodes"] for r in rows) if rows else None,
        })
    return results


def xy_equivalence_check() -> dict:
    """w=30 with the v0.1 base list must reproduce xy_corrected_features.csv."""
    old_closes, current_closes, current_codes, dates = load_xy_prices()
    pos = {d: i for i, d in enumerate(dates)}
    with (OUT / "xy_corrected_features.csv").open(encoding="utf-8-sig") as f:
        v01 = list(csv.DictReader(f))
    sample = [r["date"] for r in v01[::max(1, len(v01) // 24)]][:24]
    diffs = {k: [] for k in XY_FIELDS}
    for d in sample:
        i = pos[d]
        source = old_closes if d < ERA_SWITCH else current_closes
        codes = SW2014 if d < ERA_SWITCH else current_codes
        cols = []
        for c in sorted(codes):
            r = _valid_prices(source.get(c, {}), dates[i - 30:i + 1])
            if r is not None:
                cols.append(r)
        got = xy_features(np.asarray(cols, dtype=float).T)
        ref = next(r for r in v01 if r["date"] == d)
        for k in XY_FIELDS:
            diffs[k].append(abs(float(got[k]) - float(ref[k])))
    return {"n_sampled_dates": len(sample),
            "max_abs_diff_by_field": {k: (float(max(v)) if v else None)
                                      for k, v in diffs.items()},
            "passed": all(max(v) < 1e-9 for v in diffs.values() if v)}


# ---------------------------------------------------------------------------
# PHTI: same pipeline, only the VR window length changes.
# ---------------------------------------------------------------------------
def phti_worker(key: str, w: int, order: int, norm: str, codes: list, start: str) -> dict:
    panel = load_industry_panel(DB, list(codes), start, END, name=key)
    r, dates, n = panel.log_returns, list(panel.dates), len(panel.dates)
    W = np.full(n, np.nan)
    rows, prev = [], None
    for t in range(w - 1, n):
        cloud = r[t - w + 1: t + 1]
        dgms = ripser(cloud, maxdim=1, metric="euclidean", coeff=2)["dgms"]
        cur = (finite_diagram(dgms[0]), finite_diagram(dgms[1]))
        if prev is not None:
            W[t] = (wasserstein_p(prev[0], cur[0], order, norm)
                    + wasserstein_p(prev[1], cur[1], order, norm))
        prev = cur
        s = shape_of_window(cloud, dgms)
        s["date"] = dates[t]
        rows.append(s)

    def fmt(v):
        return "" if v is None or (isinstance(v, float) and not math.isfinite(v)) else v

    by_date = {x["date"]: x for x in rows}
    path = OUT / f"regime_win_summaries_phti_{key}_{w}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.writer(fh)
        wr.writerow(["date", "W_t"] + SHAPE_COLS)
        for i, d in enumerate(dates):
            s = by_date.get(d)
            wr.writerow([d, fmt(W[i])] + [fmt(s[c]) if s else "" for c in SHAPE_COLS])

    check = {"n_overlap": 0, "max_abs_W_diff": None, "passed": None}
    if w == 60:
        legacy = OUT / f"regime_daily_ph_{key}.csv"
        if legacy.exists():
            pos = {d: i for i, d in enumerate(dates)}
            with legacy.open(encoding="utf-8-sig") as fh:
                ref = {row["date"]: float(row["W_t"])
                       for row in csv.DictReader(fh) if row["W_t"]}
            diffs = [abs(W[pos[d]] - v) for d, v in ref.items()
                     if d in pos and math.isfinite(W[pos[d]])]
            check = {"n_overlap": len(diffs),
                     "max_abs_W_diff": float(max(diffs)) if diffs else None,
                     "passed": bool(diffs) and max(diffs) < 1e-10}
    return {"panel": key, "window": w, "rows": len(rows), "csv": path.name,
            "W_finite": int(np.isfinite(W).sum()), "crosscheck_v0_1": check}


def main() -> None:
    spec = tomllib.loads(CFG_V02.read_text(encoding="utf-8"))
    cfg = tomllib.loads(CFG_PHTI.read_text(encoding="utf-8"))
    xy_ws = list(spec["grid"]["xy_corr_window_days"])
    ph_ws = list(spec["grid"]["phti_vr_window_days"])
    order, norm = int(cfg["distance"]["order_p"]), cfg["distance"]["internal_norm"]
    report = {"spec": "config/regime_window_sensitivity_v0.2.toml",
              "frozen_before_evaluation": True,
              "performance_evaluated": False, "equity_index_loaded": False,
              "gate1_test_read": False, "v0_1_overwritten": False,
              "xy_windows": xy_ws, "phti_windows": ph_ws,
              "delta_threshold_log_return": DELTA, "xy": {}, "phti": []}

    t0 = time.time()
    print("[1/4] xy eligible lists + v0.1 equivalence", flush=True)
    prep = build_eligible(xy_ws)
    report["xy"]["eligible_audit"] = prep["audit"]
    report["xy"]["function_equivalence_24_dates"] = xy_equivalence_check()
    print("   audit:", prep["audit"], flush=True)
    print("   equivalence:", report["xy"]["function_equivalence_24_dates"]["passed"], flush=True)

    print("[2/4] phti window grid", flush=True)
    for key in ("p16", "p27"):
        pc = cfg["panels"][key]
        for w in ph_ws:
            out = phti_worker(key, w, order, norm, pc["codes"], pc["start"])
            report["phti"].append(out)
            print("  ", key, w, out["rows"], out["crosscheck_v0_1"], flush=True)

    print("[3/4] xy window grid (single process, one price load)", flush=True)
    gc.collect()
    for out in xy_all_windows(xy_ws):
        report["xy"][f"w{out['window']}"] = out
        print("  ", out, flush=True)

    print("[4/4] manifest", flush=True)
    report["elapsed_seconds"] = round(time.time() - t0, 1)
    (OUT / "regime_win_summaries_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    print("DONE", report["elapsed_seconds"], "s", flush=True)


if __name__ == "__main__":
    main()
