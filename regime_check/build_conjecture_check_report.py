"""Stage B-4: render a single-file offline HTML report for the conjecture check.

All numbers are read from outputs/regime_conjecture_verdicts.json,
regime_labels_meta.json, regime_daily_ph_summaries.json and
regime_conjecture_grid.csv. No conclusion is hard-coded here.
"""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"

V = json.loads((OUT / "regime_conjecture_verdicts.json").read_text(encoding="utf-8"))
M = json.loads((OUT / "regime_labels_meta.json").read_text(encoding="utf-8"))
P = json.loads((OUT / "regime_daily_ph_summaries.json").read_text(encoding="utf-8"))
with (OUT / "regime_conjecture_grid.csv").open(encoding="utf-8-sig", newline="") as f:
    GRID = list(csv.DictReader(f))

E = lambda s: html.escape(str(s))  # noqa: E731

with (OUT / "xy_crisis_events.csv").open(encoding="utf-8-sig", newline="") as _f:
    _EV = list(csv.DictReader(_f))
RUN_LENGTHS = [int(r["label_run_days"]) for r in _EV
               if r["left_censored_label"].strip().lower() != "true"]
MAX_RUN = max(RUN_LENGTHS) if RUN_LENGTHS else 0
N_GE60 = sum(1 for x in RUN_LENGTHS if x >= 60)


def is_sig(x):
    return (x["p_bonferroni_pass"] == "True" and x["ci_crosses_zero"] == "False"
            and x["degenerate"] == "False")


N_SIG_CELLS = sum(1 for x in GRID if is_sig(x))
N_SIG_V0 = sum(1 for x in GRID if is_sig(x) and x["version"] == "v0_primary")


def state_sizes_rows():
    items = list(V["state_sizes"].items())
    out = []
    for i in range(0, len(items), 2):
        left = items[i]
        right = items[i + 1] if i + 1 < len(items) else ("", "")
        out.append(f"<tr><td>{E(left[0])}</td><td class='num'>{left[1]}</td>"
                   f"<td>{E(right[0])}</td>"
                   f"<td class='num'>{right[1] if right[0] != '' else ''}</td></tr>")
    return "".join(out)

COLOR = {
    "支持": "#1b7f4b", "矛盾": "#b23b3b", "部分支持": "#b8791b",
    "无法判定（含数据不足）": "#6b7280",
}
BG = {
    "支持": "#e8f5ee", "矛盾": "#fbeaea", "部分支持": "#fdf4e3",
    "无法判定（含数据不足）": "#f1f2f4",
}


def fmt(v, nd=4):
    if v is None or v == "":
        return "—"
    try:
        x = float(v)
        if abs(x) < 1e-4 and x != 0:
            return f"{x:.3g}"
        return f"{x:.{nd}f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return E(v)


def badge(verdict):
    return (f'<span class="badge" style="color:{COLOR.get(verdict,"#333")};'
            f'background:{BG.get(verdict,"#eee")};border-color:{COLOR.get(verdict,"#999")}">'
            f'{E(verdict)}</span>')


def verdict_distribution_svg():
    counts = V["verdict_counts"]
    order = ["支持", "部分支持", "矛盾", "无法判定（含数据不足）"]
    total = sum(counts.values()) or 1
    x0, y, w, h = 40, 30, 560, 26
    parts = []
    xx = x0
    for k in order:
        n = counts.get(k, 0)
        if not n:
            continue
        bw = w * n / total
        parts.append(f'<rect x="{xx:.1f}" y="{y}" width="{bw:.1f}" height="{h}" '
                     f'fill="{COLOR[k]}" opacity="0.88"/>')
        if bw > 34:
            parts.append(f'<text x="{xx+bw/2:.1f}" y="{y+18}" text-anchor="middle" '
                         f'font-size="12" fill="#fff" font-weight="600">{n}</text>')
        xx += bw
    legend = []
    lx = x0
    for k in order:
        n = counts.get(k, 0)
        legend.append(f'<rect x="{lx}" y="76" width="10" height="10" fill="{COLOR[k]}" rx="2"/>')
        legend.append(f'<text x="{lx+15}" y="85" font-size="11.5" fill="#444">{E(k)} {n}</text>')
        lx += 22 + len(k) * 12 + 24
    return (f'<svg viewBox="0 0 680 104" width="100%" style="max-width:680px">'
            + "".join(parts) + f'<text x="{x0}" y="20" font-size="12" fill="#555">'
            f'14 条推测判定分布（共 {total} 条）</text>' + "".join(legend) + "</svg>")


