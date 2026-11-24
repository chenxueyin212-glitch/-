# -*- coding: utf-8 -*-
"""
ZigZag 分解：把真万得全A 的走势按「反弹/回撤 >= 阈值」切成下行与上行摆动，
再统计每个下行摆动吃进了几个标签段 —— 这就是「几段合一段」。
"""
import numpy as np
import pandas as pd

br = pd.read_csv("tda_project/outputs/regime_v05_benchmark_daily.csv",
                 parse_dates=["date"]).set_index("date").sort_index()
close = br["benchmark_close"].astype(float)
dates = close.index
print("序列:", dates[0].date(), "→", dates[-1].date(), len(close))
# 末端不足 20 个交易日的标签在数据末端之外，属已知限制
ev = pd.read_csv("tda_project/outputs/regime_v05_crisis_events.csv", parse_dates=["onset", "end"])
ev = ev.sort_values("onset").reset_index(drop=True)


def zigzag(theta):
    """标准 ZigZag：返回 (起点idx, 终点idx, 起点价, 终点价, 方向 1=上行/-1=下行)。"""
    swings = []
    direction = 1
    ext_i = 0
    for i in range(1, len(close)):
        v = close.iloc[i]
        if direction == 1:
            if v > close.iloc[ext_i]:
                ext_i = i
            elif v <= close.iloc[ext_i] * (1 - theta):
                swings.append((ext_i, i, close.iloc[ext_i], v, 1))
                direction, ext_i = -1, i
        else:
            if v < close.iloc[ext_i]:
                ext_i = i
            elif v >= close.iloc[ext_i] * (1 + theta):
                swings.append((ext_i, i, close.iloc[ext_i], v, -1))
                direction, ext_i = 1, i
    swings.append((ext_i, len(close) - 1, close.iloc[ext_i], close.iloc[-1], direction))
    return swings


for theta in (0.20, 0.15):
    print(f"\n{'='*72}\nZigZag 阈值 {int(theta*100)}%")
    sw = zigzag(theta)
    downs = [s for s in sw if s[4] == -1]
    print(f"摆动共 {len(sw)} 个，其中下行 {len(downs)} 个")
    rows = []
    for k, (i0, i1, p0, p1, _) in enumerate(downs, 1):
        s, e = dates[i0], dates[i1]
        sub = ev[(ev.onset >= s) & (ev.onset <= e)]
        rows.append(dict(轮=k, 起=s.date(), 止=e.date(), 交易日=int(i1 - i0 + 1),
                         幅度=round((p1 / p0 - 1) * 100, 1), 并入段数=len(sub),
                         ids=",".join(str(x) for x in sub.event_id)))
    D = pd.DataFrame(rows)
    print(D.to_string(index=False))
    hit = D[D.并入段数 > 0]
    print(f"合计：{hit['并入段数'].sum()} 段并入 {len(hit)} 轮（另有 {len(D)-len(hit)} 轮不含标签段）")

print("\n=== 阈值 20% 下未被任何下行摆动覆盖的标签段 ===")
downs = [s for s in zigzag(0.20) if s[4] == -1]
cov = np.zeros(len(ev), dtype=bool)
for i0, i1, _, _, _ in downs:
    s, e = dates[i0], dates[i1]
    cov |= ((ev.onset >= s) & (ev.onset <= e)).values
print(ev[~cov][["event_id", "onset", "end"]].to_string(index=False))
