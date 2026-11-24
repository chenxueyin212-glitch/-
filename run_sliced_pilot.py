"""真实行业面板上的密度切片工程试点。

只验证因果特征链可计算、可保存、可复现；不调阈值，不报告危机预测能力。
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config                       # noqa: E402
from src.data.pit_panel import (                         # noqa: E402
    build_pit_segments, build_point_clouds, connect_ro,
)
from src.topology.features import (                      # noqa: E402
    TOPOLOGY_FEATURE_COLUMNS, extract_sliced_features,
)

CONTROL_COLUMNS = (
    "n_full", "n_core", "density_g_median", "density_g_q90",
    "density_g_latest", "core_threshold", "edge_fraction", "latest_is_edge",
)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default="2007-01-01")
    p.add_argument("--end", default="2008-12-31")
    p.add_argument("--window", type=int, default=50)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--core-fraction", type=float, default=0.7)
    p.add_argument("--max-windows", type=int, default=0,
                   help="仅调试用；0 表示运行区间内全部窗口")
    p.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    return p.parse_args()


def main():
    args = parse_args()
    if args.start > args.end:
        raise ValueError("start 不得晚于 end")
    cfg = load_config()
    conn = connect_ro(cfg.db_path)
    try:
        segments = build_pit_segments(cfg, conn)
    finally:
        conn.close()
    matches = [s for s in segments if s.start <= args.start and args.end <= s.end]
    if len(matches) != 1:
        raise ValueError("试点区间必须完整落在同一个申万分类版本段内")
    seg = matches[0]
    clouds = build_point_clouds(seg, args.window)
    clouds = [(d, x) for d, x in clouds if args.start <= d <= args.end]
    if args.max_windows > 0:
        clouds = clouds[:args.max_windows]
    if len(clouds) < 2:
        raise RuntimeError("有效窗口不足，无法计算日间变化")

    date_index = {d: i for i, d in enumerate(seg.dates)}
    point_dates = [
        seg.dates[date_index[d] - args.window + 1:date_index[d] + 1]
        for d, _ in clouds
    ]
    rows = extract_sliced_features(
        clouds, k=args.k, core_fraction=args.core_fraction,
        point_dates=point_dates,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"sliced_features_{rows[0]['date']}_{rows[-1]['date']}"
    csv_path = args.output_dir / f"{stem}.csv"
    fields = ["date", *TOPOLOGY_FEATURE_COLUMNS, *CONTROL_COLUMNS, "edge_dates"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = {k: row.get(k) for k in fields}
            out["edge_dates"] = "|".join(row["edge_dates"] or [])
            writer.writerow(out)

    stats = {}
    for col in TOPOLOGY_FEATURE_COLUMNS:
        values = [float(r[col]) for r in rows if r[col] is not None]
        stats[col] = {
            "n": len(values),
            "min": min(values) if values else None,
            "median": statistics.median(values) if values else None,
            "max": max(values) if values else None,
        }
    d_h1_core = [float(r["D_core_h1"]) for r in rows if r["D_core_h1"] is not None]
    audit = {
        "latest_edge_days": sum(bool(r["latest_is_edge"]) for r in rows),
        "latest_edge_fraction": sum(bool(r["latest_is_edge"]) for r in rows) / len(rows),
        "negative_D_edge_h0_days": sum(
            float(r["D_edge_h0"]) < 0 for r in rows if r["D_edge_h0"] is not None
        ),
        "negative_D_edge_h1_days": sum(
            float(r["D_edge_h1"]) < 0 for r in rows if r["D_edge_h1"] is not None
        ),
        "D_core_h1_zero_fraction": (
            sum(v == 0 for v in d_h1_core) / len(d_h1_core) if d_h1_core else None
        ),
        "warning": (
            "edge 同时受窗口位置、full/core 点数差与共同波动尺度影响；"
            "D_edge 是距离之差可为负，A_edge/D_edge 未经 matched-size 与 "
            "window-position 零模型校正前不得解释为纯边缘拓扑效应。"
        ),
    }
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": "engineering_pilot_only_not_crisis_performance",
        "quality_audit": audit,
        "source": {
            "db": str(cfg.db_path), "table": "sw_industry_daily_clean",
            "segment_start": seg.start, "segment_end": seg.end,
            "n_industries": len(seg.codes), "industry_codes": list(seg.codes),
            "returns": "log(close_t/close_t-1), raw scale, no fitted scaler",
            "panel_note": seg.note,
        },
        "parameters": {
            "requested_start": args.start, "requested_end": args.end,
            "window": args.window, "knn_k": args.k,
            "core_fraction": args.core_fraction,
            "core_selection": "g_k <= window_quantile(g_k, 1-core_fraction)",
            "A": "finite-bar total persistence; infinite H0 bar excluded",
            "D": "persim Wasserstein W1(PD_t,PD_t-1); first row null",
            "edge": "full-core diagnostic difference, not an independent persistence module",
        },
        "output": {
            "n_windows": len(rows), "first_date": rows[0]["date"],
            "last_date": rows[-1]["date"],
            "n_topology_features": len(TOPOLOGY_FEATURE_COLUMNS),
            "csv": str(csv_path), "feature_stats": stats,
        },
        "remaining_boundary": (
            "离散密度切片不等价于完整双参数持续模；signed measure、秩不变量和 "
            "matching distance 的正式复核仍需可用的 WSL/Linux multipers 后端。"
        ),
    }
    json_path = args.output_dir / f"{stem}_summary.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    summary["output"]["summary_json"] = str(json_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
