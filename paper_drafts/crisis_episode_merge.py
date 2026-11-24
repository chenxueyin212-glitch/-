# -*- coding: utf-8 -*-
"""
把 45 个标签段合并成「真正的危机」：以「高点到收复该高点」为一轮完整回撤（episode），
落在同一轮里的标签段并成一段。

两种合并口径：
  A. 峰值—收复口径：从高点回撤超过阈值即开一轮，收盘重新站上该高点即结束。
  B. 间隔口径：两段标签间隔 <= N 个自然日则并成一段（对照组）。
"""
import numpy as np
import pandas as pd

br = pd.read_csv("tda_project/outputs/regime_v05_benchmark_daily.csv",
                 parse_dates=["date"]).set_index("date").sort_index()
close = br["benchmark_close"].astype(float)
dates = close.index

ev = pd.read_csv("tda_project/outputs/regime_v05_crisis_events.csv", parse_dates=["onset", "end"])
ev = ev.sort_values("onset").reset_index(drop=True)
segs = [(r.event_id, r.onset, r.end) for r in ev.itertuples()]


def episodes(threshold):
    """从高点回撤超过 threshold 开一轮，收盘重新站上该高点结束。"""
    out = []
    peak_val, peak_date = close.iloc[0], dates[0]
    in_ep, ep_start = False, None
    trough_val, trough_date = np.inf, None
    for d, v in close.items():
        if v > peak_val:
            if in_ep:                       # 收复 -> 结束
                out.append(dict(start=ep_start, recovery=d, peak=peak_val,
                                trough_date=trough_date, trough=trough_val,
                                depth=(trough_val / peak_val - 1) * 100))
                in_ep = False
            peak_val, peak_date = v, d
            continue
        dd = v / peak_val - 1
        if not in_ep and dd <= -threshold:
            in_ep = True
            ep_start = peak_date
            trough_val, trough_date = v, d
        if in_ep and v < trough_val:
            trough_val, trough_date = v, d
    if in_ep:                               # 未收复（数据末端）
        out.append(dict(start=ep_start, recovery=pd.NaT, peak=peak_val,
                        trough_date=trough_date, trough=trough_val,
                        depth=(trough_val / peak_val - 1) * 100))
    return pd.DataFrame(out)


def merge_by_gap(gap_days):
    out, cur = [], [segs[0]]
    for sid, s, e in segs[1:]:
        if (s - cur[-1][2]).days <= gap_days:
            cur.append((sid, s, e))
        else:
            out.append(cur); cur = [(sid, s, e)]
    out.append(cur)
    return out


# ---------- A. 峰值—收复口径 ----------
for thr in (0.10, 0.20, 0.30):
    eps = episodes(thr)
    eps["n_seg"] = [int(((ev.onset >= r.start) & (ev.onset <= (r.recovery if pd.notna(r.recovery) else dates[-1]))).sum())
                    for r in eps.itertuples()]
    hit = eps[eps.n_seg > 0]
    print(f"\n=== 口径A：回撤 ≥{int(thr*100)}% 且收复高点为一轮 ===")
    print(f"全样本共 {len(eps)} 轮，其中含标签段的 {len(hit)} 轮；"
          f"45 个标签段被并成这 {len(hit)} 段")
    for i, r in enumerate(hit.itertuples(), 1):
        rec = str(r.recovery.date()) if pd.notna(r.recovery) else "未收复"
        print(f"  {i:2d}. {r.start.date()} → 谷底 {r.trough_date.date()}（{r.depth:6.1f}%）→ 收复 {rec:>10}  "
              f"并入 {r.n_seg:2d} 段")

# ---------- B. 间隔口径 ----------
print("\n=== 口径B：按标签段间隔合并（不要求收复）===")
for gap in (60, 120, 180):
    g = merge_by_gap(gap)
    print(f"  间隔 ≤{gap:3d} 日 -> {len(g):2d} 段；"
          f"最大一段并入 {max(len(c) for c in g)} 个标签段")

# 明细：口径A（20%）每轮并入了哪些标签段
print("\n=== 口径A（20%）每轮的标签段明细 ===")
eps = episodes(0.20)
eps["n_seg"] = [int(((ev.onset >= r.start) & (ev.onset <= (r.recovery if pd.notna(r.recovery) else dates[-1]))).sum())
                for r in eps.itertuples()]
for r in eps[eps.n_seg > 0].itertuples():
    end = r.recovery if pd.notna(r.recovery) else dates[-1]
    sub = ev[(ev.onset >= r.start) & (ev.onset <= end)]
    ids = ", ".join(f"{x.event_id}@{x.onset.date()}" for x in sub.itertuples())
    print(f"\n[{r.start.date()} → {end.date()}] 深度 {r.depth:.1f}%，并入 {len(sub)} 段：{ids}")

# 口径A 的轮次是否都伴随深幅：列出全部轮次
print("\n=== 口径A（10%）全部轮次（含未并入任何标签段的浅轮）===")
eps10 = episodes(0.10)
eps10["n_seg"] = [int(((ev.onset >= r.start) & (ev.onset <= (r.recovery if pd.notna(r.recovery) else dates[-1]))).sum())
                  for r in eps10.itertuples()]
print(eps10.assign(start=lambda x: x.start.dt.date,
                   recovery=lambda x: x.recovery.dt.date,
                   trough_date=lambda x: x.trough_date.dt.date)
      [["start", "trough_date", "depth", "recovery", "n_seg"]].round(1).to_string(index=False))
