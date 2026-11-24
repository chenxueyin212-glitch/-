"""全史成交额集中度（拥挤度）

指标
- top5_share(t)：当日成交额前 5% 个股的成交额占全市场比重（%）
- top1_share(t)：前 1% 同理

实现注记：equity_daily_raw 的 date 索引对范围查询不生效（1677 万行全表扫 36s），
改用逐日等值查询（12ms/日），全史约 40 秒。
"""
import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path

DB = Path("a_share_pit/tdx_central.db")
OUT = Path("paper_drafts")
START = "2010-01-01"

con = sqlite3.connect(DB)
con.execute("PRAGMA cache_size=-200000")
alldays = [r[0] for r in con.execute(
    "select distinct date from equity_daily_raw where date>=? order by date", (START,))]
print(f"交易日 {len(alldays)}：{alldays[0]} → {alldays[-1]}", flush=True)

rows = []
for i, dt in enumerate(alldays):
    r = con.execute(
        "select amount from equity_daily_raw where date=? and amount>0", (dt,)).fetchall()
    if len(r) < 300:
        continue
    a = np.fromiter((x[0] for x in r), dtype=float, count=len(r))
    a = a[np.isfinite(a) & (a > 0)]
    n = a.size
    tot = a.sum()
    if n < 300 or tot <= 0:
        continue
    k5 = max(1, int(round(n * 0.05)))
    k1 = max(1, int(round(n * 0.01)))
    rows.append((dt, n, np.partition(a, n - k5)[n - k5:].sum() / tot * 100,
                 np.partition(a, n - k1)[n - k1:].sum() / tot * 100, tot / 1e8))
    if (i + 1) % 500 == 0:
        print(f"  {dt} 已处理 {i+1}/{len(alldays)}", flush=True)
con.close()

df = pd.DataFrame(rows, columns=["date", "n_stock", "top5_share", "top1_share", "amount_yi"])
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)
df.to_csv(OUT / "crowding_full_history.csv", index=False, encoding="utf-8-sig")
print(f"\n共 {len(df)} 个交易日 {df['date'].min().date()} → {df['date'].max().date()}")
print(df[["top5_share", "top1_share"]].describe().round(2).to_string())

sub = df[df["date"] >= "2021-01-01"]
print(f"\n2021 后 {len(sub)} 个交易日：")
for c in ["top5_share", "top1_share"]:
    q = sub[c].quantile([.05, .25, .5, .75, .95])
    print(f"  {c}: 5% {q.iloc[0]:.1f} | 25% {q.iloc[1]:.1f} | 中位 {q.iloc[2]:.1f} "
          f"| 75% {q.iloc[3]:.1f} | 95% {q.iloc[4]:.1f}")


def pct_in(s, v):
    return (s < v).mean()


bt = pd.read_csv("tda_project/outputs/regime_v05_benchmark_daily.csv", parse_dates=["date"])
bt = bt.set_index("date")["wind_close"]

segs = {
    "2013 钱荒": ("2013-06-01", "2013-06-30"),
    "2015 股灾": ("2015-06-12", "2015-07-08"),
    "2016 熔断": ("2016-01-04", "2016-01-28"),
    "2018 熊市": ("2018-06-15", "2018-07-12"),
    "2021 抱团瓦解": ("2021-02-18", "2021-03-17"),
    "2022 俄乌+封城": ("2022-03-01", "2022-04-26"),
    "2024 微盘崩": ("2024-01-02", "2024-02-08"),
    "2025 关税冲击": ("2025-04-01", "2025-04-30"),
    "2026-03 N1": ("2026-03-18", "2026-04-01"),
    "2026-06~07 L2": ("2026-06-18", "2026-07-10"),
    "2026-09 L3": ("2026-09-09", "2026-09-28"),
    "2026-10 下旬 N3": ("2026-10-20", "2026-11-03"),
}
print("\n" + "=" * 90)
print(f"{'区段':<18}{'top5中位':>10}{'2021后分位':>12}{'top1中位':>10}{'同期涨幅':>10}")
print("=" * 90)
for lab, (a, b) in segs.items():
    s = df[(df["date"] >= a) & (df["date"] <= b)]
    if len(s) == 0:
        print(f"{lab:<18} 无观测")
        continue
    bp = bt.loc[a:b]
    chg = bp.iloc[-1] / bp.iloc[0] - 1 if len(bp) > 1 else np.nan
    flag = f"{pct_in(sub['top5_share'], s['top5_share'].median()):>11.0%}" if a >= "2021-01-01" else f"{'—':>11}"
    print(f"{lab:<18}{s['top5_share'].median():>10.1f}{flag}{s['top1_share'].median():>10.1f}{chg:>10.1%}")
print("=" * 90)

print("\n条件概率（2021 后，未来 20 日最低累计 <= -8%）：")
b21 = bt.loc["2021-01-01":]
fwd = pd.Series(index=b21.index, dtype=float)
for i in range(len(b21)):
    seg = b21.iloc[i:i + 21]
    if len(seg) >= 5:
        fwd.iloc[i] = seg.min() / b21.iloc[i] - 1
fwd = fwd.dropna()
base = float((fwd <= -0.08).mean())
print(f"  无条件基准 {base:.1%}（{int((fwd<=-0.08).sum())}/{len(fwd)} 日）")
for thr_pct in [0.70, 0.80, 0.90, 0.95]:
    thr = sub["top5_share"].quantile(thr_pct)
    sel = sub[sub["top5_share"] > thr]["date"]
    sel = sel[sel.isin(fwd.index)]
    if len(sel) == 0:
        continue
    rate = float((fwd.loc[sel] <= -0.08).mean())
    print(f"  top5 > {thr:.1f}（{thr_pct:.0%}分位，{len(sel)} 日）→ 跌超8% 比例 {rate:.1%}"
          f"（{rate/base:.2f}× 基准）")

seg26 = pd.concat([df[(df["date"] >= a) & (df["date"] <= b)]
                   for k, (a, b) in segs.items() if k.startswith("2026")])
print(f"\n2026 四段合计 {len(seg26)} 日：top5 中位 {seg26['top5_share'].median():.1f}"
      f"（2021后分位 {pct_in(sub['top5_share'], seg26['top5_share'].median()):.0%}）")
