"""下载申万二级行业与申万A指代理基准，保存为独立只读研究快照。"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sqlite3
import ssl
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE_CSV = ROOT / "outputs" / "xy_sw2_code_list_20261107.csv"
DB = ROOT / "outputs" / "xy_replication_data.db"
AUDIT = ROOT / "outputs" / "xy_data_audit.json"
CENTRAL = ROOT.parent / "a_share_pit" / "tdx_central.db"
API = "https://www.swsresearch.com/institute-sw/api/index_publish/trend/"
CTX = ssl._create_unverified_context()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS sw2_daily(
 code TEXT NOT NULL,date TEXT NOT NULL,open REAL,high REAL,low REAL,close REAL,
 volume REAL,amount REAL,source TEXT NOT NULL,fetched_at TEXT NOT NULL,
 PRIMARY KEY(code,date));
CREATE TABLE IF NOT EXISTS sw2_meta(
 code TEXT PRIMARY KEY,name TEXT NOT NULL,parent TEXT,rows INTEGER,first_date TEXT,
 last_date TEXT,fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS benchmark_daily(
 code TEXT NOT NULL,date TEXT NOT NULL,open REAL,high REAL,low REAL,close REAL,
 source TEXT NOT NULL,PRIMARY KEY(code,date));
"""


def number(value):
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def fetch(code: str, retries: int = 4) -> list[dict]:
    url = f"{API}?swindexcode={code}&period=DAY"
    last = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=30, context=CTX) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            rows = payload.get("data") or []
            if not isinstance(rows, list) or not rows:
                raise ValueError("empty or unexpected payload")
            return rows
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{code}: {last!r}")


def main() -> None:
    with CODE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        codes = list(csv.DictReader(handle))
    if len(codes) != 131:
        raise ValueError(f"申万二级代码快照数量异常: {len(codes)}")
    con = sqlite3.connect(DB, timeout=120)
    con.executescript(SCHEMA)
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    results = []
    for i, item in enumerate(codes, 1):
        code = item["行业代码"].split(".")[0]
        name = item["行业名称"]
        try:
            rows = fetch(code)
            records = []
            for row in rows:
                date = str(row.get("bargaindate") or "")[:10].replace("/", "-")
                if len(date) != 10:
                    continue
                records.append((code, date, number(row.get("openindex")),
                                number(row.get("maxindex")), number(row.get("minindex")),
                                number(row.get("closeindex")), number(row.get("bargainamount")),
                                number(row.get("bargainsum")), API, now))
            if not records:
                raise ValueError("no valid dated rows")
            with con:
                con.executemany("INSERT OR REPLACE INTO sw2_daily VALUES(?,?,?,?,?,?,?,?,?,?)", records)
                con.execute("INSERT OR REPLACE INTO sw2_meta VALUES(?,?,?,?,?,?,?)",
                            (code, name, item["上级行业"], len(records), records[0][1],
                             records[-1][1], now))
            result = {"code": code, "name": name, "rows": len(records),
                      "first": records[0][1], "last": records[-1][1]}
        except Exception as exc:  # noqa: BLE001
            result = {"code": code, "name": name, "error": repr(exc)}
        results.append(result)
        print(f"[{i}/{len(codes)}] {result}", flush=True)
        time.sleep(0.35)
    central = sqlite3.connect(f"file:{CENTRAL}?mode=ro", uri=True)
    benchmark = central.execute(
        "SELECT date,open,high,low,close FROM sw_industry_daily WHERE code='801003' ORDER BY date"
    ).fetchall()
    central.close()
    with con:
        con.executemany("INSERT OR REPLACE INTO benchmark_daily VALUES('801003',?,?,?,?,?,'swsresearch via tdx_central.db')", benchmark)
    quality = {
        "codes_requested": len(codes), "codes_succeeded": sum("error" not in x for x in results),
        "codes_failed": [x for x in results if "error" in x],
        "sw2_rows": con.execute("SELECT COUNT(*) FROM sw2_daily").fetchone()[0],
        "nonpositive_close": con.execute("SELECT COUNT(*) FROM sw2_daily WHERE close<=0 OR close IS NULL").fetchone()[0],
        "duplicate_keys": con.execute("SELECT COUNT(*) FROM (SELECT code,date FROM sw2_daily GROUP BY code,date HAVING COUNT(*)>1)").fetchone()[0],
        "benchmark_rows": len(benchmark), "benchmark_first": benchmark[0][0], "benchmark_last": benchmark[-1][0],
    }
    audit = {"generated_at": now, "source": API, "code_snapshot": str(CODE_CSV),
             "benchmark": "801003 申万A指; proxy only, not Wind All A", "quality": quality,
             "indices": results}
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(quality, ensure_ascii=False, indent=2), flush=True)
    con.close()
    if quality["codes_failed"] or quality["nonpositive_close"] or quality["duplicate_keys"]:
        raise RuntimeError("数据验收未通过，详见xy_data_audit.json")


if __name__ == "__main__":
    sys.exit(main())