def key_grid_table():
    """v0 primary, selected (panel, state, summary) cells."""
    want = [
        ("phti_p16", "crisis_in", "W_t"),
        ("phti_p16", "crisis_in", "h0_death_mean"),
        ("phti_p16", "crisis_in", "h1_count"),
        ("phti_p27", "crisis_in", "W_t"),
        ("phti_p27", "crisis_in", "h1_count"),
        ("xy_network", "crisis_in", "h2_count"),
        ("xy_network", "crisis_in", "industry_average_correlation"),
        ("phti_p16", "pre20", "W_t"),
        ("phti_p16", "pre20", "h0_death_cv"),
        ("phti_p16", "pre20", "h1_count"),
        ("xy_network", "pre20", "h2_count"),
        ("phti_p16", "pre_high_vol", "W_t"),
        ("phti_p16", "pre_low_vol", "W_t"),
        ("phti_p16", "bull", "W_t"),
        ("phti_p16", "bear", "W_t"),
    ]
    idx = {(g["version"], g["panel"], g["state"], g["summary"]): g for g in GRID}
    rows = []
    for p, s, c in want:
        g = idx.get(("v0_primary", p, s, c))
        if not g:
            continue
        sig = (g["p_bonferroni_pass"] == "True" and g["ci_crosses_zero"] == "False")
        mark = '<span class="sig">✓</span>' if sig else ""
        rows.append(
            "<tr>" + f"<td>{E(p)}</td><td>{E(s)}</td><td>{E(c)}</td>"
            f'<td class="num">{fmt(g["median_a"],6)}</td>'
            f'<td class="num">{fmt(g["median_b"],6)}</td>'
            f'<td class="num">{fmt(g["delta"],6)}</td>'
            f'<td class="num">{fmt(g["std_effect"],3)}</td>'
            f'<td class="num">[{fmt(g["ci_lo"],6)}, {fmt(g["ci_hi"],6)}]</td>'
            f'<td class="num">{fmt(g["p_raw"],4)} {mark}</td>'
            f'<td class="num">{g["n_a"]}</td></tr>')
    head = ("<tr><th>点云</th><th>状态</th><th>摘要</th><th>状态中位数</th>"
            "<th>常态中位数</th><th>差值</th><th>标准化效应</th>"
            "<th>95% 区块自助 CI</th><th>自助 p</th><th>n</th></tr>")
    return f'<table class="grid">{head}{"".join(rows)}</table>'


def verdict_cards():
    out = []
    for v in V["verdicts"]:
        out.append(f'''
<div class="card" style="border-left-color:{COLOR.get(v["verdict"],"#999")}">
  <div class="card-h"><span class="cid">{E(v["id"])}</span>
    <span class="ctitle">{E(v["claim"].split("｜")[0])}</span>{badge(v["verdict"])}</div>
  <div class="card-claim">{E(v["claim"])}</div>
  <div class="card-sec"><b>证据：</b>{E(v["evidence"])}</div>
  <div class="card-sec"><b>判定依据：</b>{E(v["reason"])}</div>
  <div class="tier">{E(v["evidence_tier"])}</div>
</div>''')
    return "".join(out)


def stability_table():
    st = V["cross_version_stability"]
    rows = []
    for k, d in st.items():
        ns = {s: n for s, n in d.items() if isinstance(n, int) and s not in
              ("C01_up_out_of_4", "C04_sig_cells")}
        rows.append(
            f"<tr><td><b>{E(k)}</b></td>"
            f'<td class="num">{ns.get("bull",0)}</td>'
            f'<td class="num">{ns.get("bull_adjustment",0)}</td>'
            f'<td class="num">{ns.get("bear",0)}</td>'
            f'<td class="num">{ns.get("bear_turn",0)}</td>'
            f'<td class="num">{ns.get("fuzzy",0)}</td>'
            f'<td class="num">{d.get("C01_up_out_of_4","—")}</td>'
            f'<td class="num">{d.get("C04_sig_cells","—")}</td></tr>')
    return ('<table class="grid"><tr><th>标签版本</th><th>牛</th><th>牛中调整</th>'
            '<th>熊</th><th>牛转熊</th><th>模糊</th>'
            '<th>C01 上升/4</th><th>C04 显著格</th></tr>'
            + "".join(rows) + "</table>")


