"""从当前会话保存的iFind原始表格返回导入逐日补充行情。

用于连接只能展示Markdown表格、没有CSV导出权限的情形。脚本按callId提取原始
返回，检查查询区间没有截断和抽样，再写入独立补充库；不手工转录数值。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.xy_replication.import_westock_supplement import (  # noqa: E402
    PUBLIC_DB, SUPPLEMENT_DB, SCHEMA, positive_number,
)

OUT = ROOT / "outputs"
AUDIT_OUT = OUT / "xy_ifind_supplement_audit.json"
DEFAULT_SESSION = Path.home() / ".workbuddy" / "projects" / "D-WorkBuddy-2026-10-28-22-54-51" / "57008466-94fc-4594-b599-6c309bb21987.jsonl"


def load_raw_result(session: Path, needle: str) -> tuple[dict, str]:
    call_id = None
    for line in session.open(encoding="utf-8"):
        obj = json.loads(line)
        if obj.get("type") == "function_call" and obj.get("name") == "DeferExecuteTool":
            arguments = obj.get("arguments") or ""
            if needle in arguments and "mcp__ifind-mcp__get_security_indicators" in arguments:
                call_id = obj["callId"]
    if call_id is None:
        raise ValueError("没有找到匹配的iFind原始调用")
    for line in session.open(encoding="utf-8"):
        obj = json.loads(line)
        if obj.get("type") == "function_call_result" and obj.get("callId") == call_id:
            text = obj["output"]["text"]
            return json.loads(text), call_id
    raise ValueError("找到了调用但没有找到原始返回")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    parser.add_argument("--code", default="801011")
    parser.add_argument("--query-start", default="2021-04-01")
    parser.add_argument("--query-end", default="2021-06-30")
    parser.add_argument("--query-needle", default="801011.SL在2021-04-01至2021-06-30")
    args = parser.parse_args()
    payload, call_id = load_raw_result(args.session, args.query_needle)
    if payload.get("code") != 1 or not isinstance(payload.get("data"), dict):
        raise ValueError("iFind原始返回状态异常")
    answer = payload["data"].get("answer") or ""
    if "数据被截断" in answer or "部分数据" in answer:
        raise ValueError("原始表格存在截断，不能作为逐日补充行情")
    table_rows = []
    for line in answer.splitlines():
        if not line.startswith("|" + args.code + ".SL|"):
            continue
        cells = line.split("|")
        if len(cells) < 6:
            raise ValueError(f"表格列数异常: {line}")
        name, raw_date, raw_close = cells[2], cells[3], cells[4].strip()
        date = dt.datetime.strptime(raw_date, "%Y%m%d").date().isoformat()
        table_rows.append((date, name, positive_number(raw_close)))
    if not table_rows:
        raise ValueError("没有解析到目标代码表格行")
    start = dt.date.fromisoformat(args.query_start)
    end = dt.date.fromisoformat(args.query_end)
    expected_dates = {(start + dt.timedelta(days=i)).isoformat()
                      for i in range((end-start).days+1)}
    actual_dates = {r[0] for r in table_rows}
    if len(table_rows) != len(actual_dates) or actual_dates != expected_dates:
        raise ValueError({"rows": len(table_rows), "unique_dates": len(actual_dates),
                          "expected_calendar_days": len(expected_dates),
                          "missing": sorted(expected_dates-actual_dates)[:10],
                          "extra": sorted(actual_dates-expected_dates)[:10]})

    snapshot = ROOT / "third_party" / "ifind" / f"{args.code}SL_day_{args.query_start.replace('-', '')}_{args.query_end.replace('-', '')}.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot_payload = {"query": {"code": args.code + ".SL", "start": args.query_start,
                                  "end": args.query_end, "call_id": call_id},
                        "raw_result": payload}
    raw = (json.dumps(snapshot_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    snapshot.write_bytes(raw)
    snapshot_hash = hashlib.sha256(raw).hexdigest()
    source = f"iFind MCP get_security_indicators {args.code}.SL; raw markdown table"
    records = [(args.code, date, None, None, None, close, 0.0, 0.0, source, snapshot_hash)
               for date, _, close in table_rows if close is not None]
    records.sort(key=lambda row: row[1])
    if not records:
        raise ValueError("表格没有正收盘价")

    public = sqlite3.connect(f"file:{PUBLIC_DB}?mode=ro", uri=True)
    public_close = dict(public.execute("SELECT date,close FROM sw2014_daily WHERE code=?", (args.code,)))
    public.close()
    comparisons = []
    for row in records:
        old = public_close.get(row[1])
        if old is not None and old > 0:
            comparisons.append({"date": row[1], "public": float(old), "supplement": row[5],
                                "abs_diff": abs(float(old)-row[5])})
    mismatches = [r for r in comparisons if r["abs_diff"] > 0.0100001]
    rounding = [r for r in comparisons if 1e-8 < r["abs_diff"] <= 0.0100001]
    fill_dates = [row[1] for row in records
                  if public_close.get(row[1]) is None or public_close[row[1]] <= 0]

    con = sqlite3.connect(SUPPLEMENT_DB, timeout=120)
    con.executescript(SCHEMA)
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    with con:
        con.execute("DELETE FROM supplement_daily WHERE code=?", (args.code,))
        con.executemany("INSERT INTO supplement_daily VALUES(?,?,?,?,?,?,?,?,?,?)", records)
        con.execute("INSERT OR REPLACE INTO supplement_meta VALUES(?,?,?,?,?,?,?,?,?)",
                    (args.code, len(records), records[0][1], records[-1][1], args.query_start,
                     args.query_end, source, snapshot_hash, now))
    duplicate_keys = con.execute("SELECT COUNT(*) FROM (SELECT code,date FROM supplement_daily "
                                 "GROUP BY code,date HAVING COUNT(*)>1)").fetchone()[0]
    con.close()
    audit = {
        "generated_at": now, "code": args.code, "source": source, "call_id": call_id,
        "snapshot": str(snapshot), "snapshot_sha256": snapshot_hash,
        "calendar_days_checked": len(table_rows), "positive_close_days": len(records),
        "blank_calendar_days": len(table_rows)-len(records),
        "actual_close_range": [records[0][1], records[-1][1]],
        "duplicate_keys": duplicate_keys,
        "public_overlap": {"days": len(comparisons), "mismatch_days": len(mismatches),
                           "rounding_difference_days": len(rounding),
                           "max_abs_diff": max((r["abs_diff"] for r in comparisons), default=None),
                           "mismatch_examples": mismatches[:20]},
        "fillable_public_missing_or_nonpositive_days": len(fill_dates),
        "merge_rule": "公开正收盘优先；仅补公开缺失/非正收盘，不插值，不补周末或假期",
        "known_limits": ["只覆盖2021-04-01至2021-06-30峰值诊断窗口，不是2012—2021完整历史",
                         "iFind数据不是兴业Wind原始导出；空缺日期不因表格存在而视为有效行情"],
    }
    AUDIT_OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2), flush=True)
    if duplicate_keys or mismatches:
        raise RuntimeError("iFind补充行情验收失败")


if __name__ == "__main__":
    main()
