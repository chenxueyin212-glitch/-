"""补采申万2014版二级行业停用序列；只追加，不改写现有131个代码的行情。"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.xy_replication.fetch_sw2_data import DB, fetch, number  # noqa: E402

# 2014版104个二级指数与当前131代码快照的差集；名单经公开分类表交叉核对。
# 所有代码仍需通过申万官方trend接口的实际首末日期验收，不以名称推断历史。
LEGACY = {
    "801013": "农业综合", "801021": "煤炭开采", "801022": "其他采掘",
    "801023": "石油开采", "801024": "采掘服务", "801031": "化工新材料",
    "801035": "石油化工", "801041": "钢铁", "801073": "仪器仪表",
    "801075": "金属制品", "801094": "汽车整车", "801123": "饮料制造",
    "801144": "其他轻工制造", "801162": "水务", "801164": "环保工程及服务",
    "801171": "港口", "801172": "高速公路", "801173": "公交",
    "801174": "航空运输", "801175": "机场", "801176": "航运",
    "801177": "铁路运输", "801182": "园区开发", "801205": "商业物业经营",
    "801211": "景点", "801212": "酒店", "801213": "旅游综合",
    "801214": "餐饮", "801215": "其他休闲服务", "801725": "园林工程",
    "801732": "电气自动化设备", "801734": "高低压设备", "801761": "文化传媒",
    "801762": "营销传播", "801763": "互联网传媒", "801780": "银行",
}
AUDIT = ROOT / "outputs" / "xy_legacy_data_audit.json"
ACCEPTED_MISSING = {"801762", "801763"}  # 官方trend接口返回空数据；保留缺口，不替代。


def main() -> None:
    con = sqlite3.connect(DB, timeout=120)
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    results = []
    for i, (code, name) in enumerate(LEGACY.items(), 1):
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
                                "swsresearch trend; SW2014 legacy supplement", now))
            if not records:
                raise ValueError("no valid dated rows")
            valid_close = [r for r in records if r[5] is not None and r[5] > 0]
            if not valid_close:
                raise ValueError("no positive close rows")
            # 空收盘记录只用于覆盖审计；元数据首末日期必须按有效收盘价计算。
            with con:
                con.executemany("INSERT OR REPLACE INTO sw2_daily VALUES(?,?,?,?,?,?,?,?,?,?)", records)
                con.execute("INSERT OR REPLACE INTO sw2_meta VALUES(?,?,?,?,?,?,?)",
                            (code, name, "SW2014 legacy supplement", len(records),
                             valid_close[0][1], valid_close[-1][1], now))
            result = {"code": code, "name": name, "rows": len(records),
                      "valid_close_rows": len(valid_close),
                      "missing_close_rows": len(records)-len(valid_close),
                      "first": valid_close[0][1], "last": valid_close[-1][1]}
        except Exception as exc:  # noqa: BLE001
            result = {"code": code, "name": name, "error": repr(exc)}
        results.append(result)
        print(f"[{i}/{len(LEGACY)}] {result}", flush=True)
        time.sleep(0.35)
    failed = [r for r in results if "error" in r]
    audit = {
        "generated_at": now,
        "purpose": "structural universe audit: 2014 had 104 SW2 indices, main panel only had about 68 in 2015",
        "selection_rule": "fixed 36-code set difference between SW2014 104-index list and current 131-code snapshot; not return-selected",
        "source": "https://www.swsresearch.com/institute-sw/api/index_publish/trend/",
        "requested": len(LEGACY), "succeeded": len(results) - len(failed), "failed": failed,
        "accepted_missing": sorted({r["code"] for r in failed} & ACCEPTED_MISSING),
        "indices": results,
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ("requested", "succeeded", "failed")},
                     ensure_ascii=False, indent=2), flush=True)
    con.close()
    unexpected = [r for r in failed if r["code"] not in ACCEPTED_MISSING]
    if unexpected:
        raise RuntimeError(f"旧版行业出现未登记缺口: {unexpected}")


if __name__ == "__main__":
    main()