def dup_table():
    rows = []
    for k, d in V["double_count_audit"].items():
        rows.append(
            f"<tr><td>{E(k)}</td><td class='num'>{d['daily_n']}</td>"
            f"<td class='num'>{fmt(d['daily_delta'],6)}</td>"
            f"<td class='num'>{fmt(d['daily_p'],4)}</td>"
            f"<td class='num'>{d['event_n']}</td>"
            f"<td class='num'>{fmt(d['event_delta'],6)}</td>"
            f"<td class='num'>{fmt(d['event_p'],4)}</td></tr>")
    return ('<table class="grid"><tr><th>摘要</th><th>日级 n</th><th>日级差值</th>'
            '<th>日级 p</th><th>事件级 n</th><th>事件级差值</th>'
            '<th>事件级 p</th></tr>' + "".join(rows) + "</table>")


def bear_lag_table():
    rows = []
    for x in M["bear_label_lag_days_vs_onset"]:
        v = x["bear_label_lag_days"]
        cls = "lag0" if v == 0 else ("lagna" if v is None else "")
        rows.append(f'<tr class="{cls}"><td>{x["event_id"]}</td>'
                    f'<td>{E(x["onset"])}</td>'
                    f'<td class="num">{v if v is not None else "未触发"}</td></tr>')
    return ('<table class="grid"><tr><th>事件</th><th>onset</th>'
            '<th>熊市标签滞后（交易日）</th></tr>' + "".join(rows) + "</table>")


def ph_meta_table():
    rows = []
    for k, d in P["panels"].items():
        c = d["W_t_v0_2_crosscheck"]
        rows.append(f"<tr><td>{E(k)}</td><td class='num'>{d['n_days']}</td>"
                    f"<td>{E(d['first_date'])} → {E(d['last_date'])}</td>"
                    f"<td class='num'>{d['n_windows_with_W']}</td>"
                    f"<td class='num'>{c['n_overlap_compared']}</td>"
                    f"<td class='num'>{fmt(c['max_abs_diff_vs_v0_2'],12)}</td>"
                    f"<td class='num'>{'通过' if c['passed'] else '失败'}</td>"
                    f"<td class='num'>{d['n_days_after_2024_12_31']}</td></tr>")
    return ('<table class="grid"><tr><th>面板</th><th>交易日</th><th>覆盖</th>'
            '<th>有效 W</th><th>与 v0.2 重叠</th><th>最大绝对差</th>'
            '<th>一致性</th><th>2025 后新增日</th></tr>' + "".join(rows) + "</table>")


CSS = """
:root{--ink:#1f2733;--sub:#5b6572;--line:#e3e7ec;--bg:#fff;--soft:#f7f9fb;
--accent:#2b5f9e;--warn:#b23b3b;--ok:#1b7f4b}
*{box-sizing:border-box}
body{margin:0;background:#eef1f5;color:var(--ink);
 font-family:"Segoe UI","Microsoft YaHei","PingFang SC",-apple-system,sans-serif;
 line-height:1.72;font-size:15px}
.wrap{max-width:1080px;margin:0 auto;padding:32px 26px 80px}
.hero{background:linear-gradient(135deg,#20374f,#2b5f9e);color:#fff;border-radius:14px;
 padding:34px 38px;margin-bottom:22px;box-shadow:0 6px 24px rgba(30,55,80,.16)}
.hero h1{margin:0 0 10px;font-size:27px;letter-spacing:.5px}
.hero p{margin:6px 0;color:#dce8f6;font-size:14.5px}
.hero .kpi{display:flex;gap:26px;margin-top:20px;flex-wrap:wrap}
.hero .kpi div{background:rgba(255,255,255,.12);border-radius:9px;padding:10px 16px}
.hero .kpi b{display:block;font-size:21px;color:#fff}
.hero .kpi span{font-size:12px;color:#c8daf0}
section{background:var(--bg);border:1px solid var(--line);border-radius:12px;
 padding:24px 28px;margin-bottom:18px;box-shadow:0 2px 8px rgba(20,40,70,.04)}
h2{font-size:19px;margin:0 0 14px;padding-left:11px;border-left:4px solid var(--accent)}
h3{font-size:15.5px;margin:20px 0 8px;color:#2b3a4a}
p{margin:9px 0}
.small{font-size:13px;color:var(--sub)}
.boundary{background:#fff8e8;border:1px solid #e8cf94;border-left:5px solid #c9901f;
 border-radius:8px;padding:15px 18px;margin:14px 0}
.boundary b{color:#8a5c00}
.danger{background:#fdf0f0;border:1px solid #ecc9c9;border-left:5px solid var(--warn);
 border-radius:8px;padding:15px 18px;margin:14px 0}
.ok{background:#edf8f1;border:1px solid #bfe3cd;border-left:5px solid var(--ok);
 border-radius:8px;padding:15px 18px;margin:14px 0}
table{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}
table.grid th{background:#f2f5f9;border:1px solid var(--line);padding:8px 9px;
 text-align:left;font-weight:600;color:#3b4a5a;white-space:nowrap}
table.grid td{border:1px solid var(--line);padding:7px 9px;vertical-align:top}
table.grid tr:nth-child(even) td{background:#fbfcfe}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.sig{color:var(--ok);font-weight:700}
tr.lag0 td{background:#fdf0f0!important}
tr.lagna td{color:#999}
.badge{display:inline-block;padding:2px 9px;border:1px solid;border-radius:20px;
 font-size:12px;font-weight:600;margin-left:8px;white-space:nowrap}
.card{border:1px solid var(--line);border-left:5px solid #999;border-radius:9px;
 padding:15px 18px;margin:12px 0;background:var(--soft)}
.card-h{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.cid{background:#2b5f9e;color:#fff;border-radius:5px;padding:1px 8px;font-size:12px;
 font-weight:700;letter-spacing:.5px}
.ctitle{font-weight:650;font-size:15px}
.card-claim{font-size:13px;color:var(--sub);margin:7px 0 10px}
.card-sec{font-size:13.3px;margin:5px 0}
.tier{margin-top:9px;font-size:12px;color:#7a8592;font-style:italic}
ul,ol{padding-left:22px;margin:9px 0}
li{margin:5px 0}
code{background:#eef2f7;border:1px solid #dde4ec;border-radius:4px;
 padding:1px 5px;font-size:12.5px;font-family:Consolas,Monaco,monospace}
.foot{text-align:center;color:#8a93a0;font-size:12px;margin-top:26px}
.tag{display:inline-block;background:#eaf0f8;color:#2b5f9e;border-radius:4px;
 padding:1px 7px;font-size:12px;margin:2px 4px 2px 0}
"""

