"""独立复核Gate 1输出，不重训、不改参、不读取2025年测试集。"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DEFAULT_CONFIG, load_config  # noqa: E402
from src.data.pit_panel import build_fixed_panel, build_point_clouds, connect_ro  # noqa: E402
from src.topology.features import extract_single_parameter_features  # noqa: E402


def main() -> dict:
    out = ROOT / "outputs"
    summary = json.loads((out / "gate1_development_summary.json").read_text(encoding="utf-8"))
    assert summary["gate0_config_sha256"] == hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest()
    gate1_path = ROOT / "config" / "gate1.toml"
    assert summary["gate1_config_sha256"] == hashlib.sha256(gate1_path.read_bytes()).hexdigest()
    assert summary["final_test_status"] == "sealed_not_read_not_scored"
    checks = {}
    for panel, result in summary["results"].items():
        rows = list(csv.DictReader((out / f"gate1_oof_{panel}.csv").open(encoding="utf-8-sig")))
        assert len(rows) == result["n_oof"]
        assert len({r["date"] for r in rows}) == len(rows)
        assert all(r["date"] < "2025-01-01" and r["label_end"] < "2025-01-01" for r in rows)
        y = np.asarray([int(r["y"]) for r in rows])
        s0 = np.asarray([float(r["M0_score"]) for r in rows])
        s1 = np.asarray([float(r["M1_score"]) for r in rows])
        assert np.isfinite(s0).all() and np.isfinite(s1).all()
        ap0 = float(average_precision_score(y, s0))
        ap1 = float(average_precision_score(y, s1))
        assert math.isclose(ap0, result["M0_PR_AUC"], abs_tol=1e-14)
        assert math.isclose(ap1, result["M1_PR_AUC"], abs_tol=1e-14)
        assert math.isclose(ap1 - ap0, result["delta_PR_AUC_M1_minus_M0"], abs_tol=1e-14)
        feature_rows = list(csv.DictReader((out / f"gate1_features_{panel}.csv").open(encoding="utf-8-sig")))
        assert len(feature_rows) == result["n_model_ready_labeled"]
        for row in feature_rows:
            assert row["date"] < "2025-01-01" and row["label_end"] < "2025-01-01"
            assert all(math.isfinite(float(v)) for k, v in row.items() if k not in {"date", "label_end"})
        valid_fold_deltas = [
            f["M1_PR_AUC"] - f["M0_PR_AUC"] for f in result["fold_metrics"]
            if f["M0_PR_AUC"] is not None and f["M1_PR_AUC"] is not None
        ]
        checks[panel] = {
            "metric_recompute_exact": True, "no_2025_dates_or_label_ends": True,
            "finite_features_and_scores": True, "oof_unique_dates": True,
            "valid_folds": len(valid_fold_deltas),
            "positive_delta_folds": sum(d > 0 for d in valid_fold_deltas),
            "negative_delta_folds": sum(d < 0 for d in valid_fold_deltas),
            "zero_delta_folds": sum(d == 0 for d in valid_fold_deltas),
            "n_positive_oof": int(y.sum()),
            "interpretable": int(y.sum()) >= 20,
        }

    cfg = load_config()
    conn = connect_ro(cfg.db_path)
    try:
        segment = build_fixed_panel(cfg, "p31", conn)
    finally:
        conn.close()
    clouds = build_point_clouds(segment, cfg.window)[:20]
    full = extract_single_parameter_features(clouds)
    prefix = extract_single_parameter_features(clouds[:15])
    assert full[:15] == prefix
    report = {
        "overall_pass": True, "config_hashes_unchanged": True,
        "single_parameter_future_perturbation_unchanged": True,
        "final_test_status": "sealed_not_read_not_scored",
        "panels": checks,
        "note": "p31只有1个OOF正例，标记为不可解释；不把其PR-AUC当作稳定绩效证据。",
    }
    path = out / "gate1_validation.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
