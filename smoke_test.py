"""端到端最小验证：数据层 + 因果自检 + 评估层 + 拓扑后端可用性。

不依赖任何第三方库也能跑完；拓扑部分仅在 gudhi/ripser 可用时执行。
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config                       # noqa: E402
from src.data.pit_panel import (                         # noqa: E402
    build_pit_segments, build_point_clouds, connect_ro, load_benchmark,
)
from src.evaluation import (                             # noqa: E402
    detect_ews, evaluate_ews, walk_forward_splits,
)
from src.labels import market_drawdown_label            # noqa: E402
from src.topology.features import backend_status        # noqa: E402


def main() -> dict:
    report: dict = {"backend": backend_status()}
    cfg = load_config()
    report["config"] = {
        "db": str(cfg.db_path), "start": cfg.start, "end": cfg.end,
        "window": cfg.window, "horizon": cfg.horizon, "drawdown": cfg.drawdown,
    }

    conn = connect_ro(cfg.db_path)
    try:
        report["db_tables"] = {
            t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("equity_daily_raw", "index_daily_raw",
                      "sw_industry_daily_clean", "trade_calendar")
        }
        segments = build_pit_segments(cfg, conn)
        report["segments"] = [
            {"start": s.start, "end": s.end, "n_codes": len(s.codes),
             "n_dates": len(s.dates), "codes": list(s.codes[:8])}
            for s in segments
        ]
        if not segments:
            raise RuntimeError("没有构造出任何 PIT 面板分段")

        seg = segments[0]
        short = replace(
            seg,
            dates=seg.dates[:300],
            closes={c: v[:300] for c, v in seg.closes.items()},
            returns={c: v[:300] for c, v in seg.returns.items()},
        )
        w = 20
        clouds = build_point_clouds(short, w)
        report["pointclouds"] = {
            "segment": seg.start, "n_windows": len(clouds),
            "window": w, "dim": len(short.codes),
            "first_date": clouds[0][0] if clouds else None,
            "last_date": clouds[-1][0] if clouds else None,
        }

        # 因果自检：窗口末行必须等于 t 日收益，首行必须等于 t-w+1 日收益
        idx = {d: i for i, d in enumerate(short.dates)}
        violations = 0
        for date, cloud in clouds:
            t = idx[date]
            last = [short.returns[c][t] for c in short.codes]
            first = [short.returns[c][t - w + 1] for c in short.codes]
            if cloud[-1] != last or cloud[0] != first:
                violations += 1
        # 未来数据扰动：删掉末尾 10 天，前 250 天的窗口必须完全不变
        truncated = replace(
            short, dates=short.dates[:290],
            closes={c: v[:290] for c, v in short.closes.items()},
            returns={c: v[:290] for c, v in short.returns.items()},
        )
        clouds_trunc = build_point_clouds(truncated, w)
        prefix_ok = all(
            a[0] == b[0] and a[1] == b[1]
            for a, b in zip(clouds[:len(clouds_trunc)], clouds_trunc)
        )
        report["causality_check"] = {
            "window_alignment_violations": violations,
            "future_perturbation_unchanged": prefix_ok,
            "passed": violations == 0 and prefix_ok,
        }

        dates, prices = load_benchmark(cfg, conn)
        labels = market_drawdown_label(dates, prices, cfg.horizon, cfg.drawdown)
        valid = [v for v in labels if v is not None]
        report["labels"] = {
            "n_dates": len(dates), "n_valid": len(valid),
            "n_positive": sum(1 for v in valid if v),
            "positive_rate": round(sum(1 for v in valid if v) / len(valid), 4) if valid else None,
            "n_unlabeled_tail": len(labels) - len(valid),
        }

        # 评估器单元校验：单个危机 + 单个提前信号 -> TP=1, FP=0
        chk = evaluate_ews([100], [95], lead=20, lag=5, total_days=1000)
        report["evaluation_selftest"] = chk
        assert chk["TP"] == 1 and chk["FP"] == 0, "评估器口径错误"
        late = evaluate_ews([100], [103], lead=20, lag=5, total_days=1000)
        assert late["Late"] == 1 and late["TP"] == 0, "Late 判定错误"

        folds = list(walk_forward_splits(3000, cfg.initial_train_days,
                                         cfg.val_days, cfg.purge_days,
                                         cfg.embargo_days))
        overlap = [f for f in folds if f[0][1] >= f[1][0]]
        report["walk_forward"] = {
            "n_folds": len(folds), "overlapping_folds": len(overlap),
            "first_fold": folds[0] if folds else None,
        }

        # 检测器自检：加一段"未来"数据后，历史 hits 必须完全不变
        base = [1.0] * 50 + [5.0] * 5 + [8.0] * 31
        hits = detect_ews(base, 1.5, 1.2, 5, 16)
        perturbed = base + [1e6] * 50
        hits_p = detect_ews(perturbed, 1.5, 1.2, 5, 16)
        unchanged = set(h for h in hits_p if h < len(base)) == set(hits)
        report["detector_selftest"] = {
            "n_hits": len(hits), "first_hits": hits[:6],
            "future_perturbation_unchanged": unchanged,
            "passed": unchanged and len(hits) > 0,
        }

        if report["backend"]["ripser"] or report["backend"]["gudhi"]:
            from src.topology.features import (
                TOPOLOGY_FEATURE_COLUMNS, extract_sliced_features,
                inverse_density, landscape_lp_norm, sliced_bifiltration,
                vr_diagrams,
            )
            dgms = vr_diagrams(clouds[0][1], maxdim=1)
            report["topology_selftest"] = {
                "n_dims": len(dgms),
                "h0": len(dgms[0]) if dgms else 0,
                "h1": len(dgms[1]) if len(dgms) > 1 else 0,
            }
            g = inverse_density(clouds[0][1], k=3)
            slices = sliced_bifiltration(clouds[0][1], -g,
                                         quantiles=(0.4, 0.7, 1.0))
            report["sliced_bifiltration_selftest"] = {
                "n_slices": len(slices),
                "n_points": [x["n_points"] for x in slices],
                "h1_max_lifetime": [round(x["h1_max_lifetime"], 4) for x in slices],
                "note": "scores=-kNN逆密度；只验证切片敏感性管道",
            }

            pilot_clouds = clouds[:6]
            pilot_dates = [
                short.dates[idx[date] - w + 1:idx[date] + 1]
                for date, _ in pilot_clouds
            ]
            rows = extract_sliced_features(
                pilot_clouds, k=3, core_fraction=0.6, point_dates=pilot_dates,
            )
            prefix_rows = extract_sliced_features(
                pilot_clouds[:4], k=3, core_fraction=0.6,
                point_dates=pilot_dates[:4],
            )
            import math
            first_d_null = all(row[f"D_{r}_h{j}"] is None
                               for row in rows[:1]
                               for r in ("full", "core", "edge") for j in (0, 1))
            later_d_finite = all(
                math.isfinite(row[f"D_{r}_h{j}"])
                for row in rows[1:] for r in ("full", "core", "edge")
                for j in (0, 1)
            )
            edge_identity = all(
                abs(row[f"{kind}_edge_h{j}"]
                    - (row[f"{kind}_full_h{j}"] - row[f"{kind}_core_h{j}"]))
                < 1e-12
                for row in rows[1:] for kind in ("A", "D") for j in (0, 1)
            )
            report["sliced_feature_selftest"] = {
                "n_rows": len(rows), "n_topology_columns": len(TOPOLOGY_FEATURE_COLUMNS),
                "first_day_D_is_null": first_d_null,
                "later_D_all_finite": later_d_finite,
                "edge_identity_ok": edge_identity,
                "future_perturbation_unchanged": prefix_rows == rows[:4],
                "landscape_fixed_grid": landscape_lp_norm(dgms[0], grid_max=1.0),
                "sample": {k: rows[-1][k] for k in TOPOLOGY_FEATURE_COLUMNS},
            }
            assert len(TOPOLOGY_FEATURE_COLUMNS) == 12
            assert first_d_null and later_d_finite and edge_identity
            assert prefix_rows == rows[:4], "未来窗口改变了历史切片特征"
        else:
            report["topology_selftest"] = "skipped: 未安装 gudhi/ripser"
    finally:
        conn.close()

    out = ROOT / "smoke_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n报告已写入 {out}")
    return report


if __name__ == "__main__":
    main()