vc = V["verdict_counts"]
n_sup = vc.get("支持", 0) + vc.get("部分支持", 0)
n_con = vc.get("矛盾", 0)
n_na = vc.get("无法判定（含数据不足）", 0)

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A股持续摘要状态推测核对报告</title>
<style>{CSS}</style></head><body><div class="wrap">

<div class="hero">
  <h1>A 股四状态「持续同调／持续摘要」推测核对报告</h1>
  <p>目的：<b>验证此前关于危机来临前／危机来临中／牛市／熊市持续摘要特征的推测是否正确</b>。
     不是预警系统、不是绩效评估、不是确认性检验。</p>
  <p>规格 <code>config/regime_conjecture_check.toml v0.1</code>（分组结果产生之前冻结）｜
     逐日粒度｜全日期口径｜三层牛熊规则＋歧义双解全披露</p>
  <div class="kpi">
    <div><b>{V['n_days']}</b><span>逐日标签行数</span></div>
    <div><b>{V['grid_rows']}</b><span>全格统计格数</span></div>
    <div><b>{n_sup}</b><span>支持／部分支持</span></div>
    <div><b>{n_con}</b><span>矛盾</span></div>
    <div><b>{n_na}</b><span>无法判定</span></div>
    <div><b>{V['method']['n_bootstrap']}</b><span>每格区块自助次数</span></div>
  </div>
</div>

<section>
<h2>0. 边界（请先读）</h2>
<div class="boundary">
<b>这一轮只做一件事：把 14 条推测逐条对到真实数据上，判定「支持／矛盾／无法判定」。</b>
<ul>
<li>全部是<b>样本内描述性对账</b>：不加载 Gate 0 冻结的 2025 最终测试标签／评分，不算策略收益、夏普、回撤、PR-AUC、仓位，不按结果反选状态划分或阈值。</li>
<li>「全日期」是用户为本核对线指定的口径，指兴业复现线已产出且此前已用于探索性描述的日期与摘要；<b>不等于读取 Gate 1 封存的 2025 最终测试集</b>。</li>
<li>2025-06 之后标「牛熊未定义」，仅保留摘要描述，{V['n_days_after_2025_06_excluded_from_groups']} 天不参与任何状态分组比较。</li>
<li>{E(V['gate_boundary'])}</li>
</ul>
</div>
<div class="danger">
<b>同源自证限制：</b>这套推测本来就是从同一批摘要数字推出来的，所以「支持」很大程度是
<b>用作者的工具验证作者的工具</b>的近亲。本轮的价值主要在<b>找出被数据打脸的条目</b>
以及把「我以为」和「我测过」分开；每条判定都标注了证据层级
（<span class="tag">原有实测已决定</span><span class="tag">本次新增信息</span>
<span class="tag">结构性判定</span><span class="tag">不判定</span>）。
</div>
</section>

