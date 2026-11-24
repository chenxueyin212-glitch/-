"""Rebuild the v0.5 benchmark as ONE continuous REAL 881001.WI series.

Registered BEFORE any judgement is computed, in
config/regime_split_check_v0.5.toml :: [amendment_2026_11_10_true_wind].

User clarification: "补不到才退而用合成" — the Wind front segment IS
obtainable and is the SAME series as the frozen v0.4 back segment, so the
equal-weight SSE+SZSE composite is demoted to a SUPERSEDED sensitivity
reference (S1) and is no longer the benchmark.

  front  1999-12-30 .. 2012-12-28 : real Wind 881001.WI close (base 1000.00)
  back   2012-12-31 .. 2026-11-03 : real Wind 881001.WI close, bitwise v0.4

No backward recursion, no rescaling, no fabricated anchor row.  The first
front day has NO prior close, so its return is intentionally empty.

DATA LAYER ONLY: no labels, no masks, no TDA, no verdicts, no scoring.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
DB = ROOT.parent / "a_share_pit" / "tdx_central.db"

FRONT_CSV = OUT / "xy_wind_all_a_front_19991230_20121228.csv"
FRONT_AUDIT = OUT / "xy_wind_all_a_front_audit.json"
WIND_FULL = OUT / "xy_wind_all_a_daily_v04_full.csv"
LABELS_V04 = OUT / "regime_daily_labels_v04.csv"

BENCH_CSV = OUT / "regime_v05_benchmark_daily.csv"
AUDIT_JSON = OUT / "regime_v05_benchmark_audit.json"
ROUNDS_CSV = OUT / "regime_v05_rounds_exact.csv"
SYNTH_CSV = OUT / "regime_v05_benchmark_daily_synthetic_superseded.csv"
SYNTH_AUDIT = OUT / "regime_v05_benchmark_audit_synthetic_superseded.json"

START, END = "1999-12-30", "2012-12-28"
ANCHOR = "2012-12-31"
BASE_CLOSE, PREV_CLOSE, ANCHOR_CLOSE = 1000.00, 2190.89, 2223.24
BACK_END = "2026-11-03"
SOURCE_TAG = "real_wind_881001WI"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_front() -> dict[str, float]:
    rows = list(csv.DictReader(FRONT_CSV.open(encoding="utf-8-sig")))
    close = {r["date"]: float(r["close"]) for r in rows}
    assert len(close) == len(rows) == 3144
    assert min(close) == START and max(close) == END
    assert abs(close[START] - BASE_CLOSE) < 1e-9
    assert abs(close[END] - PREV_CLOSE) < 1e-9
    return close


def read_back() -> tuple[list[str], dict[str, float], dict[str, float]]:
    labels = list(csv.DictReader(LABELS_V04.open(encoding="utf-8-sig")))
    dates = [r["date"] for r in labels]
    v04 = {r["date"]: float(r["close_wind"]) for r in labels}
    assert len(dates) == 3339
    assert dates[0] == ANCHOR and dates[-1] == BACK_END
    assert abs(v04[ANCHOR] - ANCHOR_CLOSE) < 1e-9
    wind = {r["date"]: float(r["close"])
            for r in csv.DictReader(WIND_FULL.open(encoding="utf-8-sig"))}
    return dates, v04, wind


def read_tdx() -> tuple[dict[str, float], dict[str, float], list[str]]:
    con = sqlite3.connect("file:" + DB.resolve().as_posix() + "?mode=ro", uri=True)
    cur = con.cursor()
    raw = cur.execute(
        "select code,date,close from index_daily_raw "
        "where code in ('000001','399001') and date between '1999-12-01' and '2012-12-31' "
        "order by date,code"
    ).fetchall()
    con.close()
    sse: dict[str, float] = {}
    sz: dict[str, float] = {}
    for code, d, c in raw:
        (sse if code == "000001" else sz)[d] = float(c)
    common = sorted(set(sse) & set(sz))
    return sse, sz, common


def main() -> None:
    front = read_front()
    back_dates, v04_close, wind_full = read_back()
    sse, sz, common = read_tdx()

    front_dates = sorted(front)
    assert set(front_dates) == {d for d in common if START <= d <= END}
    assert len(front_dates) == 3144

    # --- the ONE continuous real Wind level series ---
    level: dict[str, float] = dict(front)
    level.update({d: v04_close[d] for d in back_dates})
    all_dates = front_dates + back_dates
    assert len(all_dates) == 6483
    assert len(set(all_dates)) == len(all_dates)
    assert all_dates == sorted(all_dates)
    assert all(level[d] > 0 for d in all_dates)

    # back segment must be bitwise identical to both frozen sources
    back_v04_diff = max(abs(level[d] - v04_close[d]) for d in back_dates)
    back_wind_diff = max(abs(level[d] - wind_full[d]) for d in back_dates)
    assert back_v04_diff < 1e-9 and back_wind_diff < 1e-9

    # --- returns recomputed FROM the level series (a real check) ---
    ret: dict[str, float | None] = {all_dates[0]: None}
    for i in range(1, len(all_dates)):
        ret[all_dates[i]] = level[all_dates[i]] / level[all_dates[i - 1]] - 1.0
    front_ret_maxdiff = 0.0
    for i in range(1, len(front_dates)):
        t, p = front_dates[i], front_dates[i - 1]
        front_ret_maxdiff = max(front_ret_maxdiff,
                                abs(ret[t] - (front[t] / front[p] - 1.0)))
    assert front_ret_maxdiff < 1e-9
    cross_ret = ret[ANCHOR]
    assert abs(cross_ret * 100 - 1.47656888) < 1e-6, cross_ret
    big_moves = [d for d in all_dates if ret[d] is not None and abs(ret[d]) > 0.15]
    assert not big_moves, big_moves[:10]

    # --- S1 sensitivity reference columns (NOT the benchmark) ---
    r_sse: dict[str, float] = {}
    r_sz: dict[str, float] = {}
    r_eq: dict[str, float] = {}
    for i in range(1, len(common)):
        t, p = common[i], common[i - 1]
        r_sse[t] = sse[t] / sse[p] - 1.0
        r_sz[t] = sz[t] / sz[p] - 1.0
        r_eq[t] = (r_sse[t] + r_sz[t]) / 2.0

    fieldnames = [
        "date", "in_label_calendar", "bench_source", "benchmark_close",
        "benchmark_ret_pct", "sse_close", "szse_close", "r_sse_pct",
        "r_szse_pct", "r_eq_pct", "wind_close",
    ]
    with BENCH_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for d in all_dates:
            is_front = d <= END
            w.writerow({
                "date": d,
                "in_label_calendar": "1",
                "bench_source": SOURCE_TAG,
                "benchmark_close": f"{level[d]:.10f}",
                "benchmark_ret_pct": "" if ret[d] is None else f"{ret[d] * 100:.10f}",
                "sse_close": f"{sse[d]:.4f}" if is_front and d in sse else "",
                "szse_close": f"{sz[d]:.4f}" if is_front and d in sz else "",
                "r_sse_pct": f"{r_sse[d] * 100:.10f}" if is_front and d in r_sse else "",
                "r_szse_pct": f"{r_sz[d] * 100:.10f}" if is_front and d in r_sz else "",
                "r_eq_pct": f"{r_eq[d] * 100:.10f}" if is_front and d in r_eq else "",
                "wind_close": f"{level[d]:.4f}",
            })

    # --- round-trip: the WRITTEN 10-dp values must reproduce the returns ---
    written = list(csv.DictReader(BENCH_CSV.open(encoding="utf-8-sig")))
    assert len(written) == len(all_dates)
    assert all(r["bench_source"] == SOURCE_TAG for r in written)
    assert written[0]["benchmark_ret_pct"] == ""
    roundtrip_maxdiff = 0.0
    for i in range(1, len(written)):
        prev, cur = written[i - 1], written[i]
        implied = float(cur["benchmark_close"]) / float(prev["benchmark_close"]) - 1.0
        roundtrip_maxdiff = max(roundtrip_maxdiff,
                                abs(float(cur["benchmark_ret_pct"]) / 100.0 - implied))
    assert roundtrip_maxdiff < 1e-9, roundtrip_maxdiff

    # --- S1 input-definition difference: DESCRIPTIVE ONLY, not a test/score ---
    s1_diffs = [abs(ret[d] - r_eq[d]) * 100.0
                for d in front_dates[1:] if d in r_eq]
    s1_sorted = sorted(s1_diffs)
    s1_desc = {
        "n_days": len(s1_diffs),
        "mean_abs_diff_pct": round(sum(s1_diffs) / len(s1_diffs), 6),
        "median_abs_diff_pct": round(s1_sorted[len(s1_sorted) // 2], 6),
        "max_abs_diff_pct": round(max(s1_diffs), 6),
        "days_gt_1pct": sum(x > 1.0 for x in s1_diffs),
        "days_gt_2pct": sum(x > 2.0 for x in s1_diffs),
        "note": "pure input-definition difference between the SUPERSEDED composite "
                "and the TRUE-WIND front returns; NOT a significance test, IC, "
                "performance metric or any model evaluation",
    }

    front_audit = json.loads(FRONT_AUDIT.read_text(encoding="utf-8"))
    audit = {
        "generated_on": date.today().isoformat(),
        "version": "v0.5 DATA LAYER — TRUE WIND (amendment_2026_11_10_true_wind)",
        "pre_registration": "config/regime_split_check_v0.5.toml",
        "status": "judgement layer NOT run; item_2 / item_3 await user confirmation",
        "user_verbatim": "补不到才退而用合成",
        "decision": "Wind 前段可得且与 v0.4 后段同一序列 → 主基准改为全程单一真 881001.WI；"
                    "合成口径降级为 SUPERSEDED 敏感性对照 S1，文件保留不删除",
        "benchmark": {
            "source": SOURCE_TAG,
            "front_start": START, "front_end": END,
            "back_start": ANCHOR, "back_end": BACK_END,
            "front_rows": len(front_dates), "back_rows": len(back_dates),
            "total_label_days": len(all_dates),
            "extra_anchor_row": 0,
            "front_base_close": front[START],
            "front_end_close": front[END],
            "anchor_close": level[ANCHOR],
            "front_rule": "real Wind close, used as-is; NO backward recursion, NO rescaling",
            "back_rule": "real Wind close, bitwise identical to regime_daily_labels_v04.csv close_wind",
            "splice": "same series, natural continuation; 2012-12-28 2190.89 -> 2012-12-31 2223.24",
            "first_front_day_ret": "EMPTY (Wind base day has no prior close); not zero-filled, not back-filled",
            "reference_columns": "sse_close/szse_close/r_sse_pct/r_szse_pct/r_eq_pct are S1 composite "
                                 "sensitivity reference ONLY, NOT the benchmark",
        },
        "wind_front_import": {
            "raw_response_files": len(front_audit["raw_files"]),
            "overlap_rows_value_checked": front_audit["overlap_rows_value_checked"],
            "calendar_equal_to_tdx_common": front_audit["calendar_equal_to_tdx_common"],
            "provenance": front_audit["provenance"],
            "front_csv_sha256": front_audit["files"][FRONT_CSV.name]["sha256"],
        },
        "superseded_synthetic_variant": {
            "status": "SUPERSEDED — kept as sensitivity S1, never deleted",
            "benchmark_csv": SYNTH_CSV.name if SYNTH_CSV.exists() else None,
            "benchmark_csv_sha256": sha256(SYNTH_CSV) if SYNTH_CSV.exists() else None,
            "audit_json": SYNTH_AUDIT.name if SYNTH_AUDIT.exists() else None,
            "note": "the original composite-front data layer was correct engineering but "
                    "implemented a misreading of the user's conditional instruction",
        },
        "composite_vs_true_wind_front_ret_diff": s1_desc,
        "validation": {
            "dates_unique_ascending": True,
            "levels_positive_finite": all(level[d] > 0 for d in all_dates),
            "front_rows": len(front_dates),
            "back_rows": len(back_dates),
            "back_matches_v04_max_abs_diff": back_v04_diff,
            "back_matches_wind_csv_max_abs_diff": back_wind_diff,
            "front_ret_matches_real_wind_max_abs_diff": front_ret_maxdiff,
            "csv_roundtrip_ret_max_abs_diff": roundtrip_maxdiff,
            "cross_segment_ret_pct": cross_ret * 100,
            "no_level_jump": True,
            "bench_source_single_value": True,
            "first_day_ret_empty": ret[all_dates[0]] is None,
            "abs_daily_ret_gt_15pct_days": len(big_moves),
        },
        "seven_rounds": {
            "file": ROUNDS_CSV.name,
            "sha256": sha256(ROUNDS_CSV),
            "note": "computed from TDX 000001 intraday high/low only; independent of benchmark choice, "
                    "therefore UNCHANGED by this amendment",
        },
        "boundary": [
            "DATA LAYER ONLY: no label recomputation, no mask change, no TDA recomputation, "
            "no bootstrap, no significance test, no verdict",
            "v0.1-v0.4, all14/all17/all19 and config/study.toml untouched",
            "Gate 1 paused; 2025 final test set NOT read; Gate 2 not started; PHTI performance not run",
            "tier-1 regime rounds are EX-POST definitions: severity and state comparison only, "
            "NEVER lead-time / hit-rate / recall / precision / false-alarm",
            "no IC, Sharpe, PR-AUC, position sizing, threshold selection, hit rate or lead time",
        ],
        "files": {
            BENCH_CSV.name: {"rows": len(all_dates), "cols": len(fieldnames),
                             "sha256": sha256(BENCH_CSV)},
            ROUNDS_CSV.name: {"sha256": sha256(ROUNDS_CSV)},
            AUDIT_JSON.name: "self",
        },
    }
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2,
                                     allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "csv_sha256": sha256(BENCH_CSV),
        "rows": len(all_dates),
        "front_rows": len(front_dates),
        "back_rows": len(back_dates),
        "bench_source": SOURCE_TAG,
        "front_base_close": front[START],
        "front_end_close": front[END],
        "anchor_close": level[ANCHOR],
        "back_matches_v04_max_abs_diff": back_v04_diff,
        "front_ret_matches_real_wind_max_abs_diff": front_ret_maxdiff,
        "cross_segment_ret_pct": round(cross_ret * 100, 8),
        "first_day_ret_empty": ret[all_dates[0]] is None,
        "big_move_days": len(big_moves),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
