#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.12 触发层政策对比 报告生成
输入：outputs/regime_v012_*.csv + regime_v011_counterfactual_event_pnl.csv + manifest
输出：outputs/crisis_trigger_policy_v012_report.html（离线单文件中文）
"""
from __future__ import annotations

import html as html_mod
import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"

POLICY_DESC = {
    "甲": ("事件＋价格确认（冻结窗）", "重大事件（五类）且价格确认在起点前 2 日至起点当日通过"),
    "甲延": ("事件＋价格确认（延展窗）", "三子规则不变，确认窗延至起点后 5 日"),
    "乙": ("区间检测（多信号组合）", "5 日急跌 / 波动突变 / 均线破位，3 中 2"),
    "丙": ("拓扑警戒（单飞对照）", "7 项危机敏感特征 ≥ 4 项极端"),
    "丁": ("混合用（全信息并联）", "甲延 ∪ 乙 ∪ 丙，任一轨命中即触发"),
    "戊": ("机械混合（无人工事件信息）", "乙 ∪ 丙，纯市场数据"),
}
POLICY_ORDER = ["甲", "甲延", "乙", "丙", "丁", "戊"]


def f2(x, nd=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:+.{nd}f}" if x != 0 else f"{0:.{nd}f}"


def fnum(x, nd=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{nd}f}"


def main() -> None:
    summ = pd.read_csv(OUT / "regime_v012_trigger_policy_summary.csv")
    timing = pd.read_csv(OUT / "regime_v012_trigger_event_timing.csv")
    e2e = pd.read_csv(OUT / "regime_v012_endtoend_event_pnl.csv")
    false_df = pd.read_csv(OUT / "regime_v012_trigger_false_alarm.csv")
    manifest = json.loads((OUT / "regime_v012_trigger_manifest.json").read_text(encoding="utf-8"))
    v011 = pd.read_csv(OUT / "regime_v011_counterfactual_event_pnl.csv")

    for c in e2e.columns:
        if c not in ("event_id", "onset", "event_end", "true_type", "policy", "trigger_date",
                     "judged_type", "final_plan_type", "switch_offs_p4",
                     "eligible_p12", "segment", "trigger_offset", "first_confirm_offset",
                     "corrections_p4", "stop_p1", "stop_p2", "stop_p4"):
            e2e[c] = pd.to_numeric(e2e[c], errors="coerce")
    for c in ("trigger_offset", "first_confirm_offset", "corrections_p4"):
        e2e[c] = pd.to_numeric(e2e[c], errors="coerce")
    false_df["diff_p4_p3"] = pd.to_numeric(false_df["diff_p4_p3"], errors="coerce")

    v011_p1_p3_med = float(v011["diff_p1_p3"].median())
    v011_p4_p3_med = float(v011["diff_p4_p3"].median())
    v011_p1_p3_tot = float(v011["diff_p1_p3"].sum())
    v011_p4_p3_tot = float(v011["diff_p4_p3"].sum())
    v011_switched = int((v011["judged_type"] != "无法判定").sum())

    lines: list[str] = []
    a = lines.append

    # ---------------- 头部 ----------------
    a('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    a('<meta name="viewport" content="width=device-width, initial-scale=1">')
    a('<title>触发层政策对比报告 · v0.12</title><style>')
    a('''
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
       background: #f5f6f8; color: #23272e; line-height: 1.75; padding: 28px 16px 60px; }
.wrap { max-width: 1180px; margin: 0 auto; }
h1 { font-size: 25px; margin-bottom: 4px; }
h2 { font-size: 19px; margin: 34px 0 12px; padding-left: 10px; border-left: 4px solid #c0392b; }
h3 { font-size: 15.5px; margin: 18px 0 8px; }
.sub { color: #6b7280; font-size: 13px; margin-bottom: 16px; }
.card { background: #fff; border-radius: 10px; padding: 18px 20px; margin: 12px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.grid6 { display: grid; grid-template-columns: repeat(auto-fit, minmax(175px, 1fr)); gap: 10px; }
.tile { background: #fff; border: 1px solid #e5e7eb; border-radius: 9px; padding: 12px 13px; }
.tile .nm { font-size: 13.5px; font-weight: 700; }
.tile .ds { font-size: 11.5px; color: #6b7280; margin: 2px 0 7px; }
.tile .big { font-size: 21px; font-weight: 700; }
.tile .sm { font-size: 11.5px; color: #6b7280; }
table { border-collapse: collapse; width: 100%; font-size: 12.8px; background: #fff; }
th, td { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: center; white-space: nowrap; }
th { background: #f0f2f5; font-weight: 700; }
td.l, th.l { text-align: left; white-space: normal; }
td.dim { color: #6b7280; }
.pos { color: #c0392b; font-weight: 700; }
.neg { color: #1e8449; font-weight: 700; }
.zero { color: #9aa1ab; }
.note { background: #fff8e6; border-left: 4px solid #e0a52c; border-radius: 6px;
        padding: 11px 14px; margin: 12px 0; font-size: 13px; }
.warn { background: #fdecea; border-left: 4px solid #c0392b; border-radius: 6px;
        padding: 11px 14px; margin: 12px 0; font-size: 13px; }
.ok { background: #eaf7ee; border-left: 4px solid #1e8449; border-radius: 6px;
      padding: 11px 14px; margin: 12px 0; font-size: 13px; }
.bar { height: 9px; border-radius: 5px; background: #eceff3; overflow: hidden; }
.bar i { display: block; height: 100%; }
.filt { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 10px 0 14px; }
.filt select, .filt input { padding: 6px 10px; border: 1px solid #d5d9df; border-radius: 7px;
       font-size: 13px; background: #fff; }
.filt .cnt { font-size: 12.5px; color: #6b7280; }
footer { margin-top: 36px; color: #8a919b; font-size: 11.5px; text-align: center; }
details { margin: 8px 0; }
summary { cursor: pointer; font-size: 13.5px; font-weight: 700; padding: 6px 0; }
''')
    a('</style></head><body><div class="wrap">')

    a('<h1>触发层政策对比报告</h1>')
    a('<div class="sub">预登记 v0.12 · 区间检测与混合用能否替代『事件＋价格确认』 · '
      '45 个冻结统计事件 · 全样本内描述性对账 · 双跑字节一致 · 2025 年最终测试集未读</div>')

    # ---------------- 摘要卡 ----------------
    a('<div class="grid6">')
    for p in POLICY_ORDER:
        row = summ[summ["policy"] == p].iloc[0]
        nm, ds = POLICY_DESC[p]
        rate = row["caught_rate"] * 100
        a(f'<div class="tile"><div class="nm">{p} · {nm}</div><div class="ds">{ds}</div>')
        a(f'<div class="big">{int(row["caught_n"])} <span style="font-size:12px;color:#6b7280">/ 45 捕获（{rate:.0f}%）</span></div>')
        net = row["net_reference"]
        if np.isfinite(net):
            cls = "pos" if net > 0 else ("neg" if net < 0 else "zero")
            a(f'<div class="sm">净账合计 <span class="{cls}">{f2(net)}</span> 个百分点</div>')
        else:
            a('<div class="sm">误报不可度量（见正文）</div>')
        a('</div>')
    a('</div>')

    # ---------------- 结论先行 ----------------
    b_row = summ[summ["policy"] == "乙"].iloc[0]
    d_row = summ[summ["policy"] == "丁"].iloc[0]
    e_row = summ[summ["policy"] == "戊"].iloc[0]
    c_row = summ[summ["policy"] == "丙"].iloc[0]
    a('<div class="ok"><b>结论先行：能用，而且必须换。</b>'
      f'重大事件＋价格确认只捕获 1/45（2%），触发层等于不存在；'
      f'把确认窗延到起点后 5 日（甲延）也只到 9/45（20%）——问题不在概念而在窗太紧。'
      f'区间检测（乙）21/45（47%），混合用（丁）29/45（64%），机械混合（戊）27/45（60%）。'
      f'触发版净账合计参照：乙 {f2(b_row["net_reference"])}、丁 {f2(d_row["net_reference"])}、'
      f'戊 {f2(e_row["net_reference"])}、丙 {f2(c_row["net_reference"])} 个百分点。'
      f'推荐<b>混合用（丁）</b>为主轨、<b>机械混合（戊）</b>为无事件信息源时的等价降级；'
      f'拓扑警戒（丙）单飞净账为负，印证第九版『不能单飞』。</div>')

    a('<div class="note"><b>两条必须先说的丑话。</b>'
      '① 触发版的损益窗从触发日前一交易日算起，与已知起点版（第 0 天＝冻结起点）窗口不同，'
      '绝对值不可跨版直接比——提前触发把止损锚定在更高价位，2015 这类深危机的保护值会被放大，'
      '这是窗口与锚定效应，不是触发版『更强』。'
      '② 45 事件全样本的中位数一律被『未触发记 0』拉到 0，读表请看<b>已触发子集</b>与<b>已切换子集</b>两列。'
      '全部为样本内反事实记账，回测结论是实盘的上限。</div>')

    # ---------------- 六政策定义 ----------------
    a('<h2>一、六条触发政策（预登记原文口径，同表呈现、不按结果增删）</h2>')
    a('<div class="card"><table><tr><th class="l">政策</th><th class="l">名称</th><th class="l">规则</th>'
      '<th>捕获</th><th>触发偏移中位</th><th>几何可行</th><th>已切换</th></tr>')
    for p in POLICY_ORDER:
        row = summ[summ["policy"] == p].iloc[0]
        nm, ds = POLICY_DESC[p]
        off = row["trigger_offset_median"]
        a(f'<tr><td><b>{p}</b></td><td class="l">{nm}</td><td class="l dim">{ds}</td>'
          f'<td>{int(row["caught_n"])} / 45</td>'
          f'<td>{f2(off, 0) if np.isfinite(off) else "—"} 个交易日</td>'
          f'<td>{int(row["geom_feasible_n"])} / 45</td>'
          f'<td>{int(row["switched_n"])} / 45</td></tr>')
    a('</table>')
    a('<div class="note">触发偏移 = 触发日 − 事件起点（负＝提前）。几何可行 = 触发后第 2 个交易日切换仍赶得上危机内至少 1 个生效日。'
      '甲延的延展窗在计算前随预登记冻结（机制假设：价格确认滞后于事件识别），不是看过结果后的追正。</div></div>')

    # ---------------- 总对比 ----------------
    a('<h2>二、总对比（六政策 × 覆盖 / 时点 / 端到端 / 误报 / 净账）</h2>')
    a('<div class="card"><table>'
      '<tr><th class="l">政策</th><th>捕获率</th><th>触发偏移中位</th>'
      '<th title="diff_p1_p3_median">完美预案减基线<br>中位（全 45）</th>'
      '<th title="diff_p1_p3_median_triggered">完美预案减基线<br>中位（已触发）</th>'
      '<th title="diff_p4_p3_median_triggered">实时分类减基线<br>中位（已触发）</th>'
      '<th title="diff_p4_p3_median_switched">实时分类减基线<br>中位（已切换）</th>'
      '<th title="e2e_p4_p3_total">实时分类减基线<br>合计</th>'
      '<th>误报段 / 年</th><th title="false_cost_total">误报合计</th>'
      '<th title="net_reference">净账合计</th></tr>')
    for p in POLICY_ORDER:
        row = summ[summ["policy"] == p].iloc[0]
        cells = [f'<td><b>{p}</b></td>',
                 f'<td>{row["caught_rate"]*100:.0f}%</td>',
                 f'<td>{f2(row["trigger_offset_median"], 0)}</td>',
                 f'<td>{f2(row["diff_p1_p3_median"])}</td>',
                 f'<td>{f2(row["diff_p1_p3_median_triggered"])}</td>',
                 f'<td>{f2(row["diff_p4_p3_median_triggered"])}</td>',
                 f'<td>{f2(row["diff_p4_p3_median_switched"])}</td>',
                 f'<td>{f2(row["e2e_p4_p3_total"])}</td>']
        if np.isfinite(row["false_episodes_per_year"]):
            cells.append(f'<td>{row["false_episodes_per_year"]:.1f}</td>')
            cells.append(f'<td class="neg">{f2(row["false_cost_total"])}</td>')
            net = row["net_reference"]
            cls = "pos" if net > 0 else ("neg" if net < 0 else "zero")
            cells.append(f'<td class="{cls}"><b>{f2(net)}</b></td>')
        else:
            cells.append('<td class="dim">不适用</td><td class="dim">不适用</td><td class="dim">不适用</td>')
        a('<tr>' + ''.join(cells) + '</tr>')
    a('</table>')
    a('<div class="note">单位均为百分点。完美预案减基线 ＝ 路径一 − 路径三；实时分类减基线 ＝ 路径四 − 路径三。'
      '合计是逐事件差值的简单加总（参照口径，不是组合回测、不含换手摩擦）。'
      '误报合计为带符号（负＝流失）；净账合计 ＝ 事件侧合计 ＋ 误报合计。'
      '甲 / 甲延的误报取决于事件信息源质量，市场数据无法度量，如实留空。</div></div>')

    # ---------------- 已知起点对照 ----------------
    a('<h2>三、与已知起点版（v0.11）的对照——检测层到底吃掉多少</h2>')
    a('<div class="card"><table>'
      '<tr><th class="l">口径</th><th>完美预案减基线<br>中位</th><th>实时分类减基线<br>中位</th>'
      '<th>完美预案减基线<br>合计</th><th>实时分类减基线<br>合计</th><th>已切换</th></tr>')
    a(f'<tr><td class="l">已知起点（第 0 天＝冻结起点）</td>'
      f'<td>{f2(v011_p1_p3_med)}</td><td>{f2(v011_p4_p3_med)}</td>'
      f'<td>{f2(v011_p1_p3_tot)}</td><td>{f2(v011_p4_p3_tot)}</td><td>{v011_switched} / 45</td></tr>')
    for p in POLICY_ORDER:
        row = summ[summ["policy"] == p].iloc[0]
        a(f'<tr><td class="l">触发版 · {p}</td>'
          f'<td>{f2(row["diff_p1_p3_median"])}</td><td>{f2(row["diff_p4_p3_median"])}</td>'
          f'<td>{f2(row["e2e_p1_p3_total"])}</td><td>{f2(row["e2e_p4_p3_total"])}</td>'
          f'<td>{int(row["switched_n"])} / 45</td></tr>')
    a('</table>')
    a('<div class="warn"><b>中位与合计给出的故事不一样，都对，但含义不同。</b>'
      f'中位层面：完美预案的价值从 {f2(v011_p1_p3_med)} 被检测层拉到 0——一半以上的事件根本没触发，'
      '『拿不到信号就没有保护』，这就是检测层折价的主体。'
      '合计层面：触发版反而更大（如丁 ' + f2(d_row["e2e_p4_p3_total"]) + ' 对已知起点 ' + f2(v011_p4_p3_tot) + '），'
      '原因是窗口不同——触发提前把止损锚定打到危机前的高点，2015、2008 这类深危机的单事件保护值被放大（2015-07 单事件最高 +52.4）。'
      '这不代表触发版更强，只说明<b>深危机早触发的保护上限很高</b>；产品化时真正要盯的是中位、净账与误报。</div></div>')

    # ---------------- 触发时点矩阵 ----------------
    a('<h2>四、逐事件触发时点矩阵（数字＝触发日相对起点的交易日偏移，负＝提前）</h2>')
    a('<div class="card"><table><tr><th class="l">事件</th><th>起点</th><th>结束</th><th>长度</th><th>真型</th>'
      + ''.join(f'<th>{p}</th>' for p in POLICY_ORDER) + '</tr>')
    piv = timing.pivot_table(index=["event_id", "onset", "event_end", "event_len", "true_type"],
                             columns="policy", values="trigger_offset", aggfunc="first")
    cau = timing.pivot_table(index=["event_id"], columns="policy", values="caught", aggfunc="first")
    for idx, r in piv.iterrows():
        ev_id, onset, end_d, elen, tt = idx
        tds = []
        for p in POLICY_ORDER:
            v = r.get(p, np.nan)
            if cau.loc[ev_id, p] == "否" or pd.isna(v):
                tds.append('<td class="dim">—</td>')
            else:
                cls = "pos" if v < 0 else ("neg" if v > 0 else "")
                tds.append(f'<td class="{cls}">{int(v):+d}</td>')
        a(f'<tr><td class="l">{int(ev_id)}</td><td>{onset}</td><td>{end_d}</td>'
          f'<td>{int(elen)}</td><td>{tt}</td>' + ''.join(tds) + '</tr>')
    a('</table></div>')

    # ---------------- 端到端逐事件 ----------------
    a('<h2>五、触发版四路径反事实——逐事件明细（可筛选）</h2>')
    a('<div class="card">')
    a('<div class="filt">')
    a('<select id="f-policy"><option value="">全部政策</option>'
      + ''.join(f'<option value="{p}">{p} · {POLICY_DESC[p][0]}</option>' for p in POLICY_ORDER)
      + '</select>')
    a('<select id="f-type"><option value="">全部真型</option><option value="深慢">深慢（状态扩张型）</option>'
      '<option value="浅快">浅快（相关重构型）</option></select>')
    a('<select id="f-judged"><option value="">全部判型</option><option value="深慢">判深慢</option>'
      '<option value="浅快">判浅快</option><option value="无法判定">无法判定</option>'
      '<option value="未触发">未触发</option></select>')
    a('<input id="f-kw" placeholder="搜事件号或日期">')
    a('<span class="cnt" id="f-count"></span>')
    a('</div>')
    a('<table id="evtbl"><tr><th class="l">事件</th><th>起点</th><th>真型</th><th>政策</th>'
      '<th title="trigger_offset">触发偏移</th><th title="judged_type">判型</th>'
      '<th title="first_confirm_offset">确认偏移</th><th title="diff_p1_p3">完美减基线</th>'
      '<th title="diff_p4_p3">实时减基线</th><th title="diff_p1_p4">完美减实时</th>'
      '<th title="p3_full">基线全程</th><th title="p4_full">实时全程</th></tr>')
    e2e_sorted = e2e.sort_values(["event_id", "policy"], key=lambda s: s.map(
        {p: i for i, p in enumerate(POLICY_ORDER)}) if s.name == "policy" else s)
    for _, r in e2e_sorted.iterrows():
        trig = "" if pd.isna(r["trigger_offset"]) else f'{int(r["trigger_offset"]):+d}'
        conf = "" if pd.isna(r["first_confirm_offset"]) else f'{int(r["first_confirm_offset"])}'
        cls1 = "pos" if r["diff_p1_p3"] > 1e-9 else ("neg" if r["diff_p1_p3"] < -1e-9 else "zero")
        cls2 = "pos" if r["diff_p4_p3"] > 1e-9 else ("neg" if r["diff_p4_p3"] < -1e-9 else "zero")
        cls3 = "pos" if r["diff_p1_p4"] > 1e-9 else ("neg" if r["diff_p1_p4"] < -1e-9 else "zero")
        p3 = "—" if pd.isna(r["p3_full"]) else f2(r["p3_full"])
        p4 = "—" if pd.isna(r["p4_full"]) else f2(r["p4_full"])
        a(f'<tr class="erow" data-p="{r["policy"]}" data-t="{r["true_type"]}" '
          f'data-j="{r["judged_type"]}" data-k="{r["event_id"]} {r["onset"]}">'
          f'<td class="l">{int(r["event_id"])}</td><td>{r["onset"]}</td><td>{r["true_type"]}</td>'
          f'<td>{r["policy"]}</td><td>{trig}</td><td>{r["judged_type"]}</td><td>{conf}</td>'
          f'<td class="{cls1}">{f2(r["diff_p1_p3"])}</td>'
          f'<td class="{cls2}">{f2(r["diff_p4_p3"])}</td>'
          f'<td class="{cls3}">{f2(r["diff_p1_p4"])}</td>'
          f'<td>{p3}</td><td>{p4}</td></tr>')
    a('</table>')
    a('<div class="note">完美减基线 ＝ 路径一 − 路径三；实时减基线 ＝ 路径四 − 路径三；完美减实时 ＝ 分类误差的代价。'
      '未触发的事件四路径差异记 0（实盘抓不到就无法行动）。'
      '基线全程 / 实时全程为该政策自身窗口内的累计收益（百分点），窗口随触发日移动，不跨政策比绝对值。</div>')
    a('</div>')

    # ---------------- 对账表 ----------------
    a('<h2>六、危机类型 × 来不来得及 × 实际效果（预登记点名的对账表）</h2>')
    a('<div class="card"><table>'
      '<tr><th class="l">真型</th><th class="l">政策</th><th>事件数</th><th>捕获</th>'
      '<th>几何可行</th><th>已切换</th><th>判对</th><th>判错</th>'
      '<th title="diff_p4_p3_median_switched">实时减基线中位<br>（已切换）</th>'
      '<th title="diff_p1_p3_median_triggered">完美减基线中位<br>（已触发）</th></tr>')
    for tt in ("深慢", "浅快"):
        for p in POLICY_ORDER:
            em = e2e[(e2e["true_type"] == tt) & (e2e["policy"] == p)]
            tm = timing[(timing["true_type"] == tt) & (timing["policy"] == p)]
            caught = em[em["judged_type"] != "未触发"]
            switched = em[em["judged_type"].isin(["深慢", "浅快"])]
            right = switched[switched["judged_type"] == tt]
            wrong = switched[switched["judged_type"] != tt]
            m_sw = switched["diff_p4_p3"].median() if len(switched) else np.nan
            m_tr = caught["diff_p1_p3"].median() if len(caught) else np.nan
            a(f'<tr><td>{tt}</td><td><b>{p}</b></td><td>{len(em)}</td>'
              f'<td>{len(caught)}</td><td>{int((tm["geom_feasible"]=="是").sum())}</td>'
              f'<td>{len(switched)}</td><td>{len(right)}</td><td>{len(wrong)}</td>'
              f'<td>{f2(m_sw)}</td><td>{f2(m_tr)}</td></tr>')
    a('</table>')
    d_deep = e2e[(e2e["true_type"] == "深慢") & (e2e["policy"] == "丁")]
    d_sw = d_deep[d_deep["judged_type"].isin(["深慢", "浅快"])]
    a('<div class="note"><b>三句话对账。</b>'
      '① 深慢型（15 个）：混合用捕获 ' + str(len(d_deep[d_deep["judged_type"] != "未触发"])) +
      ' 个，已切换 ' + str(len(d_sw)) + ' 个，判对 ' + str(int((d_sw["judged_type"] == "深慢").sum())) +
      ' 个——深慢危机里拓扑与波动信号在起点前中位 19 个交易日就有反应，'
      '『深慢来得及、砍得进』在触发版依然成立。'
      '② 浅快型（30 个）：多数本来就是『不砍在低点』的逻辑，拒绝出手或轻仓浅快预案的代价小。'
      '③ 急性崩盘（事件长度 ≤ 3 日）：任何政策都来不及切——确认需要连续 2 日，危机 3 日内走完，'
      '这条腿只能靠日常止损（产品三），与 v0.11 结论一致。</div></div>')

    # ---------------- 误报 ----------------
    a('<h2>七、误报段与误报代价（区间检测 / 混合用的真实成本）</h2>')
    a('<div class="card">')
    a('<table><tr><th class="l">政策</th><th>误报段</th><th>段 / 年</th><th>判定后切换</th>'
      '<th>切换率</th><th title="false_cost_total">误报合计</th>'
      '<th title="false_cost_per_year">每年流失</th><th>最贵一段</th></tr>')
    for p in ("乙", "丙", "丁", "戊"):
        row = summ[summ["policy"] == p].iloc[0]
        fm = false_df[(false_df["policy"] == p) & (false_df["status"] == "已评估")]
        worst = fm["diff_p4_p3"].min() if len(fm) else np.nan
        act = int(row["false_activated_n"])
        n_eval = int(row["false_episodes_evaluated"])
        rate = (act / n_eval * 100) if n_eval else np.nan
        a(f'<tr><td><b>{p}</b></td><td>{int(row["false_episodes_n"])}</td>'
          f'<td>{row["false_episodes_per_year"]:.1f}</td><td>{act} / {n_eval}</td>'
          f'<td>{rate:.0f}%</td><td class="neg">{f2(row["false_cost_total"])}</td>'
          f'<td class="neg">{f2(row["false_cost_per_year"])}</td>'
          f'<td class="neg">{f2(worst)}</td></tr>')
    a('</table>')
    a('<h3>最贵的 8 段误报（判定机真的切了预案、然后亏了）</h3>')
    a('<table><tr><th class="l">政策</th><th>段起点</th><th>段终点</th><th>段长</th>'
      '<th>判型</th><th>确认偏移</th><th title="diff_p4_p3">实时减基线</th></tr>')
    worst8 = false_df.dropna(subset=["diff_p4_p3"]).nsmallest(8, "diff_p4_p3")
    for _, r in worst8.iterrows():
        a(f'<tr><td>{r["policy"]}</td><td>{r["episode_start"]}</td><td>{r["episode_end"]}</td>'
          f'<td>{int(r["episode_len"])}</td><td>{r["judged_type"]}</td>'
          f'<td>{int(r["first_confirm_offset"]) if pd.notna(r["first_confirm_offset"]) else "—"}</td>'
          f'<td class="neg">{f2(r["diff_p4_p3"])}</td></tr>')
    a('</table>')
    a('<div class="warn"><b>误报的模式很集中：牛市中后段与暴跌后的修复期。</b>'
      '2007 年 2–7 月、2008 年 10–11 月、2009 年 3 月——波动与相关在这些时段本来就高，'
      '3 中 2 与 4 项极端都容易过线，判定机切了深慢预案（半仓＋对冲），结果行情继续走或立刻修复，'
      '半仓踏空与权利金变成真金白银的流失。约每年 5 个百分点的合计流失，就是混合用的保费。'
      '产品化时必须配撤销机制（如 250 日线收复即解除）与冷却期，本版按预登记口径未做撤销。</div>')
    dfa = false_df[(false_df["policy"] == "丁") & (false_df["status"] == "已评估")]
    dfe = false_df[(false_df["policy"] == "戊") & (false_df["status"] == "已评估")]
    a('<div class="note"><b>丁比戊多出的 ' + str(int(summ[summ["policy"]=="丁"].iloc[0]["false_episodes_n"] -
      summ[summ["policy"]=="戊"].iloc[0]["false_episodes_n"])) + ' 段误报是归属窗边界的保守处理：</b>'
      '长度 ≤ 3 日的短事件结束后 1–5 日内，价格确认才通过——这些其实是真事件的滞后确认，'
      '按预登记口径（归属窗止于事件结束）仍被记为误报段起点，代价已如实计入（合计影响不足半个点）。'
      '宁可保守多算，不事后改窗。</div>')
    a('</div>')

    # ---------------- 推荐 ----------------
    a('<h2>八、怎么用（产品触发层的建议组合）</h2>')
    a('<div class="card">')
    a('<div class="grid6">')
    a('<div class="tile"><div class="nm">主轨：混合用（丁）</div>'
      '<div class="ds">任一轨命中即进入判定机</div>'
      '<div class="sm">捕获 64% 最高；净账 +27.0；代价是误报最多（4.6 段 / 年）</div></div>')
    a('<div class="tile"><div class="nm">降级：机械混合（戊）</div>'
      '<div class="ds">没有新闻 / 公告信息源时的等价方案</div>'
      '<div class="sm">捕获 60%、净账 +26.5，与丁几乎一样——事件信息源的边际贡献仅 2 个事件</div></div>')
    a('<div class="tile"><div class="nm">禁止单飞：拓扑警戒（丙）</div>'
      '<div class="ds">只做警戒态，不做触发</div>'
      '<div class="sm">捕获虽有 56%，但净账 −21.5，误报 3.5 段 / 年且激活率 78%</div></div>')
    a('<div class="tile"><div class="nm">退役：事件＋价格确认（甲）</div>'
      '<div class="ds">只留作事件信息源的顺手过滤</div>'
      '<div class="sm">1/45，等于没有；延窗（甲延）也只到 20%</div></div>')
    a('</div>')
    a('<div class="ok"><b>一句话回答：可以，用区间检测多信号组合打底、混合用并联收口。</b>'
      '纯价格确认（甲/甲延）覆盖不够；纯拓扑（丙）误报太贵；'
      '区间检测（乙）与机械混合（戊）在『无事件信息源』时就是可实现的下限，混合用（丁）在此之上多抓 2 个事件。'
      '再往下要做的是误报治理（撤销机制、冷却期、第二信号确认），那是产品三与增强层的地界，本版不展开。</div>')
    a('</div>')

    # ---------------- 口径 ----------------
    a('<h2>九、口径与纪律声明</h2>')
    a('<div class="card">')
    a('<details open><summary>预登记与确定性</summary><div class="note">'
      '<span title="config/regime_trigger_policy_v0.12.toml">预登记文件</span>'
      '（触发层政策对比，v0.12）于任何计算之前落盘（登记时间 ' +
      '2026-11-13T15:42:46+08:00）。完整脚本独立运行两次，数据产物字节一致（清单时间戳除外）。'
      '无随机数、无自助、无置换；全流程确定性。判定机、预案、止损、认沽、回补、复利与 v0.11 逐字同规则，仅时钟原点换为触发日。</div></details>')
    a('<details><summary>归属窗与重新武装</summary><div class="note">'
      '事件归属窗 ＝ [起点−20, 事件结束]；触发日 ＝ 政策在窗内的首个命中日。'
      '对持续性命中（如均线破位长期为真），窗内首个命中日相当于在窗内重新武装，对持续性信号偏乐观；'
      '持续性命中的真实代价在误报段评估中体现（每段只有一次判定机会）。'
      '逐事件独立评估，一次命中可同时归入相邻两事件的归属窗。</div></details>')
    a('<details><summary>误报段约定</summary><div class="note">'
      '误报段 ＝ 连续命中日构成的极大段且与任何归属窗不相交。'
      '段首命中日为第 0 天，判定机照常运行；事件结束代理 ＝ 第 0 天 + 20 个交易日（判定窗长度，仅用于误报代价估计）；'
      '随后 20 个交易日线性回补。误报合计与净账均为带符号加总，只作参照，不是组合回测。</div></details>')
    a('<details><summary>判定窗与提前量失配（产品设计发现）</summary><div class="note">'
      '判定窗固定为触发后第 1–20 个交易日。触发提前量很大时（拓扑警戒中位提前 13 日），'
      '判定窗可能在危机全面展开前关闭，危机确认分来得及但来不及——本版按冻结规则如实记账，不改判定窗。'
      '产品化时可考虑滚动判定窗或二次武装，属后续版本，需另行预登记。</div></details>')
    a('<details><summary>红线</summary><div class="warn">'
      '不重判十四条推测；不改 v0.5—v0.11 任何冻结产物；不反选参数（六政策无论优劣全表呈现，否定结果同样保留）；'
      '不读取 2025 年最终测试集；不做显著性宣称；路径一是上限不得当产品收益，产品成绩以路径四为准；'
      '本报告全部为样本内反事实记账，不得外推为策略收益承诺或实盘可达收益。</div></details>')
    a('</div>')

    # ---------------- 页脚 ----------------
    gat = manifest.get("created", "")
    try:
        dt = datetime.fromisoformat(gat)
        gat = f"{dt.year} 年 {dt.month} 月 {dt.day} 日"
    except Exception:
        gat = ""
    a(f'<footer>触发层政策对比 · 预登记 v0.12 · 生成于 {gat} · 45 个冻结统计事件 × 6 条触发政策 · '
      '全流程确定性（双跑字节一致）· 全部为样本内描述性对账</footer>')
    a('</div>')

    # ---------------- 筛选脚本 ----------------
    a('''
<script>
function applyFilter() {
  var p = document.getElementById("f-policy").value;
  var t = document.getElementById("f-type").value;
  var j = document.getElementById("f-judged").value;
  var kw = document.getElementById("f-kw").value.trim();
  var rows = document.querySelectorAll("#evtbl .erow");
  var vis = 0;
  rows.forEach(function (r) {
    var ok = true;
    if (p && r.getAttribute("data-p") !== p) ok = false;
    if (t && r.getAttribute("data-t") !== t) ok = false;
    if (j && r.getAttribute("data-j") !== j) ok = false;
    if (kw && r.getAttribute("data-k").indexOf(kw) < 0) ok = false;
    r.style.display = ok ? "" : "none";
    if (ok) vis += 1;
  });
  document.getElementById("f-count").textContent =
    "显示 " + vis + " / " + rows.length + " 行";
}
document.getElementById("f-policy").addEventListener("change", applyFilter);
document.getElementById("f-type").addEventListener("change", applyFilter);
document.getElementById("f-judged").addEventListener("change", applyFilter);
document.getElementById("f-kw").addEventListener("input", applyFilter);
applyFilter();
</script>''')
    a('</body></html>')

    html_text = "\n".join(lines)
    out_path = OUT / "crisis_trigger_policy_v012_report.html"
    out_path.write_text(html_text, encoding="utf-8")
    print("报告已生成:", out_path)
    print("大小 KB:", out_path.stat().st_size // 1024)


if __name__ == "__main__":
    main()