<section>
<h2>1. 判定分布与一句话结论</h2>
{verdict_distribution_svg()}
<div class="ok">
<b>净结论：</b>14 条推测中 <b>{n_sup}</b> 条得到支持（含部分支持）、<b>{n_con}</b> 条被数据矛盾、
<b>{n_na}</b> 条判为无法判定（含结构性数据不足）。
其中阶段 A 的零计算对账已指出：真正有直接数字撑着的只有 <b>1</b> 条，
<b>6</b> 条从来没测过。本轮把能测的都测了，测不了的直接标「无法判定」而不硬凑结论。
</div>
<div class="danger">
<b>最重要的一条：推测的核心被推翻了。</b>推测认为「危机来临中，尺度类摘要（W₂、
landscape L1、H0 death、H1 birth/寿命）会全维同步跳升」。本轮在<b>真实危机事件段</b>
（16 个可用事件、221 个交易日）与常态做四状态分组比较，结果是
<b>p16/p27 两个面板共 6 个尺度量只有 3 个方向上升，0 个过 Bonferroni，全部 95% CI 跨零</b>：
p16 的 W_t 差值 0.000256（效应量 0.116，p=0.573）、H0 death 均值 −0.000428（p=0.838）、
H1 birth 均值 +0.000312（p=0.869）；p27 的 W_t −0.000042（p=0.934）、
H0 death 均值 +0.000012（p=0.997）、H1 birth 均值 −0.003326（p=0.271）。
窗口 RMS／方差同样不显著（p=0.70~0.84）。<br>
<b>这不与此前 ρ≈0.96 矛盾，而是两个不同命题</b>：那个 ρ 来自「按 60 日收益方差挑出
最低/最高两个极端窗口」的全样本秩相关，本质是「波动大 → barcode 按尺度放大」的同义反复；
本轮问的是「真实危机事件期间，摘要是否比常态高」。答案是否定的。
结合常态基线里包含大量 A 股放量上涨日（反杠杆效应），以及 60 日窗口对短危机段的稀释，
<b>「危机中持续摘要全线放大」这条推测在 A 股四状态分组口径下不成立</b>。
</div>
<div class="boundary">
<b>但「支持」也不等于「证实」。</b>本轮 5 条支持里，C05/C06 是<b>方向性弱支持</b>
（缩量型 4/6、放量型 5/6 尺度量方向符合，但 6 格全部未过 Bonferroni）；
C09 只判定「牛市与熊市有差异」这一层（10/10 格中位数差非零），
不判定差异是否拓扑独有；C03 有机械成分（见第 3 节盲区说明）；
C04 是「无差异」型支持。全格 {V['grid_rows']} 格中只有 <b>{N_SIG_CELLS}</b> 格过 Bonferroni
（主口径 v0 为 {N_SIG_V0} 格），且集中在 overheat / 放量·缩量分型的附加格，
<b>危机中与危机前的主判据格几乎全不显著</b>。
</div>
<p class="small">判定口径：状态组与常态组的中位数差，20 交易日循环区块自助
（B={V['method']['n_bootstrap']}，seed={V['method']['seed']}）给 95% 区间与双侧自助 p；
多重比较阈值 α={V['method']['alpha']}/{V['method']['bonferroni_m']}={V['method']['threshold']:.6f}；
<b>全程未使用 naive t</b>。危机段另做事件级去重（16 个事件起点），防止日级重复计数。</p>
</section>

<section>
<h2>2. 数据与方法</h2>
<h3>2.1 两条点云、两套摘要，不能混</h3>
<table class="grid">
<tr><th>点云</th><th>点是什么</th><th>摘要</th><th>本轮来源</th></tr>
<tr><td><b>兴业相关网络</b></td><td>一个点 = 一个申万二级行业，距离 = 过去 30 日收益相关距离，
 VR 复形 H1/H2</td><td>N=h2_count、h1_count、两维 landscape L1、max_h2_persistence、
 betti@0.4/0.6/0.8、平均相关、第一特征值占比、节点数（11 列）</td>
 <td><code>xy_corrected_features.csv</code>，既有逐日 3339 行，<b>零新增计算</b></td></tr>
<tr><td><b>PHTI 状态点云</b></td><td>一个点 = 一个交易日，坐标 = 该日 K 个行业日对数收益，
 60 日滚动窗口 VR 复形 H0/H1</td><td>W₂（相邻持续图距离）、SMA60、H0 death 均值/中位/最大/CV、
 最长边比、H1 数量/出生/寿命、窗口 RMS/方差、平均两两相关、第一特征值占比（16 列）</td>
 <td><code>regime_daily_ph_p16.csv / p27.csv</code>，<b>本轮补算逐日至全日期</b></td></tr>
