"""运行Gate 1开发期OOF实验；2025年起最终测试集保持封存。

运行前必须已冻结config/gate1.toml。不得在查看结果后修改预登记再使用同名输出。
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.baselines import ordinary_risk_features  # noqa: E402
from src.config import DEFAULT_CONFIG, load_config  # noqa: E402
from src.data.pit_panel import (  # noqa: E402
    build_fixed_panel, build_point_clouds, connect_ro, load_benchmark,
)
from src.evaluation import (  # noqa: E402
    collapse_runs, evaluate_ews, walk_forward_date_splits,
)
from src.labels import market_drawdown_label, threshold_crossing_events  # noqa: E402
from src.topology.features import extract_single_parameter_features  # noqa: E402

GATE1_CONFIG = ROOT / "config" / "gate1.toml"


def make_model(spec: dict) -> LogisticRegression:
    return LogisticRegression(
        C=float(spec["C"]), penalty=spec["penalty"], solver=spec["solver"],
        max_iter=int(spec["max_iter"]), class_weight=spec["class_weight"],
        random_state=int(spec["random_state"]),
    )


def moving_block_delta(y, score0, score1, block: int, repetitions: int, seed: int) -> dict:
    y = np.asarray(y, dtype=int)
    score0, score1 = np.asarray(score0), np.asarray(score1)
    n = len(y)
    if n < block:
        raise ValueError("OOF样本少于bootstrap区块长度")
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block)
    deltas = []
    for _ in range(repetitions):
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        if len(np.unique(y[idx])) < 2:
            continue
        deltas.append(
            average_precision_score(y[idx], score1[idx])
            - average_precision_score(y[idx], score0[idx])
        )
    if not deltas:
        raise RuntimeError("bootstrap未产生有效双类别样本")
    return {
        "repetitions_requested": repetitions, "repetitions_valid": len(deltas),
        "block_length": block, "seed": seed,
        "delta_median": float(np.median(deltas)),
        "ci_95_lower": float(np.quantile(deltas, 0.025)),
        "ci_95_upper": float(np.quantile(deltas, 0.975)),
    }


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_panel(panel_key: str, cfg, gate1: dict, conn, bench_data) -> dict:
    started = time.time()
    bench_dates, bench_levels, labels, label_ends = bench_data
    label_by_date = dict(zip(bench_dates, labels))
    label_end_by_date = dict(zip(bench_dates, label_ends))
    bench_pos = {d: i for i, d in enumerate(bench_dates)}
    bench_simple_returns = np.full(len(bench_dates), np.nan)
    bench_simple_returns[1:] = bench_levels[1:] / bench_levels[:-1] - 1.0

    segment = build_fixed_panel(cfg, panel_key, conn)
    clouds = build_point_clouds(segment, cfg.window)
    tda_rows = extract_single_parameter_features(clouds)
    spec = cfg.raw["panels"][panel_key]
    m0_names = list(gate1["features"]["m0"])
    m1_added = list(gate1["features"]["m1_added"])
    samples = []
    for i in range(1, len(clouds)):
        date, cloud = clouds[i]
        y = label_by_date.get(date)
        label_end = label_end_by_date.get(date)
        if y is None or label_end is None or label_end >= cfg.test_start:
            continue
        pos = bench_pos[date]
        r = bench_simple_returns[pos - cfg.window + 1:pos + 1]
        if len(r) != cfg.window or not np.isfinite(r).all():
            raise ValueError(f"{panel_key} {date}市场收益窗口无效")
        m0 = ordinary_risk_features(cloud, r)
        samples.append({
            "date": date, "y": int(bool(y)), "label_end": label_end,
            **m0, **{k: tda_rows[i][k] for k in m1_added},
        })
    dates = [s["date"] for s in samples]
    label_end_samples = [s["label_end"] for s in samples]
    folds = list(walk_forward_date_splits(
        dates, label_end_samples, int(spec["initial_train_days"]), int(spec["val_days"]),
    ))
    X0 = np.asarray([[s[k] for k in m0_names] for s in samples], dtype=float)
    X1 = np.asarray([[s[k] for k in m0_names + m1_added] for s in samples], dtype=float)
    y = np.asarray([s["y"] for s in samples], dtype=int)
    if not np.isfinite(X0).all() or not np.isfinite(X1).all():
        raise ValueError(f"{panel_key}模型输入含NaN/Inf")

    n = len(samples)
    score0 = np.full(n, np.nan)
    score1 = np.full(n, np.nan)
    threshold0 = np.full(n, np.nan)
    threshold1 = np.full(n, np.nan)
    fold_id = np.full(n, -1, dtype=int)
    single_class_folds = []
    quantile = float(gate1["threshold"]["quantile"])
    for f in folds:
        tr = np.asarray(f["train_indices"], dtype=int)
        va = np.asarray(f["validation_indices"], dtype=int)
        single_class = len(np.unique(y[tr])) < 2
        if single_class:
            single_class_folds.append({"fold": f["fold"], "sole_class": int(y[tr][0])})
        for X, scores, thresholds in ((X0, score0, threshold0), (X1, score1, threshold1)):
            if single_class:
                train_probability = np.full(len(tr), float(y[tr][0]))
                scores[va] = float(y[tr][0])
            else:
                scaler = StandardScaler()
                X_train = scaler.fit_transform(X[tr])
                X_val = scaler.transform(X[va])
                model = make_model(gate1["model"])
                model.fit(X_train, y[tr])
                train_probability = model.predict_proba(X_train)[:, 1]
                scores[va] = model.predict_proba(X_val)[:, 1]
            thresholds[va] = np.quantile(train_probability, quantile)
        fold_id[va] = f["fold"]

    oof = np.flatnonzero(fold_id >= 0)
    assert len(oof) == sum(f["n_validation"] for f in folds)
    assert len(set(dates[i] for i in oof)) == len(oof)
    assert max(label_end_samples) < cfg.test_start
    assert dates[-1] < cfg.test_start
    ap0 = float(average_precision_score(y[oof], score0[oof]))
    ap1 = float(average_precision_score(y[oof], score1[oof]))
    delta = ap1 - ap0
    bootstrap = moving_block_delta(
        y[oof], score0[oof], score1[oof],
        int(gate1["statistics"]["block_length"]),
        int(gate1["statistics"]["repetitions"]),
        int(gate1["statistics"]["seed"]),
    )
    fold_metrics = []
    for f in folds:
        va = np.asarray(f["validation_indices"], dtype=int)
        fold_metrics.append({
            "fold": f["fold"], "validation_start": f["validation_start"],
            "validation_end": f["validation_end"], "n": len(va),
            "n_positive": int(y[va].sum()),
            "M0_PR_AUC": float(average_precision_score(y[va], score0[va])) if len(np.unique(y[va])) == 2 else None,
            "M1_PR_AUC": float(average_precision_score(y[va], score1[va])) if len(np.unique(y[va])) == 2 else None,
        })

    events = threshold_crossing_events(
        bench_dates, bench_levels, cfg.horizon, cfg.drawdown,
        int(gate1["event_evaluation"]["merge_gap_trading_days"]),
    )
    first_pos, last_pos = bench_pos[dates[oof[0]]], bench_pos[dates[oof[-1]]]
    lead = int(gate1["event_evaluation"]["lead_days"])
    lag = int(gate1["event_evaluation"]["lag_days"])
    eligible_events = [
        e["onset_index"] for e in events
        if e["onset_index"] - lead >= first_pos and e["onset_index"] + lag <= last_pos
    ]
    event_metrics = {}
    alarm_counts = {}
    for name, scores, thresholds in (("M0", score0, threshold0), ("M1", score1, threshold1)):
        alarm_dates = [dates[i] for i in oof if scores[i] > thresholds[i]]
        alarm_positions = [bench_pos[d] for d in alarm_dates]
        alarm_events = collapse_runs(alarm_positions)
        alarm_counts[name] = {"alarm_days": len(alarm_positions), "alarm_events": len(alarm_events)}
        event_metrics[name] = evaluate_ews(
            eligible_events, alarm_events, lead=lead, lag=lag,
            total_days=last_pos - first_pos + 1,
            trading_days_per_year=cfg.trading_days_per_year,
        )

    feature_fields = ["date", "y", "label_end", *m0_names, *m1_added]
    feature_path = ROOT / "outputs" / f"gate1_features_{panel_key}.csv"
    write_csv(feature_path, samples, feature_fields)
    oof_rows = []
    for i in oof:
        oof_rows.append({
            "date": dates[i], "y": int(y[i]), "label_end": label_end_samples[i],
            "fold": int(fold_id[i]), "M0_score": float(score0[i]), "M1_score": float(score1[i]),
            "M0_threshold": float(threshold0[i]), "M1_threshold": float(threshold1[i]),
            "M0_alarm": int(score0[i] > threshold0[i]), "M1_alarm": int(score1[i] > threshold1[i]),
        })
    oof_path = ROOT / "outputs" / f"gate1_oof_{panel_key}.csv"
    write_csv(oof_path, oof_rows, list(oof_rows[0]))

    return {
        "panel": panel_key, "role": "confirmatory" if panel_key == "p16" else "robustness",
        "n_industries": len(segment.codes), "n_model_ready_labeled": n,
        "n_oof": len(oof), "n_positive_oof": int(y[oof].sum()),
        "positive_rate_oof": float(y[oof].mean()),
        "first_model_ready_date": dates[0], "last_model_ready_date": dates[-1],
        "last_development_label_end": max(label_end_samples),
        "first_oof_date": dates[oof[0]], "last_oof_date": dates[oof[-1]],
        "n_folds": len(folds), "single_class_folds": single_class_folds,
        "M0_PR_AUC": ap0, "M1_PR_AUC": ap1,
        "delta_PR_AUC_M1_minus_M0": delta, "paired_block_bootstrap": bootstrap,
        "development_gate_pass": bool(delta > 0 and bootstrap["ci_95_lower"] > 0),
        "fold_metrics": fold_metrics, "eligible_crisis_onsets": [
            bench_dates[i] for i in eligible_events
        ],
        "alarm_counts": alarm_counts, "event_metrics": event_metrics,
        "features_csv": str(feature_path), "oof_csv": str(oof_path),
        "runtime_seconds": round(time.time() - started, 3),
        "test_rows_read": 0,
    }


def main() -> dict:
    with GATE1_CONFIG.open("rb") as f:
        gate1 = tomllib.load(f)
    if gate1["protocol"]["status"] != "frozen_before_results":
        raise ValueError("Gate 1配置不是frozen_before_results状态")
    cfg = load_config()
    if cfg.end >= cfg.test_start or gate1["protocol"]["test_start"] != cfg.test_start:
        raise ValueError("开发/测试边界不一致")
    if cfg.window != int(gate1["features"]["window"]):
        raise ValueError("Gate 0与Gate 1窗口不一致")
    conn = connect_ro(cfg.db_path)
    try:
        bench_dates, bench_levels_tuple = load_benchmark(cfg, conn)
        labels = market_drawdown_label(bench_dates, bench_levels_tuple, cfg.horizon, cfg.drawdown)
        label_ends = [
            bench_dates[i + cfg.horizon] if i + cfg.horizon < len(bench_dates) else None
            for i in range(len(bench_dates))
        ]
        bench_data = (bench_dates, np.asarray(bench_levels_tuple, dtype=float), labels, label_ends)
        results = {
            key: run_panel(key, cfg, gate1, conn, bench_data)
            for key in ("p16", "p27", "p31")
        }
    finally:
        conn.close()
    main_result = results["p16"]
    summary = {
        "protocol_version": gate1["protocol"]["version"],
        "generated_at": datetime.now().astimezone().isoformat(),
        "gate0_config_sha256": hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest(),
        "gate1_config_sha256": hashlib.sha256(GATE1_CONFIG.read_bytes()).hexdigest(),
        "preregistered_rule": gate1["statistics"]["development_gate_pass"],
        "development_gate_pass": main_result["development_gate_pass"],
        "final_test_status": "sealed_not_read_not_scored",
        "test_rows_read": 0,
        "results": results,
    }
    path = ROOT / "outputs" / "gate1_development_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "development_gate_pass": summary["development_gate_pass"],
        "panels": {
            k: {
                "M0_PR_AUC": v["M0_PR_AUC"], "M1_PR_AUC": v["M1_PR_AUC"],
                "delta": v["delta_PR_AUC_M1_minus_M0"],
                "ci95": [v["paired_block_bootstrap"]["ci_95_lower"], v["paired_block_bootstrap"]["ci_95_upper"]],
                "event_metrics": v["event_metrics"],
            } for k, v in results.items()
        },
        "final_test_status": summary["final_test_status"], "summary": str(path),
    }, ensure_ascii=False, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    main()
