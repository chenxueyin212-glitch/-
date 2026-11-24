"""Stage B-2: DAILY regime labels for the conjecture check.

Frozen spec: config/regime_conjecture_check.toml v0.1. All rules, thresholds,
benchmarks and the ambiguity dual-solutions are declared there BEFORE any
group comparison is computed. This script only produces labels; it never looks
at persistence summaries, never computes a performance metric, and never
reads the Gate 1 sealed 2025 test set.

Outputs:
  outputs/regime_daily_labels.csv   (3339 rows, 2012-12-31..2026-11-03)
  outputs/regime_labels_meta.json   (coverage, dual-solution disclosure, biases)
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
import tomllib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DB = (ROOT.parent / "a_share_pit" / "tdx_central.db").resolve()
CFG = ROOT / "config" / "regime_conjecture_check.toml"
OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

BULL_BEAR_END = "2025-05-30"   # wind_all_a ends here; after -> undefined
UNDEFINED_AFTER = "2025-05-30"


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        hdr = next(r)
        return hdr, list(r)


def to_float(s: str):
    try:
        v = float(s)
        return v if math.isfinite(v) else np.nan
    except (ValueError, TypeError):
        return np.nan


def rolling_mean(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    cs = np.nancumsum(np.where(np.isfinite(x), x, 0.0))
    cnt = np.cumsum(np.isfinite(x).astype(float))
    for i in range(k - 1, len(x)):
        lo = 0 if i - k < 0 else i - k + 1
        s = cs[i] - (cs[i - k] if i - k >= 0 else 0.0)
        n = cnt[i] - (cnt[i - k] if i - k >= 0 else 0.0)
        out[i] = s / n if n >= k else np.nan
    return out


def rolling_max(x: np.ndarray, k: int) -> np.ndarray:
    """Rolling max over [i-k+1, i], NaN only where warm-up is incomplete."""
    out = np.full(len(x), np.nan)
    for i in range(k - 1, len(x)):
        seg = x[i - k + 1:i + 1]
        if np.isfinite(seg).all():
            out[i] = seg.max()
    return out


def rolling_midrank_pct(x: np.ndarray, k: int) -> np.ndarray:
    """Causal midrank percentile of x[i] within the trailing k values.
    Uses only x[i-k+1..i]; returns NaN when fewer than 30 observations exist.
    """
    out = np.full(len(x), np.nan)
    for i in range(len(x)):
        lo = max(0, i - k + 1)
        seg = x[lo:i + 1]
        seg = seg[np.isfinite(seg)]
        if len(seg) < 30 or not np.isfinite(x[i]):
            continue
        cur = x[i]
        out[i] = ((seg < cur).sum() + 0.5 * (seg == cur).sum()) / len(seg)
    return out


def rolling_zscore(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(len(x)):
        lo = max(0, i - k + 1)
        seg = x[lo:i + 1]
        seg = seg[np.isfinite(seg)]
        if len(seg) < 30 or not np.isfinite(x[i]):
            continue
        sd = seg.std(ddof=1)
        if sd > 1e-12:
            out[i] = (x[i] - seg.mean()) / sd
    return out


def rsi_simple(close: np.ndarray, n: int = 14) -> np.ndarray:
    """Transparent simple-average RSI (not Wilder). Documented choice."""
    out = np.full(len(close), np.nan)
    d = np.diff(close, prepend=np.nan)
    gain = np.where(np.isfinite(d), np.maximum(d, 0.0), np.nan)
    loss = np.where(np.isfinite(d), np.maximum(-d, 0.0), np.nan)
    for i in range(n, len(close)):
        g = gain[i - n + 1:i + 1]
        l = loss[i - n + 1:i + 1]
        if np.isfinite(g).all() and np.isfinite(l).all():
            ag, al = g.mean(), l.mean()
            out[i] = 100.0 if al < 1e-12 else 100 - 100 / (1 + ag / al)
    return out


def min_periods_slope(x: np.ndarray, k: int = 20) -> np.ndarray:
    """OLS slope of MA250 over last k observations (sensitivity definition)."""
    out = np.full(len(x), np.nan)
    t = np.arange(k, dtype=float)
    tc = t - t.mean()
    den = (tc ** 2).sum()
    for i in range(k - 1, len(x)):
        seg = x[i - k + 1:i + 1]
        if np.isfinite(seg).all():
            out[i] = float((tc * (seg - seg.mean())).sum() / den)
    return out


def load_index_series(code: str) -> dict[str, dict]:
    conn = sqlite3.connect(str(DB))
    rows = conn.execute(
        "SELECT date, close, volume, amount FROM index_daily_raw "
        "WHERE code=? ORDER BY date", (code,)).fetchall()
    conn.close()
    return {d: {"close": float(c) if c is not None else np.nan,
                "volume": float(v) if v is not None else np.nan,
                "amount": float(a) if a is not None else np.nan}
            for d, c, v, a in rows}


def main() -> None:
    spec = tomllib.loads(CFG.read_text(encoding="utf-8"))
    _, xy_rows = read_csv(OUT / "xy_corrected_features.csv")
    dates = [r[0] for r in xy_rows]
    n = len(dates)
    dmap = {d: i for i, d in enumerate(dates)}

    # ---------- benchmark prices ----------
    _, wa_rows = read_csv(OUT / "xy_wind_all_a_daily.csv")
    wa = {r[0]: to_float(r[2]) for r in wa_rows}       # close
    sse_full = load_index_series("000001")
    hs300 = load_index_series("000300")
    zz1000 = load_index_series("000852")

    close_wa = np.array([wa.get(d, np.nan) for d in dates])
    close_sse = np.array([sse_full.get(d, {}).get("close", np.nan) for d in dates])
    vol_sse = np.array([sse_full.get(d, {}).get("volume", np.nan) for d in dates])
    p300 = np.array([hs300.get(d, {}).get("close", np.nan) for d in dates])
    p1000 = np.array([zz1000.get(d, {}).get("close", np.nan) for d in dates])

    # ---------- breadth / amount / limit proxies ----------
    bh, bh_rows = read_csv(OUT / "regime_breadth_daily.csv")
    bi = {c: j for j, c in enumerate(bh)}
    breadth = {r[0]: {c: to_float(r[bi[c]]) for c in bh if c != "date"}
               for r in bh_rows}
    n_above = np.array([breadth.get(d, {}).get("n_above20_all", np.nan) for d in dates])
    n_above_strict = np.array([breadth.get(d, {}).get("n_above20_strict", np.nan) for d in dates])
    n_traded = np.array([breadth.get(d, {}).get("n_traded", np.nan) for d in dates])
    n_valid20 = np.array([breadth.get(d, {}).get("n_valid20", np.nan) for d in dates])
    total_amount = np.array([breadth.get(d, {}).get("total_amount", np.nan) for d in dates])
    n_up10 = np.array([breadth.get(d, {}).get("n_up_10", np.nan) for d in dates])
    n_dn10 = np.array([breadth.get(d, {}).get("n_down_10", np.nan) for d in dates])
    n_up20 = np.array([breadth.get(d, {}).get("n_up_20", np.nan) for d in dates])
    n_dn20 = np.array([breadth.get(d, {}).get("n_down_20", np.nan) for d in dates])
    n_up5 = np.array([breadth.get(d, {}).get("n_up_5", np.nan) for d in dates])
    n_dn5 = np.array([breadth.get(d, {}).get("n_down_5", np.nan) for d in dates])

    # ---------- first layer: trend (two benchmarks, two slope definitions) -----
    def layer1(close: np.ndarray, slope_kind: str) -> dict:
        ma250 = rolling_mean(close, 250)
        slope_diff = np.full(n, np.nan)
        slope_diff[20:] = ma250[20:] - ma250[:-20]
        slope_reg = min_periods_slope(ma250, 20)
        slope = slope_diff if slope_kind == "diff" else slope_reg
        hi250 = rolling_max(close, 250)
        dd = close / hi250 - 1.0
        warm = np.isfinite(ma250) & np.isfinite(slope) & np.isfinite(dd)
        bull = warm & (close > ma250) & (slope > 0) & (dd > -0.15)
        bear = warm & (close < ma250) & (slope < 0) & (dd < -0.20)
        return {"close": close, "ma250": ma250, "slope": slope,
                "dd250": dd, "bull": bull, "bear": bear,
                "warm": warm,
                "ma20": rolling_mean(close, 20),
                "ma60": rolling_mean(close, 60)}

    l1_wa = layer1(close_wa, "diff")
    l1_sse = layer1(close_sse, "diff")
    l1_wa_reg = layer1(close_wa, "reg")

    # ---------- second layer items ----------
    # A: share of stocks above MA20 (primary denominator = n_traded)
    with np.errstate(invalid="ignore", divide="ignore"):
        frac_above = n_above / n_traded
        frac_above_strict = n_above_strict / n_valid20
    A_bull = frac_above > 0.60
    A_bear = frac_above < 0.40

    # B1: 60-day change of the small/large ratio
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = p1000 / p300
    B1 = np.full(n, np.nan)
    B1[60:] = ratio[60:] / ratio[:-60] - 1.0
    # B2: difference of the two 60-day returns
    r300 = np.full(n, np.nan); r1000 = np.full(n, np.nan)
    r300[60:] = p300[60:] / p300[:-60] - 1.0
    r1000[60:] = p1000[60:] / p1000[:-60] - 1.0
    B2 = r1000 - r300

    # C1: 250-day percentile of all-A turnover (amount); C2: SSE index volume
    C1 = rolling_midrank_pct(total_amount, 250)
    C2 = rolling_midrank_pct(vol_sse, 250)

    # D: MA20 vs MA60 (benchmark-dependent)
    def item_D(l1):
        return l1["ma20"] > l1["ma60"], l1["ma20"] < l1["ma60"]

    D_bull_wa, D_bear_wa = item_D(l1_wa)
    D_bull_sse, D_bear_sse = item_D(l1_sse)

    def layer2_state(l1, B, C, D_bull, D_bear, B_thresh=0.05):
        # Every one of the four items must be computable, otherwise the fuzzy
        # state is marked undefined (-1) rather than silently "no item hit".
        ok = (np.isfinite(B) & np.isfinite(C) & np.isfinite(frac_above)
              & np.isfinite(l1["ma20"]) & np.isfinite(l1["ma60"]))
        bull_items = (A_bull.astype(int) + (B > B_thresh).astype(int)
                      + (C > 0.50).astype(int) + D_bull.astype(int))
        bear_items = (A_bear.astype(int) + (B < -B_thresh).astype(int)
                      + (C < 0.50).astype(int) + D_bear.astype(int))
        bull_items = np.where(ok, bull_items, -1)
        bear_items = np.where(ok, bear_items, -1)
        return bull_items, bear_items

    # ---------- third layer: overheat / oversold (attached labels only) -------
    bias = (close_wa - l1_wa["ma250"]) / l1_wa["ma250"]
    bias_z = rolling_zscore(bias, 60)
    rsi = rsi_simple(close_wa, 14)
    rsi5 = rolling_mean(rsi, 5)
    pct750 = rolling_midrank_pct(close_wa, 750)

    def limit_share(up, dn):
        with np.errstate(invalid="ignore", divide="ignore"):
            return up / (up + dn)

    lim10 = limit_share(n_up10, n_dn10)
    lim20 = limit_share(n_up20, n_dn20)
    lim5 = limit_share(n_up5, n_dn5)

    oh1 = bias_z > 2
    oh2 = (rsi > 80) & (rsi5 > 80)
    oh3 = (lim10 > 0.85) & (n_up10 > 80)
    oh4 = pct750 > 0.90
    os1 = bias_z < -2
    os2 = rsi < 20
    os3 = (lim10 < 0.15) & (n_dn10 > 50)
    os4 = pct750 < 0.10
    overheat = oh1 | oh2 | oh3 | oh4
    oversold = os1 | os2 | os3 | os4

    # ---------- legacy fuzzy trigger (sensitivity only) ----------------------
    below = close_wa < l1_wa["ma250"]
    prev_below = np.concatenate([[False], below[:-1]])
    break_day = below & ~prev_below
    shallow = (l1_wa["ma250"] - close_wa) / l1_wa["ma250"] < 0.05
    recovered = np.zeros(n, dtype=bool)
    for i in np.flatnonzero(break_day):
        for j in range(i + 1, min(i + 11, n)):
            if close_wa[j] > l1_wa["ma250"][j]:
                recovered[j] = True
                break
    legacy_bullish = recovered
    legacy_bearish = np.zeros(n, dtype=bool)
    for i in np.flatnonzero(break_day):
        end = min(i + 10, n - 1)
        if not recovered[i + 1:end + 1].any() and not shallow[i]:
            legacy_bearish[end] = True

    # ---------- crisis labels ------------------------------------------------
    _, ev_rows = read_csv(OUT / "xy_crisis_events.csv")
    events = [r for r in ev_rows]
    crisis_in = np.zeros(n, dtype=bool)          # all 17 segments (price fact)
    crisis_in_usable = np.zeros(n, dtype=bool)   # 16 non-left-censored
    crisis_event_id = np.zeros(n, dtype=int)
    for r in events:
        eid = int(r[0]); onset, end = r[1], r[4]
        i0 = dmap.get(onset); i1 = dmap.get(end)
        if i0 is None:
            continue
        if i1 is None:
            i1 = min(i0 + int(r[5]) - 1, n - 1)
        crisis_in[i0:i1 + 1] = True
        crisis_event_id[i0:i1 + 1] = eid
        if r[6].strip().lower() != "true":
            crisis_in_usable[i0:i1 + 1] = True

    usable_events = [r for r in events
                     if r[6].strip().lower() != "true" and r[1] in dmap]
    pre = {}
    for k in (5, 10, 20):
        arr = np.zeros(n, dtype=bool)
        for r in usable_events:
            i0 = dmap[r[1]]
            lo = max(0, i0 - k)
            arr[lo:i0] = True
        pre[k] = arr & ~crisis_in       # never label a crisis day as pre-crisis

    # ---------- volume-type split of pre-crisis windows -----------------------
    # Declared BEFORE looking at any persistence summary: mean |daily return|
    # of the primary benchmark over the 60 days before each onset, split at the
    # sample median across usable events.
    ret_wa = np.full(n, np.nan)
    ret_wa[1:] = close_wa[1:] / close_wa[:-1] - 1.0
    absret60 = rolling_mean(np.abs(ret_wa), 60)
    vol_vals = []
    for r in usable_events:
        i0 = dmap[r[1]]
        v = absret60[i0 - 1] if i0 >= 1 else np.nan
        vol_vals.append((int(r[0]), r[1], float(v) if np.isfinite(v) else None))
    finite_vals = [v for _, _, v in vol_vals if v is not None]
    vol_median = float(np.median(finite_vals)) if finite_vals else None
    vol_type = {}
    for eid, onset, v in vol_vals:
        vol_type[eid] = ("high" if v is not None and vol_median is not None
                         and v >= vol_median else "low" if v is not None else "na")
    pre_vol_type = [""] * n
    for r in usable_events:
        eid, onset = int(r[0]), r[1]
        i0 = dmap[onset]
        for j in range(max(0, i0 - 20), i0):
            if not crisis_in[j]:
                pre_vol_type[j] = vol_type[eid]

    # ---------- assemble versions -------------------------------------------
    def final_state(l1, bull_items, bear_items, fuzzy_mode="layer2"):
        date_arr = np.array(dates)
        beyond = np.array([d > UNDEFINED_AFTER for d in dates])
        st = np.full(n, "", dtype=object)
        st[:] = "undefined_warmup"
        ok = l1["warm"]
        st[ok & l1["bull"]] = "bull"
        st[ok & l1["bear"]] = "bear"
        fuzzy = ok & ~l1["bull"] & ~l1["bear"]
        if fuzzy_mode == "layer2":
            st[fuzzy & (bull_items >= 2)] = "bull_adjustment"
            st[fuzzy & (bear_items >= 2)] = "bear_turn"
            st[fuzzy & (bull_items < 2) & (bear_items < 2)] = "fuzzy"
        else:  # legacy 5% trigger
            st[fuzzy & legacy_bullish] = "bull_adjustment"
            st[fuzzy & legacy_bearish] = "bear_turn"
            st[fuzzy & ~legacy_bullish & ~legacy_bearish] = "fuzzy"
        st[beyond] = "undefined_after_2025_05_30"
        return st

    b1_wa, s1_wa = layer2_state(l1_wa, B1, C1, D_bull_wa, D_bear_wa)
    b2_wa, s2_wa = layer2_state(l1_wa, B2, C1, D_bull_wa, D_bear_wa)
    bc2_wa, sc2_wa = layer2_state(l1_wa, B1, C2, D_bull_wa, D_bear_wa)
    bsse, ssse = layer2_state(l1_sse, B1, C1, D_bull_sse, D_bear_sse)
    # note: validity for SSE version uses SSE MA20/MA60 via item_D

    V = {
        "v0_primary": final_state(l1_wa, b1_wa, s1_wa),
        "v1_benchmark_sse": final_state(l1_sse, bsse, ssse),
        "v2_B2": final_state(l1_wa, b2_wa, s2_wa),
        "v3_C2": final_state(l1_wa, bc2_wa, sc2_wa),
        "v4_legacy5pct": final_state(l1_wa, b1_wa, s1_wa, fuzzy_mode="legacy"),
    }

    def coarse(st):
        out = np.full(n, "", dtype=object)
        for src, dst in [("bull", "bull"), ("bull_adjustment", "bull"),
                         ("bear", "bear"), ("bear_turn", "bear"),
                         ("fuzzy", "fuzzy")]:
            out[st == src] = dst
        out[(st == "undefined_warmup") | (st == "undefined_after_2025_05_30")] = "undefined"
        return out

    # ---------- bear-label lag vs crisis onset --------------------------------
    bear_lag = []
    st0 = V["v0_primary"]
    for r in usable_events:
        i0 = dmap[r[1]]
        j = next((k for k in range(i0, min(i0 + 60, n))
                  if st0[k] in ("bear", "bear_turn")), None)
        bear_lag.append({"event_id": int(r[0]), "onset": r[1],
                         "bear_label_lag_days": (j - i0) if j is not None else None})

    # ---------- write CSV ----------------------------------------------------
    cols = ["date", "close_wind", "close_sse", "ma250_wind", "ma250_sse",
            "ma250_slope_diff", "dd250_wind", "dd250_sse",
            "frac_above_ma20", "frac_above_ma20_strict", "n_traded",
            "B1_ratio_chg60", "B2_ret_diff60", "C1_amount_pct250",
            "C2_sse_vol_pct250", "D_bull_wa", "D_bull_sse",
            "bias250_z60", "rsi14", "rsi14_ma5", "pct750", "lim10_share",
            "oh1", "oh2", "oh3", "oh4", "overheat", "os1", "os2", "os3",
            "os4", "oversold", "legacy_recovered", "legacy_shallow_break",
            "l1_bull_wa", "l1_bear_wa", "l1_bull_sse", "l1_bear_sse",
            "l2_bull_items_v0", "l2_bear_items_v0",
            "crisis_in", "crisis_in_usable", "crisis_event_id",
            "pre5", "pre10", "pre20", "pre_vol_type", "bull_bear_defined",
            "bear_in_crisis"] + [f"state_{k}" for k in V] + ["state_coarse_v0"]
    arrs = {
        "date": dates,
        "close_wind": close_wa, "close_sse": close_sse,
        "ma250_wind": l1_wa["ma250"], "ma250_sse": l1_sse["ma250"],
        "ma250_slope_diff": l1_wa["slope"],
        "dd250_wind": l1_wa["dd250"], "dd250_sse": l1_sse["dd250"],
        "frac_above_ma20": frac_above, "frac_above_ma20_strict": frac_above_strict,
        "n_traded": n_traded,
        "B1_ratio_chg60": B1, "B2_ret_diff60": B2,
        "C1_amount_pct250": C1, "C2_sse_vol_pct250": C2,
        "D_bull_wa": D_bull_wa, "D_bull_sse": D_bull_sse,
        "bias250_z60": bias_z, "rsi14": rsi, "rsi14_ma5": rsi5,
        "pct750": pct750, "lim10_share": lim10,
        "oh1": oh1, "oh2": oh2, "oh3": oh3, "oh4": oh4, "overheat": overheat,
        "os1": os1, "os2": os2, "os3": os3, "os4": os4, "oversold": oversold,
        "legacy_recovered": recovered, "legacy_shallow_break": break_day & shallow,
        "l1_bull_wa": l1_wa["bull"], "l1_bear_wa": l1_wa["bear"],
        "l1_bull_sse": l1_sse["bull"], "l1_bear_sse": l1_sse["bear"],
        "l2_bull_items_v0": b1_wa, "l2_bear_items_v0": s1_wa,
        "crisis_in": crisis_in, "crisis_in_usable": crisis_in_usable,
        "crisis_event_id": crisis_event_id,
        "pre5": pre[5], "pre10": pre[10], "pre20": pre[20],
        "pre_vol_type": pre_vol_type,
        "bull_bear_defined": np.array([d <= BULL_BEAR_END for d in dates]),
        "bear_in_crisis": ((V["v0_primary"] == "bear") |
                           (V["v0_primary"] == "bear_turn")) & crisis_in,
        "state_coarse_v0": coarse(V["v0_primary"]),
    }
    for k, v in V.items():
        arrs[f"state_{k}"] = v

    path = OUT / "regime_daily_labels.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i in range(n):
            row = []
            for c in cols:
                v = arrs[c][i]
                if isinstance(v, (bool, np.bool_)):
                    row.append(int(v))
                elif isinstance(v, (float, np.floating)):
                    row.append("" if not math.isfinite(float(v)) else f"{float(v):.10g}")
                else:
                    row.append(v)
            w.writerow(row)

    # ---------- metadata -----------------------------------------------------
    meta = {
        "spec": str(CFG.relative_to(ROOT)),
        "spec_version": spec["meta"]["version"],
        "n_days": n, "first_date": dates[0], "last_date": dates[-1],
        "benchmark_primary": "wind_all_a (2012-12-31..2025-05-30)",
        "benchmark_sensitivity": "000001 SSE Composite (extends to 2026-11-04)",
        "bull_bear_undefined_after": UNDEFINED_AFTER,
        "n_days_undefined_after": int(sum(1 for d in dates if d > UNDEFINED_AFTER)),
        "n_crisis_segments_all": len(events),
        "n_crisis_events_usable": len(usable_events),
        "excluded_left_censored_event_ids": [int(r[0]) for r in events
                                             if r[6].strip().lower() == "true"],
        "crisis_in_days": int(crisis_in.sum()),
        "crisis_in_usable_days": int(crisis_in_usable.sum()),
        "pre_days": {str(k): int(pre[k].sum()) for k in (5, 10, 20)},
        "vol_type_split": {
            "rule": "mean |primary benchmark daily return| over 60 days before "
                    "each usable onset; split at median across usable events; "
                    "declared BEFORE any persistence summary was inspected",
            "median": vol_median,
            "by_event": vol_vals,
            "labels": vol_type,
        },
        "bear_label_lag_days_vs_onset": bear_lag,
        "state_counts_by_version": {
            k: {s: int((v == s).sum()) for s in sorted(set(v))} for k, v in V.items()
        },
        "ambiguity_dual_solutions": {
            "B1": "ratio(000852/000300) 60d change",
            "B2": "ret60(000852) - ret60(000300)",
            "C1": "all-A turnover (sum amount) 250d midrank percentile",
            "C2": "SSE 000001 index volume 250d midrank percentile",
            "slope": "primary MA250(t)-MA250(t-20); sensitivity OLS slope over 20d",
            "benchmark": "wind_all_a primary, 000001 sensitivity",
        },
        "known_caveats": [
            "individual-stock breadth denominator excludes suspended stocks "
            "(they are MISSING rows, no volume=0 record); 2015-07 mass "
            "suspension biases the fraction upward",
            "universe size grows over time; n_traded is written per day",
            "limit-up/down counts are approximations from close/prev_close "
            "thresholds (10%/20%/5%), NOT filtered for ex-rights days; "
            "attached label only, never a main bull/bear criterion",
            "bear condition dd<-20% is an ex-post trigger -> lags crisis onset; "
            "bear lag days reported separately and bear-in-crisis is a separate cell",
            "2025-06+ has no bull/bear label; summary values remain but do not "
            "enter any state group comparison",
            "all states non-exclusive: main label + overlay labels are separate columns",
        ],
        "gate_boundary": "Gate 1 2025 final test NOT read; no performance / IC / "
                         "Sharpe / position / threshold selection performed",
    }
    meta_path = OUT / "regime_labels_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "labels": str(path), "meta": str(meta_path),
        "rows": n,
        "state_counts_v0": meta["state_counts_by_version"]["v0_primary"],
        "crisis_days": meta["crisis_in_days"],
        "pre_days": meta["pre_days"],
        "vol_median": vol_median,
        "bear_lag": [x["bear_label_lag_days"] for x in bear_lag],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