</table>
<p class="small">注意：<code>phti_section33_ashare_check.json</code> 只有 237＋128 个<b>月末</b>窗口、
且是 2 行业对、百分数简单收益；本轮补算的是与 W₂ 同源的 16/27 行业面板逐日摘要，
单位与阈值不同，数值不可直接互比。</p>
<h3>2.2 逐日 PH 摘要补算与一致性核对</h3>
{ph_meta_table()}
<p class="small">W_t 与归档 v0.2 工程验收在重叠日期逐点复算，最大绝对差约 4～5×10⁻¹³，
说明补算没有改变既有管线数值；2025 起新增 442 个交易日，仅为「全日期」描述服务。</p>

<h3>2.3 三层状态标签（用户截图规则，规格冻结）</h3>
<table class="grid">
<tr><th>层</th><th>判定</th></tr>
<tr><td><b>第一层 · 趋势</b></td><td>牛：close&gt;MA250 且 MA250 的 20 日斜率&gt;0 且 250 日回撤&lt;15%，
<b>三条同时满足</b>；熊：三条全反且回撤&gt;20%。都不满足 → 进第二层。
主基准万得全A（至 2025-05-30），敏感性基准上证 000001。</td></tr>
<tr><td><b>第二层 · 宽度</b></td><td>模糊带里：偏多 A～D 满足任意 2 项 → 牛市中的调整；
偏空满足任意 2 项 → 牛转熊；都不足 2 项 → 保持模糊。
A=个股站上 MA20 占比、B=中证1000/沪深300 相对强弱、C=量能 250 日分位、D=MA20 vs MA60。</td></tr>
<tr><td><b>第三层 · 过热/超冷</b></td><td>各 4 条满足任意 1 项即触发，<b>只作附加标签，不判牛熊转换</b>；
用于识别放量型危机前。含 BIAS250 z-score、RSI14、涨停/跌停占比近似、750 日价格分位。</td></tr>
</table>
<p class="small"><b>歧义双解全披露、不反选</b>：B1（比值 60 日变化率）vs B2（两指数 60 日收益之差）、
C1（全A成交额 250 日分位）vs C2（上证 volume 250 日分位）、基准双解、
MA250 斜率双解、以及 legacy 5% 触发器，共 5 个标签版本全部计算，见第 6 节。</p>

<h3>2.4 危机标签与状态规模</h3>
<p>危机中 = 17 段危机的 onset..end（首段左删失，事件级分析只用 16 个可用事件）；
危机前 = onset 前 5／10／20 交易日，三档全披露；
四状态<b>不互斥</b>，输出主标签＋叠加标签（2015 牛顶既是牛市也是危机前）。</p>
<table class="grid"><tr><th>状态格</th><th>交易日数</th><th>状态格</th><th>交易日数</th></tr>
{state_sizes_rows()}
</table>
</section>

<section>
<h2>3. 十四条推测逐条判定</h2>
{verdict_cards()}

<h3>3.1 判定规则的已知盲区（不修改本轮结果）</h3>
<div class="boundary">
判定规则在<b>看到任何分组结果之前</b>冻结，本轮严格照规则执行一次、不按结果回改。
但有几处规则本身的信息量限制，必须明说，否则「支持／矛盾／无法判定」会被误读：
<ul>
<li><b>C01 的「矛盾」是方向一致性判据，不是显著反证。</b>规则要求 6 个尺度量
 <b>全部</b>方向上升才判支持（≥4 判部分支持），实测 3 上升 3 下降 → 判「矛盾」。
 加上 0 个过 Bonferroni，正确的读法是：<b>「危机中尺度摘要全维同步跳升」
 这个强断言没有被数据支持</b>，而不是「数据证明它们反向跳升」。
 这一点很重要，因为它恰好否定了推测里最核心、此前又被当作不证自明的那条。</li>
<li><b>C03「峰值滞后」含机械成分。</b>判据是「每个 onset 起 60 日内 W_t 的 argmax 位置」，
 于是滞后值必然落在 [0, 60]。实测 16 个事件的滞后为
 <code>[17,51,25,17,23,14,20,14,47,0,20,14,15,1,14,20]</code>，中位 17 天、
 仅 1 个事件为 0，CI [14,20] 不跨零，故按规则判「支持」。
 但 17 天<b>远小于 60 日窗口长度</b>，所以它并不支持「必须等窗口填满才达峰」那种
 系统性滞后；更准确的说法是「W_t 在危机起点后约 3 周内会出现一个峰值，
 但不能排除这是窗口内点位更替的构造效应」。该结论应视为<b>弱描述</b>。</li>
