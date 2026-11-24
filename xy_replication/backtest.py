"""低H2择时、普通变量对照、信号明细和发布后独立表现。"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
import sys
import tomllib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA_DB = ROOT / "outputs" / "xy_replication_data.db"
RESULT_DB = ROOT / "outputs" / "xy_replication_results.db"
CONFIG = ROOT / "config" / "xy_replication.toml"
OUT = ROOT / "outputs"
MODEL_NAMES = {
    "h2_count": "H2有限持久区间数≤1",
    "average_correlation": "行业平均相关性（训练期95%分位）",
    "leading_eigenvalue": "相关矩阵最大特征值占比（训练期95%分位）",
    "market_oversold": "申万A指30日收益（训练期5%分位）",
    "market_volatility": "申万A指30日波动率（训练期95%分位）",
    "h2_landscape_low": "H2持久景观L1（训练期5%分位）",
    "h2_betti_0p4": "固定ε=0.4的H2 Betti数≤1",
    "h2_betti_0p6": "固定ε=0.6的H2 Betti数≤1",
    "h2_betti_0p8": "固定ε=0.8的H2 Betti数≤1",
}


def signal_source(start: int, hold: int, execution: str) -> np.ndarray:
    """返回一段收益期所允许使用的原始信号索引，禁止包含未来信号。"""
    if execution == "report_close":
        return np.arange(start - hold + 1, start + 1)
    if execution == "causal_open":
        return np.arange(start - hold, start)
    raise ValueError(execution)


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    if not rows:
        raise ValueError(f"无数据可写: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def metric(dates, asset_returns, positions, costs, annual_days=244) -> tuple[dict, list[dict]]:
    returns = np.asarray(asset_returns, dtype=float)
    pos = np.asarray(positions, dtype=float)
    cost = np.asarray(costs, dtype=float)
    strategy = pos * returns - cost
    equity = np.cumprod(1.0 + strategy)
    benchmark_equity = np.cumprod(1.0 + returns)
    n = len(returns)
    if n < 2 or not np.isfinite(strategy).all() or np.any(equity <= 0):
        raise ValueError("收益序列无效")
    years = n / annual_days
    peak = np.maximum.accumulate(np.concatenate([[1.0], equity]))
    dd = np.concatenate([[1.0], equity]) / peak - 1.0
    benchmark_peak = np.maximum.accumulate(np.concatenate([[1.0], benchmark_equity]))
    benchmark_dd = np.concatenate([[1.0], benchmark_equity]) / benchmark_peak - 1.0
    annual_return = float(equity[-1] ** (1.0 / years) - 1.0)
    annual_vol = float(np.std(strategy, ddof=1) * math.sqrt(annual_days))
    benchmark_annual_return = float(benchmark_equity[-1] ** (1.0 / years) - 1.0)
    benchmark_vol = float(np.std(returns, ddof=1) * math.sqrt(annual_days))
    turnover = float(cost.sum() / 0.001) if np.any(cost > 0) else 0.0
    entries = int(np.sum((pos == 1) & (np.concatenate([[0.0], pos[:-1]]) == 0)))
    out = {
        "n_return_days": n, "years": years,
        "total_return": float(equity[-1] - 1.0), "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "return_risk_ratio": annual_return / annual_vol if annual_vol > 0 else None,
        "max_drawdown": float(dd.min()), "annual_two_sided_turnover": turnover / years,
        "exposure": float(pos.mean()), "n_entries": entries,
        "benchmark_total_return": float(benchmark_equity[-1] - 1.0),
        "benchmark_annual_return": benchmark_annual_return,
        "benchmark_annual_volatility": benchmark_vol,
        "benchmark_return_risk_ratio": benchmark_annual_return / benchmark_vol if benchmark_vol > 0 else None,
        "benchmark_max_drawdown": float(benchmark_dd.min()),
    }
    daily = [{
        "date": dates[i], "asset_return": float(returns[i]), "position": int(pos[i]),
        "cost": float(cost[i]), "strategy_return_net": float(strategy[i]),
        "strategy_equity_net": float(equity[i]), "benchmark_equity": float(benchmark_equity[i]),
    } for i in range(n)]
    return out, daily


def block_bootstrap_delta(a, b, block=20, repetitions=1000, seed=20261107) -> dict:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    n = len(a)
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block)
    values = []
    for _ in range(repetitions):
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        values.append(float(np.mean(a[idx] - b[idx]) * 244))
    return {"statistic": "annualized arithmetic mean daily return difference",
            "point": float(np.mean(a - b) * 244),
            "ci95": [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))],
            "block": block, "repetitions": repetitions, "seed": seed}


def main() -> None:
    with CONFIG.open("rb") as handle:
        cfg = tomllib.load(handle)
    con = sqlite3.connect(f"file:{RESULT_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    features = [dict(r) for r in con.execute("SELECT * FROM feature_daily ORDER BY date")]
    con.close()
    if len(features) < 3000:
        raise RuntimeError(f"特征历史不完整，仅{len(features)}日")
    data = sqlite3.connect(f"file:{DATA_DB}?mode=ro", uri=True)
    bench_rows = data.execute(
        "SELECT date,open,close FROM benchmark_daily WHERE code='801003' ORDER BY date"
    ).fetchall()
    data.close()
    bench = {r[0]: {"open": float(r[1]), "close": float(r[2])} for r in bench_rows}
    rows = [r for r in features if r["date"] in bench]
    dates = [r["date"] for r in rows]
    if len(rows) != len(features):
        raise RuntimeError("特征与代理基准日历不一致")
    n = len(rows)
    close = np.asarray([bench[d]["close"] for d in dates])
    open_ = np.asarray([bench[d]["open"] for d in dates])

    fit_start, fit_end = cfg["controls"]["fit_start"], cfg["controls"]["fit_end"]
    fit = [r for r in rows if fit_start <= r["date"] <= fit_end]
    if len(fit) < 500:
        raise RuntimeError("普通对照的训练段不足")
    high_q, low_q = cfg["controls"]["high_quantile"], cfg["controls"]["low_quantile"]
    thresholds = {
        "average_correlation": float(np.quantile([r["industry_average_correlation"] for r in fit], high_q)),
        "leading_eigenvalue": float(np.quantile([r["correlation_leading_eigenvalue_share"] for r in fit], high_q)),
        "market_oversold": float(np.quantile([r["market_return_30"] for r in fit], low_q)),
        "market_volatility": float(np.quantile([r["market_realized_volatility_30"] for r in fit], high_q)),
        "h2_landscape_low": float(np.quantile([r["h2_landscape_l1"] for r in fit], low_q)),
    }
    raw = {
        "h2_count": np.asarray([r["h2_count"] <= 1 for r in rows], dtype=bool),
        "average_correlation": np.asarray([r["industry_average_correlation"] >= thresholds["average_correlation"] for r in rows]),
        "leading_eigenvalue": np.asarray([r["correlation_leading_eigenvalue_share"] >= thresholds["leading_eigenvalue"] for r in rows]),
        "market_oversold": np.asarray([r["market_return_30"] <= thresholds["market_oversold"] for r in rows]),
        "market_volatility": np.asarray([r["market_realized_volatility_30"] >= thresholds["market_volatility"] for r in rows]),
        "h2_landscape_low": np.asarray([r["h2_landscape_l1"] <= thresholds["h2_landscape_low"] for r in rows]),
    }
    for epsilon in (0.4, 0.6, 0.8):
        key = f"h2_betti_{str(epsilon).replace('.', 'p')}"
        raw[key] = np.asarray([r[key] <= 1 for r in rows], dtype=bool)

    periods = {
        "report_sample": (cfg["source"]["reported_backtest_start"], cfg["source"]["reported_backtest_end"]),
        "post_publication": (cfg["source"]["post_publication_start"], dates[-1]),
    }
    performance, daily_rows, signal_rows, bootstrap = [], [], [], {}
    cost_rate = float(cfg["execution"]["cost_per_side"])
    hold = int(cfg["execution"]["hold_days"])
    for model, signal in raw.items():
        for execution in ("report_close", "causal_open"):
            interval_dates, asset_returns, signal_sources = [], [], []
            for end in range(1, n):
                start = end - 1
                if execution == "report_close":
                    # 原始信号t对应t+1,...,t+4四段收盘收益；切片含t且止于t-3。
                    if start - hold + 1 < 0:
                        continue
                    source = signal_source(start, hold, execution)
                    asset_return = close[end] / close[end - 1] - 1.0
                else:
                    # 原始信号t对应t+1开盘至t+5开盘；每段开盘收益使用此前四次信号。
                    if start - hold < 0:
                        continue
                    source = signal_source(start, hold, execution)
                    asset_return = open_[end] / open_[end - 1] - 1.0
                interval_dates.append(dates[end])
                asset_returns.append(float(asset_return))
                signal_sources.append(source)
            interval_dates = np.asarray(interval_dates)
            asset_returns = np.asarray(asset_returns)
            date_array = np.asarray(dates)
            for period, (start_date, end_date) in periods.items():
                idx = np.flatnonzero((interval_dates >= start_date) & (interval_dates <= end_date))
                if len(idx) < 2:
                    continue
                # 每段独立起算，发布后区间不得继承发布前的持仓信号。
                period_signal = signal & (date_array >= start_date) & (date_array <= end_date)
                all_positions = np.asarray([period_signal[source].any() for source in signal_sources], dtype=int)
                p = all_positions[idx].copy()
                r = asset_returns[idx].copy()
                previous = np.concatenate([[0], p[:-1]])
                c = np.abs(p - previous) * cost_rate
                if len(p) and p[-1] == 1:
                    c[-1] += cost_rate  # 期末强制平仓，避免隐藏最后一笔成本。
                stats, daily = metric(interval_dates[idx], r, p, c)
                stats.update({"model": model, "model_name": MODEL_NAMES[model],
                              "execution": execution, "period": period,
                              "start": str(interval_dates[idx[0]]), "end": str(interval_dates[idx[-1]]),
                              "raw_signal_days_full_history": int(signal.sum())})
                performance.append(stats)
                for item in daily:
                    daily_rows.append({"model": model, "execution": execution, "period": period, **item})
        # 每个原始信号均保留，不用连续报警去重复包装事件数。
        for i in np.flatnonzero(signal):
            has_forward = i + hold + 1 < n
            signal_rows.append({
                "model": model, "date": dates[i],
                "is_raw_run_start": int(i == 0 or not signal[i - 1]),
                "h2_count": rows[i]["h2_count"], "n_nodes": rows[i]["n_nodes"],
                "h2_landscape_l1": rows[i]["h2_landscape_l1"],
                "industry_average_correlation": rows[i]["industry_average_correlation"],
                "market_return_30": rows[i]["market_return_30"],
                "forward_4d_close_return": float(close[i + hold] / close[i] - 1.0) if has_forward else None,
                "causal_4d_open_return": float(open_[i + hold + 1] / open_[i + 1] - 1.0) if has_forward else None,
                "forward_close_end": dates[i + hold] if has_forward else None,
                "causal_open_exit": dates[i + hold + 1] if has_forward else None,
            })

    signal_forward_stats = []
    for model in raw:
        for period, (start_date, end_date) in periods.items():
            subset = [x for x in signal_rows if x["model"] == model and start_date <= x["date"] <= end_date]
            close_returns = [x["forward_4d_close_return"] for x in subset if x["forward_4d_close_return"] is not None]
            open_returns = [x["causal_4d_open_return"] for x in subset if x["causal_4d_open_return"] is not None]
            signal_forward_stats.append({
                "model": model, "model_name": MODEL_NAMES[model], "period": period,
                "raw_signal_days": len(subset), "raw_run_starts": sum(x["is_raw_run_start"] for x in subset),
                "close_n": len(close_returns),
                "close_mean": float(np.mean(close_returns)) if close_returns else None,
                "close_median": float(np.median(close_returns)) if close_returns else None,
                "close_win_rate": float(np.mean(np.asarray(close_returns) > 0)) if close_returns else None,
                "open_n": len(open_returns),
                "open_mean": float(np.mean(open_returns)) if open_returns else None,
                "open_median": float(np.median(open_returns)) if open_returns else None,
                "open_win_rate": float(np.mean(np.asarray(open_returns) > 0)) if open_returns else None,
            })

    # 主模型与两个最相关普通机制对照的配对区块自助，使用相同净收益日期。
    perf_lookup = {(p["model"], p["execution"], p["period"]): p for p in performance}
    daily_lookup = {}
    for item in daily_rows:
        daily_lookup.setdefault((item["model"], item["execution"], item["period"]), []).append(item)
    for period in periods:
        base = daily_lookup[("h2_count", "causal_open", period)]
        for other in ("average_correlation", "market_oversold", "market_volatility"):
            comp = daily_lookup[(other, "causal_open", period)]
            assert [x["date"] for x in base] == [x["date"] for x in comp]
            bootstrap[f"h2_minus_{other}_{period}"] = block_bootstrap_delta(
                [x["strategy_return_net"] for x in base],
                [x["strategy_return_net"] for x in comp],
            )

    yearly = []
    for item in daily_rows:
        if item["model"] == "h2_count" and item["execution"] == "causal_open":
            yearly.append(item)
    yearly_rows = []
    for period in periods:
        subset = [x for x in yearly if x["period"] == period]
        for year in sorted({x["date"][:4] for x in subset}):
            part = [x for x in subset if x["date"].startswith(year)]
            yearly_rows.append({"period": period, "year": year,
                "h2_return_net": float(np.prod([1 + x["strategy_return_net"] for x in part]) - 1),
                "benchmark_return": float(np.prod([1 + x["asset_return"] for x in part]) - 1),
                "exposure": float(np.mean([x["position"] for x in part]))})

    cited = {}
    h2_signals = [x for x in signal_rows if x["model"] == "h2_count"]
    for month in cfg["audit"]["report_cited_periods"]:
        cited[month] = [x["date"] for x in h2_signals if x["date"].startswith(month)]
    summary = {
        "protocol": "xy-replication-v1.0",
        "config_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "source": cfg["source"], "topology": cfg["topology"], "universe": cfg["universe"],
        "execution": cfg["execution"], "threshold_fit": {"start": fit_start, "end": fit_end,
                                                        "n": len(fit), "values": thresholds},
        "feature_range": {"first": dates[0], "last": dates[-1], "n": n},
        "h2_signal_days": int(raw["h2_count"].sum()),
        "h2_signal_run_starts": int(sum(raw["h2_count"][i] and (i == 0 or not raw["h2_count"][i - 1]) for i in range(n))),
        "cited_period_signal_dates": cited,
        "report_reference_standalone": {"annual_return": 0.1287, "annual_volatility": 0.1333,
            "return_risk_ratio": 0.97, "max_drawdown": -0.1634,
            "annual_two_sided_turnover": 15.04, "benchmark_annual_return": 0.0069,
            "benchmark_annual_volatility": 0.2273, "benchmark_max_drawdown": -0.4068,
            "note": "研报表1；标的为万得全A，本项目用申万A指代理，绩效不可逐项等同"},
        "performance": performance, "signal_forward_stats": signal_forward_stats, "bootstrap": bootstrap,
        "limitations": [
            "N的精确定义未在公开全文文字中说明；主解释为有限H2持久区间数，固定epsilon结果另列",
            "申万二级代码名单为2026-11-07快照；逐日仅纳入有完整30日收益的指数，未获得2025年7月原版名单快照",
            "万得全A历史未获得，801003申万A指仅为代理；不是原报告绩效的精确复现",
            "综合择时模型缺少另外五类宏观指标，本报告只复现standalone拓扑信号",
        ],
    }
    (OUT / "xy_replication_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    write_csv(OUT / "xy_performance.csv", performance)
    write_csv(OUT / "xy_signals.csv", signal_rows)
    write_csv(OUT / "xy_signal_forward_stats.csv", signal_forward_stats)
    write_csv(OUT / "xy_daily_returns.csv", daily_rows)
    write_csv(OUT / "xy_yearly_returns.csv", yearly_rows)
    feature_export = [{k: r[k] for k in r if k != "config_sha256"} for r in rows]
    write_csv(OUT / "xy_features.csv", feature_export)
    print(json.dumps({"status": "ok", "performance_rows": len(performance),
                      "signal_rows": len(signal_rows), "h2_signal_days": summary["h2_signal_days"],
                      "cited": cited, "summary": str(OUT / "xy_replication_summary.json")},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
