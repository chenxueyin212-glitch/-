"""有代码映射缺陷的历史实验，仅保留作审计，不是有效兴业同期复现。

2026-11-07更正：OLD_2014误用801031、801780、801762、801763并遗漏801222；
正确旧版代码还包括801192、801751、801752。原有绩效不得作为行业时代口径证据，
也不得据收益反选行业或阈值。修正管线见compute_corrected_features.py。

触发原因原是事前可确认的结构缺口：2014版有104个二级行业，主面板2015年仅约68个。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import sys
import time
import tomllib
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.xy_replication.backtest import metric, signal_source, write_csv  # noqa: E402
from src.xy_replication.fetch_sw2_legacy import LEGACY  # noqa: E402
from src.xy_replication.topology import network_features  # noqa: E402

OUT = ROOT / "outputs"
DATA_DB = OUT / "xy_replication_data.db"
RESULT_DB = OUT / "xy_replication_pit_results.db"
CONFIG = ROOT / "config" / "xy_replication.toml"
FIELDS = [
    "n_nodes", "h2_count", "h1_count", "h2_landscape_l1", "h1_landscape_l1",
    "industry_average_correlation", "correlation_leading_eigenvalue_share",
    "max_h2_persistence", "h2_betti_0p4", "h2_betti_0p6", "h2_betti_0p8",
    "market_return_30", "market_realized_volatility_30",
]
OLD_2014 = set("""
801016 801015 801011 801014 801012 801013 801017 801018 801023 801021
801022 801024 801035 801033 801034 801032 801036 801037 801031 801041
801051 801055 801053 801054 801081 801083 801084 801082 801085 801094
801093 801092 801881 801111 801112 801123 801124 801131 801132 801143
801141 801142 801144 801151 801155 801152 801154 801153 801156 801161
801162 801163 801164 801171 801172 801173 801174 801175 801176 801177
801178 801181 801182 801202 801203 801204 801205 801211 801212 801213
801214 801215 801780 801193 801194 801191 801231 801711 801712 801713
801721 801722 801723 801724 801725 801731 801732 801733 801734 801072
801074 801073 801075 801076 801741 801742 801743 801744 801101 801102
801761 801762 801763 801223
""".split())
ERA_SWITCH = "2021-12-13"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    with CONFIG.open("rb") as handle:
        cfg = tomllib.load(handle)
    data = sqlite3.connect(f"file:{DATA_DB}?mode=ro", uri=True)
    current_131 = {r[0] for r in data.execute(
        "SELECT code FROM sw2_meta WHERE parent IS NOT 'SW2014 legacy supplement'")}
    available = {r[0] for r in data.execute("SELECT code FROM sw2_meta")}
    if len(OLD_2014) != 104 or len(current_131) != 131:
        raise RuntimeError((len(OLD_2014), len(current_131)))
    # 两个无数据旧代码保留为显式缺口，不以其他行业替代。
    codes = sorted(OLD_2014 | current_131)
    closes = {code: dict(data.execute("SELECT date,close FROM sw2_daily WHERE code=?", (code,)))
              for code in codes if code in available}
    bench = data.execute(
        "SELECT date,open,high,low,close FROM benchmark_daily WHERE code='801003' ORDER BY date"
    ).fetchall()
    data.close()
    dates = [r[0] for r in bench]
    positions = {d: i for i, d in enumerate(dates)}
    bench_close = {r[0]: float(r[4]) for r in bench}
    variant_payload = json.dumps({"base_config": cfg, "old_2014": sorted(OLD_2014),
                                  "current_131": sorted(current_131), "era_switch": ERA_SWITCH,
                                  "quality_filter": "complete 31 positive closes and nonzero return variance"},
                                 ensure_ascii=False, sort_keys=True).encode("utf-8")
    variant_hash = hashlib.sha256(variant_payload).hexdigest()
    result = sqlite3.connect(RESULT_DB, timeout=120)
    result.execute("""CREATE TABLE IF NOT EXISTS feature_daily(
        date TEXT PRIMARY KEY,n_nodes INTEGER,h2_count INTEGER,h1_count INTEGER,
        h2_landscape_l1 REAL,h1_landscape_l1 REAL,industry_average_correlation REAL,
        correlation_leading_eigenvalue_share REAL,max_h2_persistence REAL,
        h2_betti_0p4 INTEGER,h2_betti_0p6 INTEGER,h2_betti_0p8 INTEGER,
        market_return_30 REAL,market_realized_volatility_30 REAL,
        config_sha256 TEXT NOT NULL)""")
    candidates = [d for d in dates if d >= "2014-02-21" and positions[d] >= 30]
    started = time.time()
    completed = 0
    for date in candidates:
        if not args.force and result.execute("SELECT 1 FROM feature_daily WHERE date=?", (date,)).fetchone():
            continue
        i = positions[date]
        window_dates = dates[i-30:i+1]
        era_codes = OLD_2014 if date < ERA_SWITCH else current_131
        eligible = []
        for code in sorted(era_codes):
            series = closes.get(code, {})
            prices = [series.get(d) for d in window_dates]
            if all(p is not None and p > 0 for p in prices):
                industry_returns = np.asarray(prices, dtype=float)
                industry_returns = industry_returns[1:] / industry_returns[:-1] - 1.0
                # 相关系数要求非零方差；该确定性质量规则在计算H2前执行。
                if np.std(industry_returns, ddof=1) > 0:
                    eligible.append(prices)
        if len(eligible) < 4:
            raise RuntimeError(f"{date}有效行业不足4个")
        price_matrix = np.asarray(eligible, dtype=float).T
        returns = price_matrix[1:] / price_matrix[:-1] - 1.0
        features = network_features(returns, cfg["topology"]["fixed_epsilon_sensitivity"])
        market_prices = np.asarray([bench_close[d] for d in window_dates], dtype=float)
        market_returns = market_prices[1:] / market_prices[:-1] - 1.0
        features["market_return_30"] = float(market_prices[-1] / market_prices[0] - 1.0)
        features["market_realized_volatility_30"] = float(np.std(market_returns, ddof=1))
        result.execute(
            f"INSERT OR REPLACE INTO feature_daily VALUES(?,{','.join('?' * len(FIELDS))},?)",
            (date, *[features[k] for k in FIELDS], variant_hash))
        completed += 1
        if completed % 25 == 0:
            result.commit()
            print(json.dumps({"date": date, "completed": completed,
                              "n_nodes": features["n_nodes"], "h2_count": features["h2_count"],
                              "seconds": round(time.time()-started, 1)}), flush=True)
    result.commit()

    con = sqlite3.connect(f"file:{RESULT_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    features = [dict(r) for r in con.execute("SELECT * FROM feature_daily ORDER BY date")]
    con.close()
    if any(r["config_sha256"] != variant_hash for r in features):
        raise RuntimeError("PIT特征含不同配置哈希，请使用--force完整重算")
    feature_dates = [r["date"] for r in features]
    bench_map = {r[0]: (float(r[1]), float(r[4])) for r in bench}
    close = np.asarray([bench_map[d][1] for d in feature_dates])
    open_ = np.asarray([bench_map[d][0] for d in feature_dates])
    signal = np.asarray([r["h2_count"] <= 1 for r in features], dtype=bool)
    hold = int(cfg["execution"]["hold_days"])
    cost_rate = float(cfg["execution"]["cost_per_side"])
    periods = {
        "report_sample": (cfg["source"]["reported_backtest_start"], cfg["source"]["reported_backtest_end"]),
        "post_publication": (cfg["source"]["post_publication_start"], feature_dates[-1]),
    }
    performance, daily_rows, signal_rows = [], [], []
    for execution in ("report_close", "causal_open"):
        interval_dates, asset_returns, sources = [], [], []
        for end in range(1, len(features)):
            start = end - 1
            if execution == "report_close":
                if start - hold + 1 < 0:
                    continue
                asset_return = close[end] / close[end-1] - 1.0
            else:
                if start - hold < 0:
                    continue
                asset_return = open_[end] / open_[end-1] - 1.0
            interval_dates.append(feature_dates[end])
            asset_returns.append(float(asset_return))
            sources.append(signal_source(start, hold, execution))
        interval_dates = np.asarray(interval_dates)
        date_array = np.asarray(feature_dates)
        for period, (start_date, end_date) in periods.items():
            idx = np.flatnonzero((interval_dates >= start_date) & (interval_dates <= end_date))
            if len(idx) < 2:
                continue
            period_signal = signal & (date_array >= start_date) & (date_array <= end_date)
            all_positions = np.asarray([period_signal[s].any() for s in sources], dtype=int)
            p = all_positions[idx].copy()
            r = np.asarray(asset_returns)[idx]
            previous = np.concatenate([[0], p[:-1]])
            costs = np.abs(p-previous) * cost_rate
            if p[-1]:
                costs[-1] += cost_rate
            stats, daily = metric(interval_dates[idx], r, p, costs)
            stats.update({"model": "h2_count_pit", "execution": execution, "period": period,
                          "start": str(interval_dates[idx[0]]), "end": str(interval_dates[idx[-1]])})
            performance.append(stats)
            daily_rows.extend({"model": "h2_count_pit", "execution": execution,
                               "period": period, **item} for item in daily)
    for i in np.flatnonzero(signal):
        signal_rows.append({"date": feature_dates[i], "h2_count": features[i]["h2_count"],
                            "n_nodes": features[i]["n_nodes"],
                            "forward_4d_close_return": float(close[i+hold]/close[i]-1) if i+hold < len(features) else None,
                            "causal_4d_open_return": float(open_[i+hold+1]/open_[i+1]-1) if i+hold+1 < len(features) else None})
    yearly_nodes = defaultdict(list)
    for r in features:
        yearly_nodes[r["date"][:4]].append(r)
    yearly = [{"year": year, "days": len(part), "nodes_min": min(r["n_nodes"] for r in part),
               "nodes_max": max(r["n_nodes"] for r in part),
               "h2_le1_days": sum(r["h2_count"] <= 1 for r in part),
               "h2_zero_days": sum(r["h2_count"] == 0 for r in part)}
              for year, part in sorted(yearly_nodes.items())]
    cited = {month: [r["date"] for r in signal_rows if r["date"].startswith(month)]
             for month in cfg["audit"]["report_cited_periods"]}
    summary = {
        "protocol": "xy-replication-pit-structural-sensitivity-v1.0",
        "evidence_status": "defective_legacy_experiment; not valid XY-era replication evidence",
        "known_code_mapping_errors": "801031/801780/801762/801763误用且遗漏801222；修正见fetch_sw2014_corrected.py",
        "variant_sha256": variant_hash,
        "pre_performance_rationale": "2014版104行业与主面板2015年约68节点的已知结构差异；非收益筛选",
        "era_rule": "date<2021-12-13 use SW2014 104-code list; thereafter use 131-code current snapshot; daily complete windows and nonzero return variance only",
        "missing_legacy_series": sorted(set(LEGACY)-available),
        "feature_range": {"first": feature_dates[0], "last": feature_dates[-1], "n": len(features)},
        "h2_signal_days": int(signal.sum()),
        "cited_period_signal_dates": cited,
        "yearly_structure": yearly, "performance": performance,
        "limitations": [
            "旧实验误用的801762/801763无有效返回，正确旧版代码应为801751/801752；801144有722个空收盘日期、801215有1个，均由完整窗口规则排除；2015年实际有效节点不足104",
            "行业名单由公开分类表交叉核对，未获得兴业2025年7月Wind原始名单",
            "该实验原本只诊断行业时代口径，不改变N定义、30日窗口、4日规则或成本；但已发现代码映射错误，所有绩效只作缺陷审计",
            "申万A指仍是万得全A代理，不能把变体绩效当作原报告精确复现",
        ],
    }
    (OUT / "xy_pit_sensitivity_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    write_csv(OUT / "xy_pit_performance.csv", performance)
    write_csv(OUT / "xy_pit_daily_returns.csv", daily_rows)
    write_csv(OUT / "xy_pit_signals.csv", signal_rows)
    feature_export = [{k: r[k] for k in r if k != "config_sha256"} for r in features]
    write_csv(OUT / "xy_pit_features.csv", feature_export)
    print(json.dumps({"status": "ok", "new_rows": completed, "features": len(features),
                      "h2_signal_days": summary["h2_signal_days"], "cited": cited,
                      "performance": performance}, ensure_ascii=False, indent=2), flush=True)
    result.close()


if __name__ == "__main__":
    main()