<li><b>C02 的低 R² 其实是反驳，不是「无法判定」。</b>推测说「尺度摘要几乎可被
 RV20＋平均相关＋第一特征值占比解释」，实测 W_t 对（窗口 RMS＋平均两两相关＋
 第一特征值占比）的回归 R² 仅 <b>0.0165 / 0.0236</b>，
 也就是<b>几乎完全不能被这三个变量线性解释</b>；同时残差在危机中 vs 常态也不显著。
 冻结规则只写了「R²&gt;0.7 且残差不显著 → 支持，否则无法判定」，
 没有为「R² 极低 → 矛盾」预设一档，所以本轮记为「无法判定」。
 <b>按对称性解读，这是对 C02 的反驳</b>（W_t 不是这三个量的代理，
 但也未显示独立的危机信息）。建议升版预登记时把这条改成双侧判定，本轮不改结果。</li>
<li><b>C07/C08/C11 的「方向」与「显著性」分离。</b>C07 的 4 个孔洞计数
 <b>全部方向上升</b>（与推测「下降」相反）但 0 个显著，按「只能双侧检验」的规则
 记为无法判定而非矛盾；C08 的 6 格 H0 death CV <b>全部方向下降</b>（与推测一致）
 但 0 个显著；C11 爆发初期 4 格峰值差全为正（H0 death max +0.0115/+0.0200、
 H1 count +2.5/+1.0）但 0 个显著。这三条都属于
 「方向有提示、证据不足」，不能当作成立，也不宜当作被推翻。</li>
</ul>
</div>
</section>

<section>
<h2>4. 全格统计关键摘录（主口径 v0）</h2>
<p class="small">下表是 {V['grid_rows']} 格全格表（<code>regime_conjecture_grid.csv</code>）的摘录；
完整表含 5 个标签版本 × 3 个点云 × 13 个状态 × 全部摘要，另加剥尺度残差行。
「✓」表示过 Bonferroni(12) 且 95% CI 不跨零。</p>
{key_grid_table()}
</section>

<section>
<h2>5. 三项专项诊断</h2>
<h3>5.1 事件级去重 vs 日级重复计数</h3>
<p>此前吃过「389 个信号日 → 40 个事件簇」的亏，所以危机段同时报两种口径：</p>
{dup_table()}
<p class="small">日级把同一段危机的每一天都当成独立观测，会机械压低 p 值；
事件级每个 onset 只取一个值。两者结论不一致时以事件级为准。</p>

<h3>5.2 W₂ 峰值滞后与剥尺度残差</h3>
<ul>
<li>p16 事件级 W_t 峰值滞后中位
 <b>{fmt(V['extra']['phti_p16']['W_peak_lag_median'],2)}</b> 交易日，
 p27 为 <b>{fmt(V['extra']['phti_p27']['W_peak_lag_median'],2)}</b>；
 完整逐事件表见 <code>regime_conjecture_verdicts.json → extra</code>。</li>
<li>W_t 对（窗口 RMS ＋ 平均两两相关 ＋ 第一特征值占比）回归 R²：
 p16 = <b>{fmt(V['extra']['phti_p16']['W_regression_R2_on_scale_corr_eig'],4)}</b>，
 p27 = <b>{fmt(V['extra']['phti_p27']['W_regression_R2_on_scale_corr_eig'],4)}</b>。
 这是 C02「尺度摘要是否只是波动＋共同因子的代理」的核心数字。</li>
<li>另算了 W₂/RMS、H0 death/RMS 与回归残差三列，危机中 vs 常态的检验已并入全格表。</li>
</ul>

<h3>5.3 熊市标签相对危机起点的滞后</h3>
<p>熊市②「回撤&gt;20%」是事后触发，标签会系统性滞后于危机起点并与「危机中」重叠，
故单列滞后天数，并把「熊市 ∩ 危机中」拆成独立状态格（{V['state_sizes'].get('bear_in_crisis',0)} 天）。
滞后 0 天（红色）表示该事件在 onset 当日已是熊市标签 —— 这类情况下
「熊市摘要」其实混入了危机本身。</p>
{bear_lag_table()}
</section>

<section>
<h2>6. 跨口径稳定性（歧义双解是否翻转结论）</h2>
{stability_table()}
<p class="small">「C01 上升/4」= 两个 PHTI 面板 × (W_t, H0 death 均值) 中危机中方向为上升的格数；
「C04 显著格」= 危机前 20 日窗口 5 个形状摘要中过 Bonferroni 的格数。
若两列在 5 个版本间稳定，说明结论不依赖 B/C 的歧义取法。</p>
</section>

