"""拥挤度 vs 宽度差（结构性下跌的操作化定义）

「结构性下跌」的操作化定义
  宽度差 breadth(t) = 个股收益中位 - 宽基收益
  > 0 且幅度大 = 指数没怎么跌，但多数个股在跌（权重股护盘、赛道崩塌）
  ≈ 0 = 普涨普跌（系统性）

这是把"结构性"从叙事变成可测量量的关键一步，也是唯一能检验
"拥挤度是否真的指向结构性风险"的方式——如果拥挤度高但宽度差不变，
那拥挤度只是"集中度"的另一个名字，对产品没有增量。

数据：本地全市场个股日线（5221 只）+ 万得全A
"""
import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path

DB = Path("a_share_pit/tdx_central.db")
OUT = Path("paper_drafts")

con = sqlite3.connect(DB)
con.execute("PRAGMA cache_size=-200000")
days = [r[0] for r in con.execute(
    "select distinct date from equity_daily_raw where date>='2013-01-01' order by date")]
print(f"交易日 {len(days)}", flush=True)

rows = []
prev = None
# 逐日取当日收盘，与前一交易日对齐算收益
px_cache = {}
for i, dt in enumerate(days):
    r = con.execute("select code, close from equity_daily_raw where date=? and close>0", (dt,)).fetchall()
    cur = dict(r)
    if prev is not None and len(cur) > 300:
        common = set(cur) & set(prev)
        if len(common) > 300:
            rets = np.array([cur[c] / prev[c] - 1 for c in common])
            rets = rets[np.isfinite(rets)]
            rets = rets[(rets > -0.35) & (rets < 0.35)]  # 剔除异常/新股
            if rets.size > 300:
                rows.append((dt, rets.size, float(np.median(rets)) * 100,
                             float((rets > 0).mean()) * 100,
                             float((rets < -0.02).mean()) * 100,
                             float((rets < -0.05).mean()) * 100))
    prev = cur
    if (i + 1) % 500 == 0:
        print(f"  {dt} {i+1}/{len(days)}", flush=True)
con.close()

br = pd.DataFrame(rows, columns=["date", "n", "med_ret", "up_share", "down2", "down5"])
br["date"] = pd.to_datetime(br["date"])
br = br.sort_values("date").set_index("date")
print(f"宽度面板 {len(br)} 日")

bt = pd.read_csv("tda_project/outputs/regime_v05_benchmark_daily.csv", parse_dates=["date"])
bt = bt.set_index("date")["wind_close"]
bret = bt.pct_change() * 100

df = br.join(bret.rename("bmk_ret"), how="inner")
df["breadth"] = df["med_ret"] - df["bmk_ret"]
df.to_csv(OUT / "market_breadth_daily.csv", encoding="utf-8-sig")
print(f"合并 {len(df)} 日，已存 {OUT/'market_breadth_daily.csv'}")
print(f"宽度差 全样本：中位 {df['breadth'].median():+.2f}pp | 10% {df['breadth'].quantile(.1):+.2f} "
      f"| 90% {df['breadth'].quantile(.9):+.2f}")

# 20 日累计宽度差
df["breadth_20"] = df["breadth"].rolling(20).sum()

cg = pd.read_csv(OUT / "crowding_full_history_pct.csv", parse_dates=["date"]).set_index("date")
m = df.join(cg[["top5_share", "top5_share_pct"]], how="inner").dropna(subset=["breadth_20", "top5_share_pct"])
print(f"对齐样本 {len(m)} 日\n")

# 关键检验：拥挤度分位 → 未来 20 日累计宽度差
print("拥挤度分位 vs 随后 20 日累计宽度差（pp，正=个股跑输指数）：")
m["fwd_breadth_20"] = m["breadth_20"].shift(-20)
mm = m.dropna(subset=["fwd_breadth_20"])
for lo, hi in [(0, 50), (50, 70), (70, 85), (85, 95), (95, 101)]:
    sel = mm[(mm["top5_share_pct"] * 100 >= lo) & (mm["top5_share_pct"] * 100 < hi)]
    if len(sel) < 20:
        continue
    print(f"  分位 {lo:>3}-{hi:<3}%（{len(sel):4d} 日）：随后20日宽度差中位 "
          f"{sel['fwd_breadth_20'].median():+.2f}pp，均值 {sel['fwd_breadth_20'].mean():+.2f}pp")

# 秩相关（手工实现，环境无 scipy）
x = mm["top5_share_pct"].rank()
y = mm["fwd_breadth_20"].rank()
rho = float(np.corrcoef(x, y)[0, 1])
print(f"\n拥挤度分位 与 随后20日累计宽度差 的 Spearman 秩相关：{rho:+.3f}（n={len(mm)}）")

# 分段：2021 前 / 后
for lab, sub in [("2013-2020", mm[mm.index < "2021-01-01"]), ("2021 后", mm[mm.index >= "2021-01-01"])]:
    if len(sub) < 50:
        continue
    r = float(np.corrcoef(sub["top5_share_pct"].rank(), sub["fwd_breadth_20"].rank())[0, 1])
    print(f"  {lab:<10} 秩相关 {r:+.3f}（n={len(sub)}）")

# 各危机段的实际宽度差
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
print(f"{'区段':<18}{'拥挤度分位':>11}{'累计宽度差':>11}{'个股中位':>10}{'宽基':>9}{'跌超5%占比':>11}")
print("=" * 90)
for lab, (a, b) in segs.items():
    s = m.loc[a:b]
    if len(s) == 0:
        continue
    print(f"{lab:<18}{s['top5_share_pct'].median():>10.0%}"
          f"{s['breadth'].sum():>+11.2f}{s['med_ret'].sum():>+10.2f}{s['bmk_ret'].sum():>+9.2f}"
          f"{s['down5'].mean():>10.1f}%")
print("=" * 90)
