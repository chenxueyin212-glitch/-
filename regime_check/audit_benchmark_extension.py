"""READ-ONLY audit: is the 2025-05-30 bull/bear cutoff a data limit?

Question from user (2026-11-09): Wind All-A (881001.WI proxy) daily CSV ends
2025-05-30, but the local TDX database has index and equity daily bars through
2026-11-04. Can a composite benchmark be built from those to extend the
bull/bear labels past 2025-05-30?

This script does NOT:
  - modify any frozen label / verdict / grid / report file,
  - recompute any persistence summary, bootstrap, or conjecture verdict,
  - read the Gate 1 sealed 2025 test set,
  - compute any performance / IC / PR-AUC / position metric.

It only:
  1. builds candidate composite benchmark series from tdx_central.db,
  2. compares them with the frozen wind_all_a proxy over the overlap,
  3. counts how many of the 345 "undefined_after" days would become definable,
  4. quantifies the impact on the v0.3 NORMAL baseline (read-only arithmetic).

Outputs (new files only):
  outputs/regime_v03_benchmark_candidates.csv
  outputs/regime_v03_benchmark_extension_audit.json
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DB = (ROOT.parent / "a_share_pit" / "tdx_central.db").resolve()
OUT = ROOT / "outputs"
CUTOFF = "2025-05-30"

# Gate 0 frozen market-benchmark convention (user-confirmed):
# equal-weight daily SIMPLE returns of 000001 and 399001, chain-linked.
SSE, SZSE = "000001", "399001"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def chain_from_returns(dates: list[str], rets: list[float], base=1000.0) -> dict:
    out, p = {}, base
    for d, r in zip(dates, rets):
        p *= (1.0 + r)
        out[d] = p
    return out


def index_close(con, code: str, market: int) -> dict:
    return {d: c for d, c in con.execute(
        "select date, close from index_daily_raw where code=? and market=? "
        "and date>=? order by date", (code, market, "2012-12-31"))
        if c is not None and c > 0}


def main() -> None:
    con = sqlite3.connect(str(DB))

    labels = read_csv(OUT / "regime_daily_labels.csv")
    dates = [r["date"] for r in labels]
    wa = {r["date"]: float(r["close"]) for r in
          read_csv(OUT / "xy_wind_all_a_daily.csv")}

    # ---------- candidate 1: Gate-0 frozen composite (000001 + 399001) -------
    psse = index_close(con, SSE, 1)
    psz = index_close(con, SZSE, 0)
    common = sorted(set(psse) & set(psz))
    comp_ret = {}
    for i in range(1, len(common)):
        d0, d1 = common[i - 1], common[i]
        r1 = psse[d1] / psse[d0] - 1.0
        r2 = psz[d1] / psz[d0] - 1.0
        comp_ret[d1] = 0.5 * (r1 + r2)
    g0 = chain_from_returns(common[1:], [comp_ret[d] for d in common[1:]])

    # ---------- candidate 2: equal-weight all-share median daily return -----
    # Cross-sectional MEDIAN is used because it is insensitive to single-name
    # ex-dividend / split jumps (unadjusted TDX closes). Trading-day adjacency
    # is enforced via the trade calendar so suspended names cannot inject a
    # multi-day cumulative return as a single daily return.
    cal = [r[0] for r in con.execute(
        "select date from trade_calendar where date>=? order by date",
        ("2012-12-31",))]
    seq = {d: i for i, d in enumerate(cal)}
    rows = con.execute(
        "select code, date, close from equity_daily_raw where date>=? "
        "order by code, date", ("2012-12-31",))
    by_day = defaultdict(list)
    prev_code, prev_close, prev_seq = None, None, None
    for code, d, c in rows:
        if c is None or c <= 0:
            prev_code, prev_close, prev_seq = code, None, None
            continue
        if code == prev_code and prev_close is not None and prev_seq is not None:
            if seq.get(d, -999) == prev_seq + 1:
                r = c / prev_close - 1.0
                if -0.5 < r < 1.0:          # drop obvious bad ticks / corp actions
                    by_day[d].append(r)
        prev_code, prev_close, prev_seq = code, c, seq.get(d)
    eq_dates = sorted(d for d in by_day if d in seq and len(by_day[d]) >= 500)
    eq_rets = [statistics.median(by_day[d]) for d in eq_dates]
    eq = chain_from_returns(eq_dates, eq_rets)

    # ---------- candidate 3: SSE alone (already used by v1 sensitivity) -----
    sse_only = {d: psse[d] for d in psse}

    con.close()

    # ---------- overlap comparison vs frozen wind_all_a ---------------------
    def daily_ret(p: dict, ds: list[str]) -> list[float]:
        out = []
        for i in range(1, len(ds)):
            a, b = p.get(ds[i - 1]), p.get(ds[i])
            out.append(b / a - 1.0 if (a and b) else np.nan)
        return out

    overlap = [d for d in dates if d <= CUTOFF and d in wa]
    wa_r = np.array(daily_ret(wa, overlap), float)

    def compare(name: str, p: dict) -> dict:
        r = np.array(daily_ret(p, overlap), float)
        ok = np.isfinite(wa_r) & np.isfinite(r)
        a, b = wa_r[ok], r[ok]
        pear = float(np.corrcoef(a, b)[0, 1])
        # Spearman via rank
        ra = np.argsort(np.argsort(a)).astype(float)
        rb = np.argsort(np.argsort(b)).astype(float)
        spear = float(np.corrcoef(ra, rb)[0, 1])
        # MA250 above/below agreement (both series must have 250 valid days)
        def ma_state(px):
            v = np.array([px.get(d, np.nan) for d in dates], float)
            ma = np.full(len(v), np.nan)
            cs = np.nancumsum(np.where(np.isfinite(v), v, 0.0))
            cnt = np.cumsum(np.isfinite(v).astype(float))
            for i in range(249, len(v)):
                s = cs[i] - (cs[i - 250] if i - 250 >= 0 else 0.0)
                nn = cnt[i] - (cnt[i - 250] if i - 250 >= 0 else 0.0)
                ma[i] = s / nn if nn >= 250 else np.nan
            valid = np.isfinite(v) & np.isfinite(ma)
            return (v > ma), valid
        wa_above, wa_valid = ma_state(wa)
        p_above, p_valid = ma_state(p)
        both = wa_valid & p_valid & np.array([d <= CUTOFF for d in dates])
        agree = float((wa_above[both] == p_above[both]).mean()) if both.any() else None
        return {"name": name, "n_overlap_returns": int(ok.sum()),
                "pearson_daily_return": round(pear, 6),
                "spearman_daily_return": round(spear, 6),
                "ma250_above_agreement": round(agree, 6) if agree else None,
                "n_ma250_days": int(both.sum()),
                "ann_vol_wa": round(float(np.std(a) * math.sqrt(250)), 6),
                "ann_vol_candidate": round(float(np.std(b) * math.sqrt(250)), 6)}

    comp = [compare("gate0_000001_399001_equal_chain", g0),
            compare("allshare_equal_median_chain", eq),
            compare("sse_000001_only", sse_only)]

    # ---------- how many of the 345 days would become definable -------------
    after = [r for r in labels if r["date"] > CUTOFF]
    after_dates = [r["date"] for r in after]
    cov = {
        "gate0_composite": sum(1 for d in after_dates if d in g0),
        "allshare_median": sum(1 for d in after_dates if d in eq),
        "sse_only": sum(1 for d in after_dates if d in sse_only),
        "frozen_wind_all_a": sum(1 for d in after_dates if d in wa),
        "breadth_total_amount": None,
        "n_traded": None,
    }
    bh = read_csv(OUT / "regime_breadth_daily.csv")
    bh_by_date = {r["date"]: r for r in bh}
    cov["breadth_total_amount"] = sum(
        1 for d in after_dates
        if d in bh_by_date and bh_by_date[d]["total_amount"].strip() not in ("", "nan"))
    cov["n_traded"] = sum(
        1 for d in after_dates
        if d in bh_by_date and bh_by_date[d]["n_traded"].strip() not in ("", "nan"))

    # ---------- already-computed inputs in the 345 days (from label file) ---
    key_cols = ["close_sse", "ma250_sse", "dd250_sse", "frac_above_ma20",
                "n_traded", "B1_ratio_chg60", "close_wind", "ma250_wind"]
    filled = {c: sum(1 for r in after if r.get(c, "").strip() not in ("", "nan"))
              for c in key_cols}

    # ---------- impact on v0.3 NORMAL baseline (read-only arithmetic) -------
    sd = read_csv(OUT / "regime_v03_state_daily.csv")
    sd_by_date = {r["date"]: r for r in sd}
    # EXACT v0.3 baseline: pre20 rebuilt from the 14 included onsets, not the
    # frozen 16-event pre20 column. Mixing the two gives 2419 instead of 2450.
    normal_old = sum(1 for r in sd if r["normal_baseline"] == "1")
    after_crisis = sum(1 for r in after if r["crisis_in"] == "1")
    after_pre20 = sum(1 for r in after
                      if sd_by_date[r["date"]]["pre20_judged"] == "1")
    after_normal = sum(1 for r in after
                       if r["crisis_in"] != "1"
                       and sd_by_date[r["date"]]["pre20_judged"] != "1")
    normal_new = normal_old + after_normal

    # ---------- descriptive estimate: layer-1 trend on the G0 composite -----
    # NOT a recomputed verdict; only shows what the 345 days would roughly be.
    def roll_stats(v: np.ndarray, w: int = 250):
        ma = np.full(len(v), np.nan)
        hi = np.full(len(v), np.nan)
        for i in range(w - 1, len(v)):
            seg = v[i - w + 1:i + 1]
            if np.isfinite(seg).all():
                ma[i], hi[i] = float(seg.mean()), float(seg.max())
        slope = np.full(len(v), np.nan)
        slope[20:] = ma[20:] - ma[:-20]
        dd = v / hi - 1.0
        warm = np.isfinite(ma) & np.isfinite(slope) & np.isfinite(dd)
        bull = warm & (v > ma) & (slope > 0) & (dd > -0.15)
        bear = warm & (v < ma) & (slope < 0) & (dd < -0.20)
        return warm, bull, bear

    gv = np.array([g0.get(d, np.nan) for d in dates], float)
    warm, bull, bear = roll_stats(gv)
    ai = [i for i, d in enumerate(dates) if d > CUTOFF]
    trend_after = {
        "basis": "layer-1 only (MA250 / 20d slope / 250d drawdown), "
                 "G0 composite, descriptive estimate NOT a verdict",
        "warm": int(warm[ai].sum()), "bull": int(bull[ai].sum()),
        "bear": int(bear[ai].sum()),
        "fuzzy": int((warm & ~bull & ~bear)[ai].sum()),
        "undefined": int((~warm)[ai].sum()),
    }

    # ---------- drift diagnostic for the equal-weight median composite ------
    eq_overlap = [eq[d] for d in overlap if d in eq]
    g0_overlap = [g0[d] for d in overlap if d in g0]
    wa_overlap = [wa[d] for d in overlap]
    drift = {
        "wind_all_a_overlap_multiple": round(wa_overlap[-1] / wa_overlap[0], 4),
        "gate0_overlap_multiple": round(g0_overlap[-1] / g0_overlap[0], 4),
        "allshare_median_overlap_multiple": round(
            eq_overlap[-1] / eq_overlap[0], 4),
        "note": "equal-weight cross-sectional MEDIAN daily return has a "
                "strongly negative long-run drift on unadjusted TDX closes; "
                "it tracks short-term moves (Pearson ~0.93) but its LEVEL / "
                "MA250 state diverges from a cap-weighted All-A index. "
                "It cannot substitute for the trend layer without "
                "capitalisation weighting + corporate-action adjustment.",
    }

    # ---------- write outputs ----------------------------------------------
    cand_path = OUT / "regime_v03_benchmark_candidates.csv"
    with cand_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "wind_all_a_frozen", "gate0_composite",
                    "allshare_equal_median", "sse_000001",
                    "after_2025_05_30"])
        for d in dates:
            w.writerow([d, wa.get(d, ""), g0.get(d, ""), eq.get(d, ""),
                        sse_only.get(d, ""), int(d > CUTOFF)])

    audit = {
        "purpose": "READ-ONLY feasibility audit; no frozen file modified, "
                   "no verdict / grid / bootstrap / TDA recomputed",
        "trigger": "user 2026-11-09: Wind All-A daily ends 2025-05-30 but "
                   "TDX database has index/equity bars to 2026-11-04",
        "database": {
            "path": str(DB),
            "equity_daily_raw_range": None,
            "index_daily_raw_codes": None,
        },
        "frozen_proxy": {
            "file": "outputs/xy_wind_all_a_daily.csv",
            "rows": len(read_csv(OUT / "xy_wind_all_a_daily.csv")),
            "first": min(wa), "last": max(wa),
            "note": "881001.WI proxy, NOT a Wind original export; OHLC only",
        },
        "cutoff_implementation": {
            "code": "src/regime_check/build_regime_labels.py",
            "line": 'st[beyond] = "undefined_after_2025_05_30"',
            "effect": "unconditionally overwrites ALL 5 label versions, "
                      "including v1_benchmark_sse whose inputs are complete",
            "defined_col_after_cutoff": dict(Counter(
                r["bull_bear_defined"] for r in after)),
        },
        "after_cutoff": {
            "n_days": len(after), "first": after_dates[0], "last": after_dates[-1],
            "crisis_in_days": after_crisis, "pre20_days": after_pre20,
            "already_filled_input_columns": filled,
            "candidate_coverage": cov,
        },
        "overlap_comparison": comp,
        "normal_baseline_if_extended": {
            "v0_3_frozen": 2450,
            "recomputed_exact_v03_rule": normal_old,
            "after_days_crisis": after_crisis,
            "after_days_pre20": after_pre20,
            "after_days_that_would_join_normal": after_normal,
            "if_all_345_days_defined": normal_new,
            "delta_days": normal_new - normal_old,
            "warning": "normal is the BASELINE for every one of the 8340 grid "
                       "cells; extending it changes delta / CI / p for ALL "
                       "cells, not just 345 rows. Crisis groups themselves do "
                       "not change because all 14 included events end before "
                       "2025-05-30. Do NOT use the frozen 16-event pre20 "
                       "column to recompute this: that gives 2419.",
        },
        "layer1_trend_estimate_after_cutoff": trend_after,
        "composite_drift_diagnostic": drift,
        "candidate_caveats": [
            "gate0_composite uses the user-confirmed Gate 0 market benchmark "
            "convention (equal-weight daily SIMPLE returns, chain-linked); it "
            "is a 2-index composite, NOT Wind All-A.",
            "allshare_equal_median uses unadjusted TDX closes; cross-sectional "
            "median suppresses single-name ex-dividend jumps but cannot remove "
            "seasonal clustering of corporate actions. Survivorship / PIT "
            "membership is whatever equity_daily_raw contains on that day.",
            "sse_only is already the v1 sensitivity benchmark; its MA250 / DD "
            "inputs are present for all 345 days.",
            "PE and margin-financing data remain unavailable; the 2/3 rule is "
            "still a degraded implementation regardless of benchmark choice.",
        ],
        "boundary": ["Gate 1 sealed 2025 test set not read",
                     "Gate 2 not started", "PHTI formal backtest not run",
                     "no performance / IC / PR-AUC / position computed",
                     "no frozen v0.1 / v0.2 / v0.3 file overwritten"],
    }
    con2 = sqlite3.connect(str(DB))
    audit["database"]["equity_daily_raw_range"] = con2.execute(
        "select min(date),max(date) from equity_daily_raw").fetchone()
    audit["database"]["index_daily_raw_codes"] = [
        r[0] for r in con2.execute(
            "select distinct code from index_daily_raw order by code")]
    con2.close()

    jp = OUT / "regime_v03_benchmark_extension_audit.json"
    jp.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "candidates_csv": str(cand_path),
        "audit_json": str(jp),
        "after_days": len(after),
        "coverage": cov,
        "filled_inputs": filled,
        "overlap": [{k: c[k] for k in ("name", "pearson_daily_return",
                                        "spearman_daily_return",
                                        "ma250_above_agreement")} for c in comp],
        "normal_old": normal_old, "normal_new": normal_new,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