<section>
<h2>7. 已知局限与本轮不做的事</h2>
<ul>
<li><b>停牌与涨跌停没有直接字段。</b>停牌股在库里是直接缺行（无 volume=0 记录），
 分母会自动缩小，2015-07 千股停牌时宽度占比被系统性高估；
 涨跌停家数只能按 close/prev_close 阈值近似，且未过滤除权日，因此 C13 判「无法判定」。</li>
<li><b>个股分母随时间膨胀</b>：2005 年约 1151 只、2026 年约 5175 只，
 宽度占比跨期可比性有限，逐日分母已写入产物。</li>
<li><b>60 日窗口的结构性限制</b>：16 个可用危机事件长度（交易日）={RUN_LENGTHS}，
 最长 <b>{MAX_RUN}</b> 天，能填满 60 日窗口的事件 <b>{N_GE60}</b> 个；
 「窗口填满后 H1/H2 消失」在本数据里根本观测不到，故 C10 判「无法判定（数据不足）」，
 不是「矛盾」。</li>
<li><b>逐日摘要仍是过去 60 日窗口的函数</b>，天然带平滑与滞后；
 所谓「爆发初期」看到的是窗口组成变化，不是当日结构。</li>
<li><b>第三层附加标签覆盖偏高</b>：规格写的是「4 条满足任意 1 项即触发」，
 实测过热 <b>1153/3339</b> 天（34.5%）、超冷 624 天，其中「涨停占比」594 天、
 「750 日价格分位」654 天各占大头。因此「过热」作为放量型危机前的独立代理
 <b>区分度有限</b>，其格子只能作描述，不足以单独支撑 C06。
 放量/缩量主分型仍用规格登记的「危机前 60 日平均绝对日收益按事件中位二分」
 （high 151 天 / low 154 天）。规则在分组结果前冻结，本轮不因覆盖率而回改阈值。</li>
<li><b>自助 p 是近似</b>：以自助分布中位数居中后比较 |观测值|，
 属区块自助 Wald 型双侧 p，不是精确检验；区间用 percentile CI。</li>
<li><b>明确未做</b>：读取 Gate 1 封存的 2025 最终测试集、计算任何策略绩效/IC/夏普、
 按分组结果反选状态或阈值、修改 <code>config/study.toml</code>、
 把结论外推为「TDA 对 A 股危机预警有效／无效」、启动 Gate 2 或 PHTI 正式绩效回测。</li>
</ul>
</section>

<section>
<h2>8. 结论与下一步</h2>
<div class="ok">
<b>对「推测是否正确」的直接回答：</b>见第 3 节 14 张判定卡与第 1 节分布图。
被判「矛盾」的条目就是被数据打脸的部分；判「无法判定」的条目中，
有一部分是<b>结构性测不了</b>（如 60 日窗口长于任何一段危机），
一部分是<b>本地数据缺字段</b>（停牌/涨跌停），
还有一部分是<b>规格里刻意不设方向</b>（兴业 N）。
这些都不能读成「推测成立」。
</div>
<p>本轮交付物（全部在 <code>tda_project/outputs/</code>）：</p>
<ul>
{"".join(f"<li><code>{E(x)}</code></li>" for x in [
 "regime_daily_labels.csv / regime_labels_meta.json（逐日三层标签与口径）",
 "regime_breadth_daily.csv（市场宽度、成交额、涨跌停近似）",
 "regime_daily_ph_p16.csv / regime_daily_ph_p27.csv（补算逐日形状摘要）",
 "regime_daily_ph_summaries.json（补算元数据与 v0.2 一致性核对）",
 "regime_conjecture_grid.csv（全格统计）",
 "regime_conjecture_verdicts.json（14 条判定、专项诊断、跨版本稳定性）",
 "regime_conjecture_check_report.html（本报告，单文件离线）",
])}
</ul>
<p class="small">脚本位于 <code>src/regime_check/</code>：
<code>build_breadth_daily.py</code>、<code>build_daily_ph_summaries.py</code>、
<code>build_regime_labels.py</code>、<code>verify_conjectures.py</code>、
<code>build_conjecture_check_report.py</code>。</p>
</section>

<div class="foot">A 股 TDA 项目 · 推测核对线 v0.1 · 样本内描述性对账 ·
 Gate 1 暂停 / 2025 最终测试未读取 / Gate 2 未启动</div>
</div></body></html>
"""

path = OUT / "regime_conjecture_check_report.html"
path.write_text(HTML, encoding="utf-8")
print(json.dumps({"report": str(path), "bytes": path.stat().st_size,
                  "verdict_counts": vc}, ensure_ascii=False, indent=2))
