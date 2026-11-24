# -*- coding: utf-8 -*-
"""
检验：2026 的 AI 硬件链事件，A 股更好的本地代理是不是科创50 / 创业板指，而非万得全A宽基？

三个问题：
  1) 与海外（韩国/日经/台湾）的 60 日滚动相关，科创/创业板是否显著高于宽基？
  2) 2026 各段涨跌，科创/创业板的幅度是否接近韩国（而不是宽基那种温和）？
  3) L2 期间行业分化与指数内部结构，能否说明"宽基稀释"了多少。

口径：全部日收盘价；相关性用日简单收益 60 日滚动（min 40）。
数据：本地 index_daily_raw（到 2026-11-04）+ akshare 科创50/科创综指 + 万得全A + 新浪全球指数。
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "a_share_pit" / "tdx_central.db"
OUT = ROOT / "paper_drafts"
US = OUT / "us_data"


def load_local_index() -> pd.DataFrame:
    con = sqlite3.connect(DB)
    df = pd.read_sql("select code, date, close from index_daily_raw where close is not null", con)
    con.close()
    df["date"] = pd.to_datetime(df["date"])
    piv = df.pivot_table(index="date", columns="code", values="close").sort_index()
    return piv


def load_kc() -> pd.DataFrame:
    import akshare as ak

    out = {}
    for sym, name in [("sh000688", "科创50"), ("sh000680", "科创综指")]:
        try:
            d = ak.stock_zh_index_daily(symbol=sym)
            d["date"] = pd.to_datetime(d["date"])
            out[name] = d.set_index("date")["close"].astype(float)
        except Exception as e:  # pragma: no cover
            print(f"[warn] {name} 取数失败: {e}")
    return pd.DataFrame(out).sort_index()


def load_wind_a() -> pd.Series:
    b = pd.read_csv(ROOT / "tda_project" / "outputs" / "regime_v05_benchmark_daily.csv")
    dcol = [c for c in b.columns if "date" in c.lower()][0]
    ccol = [c for c in b.columns if "close" in c.lower()][0]
    s = pd.Series(b[ccol].values, index=pd.to_datetime(b[dcol]))
    return s.sort_index().rename("万得全A")


def build() -> pd.DataFrame:
    loc = load_local_index()
    ren = {
        "000300": "沪深300",
        "000905": "中证500",
        "000852": "中证1000",
        "399006": "创业板指",
        "399005": "中小100",
        "399303": "国证2000",
        "000001": "上证综指",
        "399001": "深证成指",
    }
    px = loc[[c for c in ren if c in loc.columns]].rename(columns=ren)
    px = px.join(load_kc(), how="outer")
    px = px.join(load_wind_a(), how="outer")

    g = pd.read_csv(US / "global_px.csv", index_col=0, parse_dates=True)
    keep = [c for c in ["韩国KOSPI", "台湾加权", "日经225", "恒生", "SP500"] if c in g.columns]
    px = px.join(g[keep], how="outer")
    px = px.sort_index()
    return px


def corr_table(px: pd.DataFrame, start="2025-01-01", win=60) -> pd.DataFrame:
    r = px.pct_change()
    rows = []
    for a in px.columns:
        if a in ("韩国KOSPI", "台湾加权", "日经225", "恒生", "SP500"):
            continue
        rec = {"A股指数": a}
        for t in ["韩国KOSPI", "台湾加权", "日经225", "恒生", "SP500"]:
            if t not in px.columns:
                continue
            j = pd.concat([r[a], r[t]], axis=1).dropna()
            if len(j) < win:
                rec[t] = np.nan
                continue
            c = j.iloc[:, 0].rolling(win, min_periods=40).corr(j.iloc[:, 1])
            c = c[c.index >= start]
            rec[t] = round(float(c.mean()), 3) if len(c) else np.nan
        sub = r[a].dropna()
        sub = sub[sub.index >= start]
        rec["样本起点"] = sub.index.min().date() if len(sub) else None
        rows.append(rec)
    t = pd.DataFrame(rows)
    return t.sort_values("韩国KOSPI", ascending=False)


SEGS = [
    ("年初→A股高点 01-02~05-13", "2026-01-02", "2026-05-13"),
    ("滞涨期 05-13~06-17", "2026-05-13", "2026-06-17"),
    ("L2 06-18~07-30", "2026-06-18", "2026-07-30"),
    ("反弹 07-30~09-08", "2026-07-30", "2026-09-08"),
    ("L3 09-09~09-28", "2026-09-09", "2026-09-28"),
    ("N3 09-28~10-30", "2026-09-28", "2026-10-30"),
]


def seg_returns(px: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lab, a, b in SEGS:
        d = px.loc[a:b]
        if len(d) < 2:
            continue
        rec = {"段": lab}
        for c in d.columns:
            s = d[c].dropna()
            rec[c] = round(100 * (s.iloc[-1] / s.iloc[0] - 1), 1) if len(s) > 1 else np.nan
        rows.append(rec)
    return pd.DataFrame(rows).set_index("段")


def drawdown_2026(px: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in px.columns:
        s = px[c].dropna().loc["2026-01-01":"2026-10-31"]
        if len(s) < 30:
            continue
        hi_d = s.idxmax()
        after = s.loc[hi_d:]
        lo_d = after.idxmin()
        rows.append(
            dict(
                市场=c,
                年内高点日=hi_d.date(),
                高点回撤=round(100 * (after.min() / s.max() - 1), 1),
                低点日=lo_d.date(),
                高点前涨幅=round(100 * (s.max() / s.iloc[0] - 1), 1),
            )
        )
    return pd.DataFrame(rows).sort_values("高点回撤")


def main():
    px = build()
    px.to_csv(OUT / "ai_chain_proxy_px.csv", encoding="utf-8-sig")

    print("=" * 78)
    print("一、与海外的 60 日滚动相关（2025-01-01 起均值，min40）")
    print("=" * 78)
    ct = corr_table(px)
    print(ct.to_string(index=False))
    ct.to_csv(OUT / "ai_chain_proxy_corr.csv", index=False, encoding="utf-8-sig")

    print()
    print("=" * 78)
    print("二、2026 分段涨跌（%）")
    print("=" * 78)
    sr = seg_returns(px)
    cols = [c for c in ["万得全A", "上证综指", "沪深300", "中证500", "中证1000", "科创50", "科创综指", "创业板指", "韩国KOSPI", "台湾加权", "日经225", "恒生", "SP500"] if c in sr.columns]
    print(sr[cols].to_string())
    sr.to_csv(OUT / "ai_chain_proxy_segments.csv", encoding="utf-8-sig")

    print()
    print("=" * 78)
    print("三、2026 年内高点与随后回撤")
    print("=" * 78)
    dd = drawdown_2026(px)
    print(dd.to_string(index=False))
    dd.to_csv(OUT / "ai_chain_proxy_drawdown.csv", index=False, encoding="utf-8-sig")

    # L2 区间日均相关（用 60 日滚动值的区间均值已在上表，这里给 L2 内单日相关）
    print()
    print("=" * 78)
    print("四、L2 区间内（06-18~07-30）日收益与韩国的相关")
    print("=" * 78)
    r = px.pct_change()
    win = r.loc["2026-06-18":"2026-07-30"]
    for a in [c for c in px.columns if c not in ("韩国KOSPI", "台湾加权", "日经225", "恒生", "SP500")]:
        for t in ["韩国KOSPI", "日经225"]:
            if t not in win.columns:
                continue
            j = win[[a, t]].dropna()
            if len(j) > 5:
                print(f"  {a:8s} vs {t:8s} n={len(j):3d} r={j.iloc[:,0].corr(j.iloc[:,1]):+.3f}")


if __name__ == "__main__":
    main()
