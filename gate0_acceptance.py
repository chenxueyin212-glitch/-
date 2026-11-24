"""Gate 0工程验收：固定面板、合成标签、日期purge与完整逐折切分表。

默认配置只读取2024-12-31及以前数据；2025年起最终测试集保持封存。
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DEFAULT_CONFIG, load_config  # noqa: E402
from src.data.pit_panel import (  # noqa: E402
    build_fixed_panel, build_point_clouds, connect_ro, load_benchmark,
)
from src.evaluation import walk_forward_date_splits  # noqa: E402
from src.labels import market_drawdown_label  # noqa: E402


def main() -> dict:
    cfg = load_config()
    out_dir = ROOT / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "protocol_version": cfg.raw["protocol"]["version"],
        "generated_at": datetime.now().astimezone().isoformat(),
        "config_sha256": hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest(),
        "test_start": cfg.test_start,
        "test_policy": "sealed_no_2025_rows_read",
        "panels": {},
    }
    all_passed = True
    conn = connect_ro(cfg.db_path)
    try:
        bench_dates, bench_levels = load_benchmark(cfg, conn)
        assert bench_dates[-1] < cfg.test_start
        labels = market_drawdown_label(bench_dates, bench_levels, cfg.horizon, cfg.drawdown)
        label_by_date = dict(zip(bench_dates, labels))
        label_end_by_date = {
            d: bench_dates[i + cfg.horizon] if i + cfg.horizon < len(bench_dates) else None
            for i, d in enumerate(bench_dates)
        }
        valid_labels = [v for v in labels if v is not None]
        report["benchmark"] = {
            "definition": "I_t=I_{t-1}*(1+0.5*(r_000001_t+r_399001_t)); common dates only",
            "n_dates": len(bench_dates), "first_date": bench_dates[0], "last_date": bench_dates[-1],
            "n_labeled": len(valid_labels), "n_positive": sum(bool(v) for v in valid_labels),
            "n_unlabeled_tail": len(labels) - len(valid_labels),
            "development_label_boundary": "label_end(t) < 2025-01-01",
        }
        for panel_key in ("p16", "p27", "p31"):
            spec = cfg.raw["panels"][panel_key]
            segment = build_fixed_panel(cfg, panel_key, conn)
            clouds = build_point_clouds(segment, cfg.window)
            # M1的D特征需要前一个点云，故首个点云不进入监督样本。
            candidate_dates = [d for d, _ in clouds[1:]]
            eligible_dates, eligible_label_ends = [], []
            for d in candidate_dates:
                y = label_by_date.get(d)
                label_end = label_end_by_date.get(d)
                if y is not None and label_end is not None and label_end < cfg.test_start:
                    eligible_dates.append(d)
                    eligible_label_ends.append(label_end)
            folds = list(walk_forward_date_splits(
                eligible_dates, eligible_label_ends,
                int(spec["initial_train_days"]), int(spec["val_days"]),
            ))
            assert folds, f"{panel_key}未生成任何切分折"
            validation_dates = [eligible_dates[i] for f in folds for i in f["validation_indices"]]
            assert len(validation_dates) == len(set(validation_dates)), f"{panel_key}验证日期重叠"
            expected_oof = set(eligible_dates[int(spec["initial_train_days"]):])
            assert set(validation_dates) == expected_oof, f"{panel_key}OOF日期未完整覆盖"
            for f in folds:
                assert f["max_train_label_end"] < f["validation_start"]
                assert f["n_validation"] <= int(spec["val_days"])
            assert max(eligible_label_ends) < cfg.test_start
            assert eligible_dates[-1] < cfg.test_start

            short = replace(
                segment, dates=segment.dates[:300],
                closes={c: v[:300] for c, v in segment.closes.items()},
                returns={c: v[:300] for c, v in segment.returns.items()},
            )
            truncated = replace(
                segment, dates=segment.dates[:290],
                closes={c: v[:290] for c, v in segment.closes.items()},
                returns={c: v[:290] for c, v in segment.returns.items()},
            )
            full_clouds = build_point_clouds(short, cfg.window)
            truncated_clouds = build_point_clouds(truncated, cfg.window)
            future_unchanged = (
                full_clouds[:len(truncated_clouds)] == truncated_clouds
            )
            assert future_unchanged

            fields = [
                "fold", "train_raw_start", "train_raw_end", "train_used_start", "train_used_end",
                "max_train_label_end", "validation_start", "validation_end", "n_train_raw",
                "n_train", "n_purged", "n_validation",
            ]
            csv_path = out_dir / f"gate0_splits_{panel_key}.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for fold in folds:
                    writer.writerow({k: fold[k] for k in fields})
            report["panels"][panel_key] = {
                "n_industries": len(segment.codes), "codes": list(segment.codes),
                "panel_dates": len(segment.dates), "panel_first": segment.dates[0],
                "panel_last": segment.dates[-1], "model_ready_labeled_dates": len(eligible_dates),
                "first_model_ready_date": eligible_dates[0], "last_development_label_end": max(eligible_label_ends),
                "n_folds": len(folds), "first_validation_start": folds[0]["validation_start"],
                "last_validation_end": folds[-1]["validation_end"],
                "last_fold_validation_days": folds[-1]["n_validation"],
                "purge_counts": sorted(set(f["n_purged"] for f in folds)),
                "future_perturbation_unchanged": future_unchanged,
                "split_csv": str(csv_path), "passed": True,
            }
            print(json.dumps({panel_key: report["panels"][panel_key]}, ensure_ascii=False), flush=True)
    finally:
        conn.close()
    report["overall_pass"] = all_passed
    path = out_dir / "gate0_acceptance.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"overall_pass": all_passed, "report": str(path)}, ensure_ascii=False), flush=True)
    return report


if __name__ == "__main__":
    main()
