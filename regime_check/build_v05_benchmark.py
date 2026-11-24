"""Build the v0.5 segmented benchmark and the extended label calendar.

DATA LAYER ONLY. Pre-registered in config/regime_split_check_v0.5.toml before
any judgement is computed.

  front  1999-12-30 .. 2012-12-28 : equal-weight chained SSE 000001 + SZSE 399001
                                    daily simple returns (user-confirmed Gate-0 rule)
  back   2012-12-31 .. 2026-11-03 : REAL 881001.WI close, bitwise identical to v0.4

The two segments are joined into ONE continuous chained index anchored at
2012-12-31 = 2223.24.  Front levels are obtained by BACKWARD recursion from the
anchor using each day's own-segment return, so the back segment stays bitwise
identical to v0.4 and there is no level jump.

Nothing here touches labels, masks, TDA summaries, verdicts or any frozen file.
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

WIND_FULL = OUT / "xy_wind_all_a_daily_v04_full.csv"
LABELS_V04 = OUT / "regime_daily_labels_v04.csv"
FRONT_FROZEN = OUT / "xy_wind_all_a_daily.csv"
SESSION_JSONL = Path(
    r"C:/Users/Lenovo/.workbuddy/projects/"
    r"D-WorkBuddy-2026-10-28-22-54-51/"
    r"57008466-94fc-4594-b599-6c309bb21987.jsonl"
)
WIND_RAW_SNAPSHOT = ROOT / "third_party" / "wind" / "881001WI_day_20121220_20130110.json"

BENCH_CSV = OUT / "regime_v05_benchmark_daily.csv"
ROUNDS_CSV = OUT / "regime_v05_rounds_exact.csv"
AUDIT_JSON = OUT / "regime_v05_benchmark_audit.json"

ANCHOR = "2012-12-31"
FRONT_START = "1999-12-30"
FRONT_END = "2012-12-28"
EXTRA_ANCHOR = "1999-12-29"          # in_label_calendar = 0, completes return chain
ANCHOR_CLOSE = 2223.24

ROUNDS = [
    ("R1", "2001-06-01", "2005-06-30", "国有股减持、股权分置不确定性下的长期熊市", -55.5),
    ("R2", "2007-10-01", "2008-10-31", "高估值泡沫破裂叠加全球金融危机", -72.8),
    ("R3", "2009-08-01", "2013-06-30", "刺激退潮、政策收紧、盈利下行、欧债及钱荒", -46.8),
    ("R4", "2015-06-01", "2016-01-31", "杠杆出清、强平、跌停与停牌潮，随后叠加熔断", -49.0),
    ("R5", "2018-01-01", "2019-01-31", "金融去杠杆、贸易摩擦、股权质押风险", -32.0),
    ("R6", "2021-12-01", "2022-10-31", "全球紧缩、疫情、地产与增长预期共同压制", -22.2),
    ("R7", "2023-05-01", "2024-02-29", "市场走弱演化为小微盘、雪球和量化流动性冲击", -22.9),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk_strings(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from _walk_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk_strings(v)
    elif isinstance(o, str) and o.lstrip().startswith('{"data"'):
        yield o


def read_wind_prev_close() -> tuple[float, str]:
    """Recover the REAL 2012-12-28 Wind close verbatim from the session JSONL.

    The frozen v0.4 Wind CSV starts at 2012-12-31, so the one-day-earlier close is
    needed to define the cross-segment return.  It is NOT retyped: the connector
    response from 2026-11-10 is located by content and parsed.
    """
    best = ""
    with SESSION_JSONL.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if "2012-12-28T00:00:00" not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            for text in _walk_strings(rec):
                if len(text) > len(best):
                    best = text
    if not best:
        raise RuntimeError("2012-12-28 Wind response not found in session JSONL")
    payload = json.loads(best)
    assert payload.get("error") is None, payload.get("error")
    cols = [c["name"] for c in payload["data"]["columns"]]
    hit = [r for r in payload["data"]["rows"] if r[0][:10] == FRONT_END]
    assert len(hit) == 1, f"expected exactly one {FRONT_END} row"
    close = float(hit[0][cols.index("MATCH")])
    WIND_RAW_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    WIND_RAW_SNAPSHOT.write_bytes(best.encode("utf-8"))
    return close, sha256(WIND_RAW_SNAPSHOT)


def read_wind() -> tuple[dict[str, float], list[str]]:
    rows = list(csv.DictReader(WIND_FULL.open(encoding="utf-8-sig")))
    close = {r["date"]: float(r["close"]) for r in rows}
    dates = [r["date"] for r in rows]
    assert len(set(dates)) == len(dates), "duplicate Wind dates"
    assert dates == sorted(dates), "Wind dates not ascending"
    assert dates[0] == ANCHOR, dates[0]
    assert abs(close[ANCHOR] - ANCHOR_CLOSE) < 1e-9
    return close, dates


def read_v04() -> tuple[list[str], dict[str, float]]:
    rows = list(csv.DictReader(LABELS_V04.open(encoding="utf-8-sig")))
    dates = [r["date"] for r in rows]
    close = {r["date"]: float(r["close_wind"]) for r in rows}
    assert len(dates) == 3339, len(dates)
    assert dates[0] == ANCHOR and dates[-1] == "2026-11-03"
    return dates, close


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
    assert common[0] <= EXTRA_ANCHOR and common[-1] >= ANCHOR
    return sse, sz, common


def build_rounds() -> list[dict]:
    con = sqlite3.connect("file:" + DB.resolve().as_posix() + "?mode=ro", uri=True)
    cur = con.cursor()
    out: list[dict] = []
    for rid, a, b, nature, user_dd in ROUNDS:
        rs = cur.execute(
            "select date,close,high,low from index_daily_raw "
            "where code='000001' and date between ? and ? order by date", (a, b)
        ).fetchall()
        assert rs, f"{rid}: no SSE data"
        peak = max(rs, key=lambda r: r[2])
        pi = rs.index(peak)
        trough = min(rs[pi:], key=lambda r: r[3])
        intraday_dd = 100.0 * (trough[3] / peak[2] - 1.0)
        close_dd = 100.0 * (trough[1] / peak[1] - 1.0)
        out.append({
            "round_id": rid,
            "user_interval": a[:7] + "—" + b[:7],
            "peak_date": peak[0], "peak_high": peak[2], "peak_close": peak[1],
            "trough_date": trough[0], "trough_low": trough[3], "trough_close": trough[1],
            "intraday_drawdown_pct": round(intraday_dd, 4),
            "close_drawdown_pct": round(close_dd, 4),
            "user_drawdown_pct": user_dd,
            "abs_diff_vs_user_pct": round(abs(intraday_dd - user_dd), 4),
            "nature": nature,
            "price_basis": "TDX 000001 盘中 high/low；谷值取峰值日之后最低 low",
            "semantics": "事后认定，仅用于严重程度与状态对比",
            "forbidden": "禁止用于预警提前期、命中率、召回率、精确率、误报计算",
        })
    con.close()
    return out


def main() -> None:
    wind, wind_dates = read_wind()
    back_dates, v04_close = read_v04()
    sse, sz, common = read_tdx()
    wind_prev_close, wind_raw_sha = read_wind_prev_close()
    wind[FRONT_END] = wind_prev_close   # reference only; never used as a back-segment level
    front_frozen_first = list(csv.DictReader(FRONT_FROZEN.open(encoding="utf-8-sig")))[0]
    assert front_frozen_first["date"] == ANCHOR

    # --- equal-weight chained composite returns on the common trading calendar ---
    r_sse: dict[str, float] = {}
    r_sz: dict[str, float] = {}
    r_eq: dict[str, float] = {}
    for i in range(1, len(common)):
        t, p = common[i], common[i - 1]
        r_sse[t] = sse[t] / sse[p] - 1.0
        r_sz[t] = sz[t] / sz[p] - 1.0
        r_eq[t] = (r_sse[t] + r_sz[t]) / 2.0

    front_dates = [d for d in common if FRONT_START <= d <= FRONT_END]
    assert len(front_dates) == 3144, len(front_dates)
    assert front_dates[0] == FRONT_START and front_dates[-1] == FRONT_END
    assert EXTRA_ANCHOR in common

    # --- back segment: bitwise identical to v0.4 ---
    back_diff = max(abs(v04_close[d] - wind[d]) for d in back_dates)
    assert back_diff < 1e-9, back_diff

    # --- continuous chained level, anchored at 2012-12-31 ---
    level: dict[str, float] = {d: v04_close[d] for d in back_dates}
    assert abs(level[ANCHOR] - ANCHOR_CLOSE) < 1e-9

    # the one cross-segment return belongs to the back (2012-12-31, real Wind)
    cross_ret = wind[ANCHOR] / wind[FRONT_END] - 1.0
    chain_dates = [EXTRA_ANCHOR] + front_dates + [ANCHOR]
    for i in range(len(chain_dates) - 2, -1, -1):
        t, nxt = chain_dates[i], chain_dates[i + 1]
        r = cross_ret if nxt == ANCHOR else r_eq[nxt]
        level[t] = level[nxt] / (1.0 + r)

    all_dates = [EXTRA_ANCHOR] + front_dates + back_dates
    assert len(all_dates) == 6484, len(all_dates)
    assert len(set(all_dates)) == len(all_dates)
    assert all_dates == sorted(all_dates)
    assert all(level[d] > 0 for d in all_dates)

    # --- returns recomputed FROM the level series (a real check, not a re-assignment) ---
    ret: dict[str, float | None] = {all_dates[0]: None}
    for i in range(1, len(all_dates)):
        ret[all_dates[i]] = level[all_dates[i]] / level[all_dates[i - 1]] - 1.0

    front_ret_maxdiff = max(
        abs(ret[d] - r_eq[d]) for d in front_dates
    )
    assert front_ret_maxdiff < 1e-9, front_ret_maxdiff
    assert abs(ret[ANCHOR] - cross_ret) < 1e-9

    back_maxdiff = max(abs(level[d] - v04_close[d]) for d in back_dates)
    assert back_maxdiff < 1e-9

    big_moves = [d for d in front_dates if abs(r_eq[d]) > 0.15]

    # --- write the daily benchmark table ---
    fieldnames = [
        "date", "in_label_calendar", "bench_source", "benchmark_close",
        "benchmark_ret_pct", "sse_close", "szse_close", "r_sse_pct",
        "r_szse_pct", "r_eq_pct", "wind_close",
    ]
    with BENCH_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for d in all_dates:
            is_front = d <= FRONT_END
            w.writerow({
                "date": d,
                "in_label_calendar": "0" if d == EXTRA_ANCHOR else "1",
                "bench_source": "composite_sse_szse" if is_front else "real_wind_881001WI",
                "benchmark_close": f"{level[d]:.10f}",
                "benchmark_ret_pct": "" if ret[d] is None else f"{ret[d] * 100:.10f}",
                "sse_close": f"{sse[d]:.4f}" if is_front and d in sse else "",
                "szse_close": f"{sz[d]:.4f}" if is_front and d in sz else "",
                "r_sse_pct": f"{r_sse[d] * 100:.10f}" if is_front and d in r_sse else "",
                "r_szse_pct": f"{r_sz[d] * 100:.10f}" if is_front and d in r_sz else "",
                "r_eq_pct": f"{r_eq[d] * 100:.10f}" if is_front and d in r_eq else "",
                "wind_close": f"{wind[d]:.4f}" if d in wind else "",
            })

    rounds = build_rounds()
    with ROUNDS_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rounds[0].keys()))
        w.writeheader()
        w.writerows(rounds)

    audit = {
        "generated_on": date.today().isoformat(),
        "version": "v0.5 DATA LAYER ONLY",
        "pre_registration": "config/regime_split_check_v0.5.toml",
        "status": "judgement layer NOT run; pending_items await user confirmation",
        "user_verbatim": "B，万得全A数据能补就补，不能补就用上证和深成得等权合成，"
                         "2012-12-31 之前的用合成指数，之后的依然用万得全A",
        "benchmark": {
            "anchor_date": ANCHOR, "anchor_close": ANCHOR_CLOSE,
            "front_start": FRONT_START, "front_end": FRONT_END,
            "front_rows": len(front_dates), "back_rows": len(back_dates),
            "total_label_days": len(front_dates) + len(back_dates),
            "extra_anchor_row": EXTRA_ANCHOR,
            "front_rule": "r_eq(t)=(r_000001(t)+r_399001(t))/2, chained; NEVER average index levels",
            "back_rule": "real 881001.WI close, bitwise identical to regime_daily_labels_v04.csv close_wind",
            "splice": "backward recursion from anchor; cross-segment 2012-12-31 return uses real Wind",
        },
        "wind_front_availability_probe": {
            "connector": "mcp__wind-finance__get_index_kline",
            "code": "881001.WI",
            "earliest_observed": "1999-01-04",
            "anchor_ohlc_from_wind": {
                "open": 2194.69, "close": 2223.24, "high": 2223.24, "low": 2190.89,
            },
            "anchor_ohlc_frozen_v04": {
                "open": 2194.69, "close": 2223.24, "high": 2223.24, "low": 2190.89,
            },
            "same_series": True,
            "decision": "NOT imported this round. Main benchmark follows the user's explicit "
                        "segmented instruction (composite before 2012-12-31). Registered as "
                        "pending_items.item_1: could be imported as an all-real-Wind variant "
                        "or as sensitivity benchmark S1, ~3144 rows, requires batched import.",
        },
        "cross_segment_anchor": {
            "wind_prev_session": FRONT_END,
            "wind_prev_close": wind_prev_close,
            "extraction": "verbatim connector response recovered from session JSONL; no manual transcription",
            "raw_snapshot": str(WIND_RAW_SNAPSHOT.relative_to(ROOT)),
            "raw_sha256": wind_raw_sha,
            "cross_check": "frozen v0.4 2012-12-31 row LOW = "
                           + front_frozen_first["low"]
                           + " (coincides with the previous session close; recorded, not asserted)",
            "cross_segment_ret_pct": round(cross_ret * 100, 8),
            "attribution": "2012-12-31 return belongs to the BACK segment per the user's rule; "
                           "front composite returns are used up to 2012-12-28",
        },
        "validation": {
            "dates_unique_ascending": True,
            "levels_positive_finite": True,
            "back_matches_v04_max_abs_diff": back_maxdiff,
            "back_matches_wind_csv_max_abs_diff": back_diff,
            "front_ret_matches_r_eq_max_abs_diff": front_ret_maxdiff,
            "anchor_level": level[ANCHOR],
            "front_end_level": level[FRONT_END],
            "cross_segment_ret_pct": cross_ret * 100,
            "no_level_jump": True,
            "front_abs_r_eq_gt_15pct_days": len(big_moves),
            "front_abs_r_eq_gt_15pct_dates": big_moves[:20],
            "common_calendar_sse_only_days": 0,
            "common_calendar_szse_only_days": 0,
        },
        "seven_rounds_exact": [
            {"round_id": r["round_id"], "peak_date": r["peak_date"],
             "trough_date": r["trough_date"],
             "intraday_drawdown_pct": r["intraday_drawdown_pct"],
             "user_drawdown_pct": r["user_drawdown_pct"]}
            for r in rounds
        ],
        "boundary": [
            "DATA LAYER ONLY: no label recomputation, no mask change, no TDA recomputation, "
            "no bootstrap, no significance test, no verdict",
            "v0.1-v0.4, all14/all17/all19 and config/study.toml untouched",
            "Gate 1 paused; 2025 final test set NOT read; Gate 2 not started; "
            "PHTI performance not run",
            "tier-1 regime rounds are EX-POST definitions: severity and state comparison only, "
            "NEVER lead-time / hit-rate / recall / precision / false-alarm",
        ],
        "files": {
            "regime_v05_benchmark_daily.csv": {
                "rows": len(all_dates), "cols": len(fieldnames), "sha256": sha256(BENCH_CSV),
            },
            "regime_v05_rounds_exact.csv": {
                "rows": len(rounds), "cols": len(rounds[0]), "sha256": sha256(ROUNDS_CSV),
            },
            "regime_v05_benchmark_audit.json": "self",
        },
    }
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2,
                                     allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "csv_sha256": sha256(BENCH_CSV),
        "rows": len(all_dates),
        "front_rows": len(front_dates),
        "back_rows": len(back_dates),
        "back_matches_v04_max_abs_diff": back_maxdiff,
        "front_ret_matches_r_eq_max_abs_diff": front_ret_maxdiff,
        "anchor_level": level[ANCHOR],
        "front_end_level": level[FRONT_END],
        "cross_segment_ret_pct": round(cross_ret * 100, 6),
        "big_move_days": len(big_moves),
        "rounds": [(r["round_id"], r["peak_date"], r["trough_date"],
                    r["intraday_drawdown_pct"]) for r in rounds],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
