# -*- coding: utf-8 -*-
"""
「真正的一次危机」= 指数连续处于「自 250 日高点回撤超过阈值」的时段。
相邻压力时段间隔 <= 20 个交易日则并成一段（同一轮危机的反抽）。
再统计每个时段吃进几个标签段。
"""
import numpy as np
import pandas as pd

br = pd.read_csv("tda_project/outputs/regime_v05_benchmark_daily.csv",
                 parse_dates=["date"]).set_index("date").sort_index()
close = br["benchmark_close"].astype(float)
dates = close.index
ev = pd.read_csv("tda_project/outputs/regime_v05_crisis_events.csv", parse_dates=["onset", "end"])
ev = ev.sort_values("onset").reset_index(drop=True)

roll_max = close.rolling(250, min_periods=60).max()
dd = close / roll_max - 1


def stress_episodes(thr, gap=20):
    flag = (dd <= -thr).values
    eps, i = [], 0
    while i < len(flag):
        if not flag[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(flag) and (flag[j + 1] or (j + 1 + gap < len(flag) and flag[j + 1:j + 1 + gap].any())):
            j += 1
            if flag[j]:
                continue
            # 允许 gap 内的空档，但必须在 gap 内重新进入压力
            break
        eps.append((i, j))
        i = j + 1
    return eps


for thr in (0.10, 0.15, 0.20):
    eps = stress_episodes(thr)
    print(f"\n{'='*74}\n阈值 {int(thr*100)}%（自 250 日高点回撤）: 压力时段 {len(eps)} 段")
    rows = []
    for k, (i0, i1) in enumerate(eps, 1):
        s, e = dates[i0], dates[i1]
        sub = ev[(ev.onset >= s) & (ev.onset <= e)]
        seg = close.loc[s:e]
        rows.append(dict(轮=k, 起=s.date(), 止=e.date(), 交易日=int(i1 - i0 + 1),
                         最差回撤=round(dd.iloc[i0:i1 + 1].min() * 100, 1),
                         并入=len(sub), ids=",".join(str(x) for x in sub.event_id)))
    D = pd.DataFrame(rows)
    print(D.to_string(index=False))
    hit = D[D.并入 > 0]
    print(f"→ {hit['并入'].sum()} 个标签段并入 {len(hit)} 轮；空轮 {len(D)-len(hit)} 个")

print("\n=== 阈值 10% 下没被覆盖的标签段 ===")
eps = stress_episodes(0.10)
cov = np.zeros(len(ev), dtype=bool)
for i0, i1 in eps:
    s, e = dates[i0], dates[i1]
    cov |= ((ev.onset >= s) & (ev.onset <= e)).values
print(ev[~cov][["event_id", "onset", "end"]].to_string(index=False))
