"""独立核验修正版行业输入、补充来源和兴业图13/14的数量级差异。

不计算策略收益，不读取Gate 1/2数据；公开-only和各补充版本分别保留。
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.xy_replication.fetch_sw2014_corrected import CODES as SW2014  # noqa: E402
from src.xy_replication.topology import network_features  # noqa: E402

OUT = ROOT / "outputs"
ERA_SWITCH = "2021-12-13"
REPORT_END = "2025-05-30"
FIGURE14_START = "2019-12-01"
SELECTED_DATES = ("2015-07-01", "2020-03-02", "2021-06-09", "2021-06-29",
                  "2021-06-30", "2021-12-13", "2024-02-21", "2024-12-31", "2025-05-30")
FIELDS = ("n_nodes", "h2_count", "h1_count", "h2_landscape_l1", "h1_landscape_l1",
          "industry_average_correlation", "correlation_leading_eigenvalue_share",
          "max_h2_persistence", "h2_betti_0p4", "h2_betti_0p6", "h2_betti_0p8")


def read_features(filename: str) -> list[dict]:
    con = sqlite3.connect(f"file:{OUT / filename}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM feature_daily ORDER BY date")]
    con.close()
    return rows


def metrics(rows: list[dict], start: str, end: str) -> dict:
    part = [r for r in rows if start <= r["date"] <= end]
    h2_max = max(r["h2_count"] for r in part)
    landscape_max = max(r["h2_landscape_l1"] for r in part)
    return {"range": [part[0]["date"], part[-1]["date"]], "days": len(part),
            "nodes_min": min(r["n_nodes"] for r in part), "nodes_max": max(r["n_nodes"] for r in part),
            "h2_max": h2_max, "h2_max_dates": [r["date"] for r in part if r["h2_count"] == h2_max],
            "landscape_l1_max": landscape_max,
            "landscape_max_dates": [r["date"] for r in part if r["h2_landscape_l1"] == landscape_max],
            "h2_le1_days": sum(r["h2_count"] <= 1 for r in part)}


def difference(a: list[dict], b: list[dict]) -> dict:
    amap = {r["date"]: r for r in a}
    bmap = {r["date"]: r for r in b}
    dates = sorted(set(amap) & set(bmap))
    out = {}
    for label, selected in (
            ("all", dates),
            ("sw2014_era", [d for d in dates if d < ERA_SWITCH]),
            ("sw2021_through_discontinuation", [d for d in dates if ERA_SWITCH <= d < "2024-06-18"]),
            ("after_2024_06_17", [d for d in dates if d >= "2024-06-18"])):
        if not selected:
            continue
        dh2 = np.asarray([amap[d]["h2_count"]-bmap[d]["h2_count"] for d in selected], dtype=float)
        dnodes = np.asarray([amap[d]["n_nodes"]-bmap[d]["n_nodes"] for d in selected], dtype=float)
        dland = np.asarray([abs(amap[d]["h2_landscape_l1"]-bmap[d]["h2_landscape_l1"])
                            for d in selected], dtype=float)
        out[label] = {"days": len(selected), "same_h2_share": float(np.mean(dh2 == 0)),
                      "h2_median_abs_delta": float(np.median(abs(dh2))),
                      "h2_max_abs_delta": int(max(abs(dh2))),
                      "nodes_delta_min": int(min(dnodes)), "nodes_delta_max": int(max(dnodes)),
                      "landscape_max_abs_delta": float(max(dland))}
    return out


def main() -> None:
    variants = {
        "main_fixed_active124": ("xy_replication_results.db", None),
        "defective_legacy_experiment": ("xy_replication_pit_results.db", None),
        "corrected_public_v1_0": ("xy_corrected_features.db", "xy_corrected_feature_summary.json"),
        "supplement_sw193_v1_1": ("xy_corrected_supplemented_features.db", "xy_corrected_supplemented_feature_summary.json"),
    }
    peak_db = OUT / "xy_corrected_sw193_ifind_peak_features.db"
    if peak_db.exists():
        variants["supplement_sw193_ifind_peak_v1_2"] = (
            peak_db.name, "xy_corrected_sw193_ifind_peak_feature_summary.json")
    rows = {name: read_features(db) for name, (db, _) in variants.items()}
    summaries = {name: json.loads((OUT / summary).read_text(encoding="utf-8"))
                 for name, (_, summary) in variants.items() if summary}

    old = sqlite3.connect(f"file:{OUT / 'xy_sw2014_corrected_data.db'}?mode=ro", uri=True)
    old_close = {r[0]: dict(old.execute("SELECT date,close FROM sw2014_daily WHERE code=?", (r[0],)))
                 for r in old.execute("SELECT code FROM sw2014_meta")}
    old.close()
    current = sqlite3.connect(f"file:{OUT / 'xy_replication_data.db'}?mode=ro", uri=True)
    current_codes = {r[0] for r in current.execute(
        "SELECT code FROM sw2_meta WHERE parent IS NOT 'SW2014 legacy supplement'")}
    current_close = {code: dict(current.execute("SELECT date,close FROM sw2_daily WHERE code=?", (code,)))
                     for code in current_codes}
    dates = [r[0] for r in current.execute(
        "SELECT date FROM benchmark_daily WHERE code='801003' ORDER BY date")]
    current.close()
    positions = {d: i for i, d in enumerate(dates)}
    supplement = sqlite3.connect(f"file:{OUT / 'xy_sw2014_supplement.db'}?mode=ro", uri=True)
    supplement_close = {r[0]: dict(supplement.execute(
        "SELECT date,close FROM supplement_daily WHERE code=?", (r[0],)))
        for r in supplement.execute("SELECT code FROM supplement_meta")}
    supplement_hashes = {r[0]: r[1] for r in supplement.execute(
        "SELECT code,snapshot_sha256 FROM supplement_meta")}
    supplement.close()

    validation = {}
    for name, summary in summaries.items():
        data = rows[name]
        assert len(data) == len({r["date"] for r in data}) == summary["feature_days"] == 3339
        assert all(r["config_sha256"] == summary["config_sha256"] for r in data)
        assert all(r["h2_count"] >= 0 and math.isfinite(r["h2_landscape_l1"]) for r in data)
        expected_supplement = {r["code"] for r in summary.get("supplement") or []}
        for item in summary.get("supplement") or []:
            assert supplement_hashes[item["code"]] == item["snapshot_sha256"]
        con = sqlite3.connect(f"file:{OUT / variants[name][0]}?mode=ro", uri=True)
        provenance = {r[0]: set(json.loads(r[1])) for r in con.execute(
            "SELECT date,eligible_codes_json FROM feature_supplement")} if expected_supplement else {}
        con.close()
        selected_set = set(SELECTED_DATES)
        selected_checks = 0
        membership_checks = 0
        provenance_checks = 0
        feature_map = {r["date"]: r for r in data}
        for date in feature_map:
            i = positions[date]
            window = dates[i-30:i+1]
            source = old_close if date < ERA_SWITCH else current_close
            codes = SW2014 if date < ERA_SWITCH else current_codes
            eligible = []
            supplemented_eligible = []
            for code in sorted(codes):
                prices = []
                used_supplement = False
                for d in window:
                    price = source.get(code, {}).get(d)
                    if price is None or price <= 0:
                        extra = supplement_close.get(code, {}).get(d) if code in expected_supplement else None
                        if extra is not None and extra > 0:
                            price = extra
                            used_supplement = True
                    prices.append(price)
                if all(p is not None and p > 0 for p in prices):
                    values = np.asarray(prices, dtype=float)
                    returns = values[1:] / values[:-1] - 1.0
                    if np.std(returns, ddof=1) > 0:
                        eligible.append(prices)
                        if used_supplement:
                            supplemented_eligible.append(code)
            assert len(eligible) == feature_map[date]["n_nodes"], (name, date)
            membership_checks += 1
            if expected_supplement:
                assert set(supplemented_eligible) == provenance[date], (name, date)
                provenance_checks += 1
            if date in selected_set:
                matrix = np.asarray(eligible, dtype=float).T
                returns = matrix[1:] / matrix[:-1] - 1.0
                recomputed = network_features(returns)
                for field in FIELDS:
                    assert math.isclose(float(recomputed[field]), float(feature_map[date][field]),
                                        rel_tol=1e-9, abs_tol=1e-9), (name, date, field)
                selected_checks += 1
        validation[name] = {"membership_days_recalculated": membership_checks,
                            "provenance_days_recalculated": provenance_checks,
                            "selected_dates_topology_recalculated": selected_checks}

    report_metrics = {name: {"full_figure13_window": metrics(data, "2012-12-31", REPORT_END),
                             "figure14_window": metrics(data, FIGURE14_START, REPORT_END)}
                      for name, data in rows.items()}
    comparisons = {}
    for name in summaries:
        comparisons[name] = {"vs_main_fixed_active124": difference(rows[name], rows["main_fixed_active124"]),
                             "vs_corrected_public_v1_0": difference(rows[name], rows["corrected_public_v1_0"])}
    peak = report_metrics["corrected_public_v1_0"]["full_figure13_window"]
    reference = {"status": "原图估读，不是逐日原始数值", "landscape_l1_peak_approx": 0.014,
                 "h2_peak_approx_range": [75, 80]}
    reference_comparison = {}
    for name in summaries:
        item = report_metrics[name]["full_figure13_window"]
        reference_comparison[name] = {
            "landscape_abs_gap_vs_0p014": item["landscape_l1_max"]-0.014,
            "h2_count_gap_vs_75_to_80": [item["h2_max"]-80, item["h2_max"]-75],
            "note": "图片估读只用于数量级核验，不计算精确复现误差"}
    result = {
        "overall_pass": True, "validation": validation, "report_period_metrics": report_metrics,
        "pairwise_differences": comparisons, "original_figure_reference": reference,
        "reference_comparison": reference_comparison,
        "cited_periods": {name: summary["cited_periods"] for name, summary in summaries.items()},
        "supplement_audits": {
            "westock": json.loads((OUT / "xy_sw2014_supplement_audit.json").read_text(encoding="utf-8")),
            "ifind_peak": json.loads((OUT / "xy_ifind_supplement_audit.json").read_text(encoding="utf-8"))
            if (OUT / "xy_ifind_supplement_audit.json").exists() else None},
        "defective_legacy_status": "代码映射有缺陷的历史实验；绩效不得作为兴业同期口径证据",
        "remaining_gaps": ["林业801011和其他轻工制造801144等完整2012—2021历史尚未取得",
                           "证券801193在2016-12-12以前仍缺可批量核验历史",
                           "其他休闲服务801215早期无有效行情，不能用其他行业或插值替代",
                           "兴业Wind逐日代码清单、收益细节和万得全A原始序列仍未获得",
                           "2012—2014年初公开面板仅74个有效节点，不能宣称完整重建"],
        "public_only_landscape_peak_for_sanity": peak["landscape_l1_max"],
        "strategy_performance_calculated": False, "gate1_touched": False, "gate2_started": False,
    }
    target = OUT / "xy_corrected_comparison.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"overall_pass": True, "validation": validation,
                      "report_period_metrics": report_metrics,
                      "reference_comparison": reference_comparison,
                      "output": str(target)}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
