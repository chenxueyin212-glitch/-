"""把已保存的WeStock原始返回导入独立补充库，不修改申万公开数据库。

只接受本项目保存的原始JSON；代码、日期和数值不由手工转录。
后续特征计算仍以申万公开正值为主，只在公开收盘缺失时采用补充值。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
PUBLIC_DB = OUT / "xy_sw2014_corrected_data.db"
SUPPLEMENT_DB = OUT / "xy_sw2014_supplement.db"
AUDIT_OUT = OUT / "xy_sw2014_supplement_audit.json"
DEFAULT_SNAPSHOT = ROOT / "third_party" / "westock" / "pt01801193_day_20121101_20211210.json"
SCHEMA = """
CREATE TABLE IF NOT EXISTS supplement_daily(
 code TEXT NOT NULL,date TEXT NOT NULL,open REAL,high REAL,low REAL,close REAL,
 volume REAL,amount REAL,source TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
 PRIMARY KEY(code,date));
CREATE TABLE IF NOT EXISTS supplement_meta(
 code TEXT PRIMARY KEY,rows INTEGER NOT NULL,first_date TEXT NOT NULL,last_date TEXT NOT NULL,
 query_start TEXT NOT NULL,query_end TEXT NOT NULL,source TEXT NOT NULL,
 snapshot_sha256 TEXT NOT NULL,imported_at TEXT NOT NULL);
"""


def positive_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--code", default="801193")
    parser.add_argument("--query-start", default="2012-11-01")
    parser.add_argument("--query-end", default="2021-12-10")
    args = parser.parse_args()
    raw = args.snapshot.read_bytes()
    snapshot_hash = hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw.decode("utf-8"))
    if not payload.get("ok") or not isinstance(payload.get("data"), dict):
        raise ValueError("不是有效的单标的WeStock原始返回")
    nodes = payload["data"].get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("原始返回没有K线节点")
    expected_symbol = "pt01" + args.code
    source = f"WeStock MCP data_kline {expected_symbol}; saved raw connector output"
    records = []
    for node in nodes:
        date = str(node.get("date") or "")
        close = positive_number(node.get("last"))
        if len(date) != 10 or close is None:
            raise ValueError(f"无效日期或非正收盘: {node!r}")
        records.append((args.code, date, positive_number(node.get("open")),
                        positive_number(node.get("high")), positive_number(node.get("low")), close,
                        float(node.get("volume") or 0), float(node.get("amount") or 0),
                        source, snapshot_hash))
    records.sort(key=lambda row: row[1])
    dates = [row[1] for row in records]
    if len(dates) != len(set(dates)):
        raise ValueError("原始返回存在重复日期")
    if dates[0] < args.query_start or dates[-1] > args.query_end:
        raise ValueError("原始返回超出登记查询区间")

    public = sqlite3.connect(f"file:{PUBLIC_DB}?mode=ro", uri=True)
    public_close = dict(public.execute(
        "SELECT date,close FROM sw2014_daily WHERE code=?", (args.code,)))
    public.close()
    comparisons = []
    for row in records:
        date, close = row[1], row[5]
        old = public_close.get(date)
        if old is not None and old > 0:
            comparisons.append({"date": date, "public": float(old), "supplement": close,
                                "abs_diff": abs(float(old)-close),
                                "rel_diff": abs(float(old)-close)/abs(close)})
    exact_mismatches = [r for r in comparisons if not math.isclose(
        r["public"], r["supplement"], rel_tol=1e-9, abs_tol=1e-8)]
    # 两个公开前端都按0.01点展示；仅允许这一量级的显示精度差，保留申万公开值。
    mismatches = [r for r in exact_mismatches if r["abs_diff"] > 0.0100001]
    rounding_differences = [r for r in exact_mismatches if r["abs_diff"] <= 0.0100001]
    fill_dates = [row[1] for row in records
                  if public_close.get(row[1]) is None or public_close[row[1]] <= 0]

    con = sqlite3.connect(SUPPLEMENT_DB, timeout=120)
    con.executescript(SCHEMA)
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    with con:
        con.execute("DELETE FROM supplement_daily WHERE code=?", (args.code,))
        con.executemany("INSERT INTO supplement_daily VALUES(?,?,?,?,?,?,?,?,?,?)", records)
        con.execute("INSERT OR REPLACE INTO supplement_meta VALUES(?,?,?,?,?,?,?,?,?)",
                    (args.code, len(records), dates[0], dates[-1], args.query_start,
                     args.query_end, source, snapshot_hash, now))
    duplicate_keys = con.execute(
        "SELECT COUNT(*) FROM (SELECT code,date FROM supplement_daily "
        "GROUP BY code,date HAVING COUNT(*)>1)").fetchone()[0]
    con.close()
    audit = {
        "generated_at": now, "code": args.code, "symbol": expected_symbol,
        "source": source, "snapshot": str(args.snapshot), "snapshot_sha256": snapshot_hash,
        "query": {"period": "day", "start": args.query_start, "end": args.query_end,
                  "limit": 4000, "fq": "unadjusted"},
        "rows": len(records), "actual_range": [dates[0], dates[-1]],
        "duplicate_keys": duplicate_keys,
        "public_overlap": {
            "days": len(comparisons), "mismatch_days": len(mismatches),
            "rounding_difference_days": len(rounding_differences),
            "rounding_tolerance_index_points": 0.0100001,
            "max_abs_diff": max((r["abs_diff"] for r in comparisons), default=None),
            "max_rel_diff": max((r["rel_diff"] for r in comparisons), default=None),
            "mismatch_examples": mismatches[:20],
            "rounding_examples": rounding_differences[:20],
        },
        "fillable_public_missing_or_nonpositive_days": len(fill_dates),
        "fillable_range": [min(fill_dates), max(fill_dates)] if fill_dates else None,
        "merge_rule": "保留申万公开正收盘；仅在公开收盘缺失或非正时采用补充值，不插值",
        "known_limits": ["该源实际只覆盖2016-12-12至2021-12-10，不能补齐2015年缺口",
                         "第三方行情不是兴业Wind原始导出；来源差异必须保留"],
    }
    AUDIT_OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False),
                           encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2), flush=True)
    if duplicate_keys or mismatches:
        raise RuntimeError("补充行情验收失败，详见审计JSON")


if __name__ == "__main__":
    main()
