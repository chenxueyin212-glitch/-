"""对照兴业图12/13与本地H1/H2持久景观形态；不重算拓扑或策略收益。

拓扑输入只读三套已审计修正版特征。万得全A为连接器月线MATCH收盘，
仅作图形背景，不参与任何拓扑、信号或收益计算。原图数值只作图片估读，
没有原始逐日序列，因此不计算伪精确的曲线相关系数或复现误差。
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sqlite3
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
START = "2012-12-31"
END = "2025-05-30"
VERSIONS = {
    "corrected_public_v1_0": ("xy_corrected_features.db", "v1.0 public only"),
    "supplement_sw193_v1_1": ("xy_corrected_supplemented_features.db", "v1.1 + brokers II"),
    "supplement_sw193_ifind_peak_v1_2": (
        "xy_corrected_sw193_ifind_peak_features.db", "v1.2 + brokers II + forestry peak"),
}
WINDOWS = {
    "2015": ("2015-01-01", "2015-12-31"),
    "2020": ("2020-01-01", "2020-12-31"),
    "2021H1": ("2021-01-01", "2021-06-30"),
    "2021H2": ("2021-07-01", "2021-12-31"),
    "2022": ("2022-01-01", "2022-12-31"),
    "2023": ("2023-01-01", "2023-12-31"),
    "2024": ("2024-01-01", "2024-12-31"),
}


def read_features(filename: str) -> list[dict]:
    con = sqlite3.connect(f"file:{OUT / filename}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT date,n_nodes,h1_landscape_l1,h2_landscape_l1 "
        "FROM feature_daily WHERE date BETWEEN ? AND ? ORDER BY date", (START, END))]
    con.close()
    if len(rows) != 2994 or rows[0]["date"] != START or rows[-1]["date"] != END:
        raise RuntimeError(f"{filename}报告期日期覆盖异常")
    return rows


def read_wind_monthly() -> list[dict]:
    with (OUT / "xy_wind_all_a_monthly.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = [{"date": r["date"], "close": float(r["close"])} for r in csv.DictReader(handle)]
    if len(rows) != 150 or rows[0]["date"] != START or rows[-1]["date"] != END:
        raise RuntimeError("万得全A月线应为2012-12至2025-05共150个点")
    months = [(int(r["date"][:4]), int(r["date"][5:7])) for r in rows]
    expected = []
    year, month = 2012, 12
    while (year, month) <= (2025, 5):
        expected.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    if months != expected or len({r["date"] for r in rows}) != len(rows):
        raise RuntimeError("万得全A月线月份不连续或存在重复")
    if any(r["close"] <= 0 for r in rows):
        raise RuntimeError("万得全A月线存在非正收盘")
    return rows


def peak(rowset: list[dict], field: str, start: str, end: str) -> dict:
    part = [r for r in rowset if start <= r["date"] <= end]
    row = max(part, key=lambda r: r[field])
    return {"date": row["date"], "value": row[field], "n_nodes": row["n_nodes"]}


def separated_peaks(rowset: list[dict], field: str, count: int = 6, gap_days: int = 60) -> list[dict]:
    chosen = []
    for row in sorted(rowset, key=lambda r: r[field], reverse=True):
        date = dt.date.fromisoformat(row["date"])
        if all(abs((date - dt.date.fromisoformat(x["date"])).days) >= gap_days for x in chosen):
            chosen.append({"date": row["date"], "value": row[field], "n_nodes": row["n_nodes"]})
            if len(chosen) == count:
                break
    return chosen


def summarize(rows: list[dict]) -> dict:
    result = {"days": len(rows)}
    for field in ("h1_landscape_l1", "h2_landscape_l1"):
        result[field] = {
            "maximum": peak(rows, field, START, END),
            "separated_peaks_60d": separated_peaks(rows, field),
            "windows": {name: peak(rows, field, start, end)
                        for name, (start, end) in WINDOWS.items()},
        }
    return result


def dates(rows: list[dict]):
    return [dt.date.fromisoformat(r["date"]) for r in rows]


def draw_wind_pair(rows: list[dict], wind: list[dict], field: str, dimension: str,
                   ylim: tuple[float, float], wind_ylim: tuple[float, float], target: Path) -> None:
    fig, ax = plt.subplots(figsize=(13.6, 5.4), dpi=160)
    ax.plot(dates(rows), [r[field] for r in rows], color="#174a7c", lw=1.05,
            label=f"{dimension} persistence landscape L1 (daily)")
    ax.set_ylim(*ylim)
    ax.set_ylabel(f"{dimension} landscape L1")
    ax.grid(axis="y", alpha=0.18)
    other = ax.twinx()
    other.plot(dates(wind), [r["close"] for r in wind], color="#d45b61", lw=1.55,
               label="Wind All A 881001.WI (monthly close)")
    other.set_ylim(*wind_ylim)
    other.set_ylabel("Wind All A")
    ax.set_xlim(dt.date(2012, 12, 1), dt.date(2025, 6, 15))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    lines = ax.get_lines() + other.get_lines()
    ax.legend(lines, [line.get_label() for line in lines], loc="upper left", frameon=False)
    ax.set_title(f"Local corrected v1.2: {dimension} landscape vs Wind All A (2012/12-2025/05)")
    fig.text(0.01, 0.01,
             "Topology: audited daily corrected features; benchmark: Wind Alice monthly MATCH close. "
             "Different frequencies; chart comparison only, no strategy performance.",
             fontsize=8, color="#586579")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(target, bbox_inches="tight")
    plt.close(fig)


def draw_versions(all_rows: dict[str, list[dict]], target: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(13.6, 8.6), dpi=160, sharex=True)
    colors = ["#6b8fb3", "#a56a09", "#174a7c"]
    for ax, field, dimension, upper in zip(
            axes, ("h1_landscape_l1", "h2_landscape_l1"), ("H1", "H2"), (0.12, 0.016)):
        for (name, rows), color in zip(all_rows.items(), colors):
            ax.plot(dates(rows), [r[field] for r in rows], lw=1.0, color=color,
                    label=VERSIONS[name][1])
        ax.set_ylim(0, upper)
        ax.set_ylabel(f"{dimension} landscape L1")
        ax.grid(axis="y", alpha=0.18)
        ax.legend(loc="upper left", frameon=False)
    axes[0].set_title("Three preserved corrected versions: no ex-post selection by visual closeness")
    axes[1].xaxis.set_major_locator(mdates.YearLocator())
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.tight_layout()
    fig.savefig(target, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    all_rows = {name: read_features(filename) for name, (filename, _) in VERSIONS.items()}
    wind = read_wind_monthly()
    summaries = {name: summarize(rows) for name, rows in all_rows.items()}
    latest = all_rows["supplement_sw193_ifind_peak_v1_2"]
    draw_wind_pair(latest, wind, "h1_landscape_l1", "H1", (0, 0.12), (0, 8000),
                   OUT / "xy_h1_landscape_wind_monthly.png")
    draw_wind_pair(latest, wind, "h2_landscape_l1", "H2", (0, 0.016), (2000, 8000),
                   OUT / "xy_h2_landscape_wind_monthly.png")
    draw_versions(all_rows, OUT / "xy_landscape_three_versions.png")
    payload = {
        "generated_on": "2026-11-07",
        "period": [START, END],
        "feature_days_per_version": 2994,
        "local_formula": "sum((death-birth)^2)/4 over finite intervals",
        "wind_benchmark": {
            "code": "881001.WI", "frequency": "monthly", "rows": len(wind),
            "source": "Wind Alice MCP get_index_kline period=12; MATCH close",
            "query_date": "2026-11-07",
            "use": "chart background only; not topology, signal or return input",
            "file": "outputs/xy_wind_all_a_monthly.csv",
        },
        "original_image_reference": {
            "status": "visual estimates only; no original daily values",
            "figure12_h1": "main spikes around 2021 and 2023; highest visible spikes about 0.10-0.11",
            "figure13_h2": "two prominent 2021 spikes about 0.013-0.014; 2023 cluster visibly lower",
        },
        "versions": summaries,
        "shape_assessment": {
            "h1": "相似度较高：2021与2023主峰、2015较小尖峰及约0.10量级均相近；2021下半年等局部峰值仍有差异。",
            "h2": "主要峰值簇相似：2021年两段尖峰和2023年次生峰值簇均存在；但峰值高度、局部日期及其他年份并不逐点一致。",
            "forbidden_inference": "不得由截图计算或声称精确相似度、逐日相关系数、复现误差或策略有效性。",
        },
        "outputs": [
            "outputs/xy_h1_landscape_wind_monthly.png",
            "outputs/xy_h2_landscape_wind_monthly.png",
            "outputs/xy_landscape_three_versions.png",
        ],
        "strategy_performance_calculated": False,
    }
    target = OUT / "xy_landscape_shape_comparison.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "summary": str(target),
        "h1_max": summaries["supplement_sw193_ifind_peak_v1_2"]["h1_landscape_l1"]["maximum"],
        "h2_max": summaries["supplement_sw193_ifind_peak_v1_2"]["h2_landscape_l1"]["maximum"],
        "wind_monthly_rows": len(wind),
        "strategy_performance_calculated": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
