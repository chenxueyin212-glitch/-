#!/usr/bin/env python
"""v0.23 记账补丁：45 事件漏保账（纯描述性重分类，不拟合任何参数）。

背景：旧账本把「事件发生但确认门未开」记为贡献 0（中性），盲区永不暴露。
本脚本把 45 事件逐个标注保护状态：
  已保护   = 判型为深慢/浅快（确认门打开并切换）
  触发层漏 = 归属窗内无可用触发（v0.21 judged_type=未触发）。
             注意：S3 并非从未命中——45/45 宽窗识别中这 14 个属「仅损伤窗事后识别」
             （论文 5.3（三）24/7/14 分档），告警落在事件结束之后，来不及保护。
  确认门漏 = S3 触发了但确认门未开（judged_type=无法判定）
并列出每个漏保事件的谷底回撤（冻结字段 worst_cumulative_return_from_onset）
与窗内基准损益（market_breadth_daily.bmk_ret，2013-01 起可得）。

纪律：不覆盖任何冻结产物；输出独立 v0.23 文件。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("D:/WorkBuddy/2026-10-28-22-54-51")
OUT = ROOT / "tda_project/outputs"

ev = pd.read_csv(OUT / "regime_v05_crisis_events.csv",
                 parse_dates=["onset", "end", "label_end_date", "worst_date"])
m = pd.read_csv(OUT / "regime_v021_rolling_event_matrix.csv")
tt = (m[m.arm == "F7K4"][["event_id", "trigger_date", "trigger_offset",
                          "first_confirm_offset", "judged_type", "true_type",
                          "final_plan_type", "switch_dates_p4"]]
      .drop_duplicates("event_id"))
d = ev.merge(tt, on="event_id", how="left", suffixes=("", "_m"))

# ---- 保护状态分类（规则与 v0.21 触发语义一致，仅重标记） ----
def classify(row):
    jt = row["judged_type"]
    if jt in ("深慢", "浅快"):
        return "已保护", ""
    if jt == "未触发":
        return "触发层漏", "仅损伤窗事后识别(归属窗内无可用触发)"
    if jt == "无法判定":
        return "确认门漏", "S3触发但确认门未开"
    return "未知", f"judged_type={jt}"

d[["protection_status", "miss_layer"]] = d.apply(
    lambda r: pd.Series(classify(r)), axis=1)

# ---- 宽基窗内收益（2013 起可得） ----
b = pd.read_csv(ROOT / "paper_drafts/market_breadth_daily.csv",
                parse_dates=["date"]).set_index("date")
nav = (1 + b["bmk_ret"] / 100.0).cumprod()

def win_ret(a, b_):
    try:
        n = nav.loc[a:b_]
        if len(n) < 2:
            return np.nan, np.nan
        return (n.iloc[-1] / n.iloc[0] - 1) * 100, (n / n.cummax() - 1).min() * 100
    except Exception:
        return np.nan, np.nan

d[["ret_onset_trough", "dd_breadth"]] = d.apply(
    lambda r: pd.Series(win_ret(r["onset"], r["worst_date"])), axis=1)

d["deep"] = d["worst_cumulative_return_from_onset"] <= -0.10
d["deep_miss"] = (d["protection_status"] != "已保护") & d["deep"]

cols = ["event_id", "onset", "worst_date", "label_end_date", "end",
        "true_type", "judged_type", "protection_status", "miss_layer",
        "trigger_date", "trigger_offset", "first_confirm_offset",
        "avg_corr_at_onset", "N_at_onset",
        "worst_cumulative_return_from_onset", "ret_onset_trough", "dd_breadth",
        "deep", "deep_miss"]
ledger = d[cols].sort_values("onset")
ledger.to_csv(OUT / "regime_v023_miss_ledger.csv", index=False, encoding="utf-8-sig")

# ---- 摘要 ----
summary = {
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "rule": "judged in (深慢,浅快)=已保护; 未触发=触发层漏; 无法判定=确认门漏",
    "n_events": int(len(ledger)),
    "by_status": ledger["protection_status"].value_counts().to_dict(),
    "n_deep_miss": int(ledger["deep_miss"].sum()),
    "deep_miss_events": [
        {"event_id": int(r.event_id), "onset": str(r.onset)[:10],
         "worst": str(r.worst_date)[:10], "miss_layer": r.miss_layer,
         "true_type": r.true_type,
         "worst_cum_ret": round(float(r.worst_cumulative_return_from_onset), 4)}
        for r in ledger[ledger.deep_miss].itertuples()
    ],
}
(OUT / "regime_v023_miss_ledger_manifest.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print(ledger.groupby("protection_status").size().to_string())
print(f"\n深漏保 {summary['n_deep_miss']} 个：")
print(ledger[ledger.deep_miss][
    ["event_id", "onset", "worst_date", "miss_layer", "true_type",
     "worst_cumulative_return_from_onset"]].to_string(index=False))
print(f"\n已存 {OUT/'regime_v023_miss_ledger.csv'}")
