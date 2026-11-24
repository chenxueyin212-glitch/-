"""独立复核兴业复现：日期、信号、收益、仓位和汇总指标。"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
CONFIG = ROOT / "config" / "xy_replication.toml"


def read_csv(name):
    with (OUT / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def close_enough(a, b, tol=1e-9):
    return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)


def validate_pit(bench) -> dict | None:
    """若时代口径变体已生成，则用相同原始行情独立重算其全部日收益与指标。"""
    path = OUT / "xy_pit_sensitivity_summary.json"
    if not path.exists():
        return None
    summary = json.loads(path.read_text(encoding="utf-8"))
    con = sqlite3.connect(f"file:{OUT / 'xy_replication_pit_results.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    features = [dict(r) for r in con.execute("SELECT * FROM feature_daily ORDER BY date")]
    con.close()
    assert len(features) == len({r["date"] for r in features}) == summary["feature_range"]["n"]
    assert all(r["config_sha256"] == summary["variant_sha256"] for r in features)
    dates = [r["date"] for r in features]
    pos = {d: i for i, d in enumerate(dates)}
    opens = np.asarray([bench[d][0] for d in dates])
    closes = np.asarray([bench[d][1] for d in dates])
    signals = read_csv("xy_pit_signals.csv")
    expected = {r["date"] for r in features if r["h2_count"] <= 1}
    assert {r["date"] for r in signals} == expected
    forward_checked = 0
    for row in signals:
        i = pos[row["date"]]
        if row["forward_4d_close_return"]:
            assert close_enough(row["forward_4d_close_return"], closes[i+4] / closes[i] - 1)
            forward_checked += 1
        if row["causal_4d_open_return"]:
            assert close_enough(row["causal_4d_open_return"], opens[i+5] / opens[i+1] - 1)
    daily = read_csv("xy_pit_daily_returns.csv")
    grouped = defaultdict(list)
    for row in daily:
        grouped[(row["execution"], row["period"])].append(row)
    performance = {(r["execution"], r["period"]): r for r in read_csv("xy_pit_performance.csv")}
    assert set(grouped) == set(performance)
    raw = {r["date"] for r in signals}
    checked_positions = 0
    for key, rows in grouped.items():
        execution, period = key
        start_date, end_date = rows[0]["date"], rows[-1]["date"]
        period_raw = {d for d in raw if start_date <= d <= end_date}
        previous_position = 0
        for j, row in enumerate(rows):
            end = pos[row["date"]]
            start = end - 1
            if execution == "report_close":
                source = range(start-3, start+1)
                asset_return = closes[end] / closes[end-1] - 1
            else:
                source = range(start-4, start)
                asset_return = opens[end] / opens[end-1] - 1
            expected_position = int(any(dates[k] in period_raw for k in source))
            assert int(row["position"]) == expected_position, (key, row["date"])
            assert close_enough(row["asset_return"], asset_return)
            expected_cost = abs(expected_position-previous_position) * 0.001
            if j == len(rows)-1 and expected_position:
                expected_cost += 0.001
            assert close_enough(row["cost"], expected_cost)
            assert close_enough(row["strategy_return_net"], expected_position*asset_return-expected_cost)
            previous_position = expected_position
            checked_positions += 1
        strategy = np.asarray([float(r["strategy_return_net"]) for r in rows])
        asset = np.asarray([float(r["asset_return"]) for r in rows])
        equity = np.cumprod(1+strategy)
        stats = performance[key]
        assert close_enough(stats["total_return"], equity[-1]-1)
        assert close_enough(stats["annual_return"], equity[-1]**(244/len(rows))-1)
        assert close_enough(stats["annual_volatility"], np.std(strategy, ddof=1)*math.sqrt(244))
        curve = np.concatenate([[1.0], equity])
        assert close_enough(stats["max_drawdown"], np.min(curve/np.maximum.accumulate(curve)-1))
        assert close_enough(stats["benchmark_total_return"], np.prod(1+asset)-1)
    validation = {"overall_pass": True, "variant_sha256": summary["variant_sha256"],
                  "n_features": len(features), "n_signal_days": len(signals),
                  "forward_returns_recalculated": forward_checked,
                  "daily_positions_recalculated": checked_positions,
                  "performance_groups_recalculated": len(grouped),
                  "cited_period_signal_dates": summary["cited_period_signal_dates"],
                  "gate1_touched": False}
    (OUT / "xy_pit_validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    return validation


def main() -> None:
    summary = json.loads((OUT / "xy_replication_summary.json").read_text(encoding="utf-8"))
    config_hash = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    assert summary["config_sha256"] == config_hash
    con = sqlite3.connect(f"file:{OUT / 'xy_replication_results.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    features = [dict(r) for r in con.execute("SELECT * FROM feature_daily ORDER BY date")]
    con.close()
    assert len(features) == len({r["date"] for r in features}) == summary["feature_range"]["n"]
    assert all(r["config_sha256"] == config_hash for r in features)
    assert all(4 <= r["n_nodes"] <= 124 for r in features)
    assert all(r["h2_count"] >= 0 and math.isfinite(r["h2_landscape_l1"]) for r in features)
    dates = [r["date"] for r in features]
    pos = {d: i for i, d in enumerate(dates)}
    data = sqlite3.connect(f"file:{OUT / 'xy_replication_data.db'}?mode=ro", uri=True)
    bench = {r[0]: (float(r[1]), float(r[2])) for r in data.execute(
        "SELECT date,open,close FROM benchmark_daily WHERE code='801003' ORDER BY date")}
    data.close()
    opens = np.asarray([bench[d][0] for d in dates])
    closes = np.asarray([bench[d][1] for d in dates])

    signals = read_csv("xy_signals.csv")
    expected_h2 = {r["date"] for r in features if r["h2_count"] <= 1}
    actual_h2 = {r["date"] for r in signals if r["model"] == "h2_count"}
    assert actual_h2 == expected_h2
    checked_forward = 0
    for row in signals:
        if not row["forward_close_end"]:
            continue
        i = pos[row["date"]]
        expected_close = closes[i + 4] / closes[i] - 1.0
        expected_open = opens[i + 5] / opens[i + 1] - 1.0
        assert close_enough(row["forward_4d_close_return"], expected_close)
        assert close_enough(row["causal_4d_open_return"], expected_open)
        assert row["forward_close_end"] == dates[i + 4]
        assert row["causal_open_exit"] == dates[i + 5]
        checked_forward += 1

    daily = read_csv("xy_daily_returns.csv")
    grouped = defaultdict(list)
    for row in daily:
        grouped[(row["model"], row["execution"], row["period"])].append(row)
    performance = {(r["model"], r["execution"], r["period"]): r for r in read_csv("xy_performance.csv")}
    assert set(grouped) == set(performance)
    raw_by_model = defaultdict(set)
    for row in signals:
        raw_by_model[row["model"]].add(row["date"])
    period_bounds = {key: (values[0]["date"], values[-1]["date"]) for key, values in grouped.items()}
    checked_positions = 0
    for key, rows in grouped.items():
        model, execution, period = key
        start_date, end_date = period_bounds[key]
        raw = {d for d in raw_by_model[model] if start_date <= d <= end_date}
        previous_position = 0
        for j, row in enumerate(rows):
            end = pos[row["date"]]
            start = end - 1
            if execution == "report_close":
                source = range(start - 3, start + 1)
                asset_return = closes[end] / closes[end - 1] - 1.0
            else:
                source = range(start - 4, start)
                asset_return = opens[end] / opens[end - 1] - 1.0
            expected_position = int(any(dates[k] in raw for k in source))
            assert int(row["position"]) == expected_position, (key, row["date"])
            assert close_enough(row["asset_return"], asset_return)
            expected_cost = abs(expected_position - previous_position) * 0.001
            if j == len(rows) - 1 and expected_position:
                expected_cost += 0.001
            assert close_enough(row["cost"], expected_cost)
            assert close_enough(row["strategy_return_net"], expected_position * asset_return - expected_cost)
            previous_position = expected_position
            checked_positions += 1
        strategy = np.asarray([float(r["strategy_return_net"]) for r in rows])
        asset = np.asarray([float(r["asset_return"]) for r in rows])
        equity = np.cumprod(1 + strategy)
        benchmark_equity = np.cumprod(1 + asset)
        stats = performance[key]
        assert close_enough(stats["total_return"], equity[-1] - 1)
        assert close_enough(stats["benchmark_total_return"], benchmark_equity[-1] - 1)
        assert close_enough(stats["annual_return"], equity[-1] ** (244 / len(rows)) - 1)
        assert close_enough(stats["annual_volatility"], np.std(strategy, ddof=1) * math.sqrt(244))
        curve = np.concatenate([[1.0], equity])
        mdd = np.min(curve / np.maximum.accumulate(curve) - 1)
        assert close_enough(stats["max_drawdown"], mdd)

    validation = {
        "overall_pass": True, "config_sha256": config_hash,
        "n_features": len(features), "feature_first": dates[0], "feature_last": dates[-1],
        "n_signal_rows": len(signals), "forward_returns_recalculated": checked_forward,
        "daily_positions_recalculated": checked_positions,
        "performance_groups_recalculated": len(grouped),
        "h2_signal_days": len(actual_h2),
        "cited_period_signal_dates": summary["cited_period_signal_dates"],
        "causality": "raw signal t only enters t+1..t+4 close returns or t+1-open..t+5-open returns",
        "universe": "124 series active through report sample end; daily complete 30-return windows only",
        "gate1_touched": False,
    }
    (OUT / "xy_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    pit_validation = validate_pit(bench)
    if pit_validation is not None:
        print(json.dumps({"pit_sensitivity": pit_validation}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
