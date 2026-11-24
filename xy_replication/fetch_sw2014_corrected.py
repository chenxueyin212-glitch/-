"""独立采集修正版SW2014二级行业指数，不覆盖既有主面板或时代变体。

修正来自逐行核对公开分类表与申万官方行情：
- 801031为2014年前停用序列，不属于2014版104行业；
- 801192银行、801222计算机应用、801751营销传播、801752互联网传媒
  替代此前误用的801780、801762、801763，并补入此前遗漏的801222。
本库仍不是Wind原始导出；新旧共用代码的历史断档必须单独披露。
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.xy_replication.fetch_sw2_data import fetch, number  # noqa: E402

OUT = ROOT / "outputs"
DB = OUT / "xy_sw2014_corrected_data.db"
AUDIT = OUT / "xy_sw2014_corrected_audit.json"
OLD_DB = OUT / "xy_replication_data.db"
CODES = frozenset("""
801011 801012 801013 801014 801015 801016 801017 801018 801021 801022
801023 801024 801032 801033 801034 801035 801036 801037 801041 801051
801053 801054 801055 801072 801073 801074 801075 801076 801081 801082
801083 801084 801085 801092 801093 801094 801101 801102 801111 801112
801123 801124 801131 801132 801141 801142 801143 801144 801151 801152
801153 801154 801155 801156 801161 801162 801163 801164 801171 801172
801173 801174 801175 801176 801177 801178 801181 801182 801191 801192
801193 801194 801202 801203 801204 801205 801211 801212 801213 801214
801215 801222 801223 801231 801711 801712 801713 801721 801722 801723
801724 801725 801731 801732 801733 801734 801741 801742 801743 801744
801751 801752 801761 801881
""".split())
NAME_OVERRIDES = {
    "801192": "银行II", "801222": "计算机应用II",
    "801751": "营销传播II", "801752": "互联网传媒II",
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS sw2014_daily(
 code TEXT NOT NULL,date TEXT NOT NULL,open REAL,high REAL,low REAL,close REAL,
 volume REAL,amount REAL,source TEXT NOT NULL,fetched_at TEXT NOT NULL,
 PRIMARY KEY(code,date));
CREATE TABLE IF NOT EXISTS sw2014_meta(
 code TEXT PRIMARY KEY,name TEXT NOT NULL,rows INTEGER,valid_close_rows INTEGER,
 first_date TEXT,last_date TEXT,fetched_at TEXT NOT NULL);
"""


def main() -> None:
    if len(CODES) != 104:
        raise RuntimeError(f"修正版代码数不是104: {len(CODES)}")
    old = sqlite3.connect(f"file:{OLD_DB}?mode=ro", uri=True)
    names = {r[0]: r[1] for r in old.execute("SELECT code,name FROM sw2_meta")}
    dates = [r[0] for r in old.execute(
        "SELECT date FROM benchmark_daily WHERE code='801003' ORDER BY date")]
    old.close()
    names.update(NAME_OVERRIDES)
    con = sqlite3.connect(DB, timeout=120)
    con.executescript(SCHEMA)
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    results = []
    for i, code in enumerate(sorted(CODES), 1):
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
                                number(row.get("bargainsum")),
                                "swsresearch trend; corrected SW2014 universe", now))
            valid = [r for r in records if r[5] is not None and r[5] > 0]
            if not records or not valid:
                raise ValueError("no valid dated positive-close rows")
            with con:
                con.executemany("INSERT OR REPLACE INTO sw2014_daily VALUES(?,?,?,?,?,?,?,?,?,?)", records)
                con.execute("INSERT OR REPLACE INTO sw2014_meta VALUES(?,?,?,?,?,?,?)",
                            (code, names.get(code, code), len(records), len(valid),
                             valid[0][1], valid[-1][1], now))
            result = {"code": code, "name": names.get(code, code), "rows": len(records),
                      "valid_close_rows": len(valid), "first": valid[0][1], "last": valid[-1][1]}
        except Exception as exc:  # noqa: BLE001
            result = {"code": code, "name": names.get(code, code), "error": repr(exc)}
        results.append(result)
        print(f"[{i}/104] {result}", flush=True)
        time.sleep(0.25)

    coverage = {}
    for target in ("2015-07-01", "2020-03-02", "2021-12-10"):
        i = dates.index(target)
        window = dates[i-30:i+1]
        placeholders = ",".join("?" * len(window))
        rows = con.execute(
            f"SELECT code,COUNT(*) FROM sw2014_daily WHERE date IN ({placeholders}) "
            "AND close>0 GROUP BY code", window).fetchall()
        complete = {code for code, n in rows if n == 31}
        coverage[target] = {"window": [window[0], window[-1]], "complete_31_close_codes": len(complete),
                            "missing": sorted(CODES-complete)}
    quality = {
        "requested": 104, "succeeded": sum("error" not in r for r in results),
        "failed": [r for r in results if "error" in r],
        "duplicate_keys": con.execute("SELECT COUNT(*) FROM (SELECT code,date FROM sw2014_daily "
                                      "GROUP BY code,date HAVING COUNT(*)>1)").fetchone()[0],
        "missing_close_rows": con.execute(
            "SELECT COUNT(*) FROM sw2014_daily WHERE close IS NULL OR close<=0").fetchone()[0],
    }
    audit = {
        "generated_at": now, "source": "申万宏源研究公开trend接口；非Wind原始导出",
        "classification_reference": "https://www.joinquant.com/data/dict/platedata",
        "corrections": {
            "removed": {"801031": "2014年前已停用"},
            "added_or_replaced": NAME_OVERRIDES,
            "retained": {"801124": "食品加工II；公开分类页误列旧代码801121，官方行情证明801121止于2011年"},
        },
        "quality": quality, "coverage": coverage, "indices": results,
        "known_risk": "新旧共用代码可能只返回当前版本或存在旧版时段断档，覆盖审计优先于总行数。",
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"quality": quality, "coverage": coverage}, ensure_ascii=False, indent=2), flush=True)
    con.close()
    if quality["failed"] or quality["duplicate_keys"]:
        raise RuntimeError("修正版SW2014数据采集验收失败，详见审计JSON")


if __name__ == "__main__":
    main()
