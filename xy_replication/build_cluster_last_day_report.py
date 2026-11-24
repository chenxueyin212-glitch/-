"""Build a single-file offline HTML report for the cluster-last-day IC study.

Reads only existing outputs; does not recompute or modify any diagnostic.
"""
from __future__ import annotations

import base64
import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
SRC = ROOT / "src" / "xy_replication"

J = json.loads((OUT / "xy_cluster_last_day_ic.json").read_text(encoding="utf-8"))
JSON_SRC = (OUT / "xy_cluster_last_day_ic.json").read_text(encoding="utf-8")
CSV_SRC = (OUT / "xy_cluster_last_day_ic.csv").read_text(encoding="utf-8-sig")
FIG_B64 = base64.b64encode((OUT / "xy_cluster_last_day_ic.png").read_bytes()).decode("ascii")
SCRIPT_SRC = (SRC / "cluster_last_day_ic.py").read_text(encoding="utf-8")
FEATURE_CSV = OUT / "xy_corrected_sw193_ifind_peak_features.csv"
WIND_CSV = OUT / "xy_wind_all_a_daily.csv"
HTML_OUT = OUT / "xy_cluster_last_day_report.html"


def esc(s) -> str:
    return html.escape(str(s), quote=False)


def f(v, d=4):
    return "—" if v is None else f"{v:.{d}f}"


def pct(v, d=2):
    return "—" if v is None else f"{v * 100:+.{d}f}%"


def pct0(v, d=1):
    return "—" if v is None else f"{v * 100:.{d}f}%"


def table(headers, rows) -> str:
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
                   for row in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def ci(lo, hi, d=4):
    if lo is None or hi is None:
        return "无定义"
    return f"[{f(lo, d)}, {f(hi, d)}]"


def yn(v):
    return "是" if v else "否"


# ---- recompute three hand-checkable examples from the ORIGINAL csv files ---
with FEATURE_CSV.open(encoding="utf-8-sig", newline="") as handle:
    feats = [r for r in csv.DictReader(handle) if r["date"] <= "2025-05-30"]
with WIND_CSV.open(encoding="utf-8-sig", newline="") as handle:
    wind = {r["date"]: float(r["open"])
            for r in csv.DictReader(handle)}
dates = [r["date"] for r in feats]
Ns = [int(r["h2_count"]) for r in feats]
opens = [wind[d] for d in dates]
example_targets = ["2015-07-29", "2019-01-21", "2024-02-21"]
examples = []
for target in example_targets:
    i = dates.index(target)
    r20 = opens[i + 21] / opens[i + 1] - 1
    rec = next(x for x in J["clusters"] if x["end"] == target)
    examples.append({
        "date": target, "N": Ns[i], "d1": dates[i + 1], "o1": opens[i + 1],
        "d21": dates[i + 21], "o21": opens[i + 21], "r20": r20,
        "json": rec["last_fwd20"], "confirm": rec["confirm_date"],
        "lag": rec["confirm_lag_calendar_days"],
        "confirm_r20": rec["confirm_fwd20"],
    })
    assert abs(r20 - rec["last_fwd20"]) < 1e-12, target

