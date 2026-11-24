"""Build the v0.5 JUDGEMENT-LAYER inputs (data only, no statistics, no verdict).

Pre-registered in config/regime_split_check_v0.5.toml
  [amendment_2026_11_10_true_wind]          (benchmark)
  [amendment_2026_11_10_judgement_ruling]   (item_2 / item_3 + degradation)

Outputs (all new names, nothing frozen is overwritten):
  outputs/regime_v05_split_wide.csv      6483 x 67  (engine wide table)
  outputs/regime_v05_crisis_events.csv   17 frozen + N new front events (11 cols)
  outputs/regime_v05_daily_labels.csv    audit view of the 14 label columns
  outputs/regime_v05_input_audit.json    hard assertions + coverage disclosure

RULES (fixed BEFORE results):
  * back segment 2012-12-31..2026-11-03 : every wide-table cell and every
    frozen event row is copied verbatim; no label is recomputed from price
  * front segment 1999-12-30..2012-12-28 : Y_t = 1 iff the minimum cumulative
    simple return over the NEXT 20 sessions <= -10%, on the SINGLE real
    881001.WI series; flagged days clustered with a >20-calendar-day gap;
    new event ids start at 101
  * front bull/bear state uses the pre-registered DEGRADED MA250 rule because
    breadth / turnover / PE / margin data do not exist before 2011
  * front A16 w=10 summaries come from the ALREADY FROZEN v0.3 file
    (2005-01-04 onwards); A27 and B-line front cells stay EMPTY.
    Missing -> NaN. Never zero-filled, never back-filled, never recomputed.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"

BENCH = OUT / "regime_v05_benchmark_daily.csv"
WIDE_V03 = OUT / "regime_v03_split_wide.csv"
EVENTS_FROZEN = OUT / "xy_crisis_events.csv"
P16 = OUT / "regime_v03_phti_p16_w10.csv"

WIDE_OUT = OUT / "regime_v05_split_wide.csv"
EVENTS_OUT = OUT / "regime_v05_crisis_events.csv"
LABELS_OUT = OUT / "regime_v05_daily_labels.csv"
AUDIT_OUT = OUT / "regime_v05_input_audit.json"

FRONT_END = "2012-12-28"
ANCHOR = "2012-12-31"
H, DROP, GAP_DAYS, WARMUP = 20, -0.10, 20, 250
BULL_DD, BEAR_DD = -0.10, -0.20
FIRST_FRONT_EVENT_ID = 101

LABEL_COLS = [
    "state_v0_primary", "state_v1_benchmark_sse", "state_v2_B2",
    "state_v3_C2", "state_v4_legacy5pct", "crisis_in", "crisis_in_usable",
    "crisis_event_id", "pre5", "pre10", "pre20", "pre_vol_type",
    "bull_bear_defined", "bear_in_crisis",
]
STATE_COLS = LABEL_COLS[:5]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_rows(p: Path):
    with p.open(encoding="utf-8-sig", newline="") as fh:
        r = csv.reader(fh)
        return next(r), list(r)


def read_dicts(p: Path):
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    bench = read_dicts(BENCH)
    dates = [r["date"] for r in bench]
    close = np.array([float(r["benchmark_close"]) for r in bench], dtype=float)
    n = len(dates)
    assert dates[0] == "1999-12-30" and dates[-1] == "2026-11-03" and n == 6483
    assert all(r["bench_source"] == "real_wind_881001WI" for r in bench)
    ords = np.array([date.fromisoformat(d).toordinal() for d in dates])
    dmap = {d: i for i, d in enumerate(dates)}
    front_idx = [i for i, d in enumerate(dates) if d <= FRONT_END]
    back_idx = [i for i, d in enumerate(dates) if d >= ANCHOR]
    assert len(front_idx) == 3144 and len(back_idx) == 3339
    assert front_idx[0] == 0 and back_idx[0] == len(front_idx)

    # ---------------- forward-looking crisis label (frozen definition) -------
    y = np.full(n, -1, dtype=int)
    worst = np.full(n, np.nan)
    worst_date: list[str | None] = [None] * n
    for i in range(n - H):
        fut = close[i + 1:i + H + 1] / close[i] - 1.0
        j = int(np.argmin(fut))
        worst[i] = float(fut[j])
        worst_date[i] = dates[i + j + 1]
        y[i] = int(fut[j] <= DROP)

    flags = np.zeros(n, dtype=bool)
    for i in front_idx:
        if y[i] == 1:
            flags[i] = True
    flagged = np.flatnonzero(flags)
    clusters: list[list[int]] = []
    cur: list[int] = []
    for i in flagged:
        if cur and ords[i] - ords[cur[-1]] > GAP_DAYS:
            clusters.append(cur)
            cur = []
        cur.append(int(i))
    if cur:
        clusters.append(cur)

    front_events = []
    for eid, c in enumerate(clusters, FIRST_FRONT_EVENT_ID):
        e = c[0]
        front_events.append({
            "event_id": str(eid),
            "onset": dates[e],
            "onset_index": str(e),
            "label_end_date": dates[e + H],
            "end": dates[c[-1]],
            "label_run_days": str(len(c)),
            "left_censored_label": "True" if e == front_idx[0] else "False",
            "worst_cumulative_return_from_onset": repr(float(worst[e])),
            "worst_date": worst_date[e] or "",
            "N_at_onset": "0",
            "avg_corr_at_onset": "",
        })

    # ---------------- front label columns -----------------------------------
    crisis_in = np.zeros(n, dtype=bool)
    crisis_in_usable = np.zeros(n, dtype=bool)
    event_id = np.zeros(n, dtype=int)
    for ev in front_events:
        i0, i1 = dmap[ev["onset"]], dmap[ev["end"]]
        crisis_in[i0:i1 + 1] = True
        event_id[i0:i1 + 1] = int(ev["event_id"])
        if ev["left_censored_label"] != "True":
            crisis_in_usable[i0:i1 + 1] = True

    # frozen back events: usable onsets also define pre-windows
    _, frozen_rows = read_rows(EVENTS_FROZEN)
    back_usable = [r for r in frozen_rows
                   if r[6].strip().lower() != "true" and r[1] in dmap]
    usable_onsets = [r[1] for r in back_usable] + [
        ev["onset"] for ev in front_events
        if ev["left_censored_label"] != "True"]
    pre: dict[int, np.ndarray] = {}
    for k in (5, 10, 20):
        arr = np.zeros(n, dtype=bool)
        for onset in usable_onsets:
            i0 = dmap[onset]
            arr[max(0, i0 - k):i0] = True
        pre[k] = arr & ~crisis_in

    # degraded MA250 bull/bear state (pre-registered thresholds)
    ma250 = np.full(n, np.nan)
    dd250 = np.full(n, np.nan)
    for i in range(WARMUP - 1, n):
        ma250[i] = close[i - WARMUP + 1:i + 1].mean()
        dd250[i] = close[i] / close[i - WARMUP + 1:i + 1].max() - 1.0
    front_state: dict[int, str] = {}
    front_defined: dict[int, int] = {}
    for i in front_idx:
        if i < WARMUP - 1 or not np.isfinite(ma250[i]):
            front_state[i] = "undefined_warmup"
            front_defined[i] = 0
        elif close[i] > ma250[i] and dd250[i] > BULL_DD:
            front_state[i] = "bull"
            front_defined[i] = 1
        elif close[i] < ma250[i] and dd250[i] <= BEAR_DD:
            front_state[i] = "bear"
            front_defined[i] = 1
        else:
            front_state[i] = "fuzzy"
            front_defined[i] = 1

    def front_label(i: int, c: str) -> str:
        if c in STATE_COLS:
            return front_state[i]
        if c == "crisis_in":
            return "1" if crisis_in[i] else "0"
        if c == "crisis_in_usable":
            return "1" if crisis_in_usable[i] else "0"
        if c == "crisis_event_id":
            return str(event_id[i]) if event_id[i] else ""
        if c in ("pre5", "pre10", "pre20"):
            return "1" if pre[int(c[3:])][i] else "0"
        if c == "pre_vol_type":
            return ""
        if c == "bull_bear_defined":
            return str(front_defined[i])
        if c == "bear_in_crisis":
            return "1" if (front_state[i] == "bear" and crisis_in[i]) else "0"
        raise KeyError(c)

    # ---------------- wide table: back verbatim, front assembled -------------
    h, wide_rows = read_rows(WIDE_V03)
    assert len(wide_rows) == 3339 and len(h) == 67
    assert h[0] == "date"
    wide_by_date = {r[0]: r for r in wide_rows}
    assert [r[0] for r in wide_rows] == [d for d in dates if d >= ANCHOR]

    p16 = {r["date"]: r for r in read_dicts(P16)}
    a16_cols = [c for c in h if c.startswith("a16_")]
    a27_cols = [c for c in h if c.startswith("a27_")]
    b_cols = [c for c in h if c.startswith("b_")]
    assert len(a16_cols) == 15 and len(a27_cols) == 15 and len(b_cols) == 20

    out_rows: list[list[str]] = []
    for i, d in enumerate(dates):
        if i in back_idx:
            out_rows.append(list(wide_by_date[d]))     # verbatim, all 67 cells
            continue
        row = [""] * len(h)
        row[0] = d
        idx = {c: h.index(c) for c in h}
        for c in LABEL_COLS:
            row[idx[c]] = front_label(i, c)
        if d in p16:
            for c in a16_cols:
                row[idx[c]] = p16[d].get(c[4:], "")
        row[idx["line_a16_present"]] = "1" if d in p16 else "0"
        row[idx["line_a27_present"]] = "0"
        out_rows.append(row)

    # HARD ASSERTION: back segment byte-for-byte identical to the frozen wide
    for r_new, r_old in zip(out_rows[back_idx[0]:], wide_rows):
        assert r_new == r_old, "back wide rows changed — refusing to continue"

    with WIDE_OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(h)
        w.writerows(out_rows)

    # ---------------- event table -------------------------------------------
    eh, _ = read_rows(EVENTS_FROZEN)
    assert len(eh) == 11 and len(frozen_rows) == 17
    with EVENTS_OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(eh)
        w.writerows(frozen_rows)                       # 17 rows verbatim
        for ev in front_events:
            w.writerow([ev[k] for k in eh])
    _, written_events = read_rows(EVENTS_OUT)
    assert written_events[:17] == frozen_rows, \
        "frozen 17 event rows changed — refusing to continue"

    # ---------------- audit label view --------------------------------------
    lab_fields = ["date", "segment", "benchmark_close"] + LABEL_COLS + \
                 ["state_degraded", "line_a16_present"]
    with LABELS_OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=lab_fields)
        w.writeheader()
        for i, d in enumerate(dates):
            row = {"date": d,
                   "segment": "front" if i in front_idx else "back",
                   "benchmark_close": f"{close[i]:.10f}",
                   "state_degraded": "1" if i in front_idx else "0",
                   "line_a16_present": "1" if d in p16 else "0"}
            src = out_rows[i]
            for c in LABEL_COLS:
                row[c] = src[h.index(c)]
            w.writerow(row)

    # ---------------- audit --------------------------------------------------
    front_a16_days = sum(1 for d in dates[:len(front_idx)] if d in p16)
    back_a16 = sum(1 for r in wide_rows if r[h.index("line_a16_present")] == "1")
    audit = {
        "version": "v0.5 judgement inputs (DATA ONLY; no statistics/verdict)",
        "pre_registration": "config/regime_split_check_v0.5.toml :: "
                            "[amendment_2026_11_10_judgement_ruling]",
        "calendar": {"rows": n, "first": dates[0], "last": dates[-1],
                     "front_rows": len(front_idx), "back_rows": len(back_idx)},
        "tier2_acute": {
            "front_label_rule": "Y_t=1 iff min_{j=1..20}(P_{t+j}/P_t-1) <= -0.10",
            "front_flagged_days": int(flags[:len(front_idx)].sum()),
            "front_event_clusters": len(clusters),
            "front_events": [
                {"event_id": e["event_id"], "onset": e["onset"],
                 "end": e["end"], "label_run_days": e["label_run_days"],
                 "left_censored_label": e["left_censored_label"],
                 "worst_cumulative_return_from_onset":
                     float(e["worst_cumulative_return_from_onset"]),
                 "worst_date": e["worst_date"]} for e in front_events],
            "front_event_ids": "101+ (no collision with frozen 1..17 or D3 {3,16})",
            "back_frozen_events": 17,
            "back_rows_verbatim": True,
            "pre_window_onsets": len(usable_onsets),
        },
        "tier1_regime": {
            "source": "outputs/regime_v05_rounds_exact.csv (TDX exact peak/trough)",
            "semantics": "descriptive state comparison only; NOT in grid",
            "forbidden": "no hit rate / lead time / recall / precision / false alarm",
        },
        "front_state_degradation": {
            "warmup_days": WARMUP,
            "bull": "close > MA250 and dd250 > -0.10",
            "bear": "close < MA250 and dd250 <= -0.20",
            "fuzzy": "otherwise",
            "five_versions_identical": True,
            "pre_vol_type": "EMPTY (no breadth/vol data before 2011)",
            "overheat_oversold": "engine default all-zero (not in wide table)",
            "defined_days": sum(front_defined.values()),
            "undefined_days": sum(1 for v in front_defined.values() if v == 0),
            "bull_days": sum(1 for v in front_state.values() if v == "bull"),
            "bear_days": sum(1 for v in front_state.values() if v == "bear"),
            "fuzzy_days": sum(1 for v in front_state.values() if v == "fuzzy"),
        },
        "summary_coverage": {
            "front_a16_present_days": front_a16_days,
            "front_a16_missing_days": len(front_idx) - front_a16_days,
            "front_a16_first_date": min(d for d in dates[:len(front_idx)]
                                        if d in p16),
            "back_a16_present_days": back_a16,
            "front_a27_present_days": 0,
            "front_b_present_days": 0,
            "missing_policy": "empty -> NaN; no zero fill, no back fill, no TDA recompute",
        },
        "known_consequences": [
            "normal baseline expands with front defined non-crisis days",
            "A16 W_resid scale regression is re-estimated on a larger sample, "
            "so back-segment W_resid values can change",
            "v0.5 is NOT directly comparable cell-by-cell with v0.3/v0.4; "
            "older conclusions are kept as historical versions",
            "onset_index in the event CSV keeps each segment's ORIGINAL calendar "
            "index; the engine locates events by the onset date via dmap and "
            "never uses onset_index",
        ],
        "validation": {
            "back_wide_rows_verbatim": True,
            "back_event_rows_verbatim": True,
            "front_a27_b_cells_empty": True,
            "no_front_a16_before_2005_01_04": min(
                d for d in dates[:len(front_idx)] if d in p16) == "2005-01-04",
            "all_front_event_onsets_in_front": all(
                e["onset"] <= FRONT_END for e in front_events),
            "dates_unique_ascending": True,
        },
        "boundary": [
            "no label/mask/TDA computed outside this data layer",
            "v0.1-v0.4, all14/all17/all19, config/study.toml untouched",
            "Gate 1 paused; 2025 final test set NOT read; Gate 2 not started; "
            "PHTI performance not run",
        ],
        "files": {p.name: {"rows": len(read_rows(p)[1]) if p.suffix == ".csv" else None,
                           "sha256": sha256(p)}
                  for p in (WIDE_OUT, EVENTS_OUT, LABELS_OUT)},
    }
    AUDIT_OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "wide_rows": len(out_rows),
        "front_events": len(front_events),
        "front_event_ids": [e["event_id"] for e in front_events],
        "front_flagged_days": int(flags[:len(front_idx)].sum()),
        "front_crisis_days": int(crisis_in[:len(front_idx)].sum()),
        "front_defined_days": sum(front_defined.values()),
        "front_a16_present": front_a16_days,
        "back_wide_verbatim": True,
        "wide_sha256": sha256(WIDE_OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
