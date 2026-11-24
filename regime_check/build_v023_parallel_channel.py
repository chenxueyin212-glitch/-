#!/usr/bin/env python
"""v0.23 分社团塌（分散式解体）并行通道 —— 评价脚本。

按 config/regime_parallel_channel_v0.23.toml 实现（登记时刻 2026-11-20T15:55:00+08:00
早于本脚本任何输出）。通道独立于 S3，不改冻结层，全部输出 v0.23 独立文件。

主口径：
  分散态 = PR30 ≥ 2.50 且 corr30 ≤ 0.60（corr=行业两两相关上三角中位数）
  深回撤 = dd20 ≤ -8%（万得全A 距 20 交易日滚动高点）
  激活   = 分散态 且 深回撤；退出 = dd20 > -4%（滞回）；解除后 20 日线性回补 0.7→1.0
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("D:/WorkBuddy/2026-10-28-22-54-51")
OUT = ROOT / "tda_project/outputs"
CFG = ROOT / "tda_project/config/regime_parallel_channel_v0.23.toml"

# ---------------- 参数（与 TOML 一致） ----------------
W = 30
PR_CUT, CORR_CUT, DD_CUT, EXIT_DD = 2.50, 0.60, -0.08, -0.04
POS_ACTIVE, REC_DAYS = 0.7, 20
TRAIN_END = pd.Timestamp("2025-04-07")
VAL_START = pd.Timestamp("2025-04-08")

# ---------------- 1. 行业面板 → 滚动 PR / 相关中位 ----------------
con = sqlite3.connect(ROOT / "a_share_pit/tdx_central.db")
sw = pd.read_sql("select code, date, close from sw_industry_daily", con)
con.close()
sw["date"] = pd.to_datetime(sw["date"])
piv = sw.pivot_table(index="date", columns="code", values="close").sort_index()
ret = np.log(piv).diff()
full = ret.loc["2004-01-01":]
cover = full.notna().mean()
ret = ret[cover[cover >= 0.98].index]
N = ret.shape[1]
print(f"行业面板 {N} 个 × {ret.shape[0]} 日")


def dims(R: np.ndarray) -> tuple[float, float]:
    """返回 (PR, 两两相关上三角中位数)。与 effective_dimension.dims 同口径。"""
    R = R[~np.isnan(R).any(axis=1)]
    T = len(R)
    if T < 20:
        return np.nan, np.nan
    C = np.corrcoef(R.T)
    if not np.all(np.isfinite(C)):
        return np.nan, np.nan
    ev = np.clip(np.linalg.eigvalsh(C), 0, None)
    s = ev.sum()
    if s <= 0:
        return np.nan, np.nan
    pr = s**2 / (ev**2).sum()
    iu = np.triu_indices(N, k=1)
    return float(pr), float(np.median(C[iu]))


def rolling_dims(win: int) -> pd.DataFrame:
    vals = ret.values
    idx = ret.index
    rows = []
    for i in range(win - 1, len(vals)):
        pr, cr = dims(vals[i - win + 1 : i + 1])
        rows.append((idx[i], pr, cr))
    return pd.DataFrame(rows, columns=["date", f"pr{win}", f"corr{win}"]).set_index("date")


feat = rolling_dims(W)
print(f"滚动 PR{W}/corr{W} 可用 {feat[f'pr{W}'].notna().sum()} 日")

# ---------------- 2. 基准 dd20（冻结万得全A 全史） ----------------
bm = pd.read_csv(OUT / "regime_v05_benchmark_daily.csv", parse_dates=["date"])
bm = bm[["date", "benchmark_close", "benchmark_ret_pct"]].set_index("date").sort_index()
bm["dd20"] = bm["benchmark_close"] / bm["benchmark_close"].rolling(20).max() - 1
bm["ret"] = bm["benchmark_ret_pct"] / 100.0

df = bm.join(feat, how="left")
for c in (f"pr{W}", f"corr{W}"):
    df[c] = df[c].ffill(limit=3)


# ---------------- 3. 状态机 ----------------
def build_state(df: pd.DataFrame, pr_cut: float, corr_cut: float, dd_cut: float,
                win: int = W) -> pd.DataFrame:
    prc, crc = f"pr{win}", f"corr{win}"
    out = df.copy()
    active = np.zeros(len(out), bool)
    pos = np.ones(len(out))
    state, rec = 0, 0
    pr_v, cr_v, dd_v = out[prc].values, out[crc].values, out["dd20"].values
    for i in range(len(out)):
        cond = (np.isfinite(pr_v[i]) and np.isfinite(cr_v[i]) and np.isfinite(dd_v[i])
                and pr_v[i] >= pr_cut and cr_v[i] <= corr_cut and dd_v[i] <= dd_cut)
        if state == 1:
            if dd_v[i] > EXIT_DD:
                state, rec = 0, REC_DAYS
            else:
                active[i] = True
                pos[i] = POS_ACTIVE
        if state == 0:
            if cond:
                state, rec = 1, 0
                active[i] = True
                pos[i] = POS_ACTIVE
            elif rec > 0:
                rec -= 1
                pos[i] = POS_ACTIVE + (1 - POS_ACTIVE) * (REC_DAYS - rec) / REC_DAYS
    out["active"] = active
    out["pos"] = pos
    return out


st = build_state(df, PR_CUT, CORR_CUT, DD_CUT)
print(f"主口径激活日 {int(st.active.sum())} 日，仓位<1日 {int((st.pos < 1).sum())} 日")

# ---------------- 4. 事件评价 ----------------
led = pd.read_csv(OUT / "regime_v023_miss_ledger.csv", parse_dates=[
    "onset", "worst_date", "label_end_date", "end"])
cal = st.index
pos_of = {d: i for i, d in enumerate(cal)}


def td_add(d: pd.Timestamp, k: int) -> int:
    """d 的交易日下标 + k（越界截断）。"""
    i = pos_of.get(d)
    if i is None:
        j = cal.searchsorted(d)
        i = int(j) if j < len(cal) else len(cal) - 1
    return min(max(i + k, 0), len(cal) - 1)


ev_rows = []
covered = np.zeros(len(cal), bool)
for r in led.itertuples():
    a, w_, le = td_add(r.onset, -5), td_add(r.worst_date, 0), td_add(r.label_end_date, 20)
    covered[a : le + 1] = True
    seg = st.iloc[a : w_ + 1]
    fire_idx = np.where(seg["active"].values)[0]
    caught = len(fire_idx) > 0
    fire_date = (seg.index[fire_idx[0]] if caught else pd.NaT)
    fire_off = int(fire_idx[0]) - 5 if caught else np.nan  # 相对 onset，负=提前
    # 简化损益：onset → worst+20td
    e = td_add(r.worst_date, 20)
    s0 = td_add(r.onset, 0)
    win = st.iloc[s0 : e + 1]
    rr = win["ret"].fillna(0.0).values
    p = win["pos"].values
    nav_f = float(np.prod(1 + rr))
    nav_c = float(np.prod(1 + p * rr))
    # 未捕获诊断：窗内 PR/corr/dd 中位与各条件是否曾成立
    diag = dict(
        pr_med=round(float(np.nanmedian(win["pr30"].values)), 3),
        corr_med=round(float(np.nanmedian(win["corr30"].values)), 3),
        dd_min=round(float(np.nanmin(win["dd20"].values)), 4),
        ever_dispersed=bool(((win["pr30"] >= PR_CUT) & (win["corr30"] <= CORR_CUT)).any()),
        ever_deep=bool((win["dd20"] <= DD_CUT).any()),
    )
    ev_rows.append(dict(
        event_id=int(r.event_id), onset=str(r.onset)[:10], worst=str(r.worst_date)[:10],
        judged=r.judged_type, protection=r.protection_status, miss_layer=r.miss_layer,
        caught=caught, fire_date=str(fire_date)[:10] if caught else "",
        fire_offset=fire_off,
        pnl_full_pct=round((nav_f - 1) * 100, 3),
        pnl_channel_pct=round((nav_c - 1) * 100, 3),
        pnl_diff_pp=round((nav_c - nav_f) * 100, 3),
        **diag))
ev = pd.DataFrame(ev_rows)

# 验证期已知危机窗（v0.18 六段）并入覆盖掩码 —— 口径修正：
# 首跑只盖 45 事件，把 2026 真实危机激活日误计为验证期误报；此处修复掩码，触发规则未动。
VAL_EPISODES = [("2026-02-25", "2026-03-02", "L1"), ("2026-03-18", "2026-03-23", "N1"),
                ("2026-06-18", "2026-07-10", "L2"), ("2026-07-09", "2026-07-31", "N2"),
                ("2026-09-09", "2026-09-28", "L3"), ("2026-10-20", "2026-11-03", "N3")]
for a_, b_, _lab in VAL_EPISODES:
    covered[td_add(pd.Timestamp(a_), -5) : td_add(pd.Timestamp(b_), 20) + 1] = True

fa_mask = st["active"].values & ~covered
fa_days = int(fa_mask.sum())
train_mask = cal <= TRAIN_END
val_mask = cal >= VAL_START
fa_train = int((fa_mask & train_mask).sum())
fa_val = int((fa_mask & val_mask).sum())
yrs_train = train_mask.sum() / 244
yrs_val = val_mask.sum() / 244

# ---------------- 5. 汇总 ----------------
miss9 = ev[ev.event_id.isin([5, 6, 7, 8, 9, 11, 13, 15, 17])]
caught9 = miss9[miss9.caught]

def episode(a: str, b: str, lab: str) -> dict:
    seg = st.loc[a:b]
    act = seg[seg.active]
    s0, e0 = td_add(pd.Timestamp(a), 0), td_add(pd.Timestamp(b), 20)
    win = st.iloc[s0 : e0 + 1]
    rr = win["ret"].fillna(0.0).values
    nav_f = float(np.prod(1 + rr))
    nav_c = float(np.prod(1 + win["pos"].values * rr))
    return dict(episode=lab, window=f"{a}~{b}", active_days=int(seg.active.sum()),
                first_active=str(act.index[0])[:10] if len(act) else "",
                max_pos_drop=round(float((1 - seg.pos.min()) * 100), 2),
                pnl_full_pct=round((nav_f - 1) * 100, 3),
                pnl_channel_pct=round((nav_c - 1) * 100, 3),
                pnl_diff_pp=round((nav_c - nav_f) * 100, 3))

episodes = [
    episode("2026-02-20", "2026-04-05", "2026 N1/L1 2-3月"),
    episode("2026-06-01", "2026-08-15", "2026 L2/N2 6-7月"),
    episode("2026-08-20", "2026-11-03", "2026 L3/N3 9-10月"),
]

rejects = []
if fa_train > 20 * yrs_train:
    rejects.append(f"训练期误报 {fa_train}日 > {20*yrs_train:.0f}日(20日/年×{yrs_train:.1f}年)")
if len(caught9) == 0:
    rejects.append("训练期可评估漏保 9 事件捕获数 = 0")
pnl_sum = float(ev.loc[ev.caught & (ev.onset <= "2025-04-07"), "pnl_diff_pp"].sum())
if pnl_sum <= 0:
    rejects.append(f"训练期捕获事件简化损益差合计 {pnl_sum:.2f}pp ≤ 0")

summary = {
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "config": str(CFG.name),
    "mask_fix_note": "首跑覆盖掩码只含45事件，把2026真实危机激活日误计为验证期误报；"
                     "已修复为45事件窗+v0.18验证期六段窗（触发规则与阈值未动）",
    "params": dict(W=W, pr_cut=PR_CUT, corr_cut=CORR_CUT, dd_cut=DD_CUT,
                   exit_dd=EXIT_DD, pos=POS_ACTIVE, recovery_days=REC_DAYS),
    "n_industries": int(N),
    "active_days_total": int(st.active.sum()),
    "false_alarm": dict(train_days=fa_train, train_years=round(float(yrs_train), 2),
                        train_per_year=round(fa_train / yrs_train, 1),
                        val_days=fa_val, val_per_year=round(fa_val / yrs_val, 1)),
    "miss9_catch": dict(caught=int(len(caught9)), total=9,
                        caught_ids=[int(x) for x in caught9.event_id],
                        offsets={int(r.event_id): r.fire_offset for r in caught9.itertuples()}),
    "train_pnl_diff_pp_sum": round(pnl_sum, 2),
    "val_episodes": episodes,
    "reject_triggered": rejects,
    "verdict": "通道不采纳" if rejects else "通道通过登记的否定门槛（仍须人工判读+论文披露污染）",
}
(OUT / "regime_v023_parallel_channel_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
ev.to_csv(OUT / "regime_v023_parallel_channel_events.csv", index=False, encoding="utf-8-sig")
st[["pr30", "corr30", "dd20", "active", "pos"]].to_csv(
    OUT / "regime_v023_parallel_channel_daily.csv", encoding="utf-8-sig")

# ---------------- 6. 敏感性（只报告不择优） ----------------
def sens(tag: str, **kw):
    win = kw.get("win", W)
    s2 = build_state(kw.get("df", df), kw.get("pr", PR_CUT), kw.get("cr", CORR_CUT),
                     kw.get("dd", DD_CUT), win=win)
    fa = int((s2.active.values & ~covered & train_mask).sum())
    rows = []
    for r in led.itertuples():
        a, w_ = td_add(r.onset, -5), td_add(r.worst_date, 0)
        if s2.iloc[a : w_ + 1]["active"].any():
            rows.append(int(r.event_id))
    c9 = [e for e in rows if e in (5, 6, 7, 8, 9, 11, 13, 15, 17)]
    return dict(tag=tag, train_fa_days=fa, train_fa_per_year=round(fa / yrs_train, 1),
                caught_all=len(rows), caught_miss9=c9, miss9_ids=c9)

train_slice = df.loc[:TRAIN_END, f"pr{W}"].dropna()
pr_p80 = float(train_slice.quantile(0.80))
cr_p20 = float(df.loc[:TRAIN_END, f"corr{W}"].dropna().quantile(0.20))
sens_rows = [
    sens("主口径"),
    sens("A 分位阈值", pr=pr_p80, cr=cr_p20),
    sens("B W=40", df=rolling_dims(40).join(bm[["dd20", "ret"]], how="right").assign(
        pr40=lambda x: x["pr40"].ffill(limit=3), corr40=lambda x: x["corr40"].ffill(limit=3)), win=40),
    sens("C dd=-6%", dd=-0.06),
    sens("C dd=-10%", dd=-0.10),
]
print("\n=== 敏感性（只报告不择优）===")
for s in sens_rows:
    print(f"  {s['tag']:<12} 训练误报 {s['train_fa_days']:>4}日({s['train_fa_per_year']}/年)  "
          f"捕获事件 {s['caught_all']:>2}  捕获漏保9中 {len(s['miss9_ids'])}: {s['miss9_ids']}")
summary["sensitivity"] = sens_rows
summary["sensitivity_params"] = dict(pr_p80=round(pr_p80, 3), corr_p20=round(cr_p20, 3))
(OUT / "regime_v023_parallel_channel_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------------- 7. 控制台报告 ----------------
print("\n=== 45 事件 × 通道捕获（漏保事件优先）===")
show = ev[ev.protection != "已保护"].sort_values("onset")
print(show[["event_id", "onset", "worst", "miss_layer", "caught", "fire_date",
            "fire_offset", "pnl_diff_pp", "pr_med", "corr_med", "dd_min",
            "ever_dispersed", "ever_deep"]].to_string(index=False))
print("\n=== 捕获事件（全部）损益差 ===")
print(ev[ev.caught][["event_id", "onset", "fire_offset", "pnl_full_pct",
                     "pnl_channel_pct", "pnl_diff_pp"]].to_string(index=False))
print(f"\n训练期误报 {fa_train} 日 / {yrs_train:.2f} 年 = {fa_train/yrs_train:.1f} 日/年")
print(f"验证期误报 {fa_val} 日 / {yrs_val:.2f} 年 = {fa_val/yrs_val:.1f} 日/年")
print("\n=== 验证期三段 ===")
for e in episodes:
    print(f"  {e['episode']}: 激活 {e['active_days']} 日, 首激活 {e['first_active']}, "
          f"最大减仓 {e['max_pos_drop']}%, 损益差 {e['pnl_diff_pp']:+.2f}pp "
          f"(满仓 {e['pnl_full_pct']:+.2f}% vs 通道 {e['pnl_channel_pct']:+.2f}%)")
print(f"\n判定：{summary['verdict']}")
if rejects:
    for x in rejects:
        print(f"  [否定] {x}")
