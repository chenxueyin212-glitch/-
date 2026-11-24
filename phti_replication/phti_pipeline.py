"""Causal PHTI indicator pipeline for A-share industry panels.

Implements Baitinger & Flegel (2021) method chain:
  60-day rolling state point cloud (one point = one trading day, coordinates =
  industry returns) -> Vietoris-Rips H0/H1 persistence diagrams -> p-Wasserstein
  distance between adjacent-day diagrams -> 60-day SMA -> month-end only ->
  causal 60-month-end midrank quintile -> next-month exposure.

No performance evaluation lives in this module. It never loads an equity index
or any return used for scoring.

Original-paper ambiguities resolved here (see config/phti_replication.toml):
  * p = 2 (paper states "p-th Wasserstein" but never gives p; v0.2 user-specified)
  * internal norm = L_inf (paper Eq. 8)
  * unequal diagram sizes handled by the standard augmented-diagonal construction
    U = A U pi(B), V = B U pi(A), then optimal assignment
  * H0 essential class (death = inf) dropped
  * W(H0) + W(H1) summed per dimension
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from ripser import ripser
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[2]
DB_DEFAULT = ROOT.parent / "a_share_pit" / "tdx_central.db"

EXPOSURE_RULES = {
    "worst_case_protection": (100, 100, 100, 100, 0),
    "flexible_exposure": (100, 80, 60, 40, 20),
    "flexible_levered": (120, 110, 90, 60, 20),
}


# --------------------------------------------------------------------------
# Wasserstein distance between two persistence diagrams
# --------------------------------------------------------------------------
def _linf(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.maximum(
        np.abs(a[:, None, 0] - b[None, :, 0]),
        np.abs(a[:, None, 1] - b[None, :, 1]),
    )


def _l2(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(
        (a[:, None, 0] - b[None, :, 0]) ** 2
        + (a[:, None, 1] - b[None, :, 1]) ** 2
    )


def _clean(diagram) -> np.ndarray:
    d = np.asarray(diagram, dtype=float).reshape(-1, 2)
    return d[np.isfinite(d).all(axis=1)]


def _diagonal_projection(d: np.ndarray) -> np.ndarray:
    """L_inf projection of (b,d) onto the diagonal: ((b+d)/2, (b+d)/2)."""
    mid = (d[:, 0] + d[:, 1]) / 2.0
    return np.column_stack([mid, mid])


def _augmented_cost(a: np.ndarray, b: np.ndarray, order: int,
                    internal_norm: str) -> np.ndarray:
    """Standard (n+m)x(n+m) cost matrix of Edelsbrunner-Harer VIII.4 /
    Kerber-Morozov-Nigmetov (2017). Rows: A finite + projections of B;
    columns: B finite + projections of A. Projection<->projection costs 0.
    """
    n, m = len(a), len(b)
    u = np.vstack([a, _diagonal_projection(b)])
    v = np.vstack([b, _diagonal_projection(a)])
    metric = _linf if internal_norm == "L_inf" else _l2
    cost = metric(u, v) ** order
    cost[n:, m:] = 0.0
    return cost


def wasserstein_p(diagram_a, diagram_b, order: int = 2,
                  internal_norm: str = "L_inf") -> float:
    """p-th Wasserstein distance with diagonal augmentation.

    W_p = ( min over perfect matchings of sum ||u-v||_inf^p )^(1/p), where
    both diagrams are augmented with the other diagram's diagonal projections.
    For any (b,d) outside the diagonal, the cheapest diagonal partner is its
    own projection and costs (d-b)/2 under L_inf (half the persistence).
    The assignment is solved by scipy's linear_sum_assignment.
    """
    a, b = _clean(diagram_a), _clean(diagram_b)
    if len(a) == 0 and len(b) == 0:
        return 0.0
    cost = _augmented_cost(a, b, order, internal_norm)
    rows, cols = linear_sum_assignment(cost)
    total = float(cost[rows, cols].sum())
    if not math.isfinite(total) or total < 0:
        raise ArithmeticError("degenerate Wasserstein assignment")
    return total ** (1.0 / order)


def wasserstein_details(diagram_a, diagram_b, order: int = 2,
                        internal_norm: str = "L_inf") -> dict:
    """Exposed for worked examples: return the matching, not only W_p."""
    a, b = _clean(diagram_a), _clean(diagram_b)
    if len(a) == 0 and len(b) == 0:
        return {"n_a": 0, "n_b": 0, "W_p": 0.0, "p": order, "pairs": []}
    n, m = len(a), len(b)
    cost = _augmented_cost(a, b, order, internal_norm)
    rows, cols = linear_sum_assignment(cost)
    pairs = []
    for i, j in zip(rows, cols):
        u_kind = "A" if i < n else "proj(B)"
        v_kind = "B" if j < m else "proj(A)"
        pairs.append({
            "u": [float(x) for x in (a[i] if i < n else _diagonal_projection(b)[i - n])],
            "v": [float(x) for x in (b[j] if j < m else _diagonal_projection(a)[j - m])],
            "u_kind": u_kind, "v_kind": v_kind,
            "cost_p": float(cost[i, j]),
        })
    total = float(cost[rows, cols].sum())
    return {
        "n_a": n, "n_b": m, "augmented_matrix": [n + m, n + m],
        "p": order, "internal_norm": internal_norm,
        "total_cost_p": total, "W_p": total ** (1.0 / order),
        "pairs": pairs,
    }


def _wasserstein_p_restricted(diagram_a, diagram_b, order: int = 1,
                              internal_norm: str = "L_inf") -> float:
    """v0.1 shortcut: only own projection is allowed. Used ONLY to verify
    equivalence with the full augmented construction in the unit tests.
    """
    a, b = _clean(diagram_a), _clean(diagram_b)
    n, m = len(a), len(b)
    if n == 0 and m == 0:
        return 0.0
    metric = _linf if internal_norm == "L_inf" else _l2
    big = 1.0e12
    cost = np.full((n + m, n + m), big, dtype=float)
    if n and m:
        cost[:n, :m] = metric(a, b) ** order
    if n:
        cost[np.arange(n), m + np.arange(n)] = (
            np.abs(a[:, 1] - a[:, 0]) / 2.0) ** order
    if m:
        cost[n + np.arange(m), np.arange(m)] = (
            np.abs(b[:, 1] - b[:, 0]) / 2.0) ** order
    cost[n:, m:] = 0.0
    rows, cols = linear_sum_assignment(cost)
    total = float(cost[rows, cols].sum())
    return total ** (1.0 / order)


def bottleneck_distance(diagram_a, diagram_b) -> float:
    """L_inf / p=infinity control (not the paper's main distance)."""
    a, b = _clean(diagram_a), _clean(diagram_b)
    if len(a) == 0 and len(b) == 0:
        return 0.0
    n, m = len(a), len(b)
    cost = _augmented_cost(a, b, 1, "L_inf")
    candidates = np.unique(np.concatenate([np.asarray([0.0]), cost.ravel()]))
    for v in candidates:
        feasible = cost <= v + 1e-12
        r, c = linear_sum_assignment(np.where(feasible, 0.0, 1.0))
        if bool(np.all(feasible[r, c])):
            return float(v)
    return float("nan")


# --------------------------------------------------------------------------
# Panel loading
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Panel:
    name: str
    codes: tuple[str, ...]
    dates: tuple[str, ...]
    log_returns: np.ndarray
    simple_returns: np.ndarray


def load_industry_panel(db_path: Path, codes: list[str], start: str, end: str,
                        name: str = "panel") -> Panel:
    """Load a fully-aligned industry price panel; returns start at the second day.

    Only trading days where every industry has a positive close are kept.
    One extra earlier date is read so the first in-range day has a return.
    """
    conn = sqlite3.connect(str(db_path))
    placeholders = ",".join("?" * len(codes))
    sql = (f"SELECT date, code, close FROM sw_industry_daily "
           f"WHERE code IN ({placeholders}) AND date <= ? ORDER BY date, code")
    by_date: dict[str, dict[str, float]] = defaultdict(dict)
    for d, code, close in conn.execute(sql, list(codes) + [end]):
        if close is not None and float(close) > 0:
            by_date[d][code] = float(close)
    conn.close()

    aligned = [d for d in sorted(by_date) if len(by_date[d]) == len(codes)]
    first_in_range = next((i for i, d in enumerate(aligned) if d >= start), None)
    if first_in_range is None:
        raise ValueError("no aligned industry dates in range")
    lo = max(0, first_in_range - 1)
    use = aligned[lo:]
    closes = np.asarray([[by_date[d][c] for c in codes] for d in use], dtype=float)
    simple = closes[1:] / closes[:-1] - 1.0
    logret = np.log(closes[1:] / closes[:-1])
    dates = tuple(use[1:])
    keep = np.asarray([start <= d <= end for d in dates])
    return Panel(name=name, codes=tuple(codes),
                 dates=tuple(d for d, k in zip(dates, keep) if k),
                 log_returns=logret[keep], simple_returns=simple[keep])


# --------------------------------------------------------------------------
# Daily persistence diagrams -> W_t
# --------------------------------------------------------------------------
def finite_diagram(dgm: np.ndarray) -> np.ndarray:
    d = np.asarray(dgm, dtype=float).reshape(-1, 2)
    return d[np.isfinite(d).all(axis=1)]


def daily_wasserstein(log_returns: np.ndarray, window: int = 60,
                      order: int = 2, internal_norm: str = "L_inf",
                      dims: tuple[str, ...] = ("H0", "H1")) -> np.ndarray:
    """W_t = sum over dims of W_p(P_{t,d}, P_{t-1,d}); NaN before warm-up."""
    n = len(log_returns)
    out = np.full(n, np.nan, dtype=float)
    prev: dict[str, np.ndarray] | None = None
    for t in range(window - 1, n):
        cloud = log_returns[t - window + 1: t + 1]
        dgms = ripser(cloud, maxdim=1, metric="euclidean", coeff=2)["dgms"]
        cur = {"H0": finite_diagram(dgms[0]), "H1": finite_diagram(dgms[1])}
        if prev is not None:
            out[t] = float(sum(
                wasserstein_p(prev[d], cur[d], order, internal_norm) for d in dims
            ))
        prev = cur
    return out


def sma_causal(values: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=float)
    for t in range(k - 1, len(values)):
        seg = values[t - k + 1: t + 1]
        if np.isfinite(seg).all():
            out[t] = float(seg.mean())
    return out


def month_end_indices(dates: list[str] | tuple[str, ...]) -> list[int]:
    idx: list[int] = []
    last_month = None
    for i, d in enumerate(dates):
        if d[:7] != last_month:
            last_month = d[:7]
            idx.append(i)
        else:
            idx[-1] = i
    return idx


def next_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{y + (m == 12):04d}-{1 if m == 12 else m + 1:02d}"


@dataclass(frozen=True)
class MonthlySignal:
    signal_date: str
    applies_to_month: str
    phti: float
    midrank: float
    quintile: int
    w_wcp: int
    w_fe: int
    w_fel: int


def build_monthly_signals(dates: tuple[str, ...], smoothed: np.ndarray,
                          history: int = 60) -> list[MonthlySignal]:
    me = [i for i in month_end_indices(dates) if np.isfinite(smoothed[i])]
    signals: list[MonthlySignal] = []
    for j in range(history - 1, len(me)):
        window_idx = me[j - history + 1: j + 1]  # inclusive current month
        vals = np.asarray([smoothed[i] for i in window_idx], dtype=float)
        cur = float(smoothed[me[j]])
        rho = (float((vals < cur).sum()) + 0.5 * float((vals == cur).sum())) / len(vals)
        q = min(int(math.floor(rho * 5)) + 1, 5)
        d = dates[me[j]]
        signals.append(MonthlySignal(
            signal_date=d, applies_to_month=next_month(d[:7]),
            phti=cur, midrank=rho, quintile=q,
            w_wcp=EXPOSURE_RULES["worst_case_protection"][q - 1],
            w_fe=EXPOSURE_RULES["flexible_exposure"][q - 1],
            w_fel=EXPOSURE_RULES["flexible_levered"][q - 1],
        ))
    return signals


# --------------------------------------------------------------------------
# Unit tests for the distance implementation (known analytic answers)
# --------------------------------------------------------------------------
def wasserstein_self_test() -> list[dict]:
    cases: list[dict] = []
    a = np.array([[0.0, 1.0]])
    b = np.array([[0.0, 2.0]])
    empty = np.empty((0, 2))
    x = np.array([[0.0, 2.0], [0.0, 4.0]])
    y = np.array([[0.0, 3.0], [1.0, 5.0], [2.0, 2.5]])

    for order, expected in [(1, 1.0), (2, 1.0)]:
        got = wasserstein_p(a, b, order, "L_inf")
        cases.append({"case": f"p={order} A(0,1) vs B(0,2)", "expected": expected,
                      "got": got, "pass": abs(got - expected) < 1e-12})
    got = wasserstein_p(empty, b, 1, "L_inf")
    cases.append({"case": "empty vs one point (0,2)", "expected": 1.0,
                  "got": got, "pass": abs(got - 1.0) < 1e-12})
    got = wasserstein_p(a, empty, 1, "L_inf")
    cases.append({"case": "one point (0,1) vs empty", "expected": 0.5,
                  "got": got, "pass": abs(got - 0.5) < 1e-12})
    got = wasserstein_p(a, a, 2, "L_inf")
    cases.append({"case": "p=2 identical diagrams", "expected": 0.0,
                  "got": got, "pass": abs(got) < 1e-12})
    got = wasserstein_p(x, x.copy(), 2, "L_inf")
    cases.append({"case": "p=2 identical multi-point", "expected": 0.0,
                  "got": got, "pass": abs(got) < 1e-12})

    # Full Kerber construction == v0.1 own-projection shortcut (same optimum).
    for order in (1, 2):
        for aa, bb in [(x, y), (a, empty), (empty, b), (x, x)]:
            full = wasserstein_p(aa, bb, order, "L_inf")
            short = _wasserstein_p_restricted(aa, bb, order, "L_inf")
            cases.append({"case": f"p={order} full vs restricted equivalence",
                          "expected": short, "got": full,
                          "pass": abs(full - short) < 1e-10})
    # symmetry and monotonicity of the family (W_2 <= W_1 for these diagrams)
    w1 = wasserstein_p(x, y, 1, "L_inf")
    w2 = wasserstein_p(x, y, 2, "L_inf")
    cases.append({"case": "W_2 <= W_1", "expected": True,
                  "got": w2 <= w1 + 1e-12, "pass": bool(w2 <= w1 + 1e-12)})
    sym = abs(wasserstein_p(x, y, 2, "L_inf") - wasserstein_p(y, x, 2, "L_inf"))
    cases.append({"case": "p=2 symmetry", "expected": 0.0,
                  "got": sym, "pass": sym < 1e-12})
    return cases
