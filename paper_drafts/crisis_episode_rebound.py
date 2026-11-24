# -*- coding: utf-8 -*-
"""
把 45 个标签段合并成「真正的一次危机」。
合并判据：相邻两段之间，市场有没有走出一次像样的反弹。
  反弹幅度 = max(close[前段end .. 后段onset]) / min(同一区间) - 1
  若反弹 < 阈值 -> 视为同一轮危机；否则切开。
只统计基准（真万得全A）自身走势，不引入外部叙事。
"""
import numpy as np
import pandas as pd

br = pd.read_csv("tda_project/outputs/regime_v05_benchmark_daily.csv",
                 parse_dates=["date"]).set_index("date").sort_index()
close = br["benchmark_close"].astype(float)
ev = pd.read_csv("tda_project/outputs/regime_v05_crisis_events.csv", parse_dates=["onset", "end"])
ev = ev.sort_values("onset").reset_index(drop=True)

pairs = []
for a, b in zip(ev.itertuples(), ev.iloc[1:].itertuples()):
    win = close.loc[a.end:b.onset]
    lo, hi = win.min(), win.max()
    pairs.append(dict(prev=a.event_id, prev_end=a.end.date(), next=b.event_id,
                      next_onset=b.onset.date(), gap_days=(b.onset - a.end).days,
                      rebound_pct=round((hi / lo - 1) * 100, 1)))
P = pd.DataFrame(pairs)
print("=== 45 段之间 44 个间隔：反弹幅度分布 ===")
print(P.rebound_pct.describe().round(1).to_string())
print("\n按反弹幅度排序（最小的 12 个 = 最该并的）：")
print(P.nsmallest(12, "rebound_pct").to_string(index=False))

for thr in (10, 15, 20, 25):
    groups, cur = [], [ev.iloc[0]]
    for i, r in P.iterrows():
        if r.rebound_pct < thr:
            cur.append(ev[ev.event_id == r.next].iloc[0])
        else:
            groups.append(cur); cur = [ev[ev.event_id == r.next].iloc[0]]
    groups.append(cur)
    print(f"\n=== 反弹阈值 {thr}%：45 段合并为 {len(groups)} 次危机 ===")
    for g in groups:
        ids = ",".join(str(x.event_id) for x in g)
        span = f"{g[0].onset.date()} → {g[-1].end.date()}"
        seg = close.loc[g[0].onset:g[-1].end]
        print(f"  {span}  {len(g):2d} 段（id {ids}）  期间最大回撤 "
              f"{(seg/seg.cummax().clip(lower=close.loc[:g[0].onset].iloc[-1]) - 1).min()*100:6.1f}%")

# 选定阈值下的明细，含每轮高低点
print("\n=== 取 15%：每轮的幅度与时长 ===")
groups, cur = [], [ev.iloc[0]]
for i, r in P.iterrows():
    if r.rebound_pct < 15:
        cur.append(ev[ev.event_id == r.next].iloc[0])
    else:
        groups.append(cur); cur = [ev[ev.event_id == r.next].iloc[0]]
groups.append(cur)
rows = []
for g in groups:
    s, e = g[0].onset, g[-1].end
    pre = close.loc[:s].iloc[:-1]
    peak = pre.iloc[-1] if len(pre) else close.loc[s]
    seg = close.loc[s:e]
    trough = seg.min()
    rows.append(dict(n_seg=len(g), onset=s.date(), end=e.date(),
                     days=(e - s).days,
                     peak_to_trough=round((trough / peak - 1) * 100, 1),
                     ids=",".join(str(x.event_id) for x in g)))
print(pd.DataFrame(rows).to_string(index=False))
