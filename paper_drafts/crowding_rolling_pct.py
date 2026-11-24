"""拥挤度：滚动分位口径 + 领先性检验

为什么不用全史分位
- 绝对水平跨期不可比：2016 熔断 top5 中位 25.1%、2015 股灾 33.5%，但 2021 后中位已升到 40.5%
  （注册制扩容、小盘股数量增加、机构集中度提升）。全史分位会把 2021 后判成普遍高位。
- 改用 756 日滚动分位（与冻结判定机的 85% 门槛同口径），只比"当下相对过去三年"的位置。

检验
1. 各危机段的滚动分位位置
2. 2026 各段拥挤度何时突破 90 分位——早于/晚于触发日多少交易日
3. 条件概率：滚动分位 > 90% 时，未来 20 日跌超 8% 的概率
"""
import numpy as np
import pandas as pd
from pathlib import Path

OUT = Path("paper_drafts")
df = pd.read_csv(OUT / "crowding_full_history.csv", parse_dates=["date"]).set_index("date")
df = df.sort_index()

# 756 日滚动分位（不含当日）
def roll_pct(s, w=756, minp=250):
    out = np.full(len(s), np.nan)
    v = s.to_numpy(float)
    for i in range(len(v)):
        h = v[max(0, i - w):i]
        h = h[np.isfinite(h)]
        if h.size >= minp and np.isfinite(v[i]):
            out[i] = (h < v[i]).mean()
    return pd.Series(out, index=s.index)

for c in ["top5_share", "top1_share"]:
    df[c + "_pct"] = roll_pct(df[c])
df.to_csv(OUT / "crowding_full_history_pct.csv", encoding="utf-8-sig")

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
print("=" * 96)
print(f"{'区段':<18}{'top5中位':>10}{'滚动分位中位':>13}{'突破90%日数':>12}{'同期涨幅':>10}{'类型':>10}")
print("=" * 96)
TYPE = {"2015 股灾": "系统性", "2016 熔断": "系统性", "2018 熊市": "系统性", "2013 钱荒": "系统性",
        "2021 抱团瓦解": "结构性", "2024 微盘崩": "结构性", "2026-03 N1": "结构性",
        "2026-06~07 L2": "结构性", "2026-09 L3": "结构性", "2026-10 下旬 N3": "结构性",
        "2022 俄乌+封城": "系统性", "2025 关税冲击": "系统性"}
for lab, (a, b) in segs.items():
    s = df.loc[a:b]
    if len(s) == 0:
        continue
    bp = bt.loc[a:b]
    chg = bp.iloc[-1] / bp.iloc[0] - 1 if len(bp) > 1 else np.nan
    n90 = int((s["top5_share_pct"] > 0.90).sum())
    print(f"{lab:<18}{s['top5_share'].median():>10.1f}{s['top5_share_pct'].median():>13.0%}"
          f"{n90:>8}/{len(s):<3}{chg:>10.1%}{TYPE.get(lab,''):>8}")
print("=" * 96)

# 领先性：2026 各段前 60 交易日，拥挤度首次突破 90% 的日期
print("\n2026 各段拥挤度首次突破 90 分位的时点（相对段起点）：")
for lab in ["2026-03 N1", "2026-06~07 L2", "2026-09 L3", "2026-10 下旬 N3"]:
    a, b = segs[lab]
    start = pd.Timestamp(a)
    win = df.loc[start - pd.Timedelta(days=120):b]
    brk = win[win["top5_share_pct"] > 0.90]
    if len(brk) == 0:
        print(f"  {lab:<16} 前 120 自然日内未突破 90%")
        continue
    first = brk.index[0]
    lead = len(df.loc[first:start]) - 1
    print(f"  {lab:<16} 首次突破 {first.date()}（提前 {lead} 交易日），段内突破 "
          f"{int((df.loc[a:b]['top5_share_pct']>0.90).sum())} 日")

# 条件概率：滚动分位 > 阈值 → 未来 20 日跌超 8%
print("\n条件概率（2013 后有滚动分位的样本，未来 20 日最低累计 <= -8%）：")
bb = bt.loc["2014-01-01":]
fwd = pd.Series(index=bb.index, dtype=float)
for i in range(len(bb)):
    seg = bb.iloc[i:i + 21]
    if len(seg) >= 5:
        fwd.iloc[i] = seg.min() / bb.iloc[i] - 1
fwd = fwd.dropna()
v = df["top5_share_pct"].reindex(fwd.index)
base = float((fwd <= -0.08).mean())
print(f"  无条件基准 {base:.1%}（{int((fwd<=-0.08).sum())}/{len(fwd)} 日）")
for thr in [0.60, 0.70, 0.80, 0.85, 0.90, 0.95]:
    sel = v[v > thr].index
    if len(sel) < 20:
        continue
    rate = float((fwd.loc[sel] <= -0.08).mean())
    # 2021 后子样本
    sel21 = [d for d in sel if d >= pd.Timestamp("2021-01-01")]
    rate21 = float((fwd.loc[sel21] <= -0.08).mean()) if sel21 else np.nan
    print(f"  分位 > {thr:.0%}（{len(sel):5d} 日）→ {rate:.1%}（{rate/base:.2f}×）"
          f" | 2021后 n={len(sel21):4d} → {rate21:.1%}")

# 分类型汇总：系统性 vs 结构性下跌的拥挤度分位
print("\n按下跌类型汇总（滚动分位中位）：")
for t in ["系统性", "结构性"]:
    labs = [k for k in segs if TYPE.get(k) == t]
    vals = [df.loc[a:b, "top5_share_pct"].median() for k, (a, b) in segs.items()
            if TYPE.get(k) == t and len(df.loc[a:b]) > 0]
    if vals:
        print(f"  {t}（{len(vals)} 段）：中位 {np.median(vals):.0%}  各段 "
              + ", ".join(f"{v:.0%}" for v in vals))
