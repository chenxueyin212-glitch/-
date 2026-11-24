# -*- coding: utf-8 -*-
"""叙事层危机轮次：每轮给定峰/谷日期（由数据核出），统计深度、时长、并入的标签段。"""
import pandas as pd

br = pd.read_csv("tda_project/outputs/regime_v05_benchmark_daily.csv",
                 parse_dates=["date"]).set_index("date").sort_index()
close = br["benchmark_close"].astype(float)
dates = close.index
ev = pd.read_csv("tda_project/outputs/regime_v05_crisis_events.csv", parse_dates=["onset", "end"])

# (名称, 峰, 谷, 标签段 id 列表)
ROUNDS = [
    ("2000-11 基金黑幕/中科创业",       "2000-11-23", "2001-02-22", [101]),
    ("2001-06→2005-07 国有股减持到 998", "2001-06-13", "2005-07-18", list(range(102, 115))),
    ("2007-05 印花税",                  "2007-05-29", "2007-07-05", [115]),
    ("2007-10→2008-11 全球金融危机",     "2007-10-16", "2008-11-04", [116, 117, 118, 119, 120]),
    ("2009-08→2012-12 四万亿退潮与欧债",  "2009-08-04", "2012-12-04", list(range(121, 129))),
    ("2015-06→2016-01 股灾与熔断",       "2015-06-12", "2016-01-28", [1, 2, 3, 4]),
    ("2018 去杠杆与贸易战",             "2018-01-24", "2018-10-18", [5, 6, 7, 8]),
    ("2020-01→2020-03 疫情",            "2020-01-13", "2020-03-23", [9, 10]),
    ("2021-02→2022-10 抱团瓦解到封城",   "2021-02-10", "2022-10-31", [11, 12, 13]),
    ("2023-12→2024-02 微盘流动性与雪球", "2023-11-20", "2024-02-05", [14]),
    ("2024-10→2025-04 政策脉冲后回落",   "2024-10-08", "2025-04-07", [15, 16, 17]),
    ("2026 AI 链调整（样本外）",         "2026-05-13", "2026-10-30", []),
]

rows = []
for name, pk, tr, ids in ROUNDS:
    pk, tr = pd.Timestamp(pk), pd.Timestamp(tr)
    if pk not in close.index:
        pk = close.loc[:pk].index[-1]
    if tr not in close.index:
        tr = close.loc[:tr].index[-1]
    depth = (close.loc[tr] / close.loc[pk] - 1) * 100
    td = int(((dates > pk) & (dates <= tr)).sum())
    seg = ev[ev.event_id.isin(ids)]
    rows.append(dict(轮=name, 峰=pk.date(), 谷=tr.date(), 幅度=round(depth, 1),
                     下跌交易日=td, 标签段=len(ids),
                     段号=(",".join(str(x) for x in sorted(ids)) if ids else "—")))
D = pd.DataFrame(rows)
pd.set_option("display.width", 220)
print(D.to_string(index=False))
print(f"\n样本内 11 轮合计并入 {D.标签段[:-1].sum()} 个标签段（应等于 45）")
print(f"跌幅 ≥50%：{int((D.幅度 <= -50).sum())} 轮；30–50%：{int(((D.幅度 > -50) & (D.幅度 <= -30)).sum())} 轮；"
      f"20–30%：{int(((D.幅度 > -30) & (D.幅度 <= -20)).sum())} 轮；<20%：{int((D.幅度 > -20).sum())} 轮")
