"""逐日计算申万二级相关网络H2，支持断点续跑和单日期试点。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
import tomllib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.xy_replication.topology import network_features  # noqa: E402

DATA_DB = ROOT / "outputs" / "xy_replication_data.db"
RESULT_DB = ROOT / "outputs" / "xy_replication_results.db"
CONFIG = ROOT / "config" / "xy_replication.toml"
FIELDS = [
    "n_nodes", "h2_count", "h1_count", "h2_landscape_l1", "h1_landscape_l1",
    "industry_average_correlation", "correlation_leading_eigenvalue_share",
    "max_h2_persistence", "h2_betti_0p4", "h2_betti_0p6", "h2_betti_0p8",
    "market_return_30", "market_realized_volatility_30",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2012-12-31")
    parser.add_argument("--end", default="9999-12-31")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    with CONFIG.open("rb") as handle:
        cfg = tomllib.load(handle)
    data = sqlite3.connect(f"file:{DATA_DB}?mode=ro", uri=True)
    codes = [r[0] for r in data.execute(
        "SELECT code FROM sw2_meta WHERE last_date>=? ORDER BY code",
        (cfg["source"]["reported_backtest_end"],),
    )]
    expected_active = int(cfg["universe"]["expected_active_codes_through_report_end"])
    if len(codes) != expected_active:
        raise RuntimeError(f"活跃二级行业数量为{len(codes)}，预期{expected_active}")
    closes = {
        code: dict(data.execute("SELECT date,close FROM sw2_daily WHERE code=?", (code,)))
        for code in codes
    }
    bench = data.execute(
        "SELECT date,open,high,low,close FROM benchmark_daily WHERE code='801003' ORDER BY date"
    ).fetchall()
    data.close()
    dates = [r[0] for r in bench]
    bench_close = {r[0]: float(r[4]) for r in bench}
    positions = {d: i for i, d in enumerate(dates)}
    result = sqlite3.connect(RESULT_DB, timeout=120)
    result.execute("""CREATE TABLE IF NOT EXISTS feature_daily(
        date TEXT PRIMARY KEY,n_nodes INTEGER,h2_count INTEGER,h1_count INTEGER,
        h2_landscape_l1 REAL,h1_landscape_l1 REAL,industry_average_correlation REAL,
        correlation_leading_eigenvalue_share REAL,max_h2_persistence REAL,
        h2_betti_0p4 INTEGER,h2_betti_0p6 INTEGER,h2_betti_0p8 INTEGER,
        market_return_30 REAL,market_realized_volatility_30 REAL,
        config_sha256 TEXT NOT NULL)""")
    config_hash = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    completed = 0
    started = time.time()
    candidates = [d for d in dates if args.start <= d <= args.end and positions[d] >= 30]
    if args.limit:
        candidates = candidates[:args.limit]
    for date in candidates:
        if not args.force and result.execute("SELECT 1 FROM feature_daily WHERE date=?", (date,)).fetchone():
            continue
        i = positions[date]
        window_dates = dates[i - 30:i + 1]
        eligible = []
        for code in codes:
            series = closes[code]
            prices = [series.get(d) for d in window_dates]
            if all(p is not None and p > 0 for p in prices):
                eligible.append((code, prices))
        if len(eligible) < 4:
            raise RuntimeError(f"{date}有效二级行业不足4个")
        price_matrix = np.asarray([p for _, p in eligible], dtype=float).T
        returns = price_matrix[1:] / price_matrix[:-1] - 1.0
        features = network_features(returns, cfg["topology"]["fixed_epsilon_sensitivity"])
        market_prices = np.asarray([bench_close[d] for d in window_dates], dtype=float)
        market_returns = market_prices[1:] / market_prices[:-1] - 1.0
        features["market_return_30"] = float(market_prices[-1] / market_prices[0] - 1.0)
        features["market_realized_volatility_30"] = float(np.std(market_returns, ddof=1))
        values = [features[k] for k in FIELDS]
        result.execute(
            f"INSERT OR REPLACE INTO feature_daily VALUES(?,{','.join('?' * len(FIELDS))},?)",
            (date, *values, config_hash),
        )
        completed += 1
        if completed % 25 == 0:
            result.commit()
            elapsed = time.time() - started
            print(json.dumps({"date": date, "completed": completed, "n_nodes": features["n_nodes"],
                              "h2_count": features["h2_count"], "seconds": round(elapsed, 1)}), flush=True)
    result.commit()
    total = result.execute("SELECT COUNT(*) FROM feature_daily").fetchone()[0]
    bounds = result.execute("SELECT MIN(date),MAX(date) FROM feature_daily").fetchone()
    result.close()
    print(json.dumps({"status": "ok", "new_rows": completed, "total_rows": total,
                      "first": bounds[0], "last": bounds[1],
                      "seconds": round(time.time() - started, 2)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