parts: list[str] = []
parts.append("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>事件簇末日 IC 诊断 · 详细报告</title>
<style>
body{font-family:"Segoe UI","Microsoft YaHei",Arial,sans-serif;color:#242321;
 max-width:1120px;margin:0 auto;padding:30px 26px 90px;line-height:1.75;background:#fff}
h1{font-size:26px;font-weight:600;margin:0 0 6px}
h2{font-size:19px;font-weight:600;margin:38px 0 12px;padding-bottom:7px;
 border-bottom:2px solid #e3e1da}
h3{font-size:15px;font-weight:600;margin:24px 0 8px}
p{margin:9px 0}small{color:#6a6862}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:12px 0}
th,td{border:1px solid #e0ded6;padding:5px 8px;text-align:left;vertical-align:top}
th{background:#f4f2ec;font-weight:600}
tbody tr:nth-child(even){background:#fbfaf7}
code{font-family:Consolas,"Courier New",monospace;background:#f4f2ec;padding:1px 4px;
 border-radius:3px;font-size:12px}
pre{font-family:Consolas,"Courier New",monospace;background:#f7f6f2;border:1px solid #e3e1da;
 padding:12px;overflow:auto;font-size:11.5px;max-height:540px;white-space:pre}
details{margin:10px 0;border:1px solid #e3e1da;border-radius:6px;padding:8px 12px}
summary{cursor:pointer;font-weight:600;font-size:13px}
.warn{background:#fff7e8;border-left:4px solid #c0861c;padding:11px 15px;margin:14px 0}
.bad{background:#fdeeee;border-left:4px solid #ad3a3a;padding:11px 15px;margin:14px 0}
.good{background:#edf6f1;border-left:4px solid #2c7a5a;padding:11px 15px;margin:14px 0}
.note{background:#f2f5fa;border-left:4px solid #3a6ea5;padding:11px 15px;margin:14px 0}
.pill{display:inline-block;background:#eef0e9;border:1px solid #d8d5ca;border-radius:12px;
 padding:1px 9px;font-size:11.5px;margin-right:6px}
.toc{background:#f7f6f2;border:1px solid #e3e1da;border-radius:8px;padding:12px 18px;
 column-count:2;font-size:13px}
.toc a{color:#185FA5;text-decoration:none}
.formula{background:#f7f6f2;border:1px solid #e3e1da;border-radius:6px;
 padding:10px 14px;font-family:Consolas,monospace;font-size:12.5px;margin:10px 0}
.axis{display:flex;align-items:stretch;gap:8px;margin:14px 0;flex-wrap:wrap}
.axis .step{flex:1;min-width:150px;background:#f2f5fa;border:1px solid #c9d7e8;
 border-radius:8px;padding:10px 12px;font-size:12.5px}
.axis .arrow{align-self:center;font-size:20px;color:#6a6862}
.axis .step.hot{background:#fff7e8;border-color:#e2c48c}
img{max-width:100%;border:1px solid #e3e1da;border-radius:6px;margin:12px 0}
.footer{border-top:1px solid #e3e1da;margin-top:46px;padding-top:14px;
 color:#6a6862;font-size:12px}
</style></head><body>""")

parts.append(
    "<h1>事件簇「最后一天」的 IC：详细报告</h1>"
    "<p><span class='pill'>只读诊断</span><span class='pill'>样本内探索性</span>"
    "<span class='pill'>非策略结果</span><span class='pill'>不修改既有输出</span>"
    "<span class='pill'>单文件离线</span></p>"
    "<p><small>生成于 2026-11-08 · 数据：xy_corrected_sw193_ifind_peak_features.csv "
    "（v1.2 修正版）＋ xy_wind_all_a_daily.csv（万得全A 881001.WI 日线）</small></p>"
)

parts.append(
    "<div class='toc'>"
    + "".join(f"<div><a href='#s{i}'>{t}</a></div>" for i, t in enumerate([
        "1. 问题与两种读法", "2. 因果警告：末日不可交易", "3. 数据与口径",
        "4. 三个可照着验算的例子", "5. 主结果：h=20 六种信号对照",
        "6. 五期 × 六种信号：30 格全矩阵", "7. 事件级统计与单日簇",
        "8. 置换检验", "9. 第二种读法：末日子样本内的 −N",
        "10. 42 个事件簇逐行清单", "11. 分年与极值", "12. 确认日审计",
        "13. 坑位、边界与结论", "附录 A：原始输出全文", "附录 B：文件与复算命令",
    ], 1)) + "</div>"
)

# ---- 1 ----
parts.append(
    "<h2 id='s1'>1. 问题与两种读法</h2>"
    "<p>此前所有事件级诊断都把信号放在<b>事件簇的第一天</b>。本次问的是："
    "如果把信号改放到<b>事件簇的最后一天</b>，IC 会怎样？</p>"
    "<p>「把最后一天算 IC」有两种可能的理解，本报告都做了，避免答非所问：</p>"
    + table(["读法", "信号定义", "评价样本", "本报告位置"], [
        ["<b>读法 A（主要）</b>", "二元 <code>s_t = 1[t 是某簇最后一天]</code>，其余日为 0",
         "全部报告日的日级面板（点二列 IC）", "第 5、6 节"],
        ["读法 A′（可执行）", "把「簇已结束」的确认放到 &gt;10 日历日后的第一个交易日 d，"
         "<code>s_d = 1</code>", "同样的日级面板", "第 5、6、12 节"],
        ["读法 B", "连续量 <code>−N</code> 与远期收益的相关，但<b>只在 42 个末日子样本内</b>算",
         "40–42 个末日", "第 9 节"],
    ])
    + "<div class='note'>读法 A 里不能把样本限制到只有末日：那时信号恒为 1，"
      "相关系数无定义。所以必须与「非末日」一起构成 0/1 对照，"
      "这就是点二列相关（point-biserial correlation），也就是本项目一直用的二元 IC。</div>"
)

# ---- 2 ----
parts.append(
    "<h2 id='s2'>2. 因果警告：末日不可交易</h2>"
    "<div class='bad'><b>簇最后一天在 t 日收盘时是不知道的。</b>"
    "簇的定义是「相邻触发日间隔 &gt;10 个<b>日历日</b>才算新事件」，"
    "因此只有等到末日之后再过 10 个日历日、仍没有新触发，才能回头确认"
    "「那天确实是最后一个触发日」。把 <code>cluster_last</code> 直接配 "
    "<code>t+1</code> 开盘入场的收益，是<b>用未来信息标注信号</b>，"
    "只能做描述性诊断，绝不能当可交易信号。</div>"
    "<div class='axis'>"
    "<div class='step'><b>t_end</b><br>最后一个 N≤1 日<br>此时<b>不知道</b>它是末日</div>"
    "<div class='arrow'>→</div>"
    "<div class='step hot'><b>等待 11–13 个日历日</b><br>4–9 个交易日<br>确认无新触发</div>"
    "<div class='arrow'>→</div>"
    "<div class='step'><b>d（确认日）收盘</b><br>此刻才<b>可知道</b>簇已结束</div>"
    "<div class='arrow'>→</div>"
    "<div class='step'><b>d+1 开盘</b><br>最早可执行入场<br>收益 r(d,h)</div>"
    "</div>"
    "<p>所以第 5、6 节里的 <code>cluster_last</code> 一律标注 <b>前视</b>；"
    "<code>cluster_last_confirmed</code> 才是因果口径，但它经济含义也变了："
    "它是在「低孔洞状态<b>已经结束之后</b>」入场，而不是在低孔洞状态中入场。"
    "两者都不能与兴业原文的规则等同。</p>"
)

# ---- 3 ----
d = J["data"]
parts.append(
    "<h2 id='s3'>3. 数据与口径</h2>"
    "<h3>符号表</h3>"
    + table(["符号", "含义"], [
        ["<code>N_t</code>", "t 日收盘后由过去 30 日行业收益相关网络算出的 H₂ 有限持久区间数"],
        ["<code>k=1</code>", "触发条件 <code>N_t ≤ 1</code>（兴业原文的阈值）"],
        ["<code>r(t,h)</code>", "<code>open[t+1+h] / open[t+1] − 1</code>，特征日历，t 日收盘得信号"],
        ["<code>IC</code>", "此处为点二列相关：<code>corr(s_t, r(t,h))</code>，<b>无量纲、不是百分比</b>"],
        ["<code>h</code>", "只用于评价的远期收益窗口，<b>不是持仓期、不是触发规则</b>"],
        ["「跨零」", "95% 自助区间包含 0，即不排除真实效应为 0"],
    ])
    + "<h3>样本漏斗</h3>"
    + table(["阶段", "天数 / 个数", "说明"], [
        ["特征文件截断到 2025-05-30", f"{d['rows_after_end_truncation']}",
         f"自 {d['first_feature_date']} 起"],
        ["报告期 2015-07-01 ～ 2025-05-30", f"{d['report_days']}", "原文报告期"],
        ["h=20 可用日", f"{d['usable_h20_days']}", "尾部 21 日无完整 20 日远期收益，剔除"],
        ["N≤1 信号日", f"{d['n_N_le_1_days']}", "其中 h=20 可用 389 日"],
        ["事件簇", f"{d['n_clusters']}", "间隔 &gt;10 日历日算新簇"],
    ])
    + "<div class='formula'>s_t ∈ {0,1}；IC = Σ(s−s̄)(r−r̄) / √[Σ(s−s̄)² · Σ(r−r̄)²]"
      "<br>95% 区间 = 把 (s_t, r_t) 成对绑定，随机抽 20 日连续块拼回原长度，"
      "重算 1000 次，取 2.5% / 97.5% 分位（种子 20261108）</div>"
    + "<p>为什么不用普通 t 检验：h 日收益窗口彼此重叠且 N 高度自相关，"
      "2370 个日级观测不是 2370 个独立样本；主报告已展示 naive t=3.23 是伪显著。"
      "本次 30 格自助退化次数为 <b>"
    + str(J["bootstrap_degenerate_total"]) + "</b>（稀疏二元信号在重采样里可能变成常数，"
      "一旦发生会显式记录而不是悄悄替换）。</p>"
)

# ---- 4 ----
ex_rows = []
for e in examples:
    ex_rows.append([
        e["date"], str(e["N"]), f"{e['d1']} / {e['o1']:.2f}",
        f"{e['d21']} / {e['o21']:.2f}",
        f"{e['o21']:.2f}/{e['o1']:.2f}−1 = <b>{e['r20']:+.8f}</b>",
        f"{e['json']:+.8f}", f"{e['confirm']}（+{e['lag']} 日）",
        f"{e['confirm_r20']:+.6f}" if e["confirm_r20"] is not None else "—",
    ])
parts.append(
    "<h2 id='s4'>4. 三个可照着验算的例子</h2>"
    "<p>下表价格直接从两个原始 CSV 读取并重新计算，最后一列与结果 JSON 逐位一致。"
    "前两列是 t+1 与 t+21 的<b>开盘价</b>（万得全A 指数点）。</p>"
    + table(["簇末日 t", "N_t", "t+1 日期 / 开盘", "t+21 日期 / 开盘",
             "复算 r(t,20)", "JSON 中的 last_fwd20", "确认日 d", "确认日 r(d,20)"], ex_rows)
    + "<p><small>例：2015-07-29 是第 1 个簇的末日，N=0；t+1 开盘 4936.19，"
      "t+21 开盘 3740.18，r = −24.2294%。确认日 2015-08-10 才过 12 个日历日，"
      "若按可执行口径入场，r(d,20) = −24.0403%，仍在股灾段。</small></p>"
)

# ---- 5 ----
h20 = [r for r in J["ic_matrix"] if r["horizon_days"] == 20]
label = {
    "daily_N_le_1": "全部 N≤1 日（日级）", "cluster_start": "簇首日（此前口径）",
    "cluster_last": "簇末日（前视）", "cluster_middle": "簇中间日",
    "cluster_last_confirmed": "末日确认日（因果）", "minus_N": "连续 −N（对照）",
}
ev = J["h20_event_level"]
evkey = {
    "daily_N_le_1": "daily_all_N_le_1", "cluster_start": "cluster_start",
    "cluster_last": "cluster_last", "cluster_middle": "cluster_middle",
    "cluster_last_confirmed": "cluster_last_confirmed", "minus_N": "unconditional",
}
rows5 = []
for r in h20:
    name = r["signal"]
    e = ev[evkey[name]] if name != "minus_N" else None
    rows5.append([
        "<b>" + label[name] + "</b>",
        "前视" if r["look_ahead"] else "因果" if name == "cluster_last_confirmed" else "—",
        str(r["signal_days"]) if r["signal_days"] is not None else "连续量",
        f"<b>{f(r['ic_point_biserial'])}</b>",
        ci(r["ci95_lo"], r["ci95_hi"]),
        yn(r["crosses_zero"]) if r["crosses_zero"] is not None else "—",
        f"{e['n']}" if e else "—", pct(e["mean"]) if e else "—",
        pct0(e["win_rate"]) if e else "—",
        ci(e["ci95_mean_iid_bootstrap"][0], e["ci95_mean_iid_bootstrap"][1]) if e else "—",
    ])
parts.append(
    "<h2 id='s5'>5. 主结果：h=20 六种信号对照</h2>"
    + table(["信号定义", "因果性", "信号日数", "点二列 IC", "95% 区块自助区间", "跨零",
             "事件级 n", "后 20 日均值", "胜率", "均值 95% 自助区间"], rows5)
    + "<div class='warn'><b>直接回答：</b>把信号从簇首日换到簇末日，"
      "h=20 的 IC 从 <b>+0.0131</b> 变成 <b>−0.0058</b>，区间 [−0.0551, +0.0422] 跨零；"
      "事件级后 20 日均值从 <b>+0.9198%</b> 变成 <b>−0.0275%</b>，"
      "胜率仍是 60.0%（少数 2015 年大额亏损把均值拖负）。"
      "换成因果的确认日口径，IC 是 <b>−0.0004</b>、均值 +0.2414%，"
      "与无条件 +0.2633% 几乎一样。<b>末日口径没有任何排除零的证据。</b></div>"
    + "<p>更值得注意的是<b>簇中间日</b>：319 天、IC <b>+0.0981</b>、"
      "后 20 日均值 <b>+1.8928%</b>、胜率 65.8%，比日级全样本 +1.6131% 还高。"
      "h=20 可用的 389 个信号日按位置拆开是 <b>40 个首日 + 319 个中间日 + 40 个末日 = 399</b>；"
      "多出来的 10 个是<b>单日簇的首日＝末日被计了两次</b>，去重后正好 389 天。"
      "也就是说日级那个看起来最好的 +0.0913 主要是<b>簇内连续触发日被重复计数</b>撑起来的，"
      "而不是首日或末日的择时能力。这与上轮「日级 → 事件级 IC 塌到 0.0131」是同一现象。</p>"
)

# ---- 6 ----
rows6 = []
for r in J["ic_matrix"]:
    cz = "—" if r["crosses_zero"] is None else ("是" if r["crosses_zero"] else "<b>否</b>")
    rows6.append([
        label[r["signal"]], str(r["horizon_days"]), str(r["n_observations"]),
        str(r["signal_days"]) if r["signal_days"] is not None else "—",
        f(r["ic_point_biserial"]), f(r["ic_spearman"]),
        ci(r["ci95_lo"], r["ci95_hi"]), cz,
        pct(r["mean_fwd_on"], 3) if r["mean_fwd_on"] is not None else "—",
        pct0(r["win_rate_on"]) if r["win_rate_on"] is not None else "—",
    ])
parts.append(
    "<h2 id='s6'>6. 五期 × 六种信号：30 格全矩阵</h2>"
    "<p>看结果前固定 6 种定义 × 5 个期限，全部披露、不按 IC 反选。"
    "<b>h=20 的 6 格全部跨零</b>；整个 30 格里有 "
    + str(J["interpretation"]["n_cells_excluding_zero"]) + " 格区间不跨零："
    + "、".join(J["interpretation"]["cells_excluding_zero"]) + "。</p>"
    + table(["信号", "h", "可用日", "信号日", "Pearson IC", "Spearman",
             "95% 区间", "跨零", "条件均值 r(h)", "信号日胜率"], rows6)
    + "<div class='warn'>那 3 格不能当发现：30 次检验在 5% 水平下纯随机也期望约 1.5 格"
      "假阳性；<code>cluster_start@h1</code> 效应只有 0.0257；"
      "两格 h=40 的重叠窗口是 40 日而自助块长只有 20 日，区间可能偏窄。"
      "主评价期 h=20 一格都没有排除零。</div>"
)

# ---- 7 ----
p = J["paired_first_vs_last"]
mp = p["multi_day_only"]
rows7 = []
for k, v in ev.items():
    rows7.append([k, str(v["n"]), pct(v["mean"]), pct(v["median"]),
                  pct0(v["win_rate"]), ci(v["ci95_mean_iid_bootstrap"][0],
                                          v["ci95_mean_iid_bootstrap"][1]),
                  pct(v["mean_excess_vs_unconditional"], 3)])
parts.append(
    "<h2 id='s7'>7. 事件级统计与单日簇</h2>"
    + table(["口径", "n", "后 20 日均值", "中位", "胜率", "均值 95% 区间",
             "相对无条件"], rows7)
    + "<h3>首日 vs 末日的配对比较</h3>"
    + table(["量", "全部 40 对", "仅多日簇 30 对"], [
        ["首日均值", pct(p["mean_start"], 4), pct(mp["mean_start"], 4)],
        ["末日均值", pct(p["mean_last"], 4), pct(mp["mean_last"], 4)],
        ["<b>差（末 − 首）</b>", "<b>" + pct(p["mean_diff_last_minus_start"], 4) + "</b>",
         "<b>" + pct(mp["mean_diff_last_minus_start"], 4) + "</b>"],
        ["中位差", pct(p["median_diff"], 4), pct(mp["median_diff"], 4)],
        ["95% 自助区间", ci(p["ci95_diff_iid_bootstrap"][0],
                            p["ci95_diff_iid_bootstrap"][1]),
         ci(mp["ci95_diff_iid_bootstrap"][0], mp["ci95_diff_iid_bootstrap"][1])],
        ["末日更好 / 更差", f"{p['n_last_better']} / {p['n_last_worse']}",
         f"{mp['n_last_better']} / {mp['n_last_worse']}"],
        ["差值恰为 0", str(p["n_exactly_equal"]), "0"],
    ])
    + "<div class='note'><b>为什么有 10 对差值恰为 0：</b>42 个簇里 <b>11 个是单日簇</b>"
      "（首日＝末日），其中 10 个有完整 20 日收益。"
      "这些配对的差必然为 0，会把「全部 40 对」的均值稀释掉。"
      "剔除后仅多日簇的差是 <b>−1.2630%</b>（9 好 / 21 差），"
      "但 95% 区间 [−4.0093%, +1.6540%] 仍跨零，不能说末日系统性地更差。"
      "首日与末日收益的 Pearson 相关 <b>0.5998</b>、Spearman 0.5276，"
      "说明同一事件内部的两个时点高度相关——这正是重复计数的来源。</div>"
)

# ---- 8 ----
perm = J["permutation_tests"]
rows8 = []
for k, v in perm.items():
    if not isinstance(v, dict):
        continue
    rows8.append([k, str(v["n_signal_days"]), pct(v["actual_mean"], 4),
                  f(v["simple_random"]["p_two_sided"], 4),
                  f(v["circular_shift"]["p_two_sided"], 4),
                  str(v["circular_shift"]["n_draws"]),
                  pct(v["circular_shift"]["null_mean"], 4)])
parts.append(
    "<h2 id='s8'>8. 置换检验</h2>"
    "<p>统计量 = 信号日的平均后 20 日收益。两个零分布：</p>"
    "<ol><li><b>简单随机</b>：从 2370 个可用日随机抽同样多的日子，5000 次；</li>"
    "<li><b>循环平移</b>：把整条可用收益序列随机滚动一个偏移，信号位置不动，2000 次。"
    "同时保留收益自相关和 42 个事件日的间隔结构，只打破信号/收益对齐"
    "（与自适应阈值研究的联合 max-IC 检验同一方法）。</li></ol>"
    + table(["信号组", "n", "实际均值", "简单随机 p（双侧）", "循环平移 p（双侧）",
             "循环平移次数", "循环零均值"], rows8)
    + "<div class='warn'>三个 p 值分别是 0.787 / 0.512 / 0.997（简单随机）与 "
      "0.773 / 0.500 / 0.999（循环平移）。<b>末日组与随机选日完全不可区分</b>，"
      "簇首日也一样；确认日组更接近零分布中心。置换检验不支持任何一组有事件级优势。</div>"
)

# ---- 9 ----
w = J["within_last_day_subsample_minus_N"]
rows9 = [[str(r["horizon_days"]), str(r["n_last_days"]), f(r["ic_pearson"]),
          f(r["ic_spearman"]),
          ci(r["ci95_ic_iid_bootstrap"][0], r["ci95_ic_iid_bootstrap"][1]),
          yn(r["crosses_zero"]) if r["crosses_zero"] is not None else "—"] for r in w]
parts.append(
    "<h2 id='s9'>9. 第二种读法：末日子样本内的 −N</h2>"
    "<p>若把问题理解成「只在这 42 个末日里，N 的大小能否排序后续收益」，"
    "则信号是连续量 <code>−N</code>，样本只有 40–42 天，区间用配对 iid 自助给出。</p>"
    + table(["h", "n", "Pearson IC(−N, r)", "Spearman", "95% iid 自助区间", "跨零"], rows9)
    + "<div class='warn'>h=1 的 IC 是 <b>−0.3002</b>、h=20 是 <b>−0.2308</b>，"
      "方向上与「孔洞越少越好」相反（−N 越大反而收益越低）。"
      "但五个区间的跨度都极大且<b>全部跨零</b>（h=1 为 [−0.5736, +0.0163]），"
      "40 个样本、5 个期限、无多重检验校正，且末日高度集中在 2015 股灾与 2018 熊市，"
      "属于典型的年份混淆。<b>不能据此声称存在反向关系。</b></div>"
)

# ---- 10 ----
rows10 = []
for r in J["clusters"]:
    rows10.append([
        str(r["event_no"]), r["start"], "<b>" + r["end"] + "</b>",
        str(r["cluster_days"]), "是" if r["is_single_day_cluster"] else "否",
        str(r["N_at_start"]), str(r["N_at_last"]),
        pct(r["start_fwd20"]), "<b>" + pct(r["last_fwd20"]) + "</b>",
        pct(r["pair_diff_last_minus_start"]),
        r["confirm_date"] or "—",
        pct(r["confirm_fwd20"]),
    ])
parts.append(
    "<h2 id='s10'>10. 42 个事件簇逐行清单</h2>"
    + table(["#", "首日", "末日", "簇长", "单日簇", "N(首)", "N(末)",
             "首日 r(20)", "末日 r(20)", "差(末−首)", "确认日", "确认日 r(20)"], rows10)
    + "<p><small>末日 r(20) 为空的 2 行是 2025 年尾部簇：没有完整 20 日远期收益，"
      "不当负例。确认日为空的 1 行是最后一个簇，其确认日落在数据截断之后；"
      "确认日 r(20) 为空共 2 行（另 1 行有确认日但同样缺完整 20 日收益），"
      "所以确认日组的事件级 n = 40。</small></p>"
)

# ---- 11 ----
rows11 = [[r["year"], str(r["n_clusters"]), str(r["n_with_fwd20"]),
           pct(r["mean_fwd20"]), pct0(r["win_rate"])]
          for r in J["by_year_of_cluster_end"]]
c = [r for r in J["clusters"] if r["last_fwd20"] is not None]
best = sorted(c, key=lambda x: x["last_fwd20"], reverse=True)[:5]
worst = sorted(c, key=lambda x: x["last_fwd20"])[:5]
ext = [["<b>最好</b>" if i == 0 else "", r["end"], str(r["cluster_days"]),
        str(r["N_at_last"]), pct(r["last_fwd20"])] for i, r in enumerate(best)]
ext += [["<b>最差</b>" if i == 0 else "", r["end"], str(r["cluster_days"]),
         str(r["N_at_last"]), pct(r["last_fwd20"])] for i, r in enumerate(worst)]
parts.append(
    "<h2 id='s11'>11. 分年与极值</h2>"
    + table(["末日所在年", "簇数", "有 r(20) 的簇", "末日均值 r(20)", "胜率"], rows11)
    + table(["组别", "末日", "簇长", "N(末)", "r(20)"], ext)
    + "<div class='note'>2015 年 4 个末日平均 <b>−13.02%</b>、2018 年 10 个 <b>−2.89%</b>，"
      "而 2017/2019/2022/2024 为正。全样本末日均值 ≈ 0 是<b>正负年份相互抵消</b>的结果，"
      "不是稳定的「无效应」。这也再次说明分年 IC 与事件级均值的剧烈摆动不能当稳健证据。</div>"
)

# ---- 12 ----
o = J["overlap_audit"]
parts.append(
    "<h2 id='s12'>12. 确认日审计</h2>"
    + table(["量", "值"], [[k, str(v)] for k, v in o.items() if k != "note"])
    + "<div class='warn'>42 个簇里 <b>41 个</b>有确认日，"
      "滞后 11–13 个<b>日历日</b>（4–9 个交易日）；"
      "有 <b>6 个确认日恰好又是下一个簇的首日</b>，"
      "所以「簇刚结束」与「新簇开始」这两个信号在 6 天里是同一个时点，"
      "两种口径的事件并非完全独立。最后一个簇没有确认日，已如实剔除。</div>"
)

# ---- 13 ----
parts.append(
    "<h2 id='s13'>13. 坑位、边界与结论</h2>"
    "<h3>九个坑位</h3><ol>"
    "<li><b>末日标签有前视</b>：<code>cluster_last</code> 只能做描述，不能回测。</li>"
    "<li><b>确认日改变了经济问题</b>：它在低孔洞状态结束后才入场，不是原文规则。</li>"
    "<li><b>单日簇</b>：11 个簇首日＝末日，配对差恒为 0，必须单列。</li>"
    "<li><b>重复计数</b>：40 首 + 319 中间 + 40 末 = 399，其中 10 个单日簇首末同日被重复计，"
    "去重后 389 日；日级 IC 主要来自 319 个中间日。</li>"
    "<li><b>稀疏二元</b>：点二列 IC 被 √(p(1−p)) 机械压小，IC 小不等于无提升，"
    "须同时看条件均值与胜率。</li>"
    "<li><b>多重比较</b>：30 格无校正，3 格「不跨零」不构成发现。</li>"
    "<li><b>自助块长</b>：20 日块对 h=40 窗口偏乐观；本次退化 0 次，已显式记录。</li>"
    "<li><b>年份混淆</b>：末日集中在 2015—2020，2015 股灾单簇可到 −28%。</li>"
    "<li><b>胜率 ≠ 均值</b>：末日组胜率 60% 但均值 −0.0275%，右尾/左尾不对称。</li>"
    "</ol>"
    "<h3>结论</h3>"
    "<div class='good'><b>按事件簇最后一天算，IC 不但没有变好，反而从首日的 +0.0131 "
    "变成 −0.0058（h=20），事件级均值从 +0.9198% 变成 −0.0275%；"
    "换成唯一可执行的确认日口径则几乎正好是零（IC −0.0004、均值 +0.2414% vs "
    "无条件 +0.2633%）。全部区间跨零，置换 p 在 0.5–1.0 之间。</b>"
    "更根本的发现是：日级 +0.0913 的高 IC 主要来自簇内 319 个中间日被重复计数，"
    "首日与末日都不具备独立排序能力。这进一步支持上轮的判断——"
    "低孔洞「状态」与后续收益的弱关联，不能转化成可交易的「事件时点」。</div>"
    "<div class='bad'><b>边界</b>：全部是样本内探索性诊断，"
    "不是有效性证据，也不构成「TDA 无效」或「兴业原文有误」的判决；"
    "N 的精确定义、Wind 逐日行业名单与万得四级行业分类仍未取得；"
    "2021 年后固定 N≤1 阈值几乎不触发，后期样本极少。"
    "确认性修正版策略绩效仍未计算。"
    "<b>Gate 1 暂停、2025 最终测试未读取、Gate 2 未启动</b>——"
    "按约定先讨论设计再动。</div>"
)

# ---- appendices ----
parts.append(
    "<h2 id='s14'>附录 A：原始输出全文</h2>"
    "<p>以下三个折叠块逐字嵌入原始文件，不删减、不改写。" 
    "图片亦以 base64 内嵌，整份报告无外链、无脚本。</p>"
    "<p><img src='data:image/png;base64," + FIG_B64 + "' alt='簇末日 IC 四面板图'></p>"
    "<details><summary>展开：xy_cluster_last_day_ic.json 全文</summary>"
    "<pre><code>" + esc(JSON_SRC) + "</code></pre></details>"
    "<details><summary>展开：xy_cluster_last_day_ic.csv 全文（42 行）</summary>"
    "<pre><code>" + esc(CSV_SRC) + "</code></pre></details>"
    "<details><summary>展开：cluster_last_day_ic.py 完整计算脚本</summary>"
    "<pre><code>" + esc("\n".join(f"{i:4d}  {line}"
                                for i, line in enumerate(SCRIPT_SRC.splitlines(), 1)))
    + "</code></pre></details>"
)
parts.append(
    "<h2 id='s15'>附录 B：文件与复算命令</h2>"
    + table(["类别", "路径", "说明"], [
        ["诊断脚本", "<code>src/xy_replication/cluster_last_day_ic.py</code>", "只读，可重跑"],
        ["结果", "<code>outputs/xy_cluster_last_day_ic.json</code>", "本报告全部数字来源"],
        ["逐簇清单", "<code>outputs/xy_cluster_last_day_ic.csv</code>", "42 行"],
        ["图", "<code>outputs/xy_cluster_last_day_ic.png</code>", "四面板，已内嵌"],
        ["报告脚本", "<code>src/xy_replication/build_cluster_last_day_report.py</code>",
         "只读既有输出生成本 HTML"],
        ["本报告", "<code>outputs/xy_cluster_last_day_report.html</code>", "单文件离线"],
        ["输入", "<code>outputs/xy_corrected_sw193_ifind_peak_features.csv</code>",
         "v1.2 修正版特征"],
        ["输入", "<code>outputs/xy_wind_all_a_daily.csv</code>", "881001.WI 日线"],
    ])
    + "<div class='formula'>"
      "# 重算诊断（会覆盖 3 个结果文件，本报告不执行）<br>"
      "tda_project/.venv/Scripts/python.exe "
      "tda_project/src/xy_replication/cluster_last_day_ic.py<br><br>"
      "# 只生成本报告（读取既有输出，不改任何结果文件）<br>"
      "tda_project/.venv/Scripts/python.exe "
      "tda_project/src/xy_replication/build_cluster_last_day_report.py</div>"
)
parts.append(
    "<div class='footer'>本报告为单文件离线 HTML：图片 base64 内嵌、样式内联、"
    "无外部链接、无 JavaScript。所有具体数字来自 "
    "<code>xy_cluster_last_day_ic.json</code>；第 4 节价格由两个原始 CSV 独立复算。"
    "统计方法说明（点二列相关、区块自助、置换检验、多重比较）属整理者补充的通用知识，"
    "不是兴业证券原文内容。</div></body></html>"
)

html_text = "\n".join(parts)
assert "data:image/png;base64," in html_text
assert "<img src=" in html_text
assert "http://" not in html_text and "https://" not in html_text
assert "<script" not in html_text
assert html_text.count("<table>") == html_text.count("</table>")
assert html_text.count("<details>") == html_text.count("</details>")
assert html_text.count("<div") == html_text.count("</div>")
HTML_OUT.write_text(html_text, encoding="utf-8")
print(json.dumps({
    "output": str(HTML_OUT),
    "bytes": HTML_OUT.stat().st_size,
    "tables": html_text.count("<table>"),
    "details": html_text.count("<details>"),
    "base64_img": html_text.count("data:image/png;base64,"),
    "h2": html_text.count("<h2 id="),
}, ensure_ascii=False, indent=2))
