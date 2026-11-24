"""用修正版SW2014与既有SW2021公开指数行情重算相关网络特征。

只输出数据覆盖、H2数量与持久景观等特征，不计算策略绩效。
原主面板和旧时代变体均保留；本结果也不冒充Wind原始导出。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.xy_replication.fetch_sw2014_corrected import CODES as SW2014  # noqa: E402
from src.xy_replication.topology import network_features  # noqa: E402

OUT = ROOT / "outputs"
OLD_DB = OUT / "xy_sw2014_corrected_data.db"
CURRENT_DB = OUT / "xy_replication_data.db"
RESULT_DB = OUT / "xy_corrected_features.db"
CSV_OUT = OUT / "xy_corrected_features.csv"
SUMMARY_OUT = OUT / "xy_corrected_feature_summary.json"
SUPPLEMENT_DB = OUT / "xy_sw2014_supplement.db"
SUPPLEMENTED_RESULT_DB = OUT / "xy_corrected_supplemented_features.db"
SUPPLEMENTED_CSV_OUT = OUT / "xy_corrected_supplemented_features.csv"
SUPPLEMENTED_SUMMARY_OUT = OUT / "xy_corrected_supplemented_feature_summary.json"
ERA_SWITCH = "2021-12-13"
FIELDS = ["n_nodes", "h2_count", "h1_count", "h2_landscape_l1", "h1_landscape_l1",
          "industry_average_correlation", "correlation_leading_eigenvalue_share",
          "max_h2_persistence", "h2_betti_0p4", "h2_betti_0p6", "h2_betti_0p8"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--with-supplement", action="store_true",
                        help="公开收盘缺失时使用独立补充库；保留公开-only结果")
    parser.add_argument("--output-tag", help="可选的独立输出标签，避免覆盖其他补充版本")
    args = parser.parse_args()
    if args.output_tag:
        if not args.output_tag.replace("-", "").replace("_", "").isalnum():
            raise ValueError("output-tag只允许字母、数字、连字符和下划线")
        result_db = OUT / f"xy_corrected_{args.output_tag}_features.db"
        csv_out = OUT / f"xy_corrected_{args.output_tag}_features.csv"
        summary_out = OUT / f"xy_corrected_{args.output_tag}_feature_summary.json"
    else:
        result_db = SUPPLEMENTED_RESULT_DB if args.with_supplement else RESULT_DB
        csv_out = SUPPLEMENTED_CSV_OUT if args.with_supplement else CSV_OUT
        summary_out = SUPPLEMENTED_SUMMARY_OUT if args.with_supplement else SUMMARY_OUT
    old = sqlite3.connect(f"file:{OLD_DB}?mode=ro", uri=True)
    if old.execute("SELECT COUNT(*) FROM sw2014_meta").fetchone()[0] != 104:
        raise RuntimeError("修正版SW2014尚未完整采集104条元数据")
    old_closes = {r[0]: dict(old.execute(
        "SELECT date,close FROM sw2014_daily WHERE code=?", (r[0],)))
        for r in old.execute("SELECT code FROM sw2014_meta")}
    old.close()
    supplement_closes = {}
    supplement_payload = []
    if args.with_supplement:
        supplement = sqlite3.connect(f"file:{SUPPLEMENT_DB}?mode=ro", uri=True)
        supplement.row_factory = sqlite3.Row
        supplement_payload = [dict(r) for r in supplement.execute(
            "SELECT code,rows,first_date,last_date,snapshot_sha256 FROM supplement_meta ORDER BY code")]
        supplement_closes = {item["code"]: dict(supplement.execute(
            "SELECT date,close FROM supplement_daily WHERE code=?", (item["code"],)))
            for item in supplement_payload}
        supplement.close()
        if not supplement_payload:
            raise RuntimeError("指定使用补充库但没有任何补充元数据")
    current = sqlite3.connect(f"file:{CURRENT_DB}?mode=ro", uri=True)
    current_codes = {r[0] for r in current.execute(
        "SELECT code FROM sw2_meta WHERE parent IS NOT 'SW2014 legacy supplement'")}
    if len(current_codes) != 131:
        raise RuntimeError(f"当前快照代码数异常: {len(current_codes)}")
    current_closes = {code: dict(current.execute(
        "SELECT date,close FROM sw2_daily WHERE code=?", (code,))) for code in current_codes}
    dates = [r[0] for r in current.execute(
        "SELECT date FROM benchmark_daily WHERE code='801003' ORDER BY date")]
    current.close()
    positions = {d: i for i, d in enumerate(dates)}
    payload = {"SW2014": sorted(SW2014), "SW2021_snapshot": sorted(current_codes),
               "era_switch": ERA_SWITCH, "return": "30 simple close-to-close returns",
               "quality": "31 complete positive closes and nonzero sample variance",
               "source": "SWS public trend, not Wind raw export",
               "supplement": supplement_payload,
               "merge_rule": "public positive close first; supplement missing/nonpositive only"}
    config_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    result = sqlite3.connect(result_db, timeout=120)
    result.execute("""CREATE TABLE IF NOT EXISTS feature_daily(
        date TEXT PRIMARY KEY,n_nodes INTEGER,h2_count INTEGER,h1_count INTEGER,
        h2_landscape_l1 REAL,h1_landscape_l1 REAL,industry_average_correlation REAL,
        correlation_leading_eigenvalue_share REAL,max_h2_persistence REAL,
        h2_betti_0p4 INTEGER,h2_betti_0p6 INTEGER,h2_betti_0p8 INTEGER,
        config_sha256 TEXT NOT NULL)""")
    if args.with_supplement:
        result.execute("""CREATE TABLE IF NOT EXISTS feature_supplement(
            date TEXT PRIMARY KEY,eligible_codes_json TEXT NOT NULL)""")
    candidates = [d for d in dates if d >= "2012-12-31" and positions[d] >= 30]
    started = time.time()
    completed = 0
    for date in candidates:
        if not args.force and result.execute(
                "SELECT 1 FROM feature_daily WHERE date=? AND config_sha256=?",
                (date, config_hash)).fetchone():
            continue
        i = positions[date]
        window_dates = dates[i-30:i+1]
        source = old_closes if date < ERA_SWITCH else current_closes
        codes = SW2014 if date < ERA_SWITCH else current_codes
        eligible = []
        supplemented_eligible = []
        for code in sorted(codes):
            series = source.get(code, {})
            prices = []
            used_supplement = False
            for d in window_dates:
                price = series.get(d)
                if price is None or price <= 0:
                    supplement_price = supplement_closes.get(code, {}).get(d)
                    if supplement_price is not None and supplement_price > 0:
                        price = supplement_price
                        used_supplement = True
                prices.append(price)
            if all(p is not None and p > 0 for p in prices):
                returns = np.asarray(prices, dtype=float)
                returns = returns[1:] / returns[:-1] - 1.0
                if np.std(returns, ddof=1) > 0:
                    eligible.append(prices)
                    if used_supplement:
                        supplemented_eligible.append(code)
        if len(eligible) < 4:
            raise RuntimeError(f"{date}有效行业不足4个")
        price_matrix = np.asarray(eligible, dtype=float).T
        returns = price_matrix[1:] / price_matrix[:-1] - 1.0
        features = network_features(returns)
        result.execute(
            f"INSERT OR REPLACE INTO feature_daily VALUES(?,{','.join('?' * len(FIELDS))},?)",
            (date, *[features[k] for k in FIELDS], config_hash))
        if args.with_supplement:
            result.execute("INSERT OR REPLACE INTO feature_supplement VALUES(?,?)",
                           (date, json.dumps(supplemented_eligible)))
        completed += 1
        if completed % 25 == 0:
            result.commit()
            print(json.dumps({"date": date, "completed": completed, "nodes": features["n_nodes"],
                              "h2": features["h2_count"], "seconds": round(time.time()-started, 1)}),
                  flush=True)
    result.commit()
    result.row_factory = sqlite3.Row
    rows = [dict(r) for r in result.execute("SELECT * FROM feature_daily ORDER BY date")]
    if any(r["config_sha256"] != config_hash for r in rows):
        raise RuntimeError("结果库存在其他配置，请使用独立数据库或--force完整重算")
    with csv_out.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["date"] + FIELDS
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r[k] for k in fields} for r in rows)
    yearly = defaultdict(list)
    for r in rows:
        yearly[r["date"][:4]].append(r)
    yearly_stats = [{"year": y, "days": len(v), "nodes_min": min(r["n_nodes"] for r in v),
                     "nodes_max": max(r["n_nodes"] for r in v),
                     "h2_max": max(r["h2_count"] for r in v),
                     "h2_min": min(r["h2_count"] for r in v),
                     "h2_zero_days": sum(r["h2_count"] == 0 for r in v),
                     "h2_le1_days": sum(r["h2_count"] <= 1 for r in v),
                     "landscape_l1_max": max(r["h2_landscape_l1"] for r in v)}
                    for y, v in sorted(yearly.items())]
    cited = {}
    for month in ("2020-03", "2022-04", "2024-02", "2025-01"):
        part = [r for r in rows if r["date"].startswith(month)]
        cited[month] = {"h2_min": min(r["h2_count"] for r in part),
                        "h2_max": max(r["h2_count"] for r in part),
                        "le1_dates": [r["date"] for r in part if r["h2_count"] <= 1]}
    supplement_usage = None
    if args.with_supplement:
        usage_rows = [(r[0], json.loads(r[1])) for r in result.execute(
            "SELECT date,eligible_codes_json FROM feature_supplement ORDER BY date")]
        by_code = defaultdict(int)
        for _, used_codes in usage_rows:
            for code in used_codes:
                by_code[code] += 1
        supplement_usage = {"days_with_supplemented_industry": sum(bool(x) for _, x in usage_rows),
                            "eligible_industry_days_by_code": dict(sorted(by_code.items())),
                            "max_supplemented_industries_per_day": max((len(x) for _, x in usage_rows), default=0)}
    protocol = "xy-corrected-supplemented-universe-v1.1" if args.with_supplement else "xy-corrected-public-universe-v1.0"
    if args.output_tag:
        protocol += "-" + args.output_tag
    limitations = ["不是兴业Wind原始文件；共用代码的历史断档仍需Wind或另一独立源核验",
                   "本步骤只核验行业输入和拓扑曲线，不计算万得全A策略绩效"]
    if args.with_supplement:
        limitations.append("证券Ⅱ补充源实际覆盖2016-12-12至2021-12-10；2015年及林业等缺口仍未解决")
    summary = {"protocol": protocol, "config_sha256": config_hash,
               "source": payload["source"], "supplement": supplement_payload,
               "supplement_usage": supplement_usage, "feature_days": len(rows),
               "range": [rows[0]["date"], rows[-1]["date"]], "new_rows": completed,
               "yearly": yearly_stats, "cited_periods": cited, "limitations": limitations}
    summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                           encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    result.close()


if __name__ == "__main__":
    main()
