# -*- coding: utf-8 -*-
"""把 45 个标签段按「一轮完整下跌 + 收复」合并成叙事层危机，并给出每轮的深度/时长/段数。"""
import numpy as np
import pandas as pd

br = pd.read_csv("tda_project/outputs/regime_v05_benchmark_daily.csv",
                 parse_dates=["date"]).set_index("date").sort_index()
close = br["benchmark_close"].astype(float)
dates = close.index

# 人工合并（依据：相邻段之间指数未走出「收复前高」级别的反弹 + 公开讨论中的同一轮危机）
ROUNDS = [
    ("2001 初 · 基金黑幕/中科创业", [101]),
    ("2001-06→2005-07 · 国有股减持到 998", list(range(102, 115))),
    ("2007-05 · 印花税", [115]),
    ("2007-10→2008-11 · 全球金融危机", [116, 117, 118, 119, 120]),
    ("2009-08→2012-12 · 四万亿退潮与欧债", list(range(121, 129))),
    ("2015-06→2016-01 · 股灾与熔断", [1, 2, 3, 4]),
    ("2018 · 去杠杆与贸易战", [5, 6, 7, 8]),
    ("2020-01→2020-03 · 疫情", [9, 10]),
    ("2021-02→2022-10 · 抱团瓦解到封城", [11, 12, 13]),
    ("2023-12→2024-02 · 微盘流动性与雪球", [14]),
    ("2024-10→2025-03 · 政策脉冲后的回落", [15, 16, 17]),
]
ev = pd.read_csv("tda_project/outputs/regime_v05_crisis_events.csv", parse_dates=["onset", "end"])
ev = ev.set_index("event_id")

rows = []
for name, ids in ROUNDS:
    sub = ev.loc[ids]
    s, e = sub.onset.min(), sub.end.max()
    peak = close.loc[:s].iloc[:-1].tail(120).max()
    trough = close.loc[s:e].min()
    trough_day = close.loc[s:e].idxmin()
    # 收复前高：trough 之后首次 >= peak
    after = close.loc[trough_day:]
    rec = after[after >= peak]
    rows.append(dict(轮=name, 首段=s.date(), 末段=e.date(), 段数=len(ids),
                     峰到谷=round((trough / peak - 1) * 100, 1),
                     谷底日=trough_day.date(),
                     收复=(rec.index[0].date() if len(rec) else "—"),
                     交易日=int(((dates >= s) & (dates <= e)).sum())))
D = pd.DataFrame(rows)
print(D.to_string(index=False))
print(f"\n合计：45 段 → {len(D)} 轮")
print("其中跌幅 ≥20% 的大级别危机：", int((D.峰到谷 <= -20).sum()), "轮")
print("跌幅 <20% 的小型冲击：", int((D.峰到谷 > -20).sum()), "轮")
