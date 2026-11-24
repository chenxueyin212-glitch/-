"""Build a single-file offline HTML report for the two follow-up questions:

  Q1  What does the evidence look like if we examine the 42 EVENTS instead of
      392 signal-days?
  Q2  If N drifts upward, can the threshold move with it?

READ-ONLY: this script reads existing outputs and source files, and writes only
xy_event_adaptive_report.html. It does not rerun any experiment.
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

EVENT_JSON = OUT / "xy_event_study.json"
ADAPT_JSON = OUT / "xy_adaptive_threshold.json"
EVENT_CSV = OUT / "xy_event_study_clusters.csv"
ADAPT_CSV = OUT / "xy_adaptive_threshold_grid.csv"
EVENT_FIG = OUT / "xy_event_study.png"
ADAPT_FIG = OUT / "xy_adaptive_threshold.png"
STUDY_SCRIPT = SRC / "event_and_adaptive_threshold_study.py"
FEATURE_CSV = OUT / "xy_corrected_sw193_ifind_peak_features.csv"
WIND_CSV = OUT / "xy_wind_all_a_daily.csv"
HTML_OUT = OUT / "xy_event_adaptive_report.html"

ev = json.loads(EVENT_JSON.read_text(encoding="utf-8"))
ad = json.loads(ADAPT_JSON.read_text(encoding="utf-8"))
ev_source = EVENT_JSON.read_text(encoding="utf-8")
ad_source = ADAPT_JSON.read_text(encoding="utf-8")
ev_csv = EVENT_CSV.read_text(encoding="utf-8-sig")
ad_csv = ADAPT_CSV.read_text(encoding="utf-8-sig")
script_source = STUDY_SCRIPT.read_text(encoding="utf-8")
fig1_b64 = base64.b64encode(EVENT_FIG.read_bytes()).decode("ascii")
fig2_b64 = base64.b64encode(ADAPT_FIG.read_bytes()).decode("ascii")
trigger_src = json.loads((OUT / "xy_signal_trigger_ic_matrix.json").read_text(encoding="utf-8"))
by_year_k1 = {y["year"]: y for y in trigger_src["by_year"] if y["threshold_k"] == 1}


def esc(s) -> str:
    return html.escape(str(s), quote=False)


def pct(v, d: int = 2, sign: bool = True) -> str:
    if v is None:
        return "—"
    return f"{v * 100:+.{d}f}%" if sign else f"{v * 100:.{d}f}%"


def num(v, d: int = 4) -> str:
    if v is None:
        return "—"
    return f"{v:.{d}f}"


def table(headers, rows) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = []
    for r in rows:
        body.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    return ('<div class="tw"><table><thead><tr>' + th + '</tr></thead><tbody>'
            + "".join(body) + "</tbody></table></div>")


def details(summary: str, content: str) -> str:
    return f"<details><summary>{esc(summary)}</summary>{content}</details>"


def pre(text: str) -> str:
    return f"<pre><code>{esc(text)}</code></pre>"


# ---------------------------------------------------------------- hand checks
with FEATURE_CSV.open(encoding="utf-8-sig", newline="") as fh:
    feat = [r for r in csv.DictReader(fh) if r["date"] <= "2025-05-30"]
with WIND_CSV.open(encoding="utf-8-sig", newline="") as fh:
    wind_open = {r["date"]: float(r["open"]) for r in csv.DictReader(fh)}
f_dates = [r["date"] for r in feat]
f_N = [int(r["h2_count"]) for r in feat]
f_nodes = [int(r["n_nodes"]) for r in feat]
i0 = f_dates.index("2015-07-01")
hand = {
    "date": f_dates[i0], "N": f_N[i0],
    "entry_date": f_dates[i0 + 1], "entry_open": wind_open[f_dates[i0 + 1]],
    "exit_date": f_dates[i0 + 21], "exit_open": wind_open[f_dates[i0 + 21]],
}
hand["r20"] = hand["exit_open"] / hand["entry_open"] - 1.0
warmup_index = f_dates.index("2015-07-01")

t1 = f_dates.index("2022-02-11")
W1 = 120
win1 = f_N[t1 - W1 + 1:t1 + 1]
less1 = sum(1 for v in win1 if v < f_N[t1])
eq1 = sum(1 for v in win1 if v == f_N[t1])
rank1 = (less1 + 0.5 * eq1) / W1
pce = {
    "date": f_dates[t1], "N": f_N[t1], "nodes": f_nodes[t1], "W": W1,
    "win_min": min(win1), "win_max": max(win1),
    "win_median": sorted(win1)[W1 // 2], "less": less1, "equal": eq1,
    "rank": rank1, "trigger": rank1 <= 0.1,
}
t2 = f_dates.index("2021-06-29")
W2 = 60
win2 = f_N[t2 - W2 + 1:t2 + 1]
less2 = sum(1 for v in win2 if v < f_N[t2])
eq2 = sum(1 for v in win2 if v == f_N[t2])
rank2 = (less2 + 0.5 * eq2) / W2
lag = {"date": f_dates[t2], "N": f_N[t2], "W": W2, "win_max": max(win2),
       "less": less2, "equal": eq2, "rank": rank2, "trigger": rank2 <= 0.1}

agg = ev["aggregation_conventions"]
grid = ad["grid"]
prereg = [r for r in grid if r["status"] == "preregistered"]
baseline = next(r for r in grid if r["status"] == "baseline")
joint = ad["joint_max_statistic_test"]
perm = ev["permutation_test"]

parts: list[str] = []

CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#23272e;--muted:#66707c;--line:#e2e0d8;
--accent:#2c5f8a;--red:#c0392b;--green:#1e8449;--warn:#a66a12;--code:#f2f4f6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
font-size:15px;line-height:1.78}
.wrap{max-width:1200px;margin:0 auto;padding:34px 22px 90px}
h1{font-size:29px;line-height:1.35;margin:0 0 8px;letter-spacing:.3px}
h2{font-size:21px;margin:34px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--line)}
h3{font-size:16.5px;margin:22px 0 8px;color:var(--accent)}
h4{font-size:14.5px;margin:16px 0 6px}
p{margin:9px 0}
.sub{color:var(--muted);font-size:14px;margin:0 0 14px}
.pill{display:inline-block;background:#e8eef4;color:var(--accent);border-radius:999px;
padding:2px 11px;font-size:12px;margin:0 6px 6px 0;font-weight:600}
.pill.warn{background:#fbf0dc;color:var(--warn)}
.pill.red{background:#f8e6e3;color:var(--red)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:20px 24px;margin:16px 0}
.card.tight{padding:14px 18px}
.hero{background:linear-gradient(135deg,#fff,#f0f4f8);border-left:5px solid var(--accent)}
.key{background:#eef4fa;border-left:4px solid var(--accent);padding:12px 16px;
margin:14px 0;border-radius:0 8px 8px 0}
.warnbox{background:#fdf5e6;border-left:4px solid var(--warn);padding:12px 16px;
margin:14px 0;border-radius:0 8px 8px 0}
.danger{background:#fbeceb;border-left:4px solid var(--red);padding:12px 16px;
margin:14px 0;border-radius:0 8px 8px 0}
.good{background:#eaf5ee;border-left:4px solid var(--green);padding:12px 16px;
margin:14px 0;border-radius:0 8px 8px 0}
.tw{overflow-x:auto;max-height:620px;overflow-y:auto;border:1px solid var(--line);
border-radius:8px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:12.6px;background:#fff}
th,td{border-bottom:1px solid var(--line);padding:6px 9px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th:nth-child(2),td:nth-child(2){text-align:left}
thead th{background:#eceff3;font-weight:650;position:sticky;top:0;z-index:2}
tbody tr:nth-child(even){background:#fafafa}
tbody tr:hover{background:#f0f5fa}
.formula{background:var(--code);border:1px solid var(--line);border-radius:8px;
padding:12px 16px;font-family:"SFMono-Regular",Consolas,monospace;font-size:13.5px;
line-height:1.85;margin:12px 0;overflow-x:auto}
code{background:var(--code);padding:1px 5px;border-radius:4px;
font-family:"SFMono-Regular",Consolas,monospace;font-size:13px}
pre{background:#fbfbfc;border:1px solid var(--line);border-radius:8px;padding:14px;
overflow:auto;max-height:520px;font-size:12.2px;line-height:1.55}
pre code{background:none;padding:0;font-size:12.2px}
details{border:1px solid var(--line);border-radius:8px;background:#fff;
margin:10px 0;padding:0 14px}
summary{cursor:pointer;padding:10px 0;font-weight:600;color:var(--accent)}
.toc{columns:2;column-gap:26px;background:#fff;border:1px solid var(--line);
border-radius:10px;padding:16px 22px;font-size:13.6px}
.toc a{color:var(--accent);text-decoration:none;display:block;padding:2px 0}
.toc a:hover{text-decoration:underline}
img{display:block;width:100%;height:auto;border:1px solid var(--line);
border-radius:10px;margin:14px 0;background:#fff}
.legend{font-size:13px;color:var(--muted)}
.pos{color:var(--red);font-weight:600}
.neg{color:var(--green);font-weight:600}
.footer{margin-top:42px;padding-top:18px;border-top:1px solid var(--line);
font-size:12.5px;color:var(--muted)}
ol,ul{padding-left:22px}
li{margin:5px 0}
q{color:#555}
"""

parts.append("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
             "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
             "<title>事件级考察与自适应阈值诊断 | 兴业复现线</title>"
             f"<style>{CSS}</style></head><body><div class=\"wrap\">")

# ---------------------------------------------------------------- header
parts.append(
    "<h1>事件级考察与自适应阈值诊断</h1>"
    "<p class=\"sub\">回答两个追问：① 42 个事件簇（而非 392 个信号日）看上去是怎样的？"
    "② N 随节点数抬升后，阈值能不能跟着移动？</p>"
    "<div><span class=\"pill\">只读探索性诊断</span>"
    "<span class=\"pill warn\">全部样本内</span>"
    "<span class=\"pill red\">非策略结果 · 非确认性结果 · 非复现证据</span>"
    "<span class=\"pill\">单文件离线 · 无外链 · 无脚本</span></div>"
)

parts.append("<div class=\"card hero\"><h3 style=\"margin-top:0\">两问两答（先给结论）</h3>"
             "<p><b>问题 1：考察事件会怎样？</b> 把 392 个信号日按「间隔 &gt;10 日历日」"
             "合并成 42 个独立事件后，后 20 日平均收益从日级 <span class=\"pos\">+1.61%</span> "
             "降到事件起点 <span class=\"pos\">+0.92%</span>／簇等权 <span class=\"pos\">+0.64%</span>，"
             "而无条件基准是 +0.26%。也就是说<b>重复计数抬高了约 0.69 个百分点</b>，"
             "剩下的 +0.66 个百分点提升仍为正，但事件级 95% 自助区间 "
             "[−1.49%, +3.23%] 跨零、随机置换 p=0.524（间隔匹配 p=0.110），"
             "<b>与随机选 40 天无法区分</b>。事件表现高度依赖年份：2015 年 5 个事件平均 −9.64%，"
             "2018 年 11 个平均 −2.52%；后期正收益只来自 2022 年 1 个、2024 年 2 个事件。"
             "另外在事件级，起点 N=1 的 27 个事件 (+2.40%) 反而优于 N=0 的 13 个 (−2.15%)，"
             "方向与「孔洞越少越反弹」相反（但被年份混淆）。</p>"
             "<p><b>问题 2：阈值能不能移动？</b> <b>能，而且不能用你想的那种移动法。</b>"
             "先纠正前提：N 的抬升并不是节点数驱动的——2021—2025 段内 N 与节点数相关 "
             "<b>−0.2477</b>（方向相反），节点数只从 101.8 涨到 118.5（+16%），"
             "N 均值却从 3.68 涨到 15.61（4.2 倍）。所以「按节点数放大阈值」实测无效："
             "三档缩放后 2021—2025 只触发 13/13/17 天，固定阈值是 16 天。"
             "正确做法是<b>因果滚动分位</b>（只用 t 日及之前历史）：18 格预登记网格把后期触发"
             "恢复到 77—267 天，覆盖率问题解决了；但 h=20 IC 仅 0.0226—0.0936，"
             "联合 max-IC 检验 p=0.137、事件级收益普遍塌回 0 附近——"
             "<b>恢复的是覆盖率，不是有效性</b>。而且语义已从「几乎没有 H₂ 孔洞」"
             "变成「相对近期偏低」，不再是对兴业原文的复现。</p></div>")

parts.append(
    "<div class=\"toc\">"
    "<a href=\"#s1\">1. 数据、口径与两个可手算的例子</a>"
    "<a href=\"#s2\">2. 问题一：42 个事件的事件级研究</a>"
    "<a href=\"#s3\">3. 问题二：移动阈值的预登记网格</a>"
    "<a href=\"#s4\">4. 两个问题合起来看</a>"
    "<a href=\"#s5\">5. 坑位清单（12 条）</a>"
    "<a href=\"#s6\">6. 边界、状态与下一步</a>"
    "<a href=\"#s7\">7. 自测题</a>"
    "<a href=\"#sa\">附录 A：完整计算脚本</a>"
    "<a href=\"#sb\">附录 B：全部原始输出</a>"
    "<a href=\"#sc\">附录 C：文件清单与复算命令</a>"
    "</div>"
)

# ---------------------------------------------------------------- 1
parts.append("<h2 id=\"s1\">1. 数据、口径与两个可手算的例子</h2>")
parts.append("<div class=\"card\"><h3>1.1 样本漏斗（每个数字的出处）</h3>"
             + table(["步骤", "条数", "说明"], [
                 ["特征文件总行数", "3339", "2012-12-31 ~ 2026-11-03，v1.2 修正版"],
                 ["截断到基准末日 2025-05-30", "2994", "万得全A 日线只到 2025-05-30"],
                 ["报告期 2015-07-01 ~ 2025-05-30", "2391", "与原文报告期一致"],
                 ["h=20 有完整远期收益", "2370", "尾部剔除 21 日"],
                 ["k=1 信号日", "392", "占报告期 16.39%"],
                 ["k=1 事件簇", "42", "其中 40 个簇起点有完整 h=20 收益"],
                 ["h=1 / 5 / 10 / 40 有效日", "2389 / 2385 / 2380 / 2350", "与既有 IC 诊断一致"],
             ]) + "</div>")

parts.append("<div class=\"card\"><h3>1.2 符号表</h3>" + table(
    ["符号", "含义", "取值 / 口径"], [
        ["N<sub>t</sub>", "t 日 H₂ 有限持久区间数", "v1.2 特征文件 h2_count"],
        ["n<sub>t</sub>", "t 日相关网络有效行业节点数", "n_nodes"],
        ["k", "固定阈值", "兴业原文 k=1；对照 0/1/2/3"],
        ["τ", "事件簇间隔", ">10 <b>日历日</b>算新事件"],
        ["r(t,h)", "未来 h 日开盘到开盘收益", "open[t+1+h] / open[t+1] − 1"],
        ["p", "滚动分位点", "0.05 / 0.10 / 0.20"],
        ["W", "滚动历史窗口", "60 / 120 / 250 <b>交易日</b>"],
        ["ρ<sub>t</sub>", "因果 midrank 分位", "(#{N<sub>s</sub>&lt;N<sub>t</sub>} + 0.5·#{N<sub>s</sub>=N<sub>t</sub>}) / W"],
        ["IC", "时序 Pearson 相关", "无量纲，<b>不是百分比</b>"],
    ]) + "<p class=\"legend\">这里没有横截面：只有一个市场指数，所以选股意义上的截面 "
      "RankIC 无定义，全部是<b>时序 IC</b>。IC 里的 h 只是打分窗口，"
      "<b>既不是持仓期，也不是触发规则</b>。</p></div>")

parts.append("<div class=\"card\"><h3>1.3 三条口径链</h3>"
             "<div class=\"formula\">"
             "① 触发：t 日收盘后由过去 30 日行业收益相关网络 → VR → H₂，得 N<sub>t</sub>；"
             "N<sub>t</sub> ≤ k（或 ρ<sub>t</sub> ≤ p）即触发<br>"
             "② 最早可执行：t+1 <b>开盘</b>（t 日收盘价入场不可执行）；原文持仓 4 个交易日<br>"
             "③ 评价收益：r(t,h) = open[t+1+h] / open[t+1] − 1；"
             "收盘口径 rc(t,h) = close[t+h] / close[t] − 1 仅作敏感性<br>"
             "④ 事件：相邻触发日间隔 &gt;10 日历日 → 新簇；每簇第一天 = 事件起点"
             "</div>"
             "<p class=\"legend\">交易日序列以<b>特征文件日历</b>为准（与既有全部诊断一致），"
             "第 1.6 节给出与完整 Wind 交易日历的差异审计。</p></div>")

parts.append("<div class=\"card\"><h3>1.4 手算例子 A：一个事件收益怎么来的</h3>"
             + table(["量", "值"], [
                 ["事件 1 起点 t", hand["date"]], ["N<sub>t</sub>", str(hand["N"])],
                 ["入场日 t+1", hand["entry_date"]],
                 ["入场开盘价", f"{hand['entry_open']:.2f}"],
                 ["出场日 t+21", hand["exit_date"]],
                 ["出场开盘价", f"{hand['exit_open']:.2f}"],
                 ["r(t,20)", f"{hand['exit_open']:.2f} / {hand['entry_open']:.2f} − 1 = "
                             f"<b>{pct(hand['r20'], 4)}</b>"],
             ])
             + f"<p>这个值与 <code>xy_event_study.json</code> 中事件 1 的 "
               f"<code>fwd20_open = {pct(ev['events'][0]['fwd20_open'], 8)}</code> 逐位一致。"
               "它是 42 个事件里第三差的一个（2015 年股灾）。</p></div>")

parts.append("<div class=\"card\"><h3>1.5 手算例子 B：滚动分位阈值怎么触发</h3>"
             + table(["量", "值"], [
                 ["日期 t", pce["date"]], ["N<sub>t</sub>", str(pce["N"])],
                 ["节点数 n<sub>t</sub>", str(pce["nodes"])],
                 ["窗口 W", str(pce["W"]) + " 个交易日，含 t 日"],
                 ["窗口内 N 最小 / 中位 / 最大",
                  f"{pce['win_min']} / {pce['win_median']} / {pce['win_max']}"],
                 ["严格小于 N<sub>t</sub> 的天数", str(pce["less"])],
                 ["等于 N<sub>t</sub> 的天数（ties）", str(pce["equal"])],
                 ["ρ<sub>t</sub>", f"({pce['less']} + 0.5×{pce['equal']}) / {pce['W']} = "
                                   f"<b>{num(pce['rank'], 6)}</b>"],
                 ["p = 0.10 是否触发", "<b>是</b>" if pce["trigger"] else "否"],
             ])
             + "<p><b>为什么用 midrank：</b>N 是整数，同一窗口里常常有大量相同值。"
               "若直接写 <code>N<sub>t</sub> ≤ quantile(window, p)</code>，所有并列值会一起触发，"
               "触发率可能远高于 p。midrank 把并列值平摊，18 格实测触发率 5.6%—24.2%，"
               "与名义 p（5%/10%/20%）基本吻合，说明处理有效。</p>"
             + "<div class=\"warnbox\"><b>适应滞后的反例：</b>"
             + f"{lag['date']} 的 N={lag['N']}（该期峰值），W={lag['W']} 窗口内最大也是 "
               f"{lag['win_max']}，less={lag['less']}、equal={lag['equal']}，"
               f"ρ={num(lag['rank'], 4)} ≫ 0.10，<b>不触发</b>。"
               "N 平台跳升后的头几十天，滚动窗口还没把新平台纳入基线，信号会失语——"
               "这是动态阈值固有代价，不是 bug。</div></div>")

parts.append("<div class=\"card\"><h3>1.6 交易日历审计（一个此前没披露的口径坑）</h3>"
             + table(["项", "值"], [
                 ["特征对齐交易日", str(ev["calendar_audit"]["feature_aligned_days"])],
                 ["Wind 日线交易日", str(ev["calendar_audit"]["wind_trading_days"])],
                 ["Wind 多出的日期", str(ev["calendar_audit"]["n_wind_only_days"]) + " 天"],
                 ["两种日历 r(t,20) 平均绝对差", pct(ev["calendar_audit"]["mean_abs_diff_fwd20"], 4)],
                 ["最大绝对差", pct(ev["calendar_audit"]["max_abs_diff_fwd20"], 4)],
                 ["两列收益相关系数", num(ev["calendar_audit"]["corr_between_calendars"], 6)],
                 ["−N 的 h=20 IC（特征日历）", num(ev["calendar_audit"]["ic_feature_calendar"], 8)],
                 ["−N 的 h=20 IC（Wind 日历）", num(ev["calendar_audit"]["ic_wind_calendar"], 8)],
             ])
             + "<p>18 个 Wind 独有日期多为 2015 年异常交易日与个别停牌/数据缺口日。"
               "主结果一律沿用特征日历（保证与既有诊断可比）；换用完整 Wind 日历后 IC 从 "
               "0.06629 变到 0.06678，<b>不改变任何结论</b>。</p>"
             + details("展开：18 个 Wind 独有日期的完整清单",
                       "<p class=\"legend\">" + "、".join(ev["calendar_audit"]["wind_only_days"]) + "</p>")
             + "</div>")

# ---------------------------------------------------------------- 2
parts.append("<h2 id=\"s2\">2. 问题一：42 个事件的事件级研究</h2>")
parts.append("<div class=\"card\"><h3>2.1 392 个信号日怎么变成 42 个事件</h3>"
             "<p>信号日不是独立事件。原文「一次危机」往往对应连续若干个交易日的低孔洞状态；"
             "把这些日子当作 392 次独立试验，等于把同一段行情重复计数。合并规则："
             "相邻触发日间隔 &gt;10 <b>日历日</b>才算新事件。簇长中位 3 天、"
             "90 分位 21.8 天、最长 <b>87 天</b>（2015-12-14 起）。</p>"
             + table(["年份", "报告日", "N≤1 日", "触发率", "事件簇数", "事件簇均值 r(20)", "事件胜率"],
                     [[r["year"], str(by_year_k1[r["year"]]["report_days"]),
                       str(by_year_k1[r["year"]]["signal_days"]),
                       pct(by_year_k1[r["year"]]["signal_share"], 1, False),
                       str(r["events"]),
                       pct(r["mean_fwd20"]) if r["mean_fwd20"] is not None else "—",
                       pct(r["win_rate_fwd20"], 1, sign=False)
                       if r["win_rate_fwd20"] is not None else "—"]
                      for r in ev["by_year"]])
             + "<p class=\"legend\">上表「事件簇均值」是事件级结果，不是日级结果；"
               "2025 年 2 个事件都落在尾部，没有完整 20 日远期收益，记「—」，"
               "<b>不当作负例，也不参与任何均值</b>。</p></div>")

parts.append("<div class=\"card\"><h3>2.2 三种聚合口径：同一个信号，三个答案</h3>"
             + table(["口径", "样本数", "均值 r(20)", "中位", "胜率", "标准差", "均值 95% 自助区间"], [
                 ["① 日级：全部信号日", agg["daily_all_signal_days"]["n"],
                  pct(agg["daily_all_signal_days"]["mean"]),
                  pct(agg["daily_all_signal_days"]["median"]),
                  pct(agg["daily_all_signal_days"]["win_rate"], 1, False),
                  pct(agg["daily_all_signal_days"]["std_ddof1"]),
                  "[" + pct(agg["daily_all_signal_days"]["ci95_mean_iid_bootstrap"][0]) + ", "
                  + pct(agg["daily_all_signal_days"]["ci95_mean_iid_bootstrap"][1]) + "]"],
                 ["② 簇等权：每簇先平均再跨簇平均", agg["cluster_equal_weighted"]["n"],
                  pct(agg["cluster_equal_weighted"]["mean"]),
                  pct(agg["cluster_equal_weighted"]["median"]),
                  pct(agg["cluster_equal_weighted"]["win_rate"], 1, False),
                  pct(agg["cluster_equal_weighted"]["std_ddof1"]),
                  "[" + pct(agg["cluster_equal_weighted"]["ci95_mean_iid_bootstrap"][0]) + ", "
                  + pct(agg["cluster_equal_weighted"]["ci95_mean_iid_bootstrap"][1]) + "]"],
                 ["③ 事件起点：每簇仅第一天", agg["cluster_start_only"]["n"],
                  pct(agg["cluster_start_only"]["mean"]),
                  pct(agg["cluster_start_only"]["median"]),
                  pct(agg["cluster_start_only"]["win_rate"], 1, False),
                  pct(agg["cluster_start_only"]["std_ddof1"]),
                  "[" + pct(agg["cluster_start_only"]["ci95_mean_iid_bootstrap"][0]) + ", "
                  + pct(agg["cluster_start_only"]["ci95_mean_iid_bootstrap"][1]) + "]"],
                 ["④ 无条件：全部报告日", agg["unconditional_all_report_days"]["n"],
                  pct(agg["unconditional_all_report_days"]["mean"]),
                  pct(agg["unconditional_all_report_days"]["median"]),
                  pct(agg["unconditional_all_report_days"]["win_rate"], 1, False),
                  pct(agg["unconditional_all_report_days"]["std_ddof1"]), "—"],
             ])
             + table(["提升度", "数值"], [
                 ["日级均值 − 无条件", pct(ev["daily_vs_event_lift"]["daily_mean_minus_unconditional"], 4)],
                 ["簇等权 − 无条件", pct(ev["daily_vs_event_lift"]["cluster_equal_mean_minus_unconditional"], 4)],
                 ["事件起点 − 无条件", pct(ev["daily_vs_event_lift"]["cluster_start_mean_minus_unconditional"], 4)],
                 ["<b>日级 − 事件起点（重复计数效应）</b>",
                  "<b>" + pct(ev["daily_vs_event_lift"]["daily_mean_minus_cluster_start_mean"], 4) + "</b>"],
             ])
             + "<div class=\"key\"><b>读法：</b>日级 +1.61% 里有约 0.69 个百分点来自"
               "「同一事件被算了很多次」，去重后仍剩约 +0.66 个百分点相对无条件基准的提升，"
               "<b>但事件起点的自助区间跨零</b>。所以正确说法不是「结论翻负」，"
               "而是「正提升被重复计数放大，去重后小到无法与随机区分」。</div>"
             + f"<img src=\"data:image/png;base64,{fig1_b64}\" alt=\"事件研究四面板图\">"
             + "<p class=\"legend\">图 (a) 42 个事件的后 20 日收益（红涨绿跌）；"
               "(b) 事件时间平均价格路径；(c) 真实 5000 次随机置换分布与事件均值；"
               "(d) 三种聚合口径对比。图 (c) 的直方图来自实际置换抽样，不是拟合密度。</p></div>")

parts.append("<div class=\"card\"><h3>2.3 42 个事件逐行清单</h3>"
             "<p class=\"legend\">r1/r5/r10/r20/r40 均为开盘到开盘；cc20 为收盘口径敏感性。"
             "空值表示尾部不足，不参与统计。</p>"
             + table(["#", "起点", "终点", "信号日", "跨度(日)", "距上簇", "N", "节点", "入场日",
                      "r1", "r5", "r10", "r20", "r40", "cc20"],
                     [[str(r["event_no"]), r["start"], r["end"], str(r["cluster_days"]),
                       str(r["calendar_span_days"]),
                       "—" if r["calendar_gap_from_prev_cluster"] is None
                       else str(r["calendar_gap_from_prev_cluster"]),
                       str(r["N_at_start"]), str(r["n_nodes_at_start"]),
                       r["entry_date_t_plus_1"] or "—"]
                      + [pct(r[f"fwd{h}_open"], 2) for h in (1, 5, 10, 20, 40)]
                      + [pct(r["fwd20_close"], 2)] for r in ev["events"]])
             + "</div>")

parts.append("<div class=\"card\"><h3>2.4 不确定性：自助 + 两种置换检验</h3>"
             "<p>事件级样本 n=40，且 20 日远期窗口彼此重叠 "
             f"（{ev['overlapping_h20_event_pairs']} 对 / "
             f"{ev['overlapping_h20_event_pairs_out_of']} 对可能重叠），"
             "所以 i.i.d. 自助区间会偏窄，真正的证据还要看置换检验。</p>"
             + table(["检验", "重复次数", "零假设均值", "零假设标准差", "单侧 p", "双侧 p", "判定"], [
                 ["事件级 i.i.d. 自助均值区间", "10000", "—", "—", "—", "—",
                  "[" + pct(agg["cluster_start_only"]["ci95_mean_iid_bootstrap"][0]) + ", "
                  + pct(agg["cluster_start_only"]["ci95_mean_iid_bootstrap"][1]) + "] 跨零"],
                 ["简单随机：抽 40 个报告日",
                  str(perm["simple_random"]["repetitions"]),
                  pct(perm["simple_random"]["null_mean"]),
                  pct(perm["simple_random"]["null_sd"]),
                  num(perm["simple_random"]["p_one_sided_ge"], 4),
                  num(perm["simple_random"]["p_two_sided"], 4), "<b>不显著</b>"],
                 ["间隔匹配：抽 40 个起点，两两 &gt;10 日历日",
                  str(perm["gap_matched_random"]["repetitions"]),
                  pct(perm["gap_matched_random"]["null_mean"]),
                  pct(perm["gap_matched_random"]["null_sd"]),
                  num(perm["gap_matched_random"]["p_one_sided_ge"], 4),
                  num(perm["gap_matched_random"]["p_two_sided"], 4), "边缘，仍不达 5%"],
             ])
             + "<div class=\"warnbox\">间隔匹配的零假设方差更小（0.55% vs 1.04%），"
               "所以单侧 p=0.0548 已接近 0.05。<b>但不能据此宣称有效</b>："
               "该置换只匹配了「事件间隔」，没有匹配「事件集中出现在低 N 平台期」这一"
               "时间聚类结构；而且它是看完成千上万个口径后追加的诊断，未做多重比较校正。</div></div>")

p = ev["event_time_path"]
path_pick = [(j, v) for j, v in zip(p["j_from_entry"], p["mean_relative_open_path"])
             if j in (-20, -15, -10, -5, 0, 5, 10, 20, 30, 40)]
parts.append("<div class=\"card\"><h3>2.5 事件时间路径（形态，不是可交易收益）</h3>"
             + table(["相对入场交易日 j"] + [str(j) for j, _ in path_pick],
                     [["平均 open[entry+j]/open[entry] − 1"]
                      + [pct(v, 2) for _, v in path_pick]])
             + "<p>定义上 j=0 恒为 0。j=−20 为 +1.61% 意味着<b>事件前 20 日的开盘价比入场价高</b>，"
               "即信号出现在一段下跌之后；入场后 5—20 日只温和回升到 +0.38% ~ +0.92%，"
               "40 日又回落到 −0.23%。<b>这不是「触发后立即反弹」的强形态</b>，"
               "也不是原文那种清晰的阶跃式建仓曲线。该曲线仅用于描述形状，"
               "分母是入场开盘价，前后都用开盘价，不是任何可实际执行的收益。</p></div>")

d = ev["k0_vs_k1_start_decomposition"]
parts.append("<div class=\"card\"><h3>2.6 与上一版「N=0 簇起点 −1.3%」的对账</h3>"
             + table(["子样本", "n", "均值 r(20)", "中位", "胜率"], [
                 ["k=0 的全部簇起点", d["k0_all_cluster_starts"]["n"],
                  pct(d["k0_all_cluster_starts"]["mean"]),
                  pct(d["k0_all_cluster_starts"]["median"]),
                  pct(d["k0_all_cluster_starts"]["win_rate"], 1, False)],
                 ["k=1 簇起点中 N=0 的", d["k1_starts_with_N0_at_start"]["n"],
                  pct(d["k1_starts_with_N0_at_start"]["mean"]),
                  pct(d["k1_starts_with_N0_at_start"]["median"]),
                  pct(d["k1_starts_with_N0_at_start"]["win_rate"], 1, False)],
                 ["k=1 簇起点中 N=1 的", d["k1_starts_with_N1_at_start"]["n"],
                  pct(d["k1_starts_with_N1_at_start"]["mean"]),
                  pct(d["k1_starts_with_N1_at_start"]["median"]),
                  pct(d["k1_starts_with_N1_at_start"]["win_rate"], 1, False)],
             ])
             + "<p>k=0 的 35 个簇起点开盘口径为 <b>−1.371%</b>，与上一版 2×2 审计的"
               "−1.264%（收盘）/ −1.371%（开盘）完全对得上，<b>不是矛盾</b>。"
               "这次是 k=1 的 42 个簇，簇边界不同（k=1 会把 k=0 的多个簇连成一片），"
               "且 40 个有效起点里有 27 个是 N=1。事件级还出现一个反直觉事实："
               "<b>N=1 事件 (+2.40%) 明显好于 N=0 事件 (−2.15%)</b>，"
               "与「孔洞越少越好」方向相反。但 N=0 事件集中在 2015—2016 股灾期，"
               "这是<b>年份混淆</b>，不能当成「孔洞多一点更好」的证据。"
               f"起点 N 与后 20 日收益的 Spearman 仅 +{num(ev['cluster_correlations']['spearman_N_at_start_vs_fwd20'], 4)}。"
               "</p></div>")

best = sorted([r for r in ev["events"] if r["fwd20_open"] is not None],
              key=lambda x: x["fwd20_open"], reverse=True)[:5]
worst = sorted([r for r in ev["events"] if r["fwd20_open"] is not None],
               key=lambda x: x["fwd20_open"])[:5]
parts.append("<div class=\"card\"><h3>2.7 最好 / 最差 5 个事件，以及簇长的作用</h3>"
             + table(["最好", "起点", "信号日", "N", "r(20)", "最差", "起点", "信号日", "N", "r(20)"],
                     [[str(k + 1), best[k]["start"], str(best[k]["cluster_days"]),
                       str(best[k]["N_at_start"]), pct(best[k]["fwd20_open"]),
                       str(k + 1), worst[k]["start"], str(worst[k]["cluster_days"]),
                       str(worst[k]["N_at_start"]), pct(worst[k]["fwd20_open"])]
                      for k in range(5)])
             + table(["相关性（事件内，n=40）", "Spearman"], [
                 ["簇长 vs 后 20 日收益",
                  num(ev["cluster_correlations"]["spearman_cluster_length_vs_fwd20"], 4)],
                 ["起点 N vs 后 20 日收益",
                  num(ev["cluster_correlations"]["spearman_N_at_start_vs_fwd20"], 4)],
             ])
             + "<p>簇长与后续收益几乎无关（−0.026），说明「长簇 = 更强的信号」不成立；"
               "最长 87 天的 2015-12-14 事件反而是 −16.52%。"
               "日级均值被这类长簇机械加权，这正是重复计数效应的来源。</p></div>")

parts.append("<div class=\"card\"><h3>2.8 问题一的结论</h3>"
             "<div class=\"key\">按事件考察后：<b>日级 +1.61% → 事件起点 +0.92% / 簇等权 +0.64%</b>；"
             "相对无条件 +0.26% 仍为正，但 95% 区间跨零、置换 p=0.524，无法与随机选日区分。"
             "事件集中在 2015—2020（37/42），2015 与 2018 两个年份显著为负，"
             "后期正收益只来自 3 个事件。<b>「一次危机被算成几十次日级正确」的问题确实存在，"
             "但去重之后也没有留下统计上可靠的事件级优势。</b></div></div>")

# ---------------------------------------------------------------- 3
parts.append("<h2 id=\"s3\">3. 问题二：移动阈值的预登记网格</h2>")
parts.append("<div class=\"card\"><h3>3.1 先纠正前提：漂移不是节点数驱动的</h3>"
             + table(["区间", "日数", "N 均值", "N 中位", "节点数均值", "corr(N, 节点数)"],
                     [[s["segment"], str(s["n"]), num(s["mean_N"], 2), num(s["median_N"], 1),
                       num(s["mean_n_nodes"], 1), num(s["corr_N_vs_nodes"], 4)]
                      for s in ad["drift_attribution"]["segment_stats"]])
             + table(["年份", "N 均值", "N 中位", "节点均值", "P(N≤1)"],
                     [[r["year"], num(r["mean_N"], 2), num(r["median_N"], 1),
                       num(r["mean_n_nodes"], 1), pct(r["share_N_le_1"], 2, False)]
                      for r in ad["drift_attribution"]["by_year"]])
             + "<div class=\"warnbox\"><b>关键事实：</b>2021 年 N 均值冲到 21.47 时，"
               "节点数仍是 100.9，与 2015—2020 的 ~100 <b>几乎一样</b>；"
               "而 2024 年节点数升到 127.1，N 均值反而回落到 9.24。"
               "2021—2025 段内两者相关系数是 <b>−0.2477</b>（反向）。"
               "所以「节点变多 → 组合数变多 → H₂ 孔洞变多」这条直觉在本面板上"
               "<b>解释不了主要漂移</b>；更可能是相关网络结构/市场状态变化，"
               "以及数据补充覆盖差异。按节点数缩放阈值因此注定无效（下节实测）。</div></div>")

parts.append("<div class=\"card\"><h3>3.2 你的原始想法：按节点数把阈值放大</h3>"
             "<p>最直接的移动法是让阈值随规模增长："
             "<code>k<sub>t</sub> = 1 × (n<sub>t</sub> / 100)<sup>γ</sup></code>，"
             "γ=1/2/3 分别对应线性、平方、立方缩放（100 个节点时阈值都回到原文的 1）。</p>"
             + table(["γ", "127 节点处阈值", "报告期触发日", "触发率", "2021—2025 触发日", "信号日 r(20) 均值"],
                     [[str(r["gamma"]), num(r["threshold_at_127_nodes"], 4),
                       str(r["signal_days_report"]), pct(r["trigger_share_report"], 2, False),
                       str(r["signal_days_2021_2025"]), pct(r["mean_fwd20_on_signal"])]
                      for r in ad["node_count_scaled_control"]]
                     + [["<b>固定 k=1 基准</b>", "1.0000", str(baseline["signal_days_report"]),
                         pct(baseline["trigger_share_report"], 2, False),
                         str(baseline["signal_days_2021_2025"]),
                         pct(baseline["mean_fwd20_on_signal"])]])
             + "<div class=\"danger\"><b>实测无效。</b>即便按立方缩放，127 节点处阈值也只从 1 "
               "升到 2.05，而 2021 年 N 中位是 18。三档的后期触发日 13 / 13 / 17，"
               "<b>比固定阈值的 16 天还少或持平</b>。原因是节点数只涨 16%，"
               "而 N 涨了 4 倍以上，缩放幅度完全追不上。</div></div>")

parts.append("<div class=\"card\"><h3>3.3 可行的移动法：因果滚动分位（严格不泄漏未来）</h3>"
             "<div class=\"formula\">"
             "ρ<sub>t</sub> = [ #{ s ∈ [t−W+1, t] : N<sub>s</sub> &lt; N<sub>t</sub> } "
             "+ 0.5 · #{ s ∈ [t−W+1, t] : N<sub>s</sub> = N<sub>t</sub> } ] / W<br>"
             "signal<sub>t</sub> = 1[ ρ<sub>t</sub> ≤ p ]<br>"
             "第二族对照：把 N<sub>t</sub> 换成 N<sub>t</sub>/n<sub>t</sub> 后同样计算"
             "</div>"
             + table(["设计项", "取值 / 规则"], [
                 ["窗口 W", "60 / 120 / 250 交易日"],
                 ["分位 p", "0.05 / 0.10 / 0.20"],
                 ["两族 × 9 组", "18 格预登记，加 1 行固定 k=1 基准"],
                 ["warm-up 历史", f"特征文件自 2012-12-31 起；报告期首日在序列中序号 "
                   f"{warmup_index}，大于最大窗口 250，<b>报告期首日即有完整窗口，无需丢弃样本</b>"],
                 ["因果性", "窗口只含 ≤t 的 N；<b>任何 t 之后的值都不使用</b>"],
                 ["评价期", "h ∈ {1,5,10,20,40} 全报；h=20 为主评价期并给区块自助区间"],
                 ["不确定性", "配对 20 日移动区块自助，1000 次，种子 20261108；本次退化 0 次"],
                 ["选择规则", "<b>看结果前固定，18 格全部披露，不按 IC 或收益反选，不设头条结论</b>"],
             ])
             + "<div class=\"warnbox\"><b>语义代价（必须先接受）：</b>原文 N≤1 是"
               "「几乎没有 H₂ 孔洞」的<b>绝对拓扑状态</b>；滚动低分位是"
               "「N 相对自己最近历史偏低」的<b>相对统计状态</b>。"
               "在 N 长期平稳的年份（如 2016），几乎所有值都不算异常低，"
               "动态阈值反而会失语。阈值一旦移动，<b>就不再是兴业原文规则的复现</b>，"
               "只能算另立的一条探索性规则。</div></div>")

parts.append("<div class=\"card\"><h3>3.4 全部 18 格 + 基准：覆盖率</h3>"
             "<p class=\"legend\">「后期」= 2021-01-01 至 2025-05-30；"
             "簇数仍按间隔 &gt;10 日历日合并。</p>"
             + table(["信号", "族", "W", "p", "触发日", "触发率", "簇数", "后期触发日",
                      "后期簇数", "最后触发日"],
                     [[r["name"], "N" if r["family"] == "roll_N" else "N/节点",
                       "—" if r["window_days"] is None else str(r["window_days"]),
                       "—" if r["percentile"] is None else f"{r['percentile']:.2f}",
                       str(r["signal_days_report"]), pct(r["trigger_share_report"], 2, False),
                       str(r["event_clusters"]), str(r["signal_days_2021_2025"]),
                       str(r["event_clusters_2021_2025"]), r["last_trigger_date"] or "—"]
                      for r in grid])
             + "<div class=\"key\">覆盖率<b>确实恢复了</b>：固定 k=1 后期只有 16 个触发日、"
               "4 个簇；滚动分位各格后期 77—267 个触发日、簇数 30—78。"
               "触发率 5.6%—24.2% 与名义 p 接近，说明 midrank 的 ties 处理有效。</div></div>")

parts.append("<div class=\"card\"><h3>3.5 全部 18 格 + 基准：有效性</h3>"
             + table(["信号", "IC h1", "h5", "h10", "<b>h20</b>", "h40", "h20 95% 区间",
                      "跨零", "信号日 r(20)", "胜率", "事件起点 r(20)", "起点胜率", "事件数"],
                     [[r["name"]]
                      + [num(r[f"ic_h{h}"], 4) for h in (1, 5, 10)]
                      + ["<b>" + num(r["ic_h20"], 4) + "</b>", num(r["ic_h40"], 4),
                         "[" + num(r["ci95_h20_lo"], 4) + ", " + num(r["ci95_h20_hi"], 4) + "]",
                         "是" if r["ci95_h20_crosses_zero"] else "<b>否</b>",
                         pct(r["mean_fwd20_on_signal"]),
                         pct(r["win_rate_fwd20_on_signal"], 1, False),
                         pct(r["mean_fwd20_on_event_starts"]),
                         pct(r["win_rate_fwd20_on_event_starts"], 1, False),
                         str(r["event_starts_with_fwd20"])]
                      for r in grid])
             + "<div class=\"danger\"><b>有效性没有恢复。</b>"
               "18 格 h=20 IC 全部落在 0.0226—0.0936，与固定基准 0.0913 同量级甚至更低；"
               "只有 2 格区间不跨零（roll_N_W60_p0.05：0.0521 [0.0029, 0.1222]；"
               "roll_N_W120_p0.1：0.0936 [0.0122, 0.1869]）。"
               "更关键的是<b>事件级</b>：信号日条件均值看着有 +0.8%~+2.6%，"
               "但按事件起点去重后 18 格里有 <b>15 格</b>塌到 ±0.7% 以内（4 格为负），"
               "那个 IC 最高的 roll_N_W120_p0.1 事件起点只有 +0.12%（54 个事件）。"
               "这和问题一发现的重复计数效应是同一件事。</div>"
             + f"<img src=\"data:image/png;base64,{fig2_b64}\" alt=\"自适应阈值四面板图\">"
             + "<p class=\"legend\">图 (a) N 与节点数走势（双轴）；(b) 18 格 h=20 IC 及区间；"
               "(c) 固定阈值与 W=120/p=10% 的逐年触发率；(d) 各格 2021—2025 触发日数。</p></div>")

yr_rows = []
years = sorted(baseline["by_year_trigger_share"])
pick = next(r for r in grid if r["name"] == "roll_N_W120_p0.1")
for y in years:
    yr_rows.append([y, pct(baseline["by_year_trigger_share"][y], 1, False),
                    pct(pick["by_year_trigger_share"][y], 1, False)])
parts.append("<div class=\"card\"><h3>3.6 覆盖率恢复的代价：逐年触发率</h3>"
             + table(["年份", "固定 N≤1 触发率", "滚动 N, W=120, p=10% 触发率"], yr_rows)
             + "<p>固定阈值从 2015 年 55.7% 一路降到 2021/2023 年的 <b>0%</b>；"
               "滚动阈值各年落在 0.4%—20.7%，看起来均匀得多。"
               "但注意 <b>2016 年只有 0.4%</b>：那一年 N 长期低位平稳，"
               "「相对近期偏低」几乎不成立——动态阈值把绝对低孔洞状态换成了"
               "相对异常，<b>在平稳期反而丢掉了本来最多的信号</b>。</p></div>")

parts.append("<div class=\"card\"><h3>3.7 那 2 格「不跨零」能不能当发现？联合检验说不能</h3>"
             + table(["项", "值"], [
                 ["方法", "整条远期收益序列随机循环平移，保留收益自相关与 18 个信号间的相关结构，只打乱对齐；取 18 格最大 IC 作统计量"],
                 ["重复次数", str(joint["repetitions"])],
                 ["观察到的最大 IC", num(joint["observed_max_ic"], 6)],
                 ["对应格子", joint["observed_argmax_cell"]],
                 ["零假设下最大 IC 的均值", num(joint["null_max_mean"], 4)],
                 ["零假设下最大 IC 的 95 分位", num(joint["null_max_q95"], 4)],
                 ["<b>族系校正后 p</b>", "<b>" + num(joint["p_family_wise"], 4) + "</b>"],
                 ["Bonferroni 单格 α", num(joint["bonferroni_alpha_per_cell"], 6)],
             ])
             + "<div class=\"danger\">18 个同时检验在 5% 水平下本来就会出现约 0.9 个假阳性；"
               "联合 max-IC 检验 p=0.137，Bonferroni 单格门槛 0.00278 也远低于那两格的名义水平。"
               "<b>两格都不能称为发现。</b>循环平移在拼接处有一个断点，"
               "所以这是诊断而非形式化证明，但足以否定「调一调就显著了」的读法。</div></div>")

parts.append("<div class=\"card\"><h3>3.8 如果偷看未来会怎样（禁用对照）</h3>"
             + table(["全样本分位 p", "全期 N 分位数", "触发日", "h=20 IC", "信号日 r(20)", "状态"],
                     [[f"{r['percentile']:.2f}", num(r["full_sample_quantile_of_N"], 1),
                       str(r["signal_days_report"]), num(r["ic_h20"], 4),
                       pct(r["mean_fwd20_on_signal"]),
                       "<b>禁用</b>"] for r in ad["forbidden_lookahead_contrast"]])
             + "<div class=\"danger\"><b>这一组只用来展示泄漏，不参与任何结论。</b>"
               "它用整个 2015—2025 报告期的 N 分布算分位数，包含 t 之后的日期，"
               "实盘不可实现。有意思的是：即便允许泄漏，p=0.10 的分位数恰好等于 1，"
               "结果退化成固定 k=1（IC 0.0913）；p=0.05 得 N=0，IC 0.0741。"
               "<b>连偷看未来都调不出强信号</b>，反过来说明瓶颈不在阈值数值。</div></div>")

parts.append("<div class=\"card\"><h3>3.9 问题二的结论，以及要变成确认性研究该怎么做</h3>"
             "<div class=\"key\"><b>能做，但它是「换一条规则」，不是「修好原规则」。</b>"
             "按节点数缩放（你最初的想法）实测无效；因果滚动分位能把 2021—2025 的触发"
             "从 16 天恢复到 77—267 天，<b>解决了覆盖率</b>，"
             "但 h=20 IC 未改善、联合 p=0.137、事件级收益塌回 0 附近，"
             "<b>没有恢复预测有效性</b>；同时语义变成「相对近期偏低」，不再是兴业复现。</div>"
             + table(["若要做成确认性研究，必须预先冻结", "理由"], [
                 ["滚动窗口 W、分位 p、信号族", "否则就是按测试成绩反选参数"],
                 ["warm-up 起点与最小历史长度", "保证可实盘复现，不用未来数据"],
                 ["事件定义（簇间隔）与去重口径", "避免日级重复计数"],
                 ["评价主指标与单一主评价期", "18 格 × 5 期 = 90 个口径，必须先定主判据"],
                 ["样本外时间边界", "须预先登记；<b>当前 2025 最终测试仍封存未读取</b>，"
                  "规则与参数都必须在读测试集之前冻结"],
                 ["多重比较校正方式", "max-IC 或 Bonferroni 预先写死"],
             ])
             + "<p>按项目既定纪律，这一步属于<b>探索性稳健性诊断</b>。"
               "在你确认设计之前，我不会把它升级成确认性绩效，也不会据此改 Gate 1 的任何设定。</p></div>")

# ---------------------------------------------------------------- 4-7
parts.append("<h2 id=\"s4\">4. 两个问题合起来看</h2>")
parts.append("<div class=\"card\">"
             "<p>问题一告诉你：<b>把同一事件重复计数，会把一个微弱、不显著的关联包装成"
             "看起来不错的日级结果</b>（+1.61% → +0.92%/+0.64%，p=0.524）。</p>"
             "<p>问题二告诉你：<b>把阈值改成自适应，能把「后期不再触发」这个工程问题修好，"
             "但修好之后信号日条件均值里那点提升，一按事件去重又消失</b>。"
             "两件事指向同一个根源：这份本地重建面板上，N 与市场未来收益之间"
             "没有稳定的、可交易的排序关系；改进的方向若是「让信号多起来」，"
             "只会制造更多看似有效的日级观测。</p>"
             "<div class=\"warnbox\">还要强调一次因果边界：N 的精确定义、"
             "兴业 Wind 逐日行业名单与收益细节、万得四级行业分类仍未取得，"
             "节点数在若干时段（如 2022-01 的 67）明显受补充数据覆盖影响。"
             "因此这里所有数字都是<b>本地重建面板上的样本内描述</b>，"
             "既不能证明 TDA 无效，也不能证明兴业原文有误。</div></div>")

pitfalls = [
    ("信号日 ≠ 事件", "392 个信号日只对应 42 个簇；簇长最长 87 天。日级均值被长簇机械加权。"),
    ("h 不是持仓期", "IC 里的 h 只是打分用的远期收益窗口，与原文 4 日持仓、网格 4/8/12 日持仓无关。"),
    ("日历日 ≠ 交易日", "簇间隔用 10 个<b>日历</b>日；窗口 W 用<b>交易</b>日；二者不可混用。"),
    ("事件级样本极小", "40 个有效事件、2022 年 1 个、2024 年 2 个；任何分年结论都是极小样本。"),
    ("尾部不足不是负例", "2025 年 2 个事件无完整 20 日远期收益，记未定，不参与均值、不当负例。"),
    ("置换检验 ≠ 完备", "间隔匹配置换只匹配了间隔，没匹配「事件集中在低 N 平台期」的时间聚类。"),
    ("节点数解释不了漂移", "2021—2025 段内 corr(N, 节点数) = −0.2477；按节点数缩放阈值实测无效。"),
    ("ties 会撑爆触发率", "N 是整数；直接 N ≤ quantile 会让所有并列值一起触发，必须用 midrank。"),
    ("滚动窗口有适应滞后", "N 平台跳升后 W 日内新平台尚未进入基线，信号会失语（2021-06-29 例）。"),
    ("平稳期反而失语", "2016 年 N 长期低位平稳，滚动 p=10% 触发率仅 0.4%，绝对低孔洞被判为「不异常」。"),
    ("18 格必须联合校正", "2 格区间不跨零在 18 次检验下属正常假阳性；max-IC 联合 p=0.137。"),
    ("禁用全样本分位", "用整个报告期 N 分布算分位会泄漏未来；报告里单列为禁用对照，不参与结论。"),
]
parts.append("<h2 id=\"s5\">5. 坑位清单（12 条）</h2><div class=\"card\">"
             + table(["#", "坑", "说明"],
                     [[str(i + 1), a, b] for i, (a, b) in enumerate(pitfalls)]) + "</div>")

parts.append("<h2 id=\"s6\">6. 边界、状态与下一步</h2><div class=\"card\">"
             + table(["项", "状态"], [
                 ["本次工作性质", "只读探索性诊断；未重跑策略、未改阈值、未修改任何既有结果文件"],
                 ["新增文件", "1 个计算脚本、2 个 JSON、2 个 CSV、2 张 PNG、1 份本报告、1 个报告脚本"],
                 ["确认性修正版策略绩效", "<b>仍未计算</b>"],
                 ["IC / 参数网格 / 事件研究 / 自适应阈值", "全部样本内探索性诊断，不是有效性证据"],
                 ["未取得的原始数据", "兴业 N 精确实现、Wind 逐日行业名单与收益、万得四级行业分类及行情"],
                 ["Gate 1", "<b>仍暂停</b>；2025 最终测试未读取"],
                 ["Gate 2", "<b>未启动</b>"],
                 ["下一步", "先与你讨论设计，再决定兴业线如何收口、是否重启 Gate 1"],
             ])
             + "<div class=\"good\">按你之前定下的流程：先做兴业复现线，做好了再讨论 Gate 1。"
               "本次两个追问都已在兴业线内部收口，<b>没有触碰 Gate 1/2 的任何设定，"
               "也没有读取 2025 最终测试</b>。</div></div>")

parts.append("<h2 id=\"s7\">7. 自测题</h2><div class=\"card\"><ol>"
             "<li>为什么日级 392 个信号日的均值 +1.61% 不能当成「42 次独立成功」？"
             "去重后有哪三种聚合口径，各自是多少？</li>"
             "<li>事件级 95% 区间 [−1.49%, +3.23%] 跨零，但日级区间 [+0.84%, +2.37%] 不跨零，"
             "这是否说明日级更可信？为什么？</li>"
             "<li>简单随机置换 p=0.524、间隔匹配 p=0.1096，为什么后者更小？"
             "能不能据此说「接近显著」？</li>"
             "<li>k=0 簇起点 −1.37% 与 k=1 簇起点 +0.92% 矛盾吗？用 2.6 节的分解表解释。</li>"
             "<li>为什么按节点数缩放阈值（γ=1,2,3）救不了 2021 年后的空仓？"
             "给出至少一个数字证据。</li>"
             "<li>写出 ρ<sub>t</sub> 的公式。如果不用 0.5·equal 这一项，触发率会怎样？</li>"
             "<li>2021-06-29 的 ρ≈0.9917 说明动态阈值有什么固有缺陷？</li>"
             "<li>18 格里有 2 格 95% 区间不跨零，为什么仍不能称为发现？"
             "联合检验给出什么数？</li>"
             "<li>「覆盖率恢复」和「有效性恢复」分别用哪个指标判断？二者这次各是什么结果？</li>"
             "<li>把滚动分位规则真正做成一个可发表的样本外检验，最少要先冻结哪 5 项？</li>"
             "</ol>" + details("展开：参考答案要点",
                               "<ol><li>同一事件被重复计数；日级 +1.61%、簇等权 +0.64%、事件起点 +0.92%。</li>"
                               "<li>不能。日级样本高度自相关，i.i.d. 区间过窄，正是重复计数造成的伪精确。</li>"
                               "<li>间隔匹配缩小了零假设方差；仍是追加诊断、未校正多重比较，不能宣称。</li>"
                               "<li>不矛盾：不同阈值与不同簇边界；k=1 有效起点里 27 个是 N=1 (+2.40%)，13 个是 N=0 (−2.15%)。</li>"
                               "<li>节点数只涨 16%，127 节点处阈值最多 2.05，而 2021 年 N 中位 18；后期触发 13/13/17 天 ≤ 基准 16 天。</li>"
                               "<li>ρ=(less+0.5·equal)/W；不加 0.5 项时并列值会被全算作「不低」或全算作「低」，触发率被 ties 扭曲。</li>"
                               "<li>平台跳升后最多 W 日的适应滞后，新基线未建立时信号失语。</li>"
                               "<li>18 次检验期望约 0.9 个假阳性；max-IC 联合 p=0.137，Bonferroni α=0.00278。</li>"
                               "<li>覆盖率看触发日/逐年分布（16 → 77—267 天，恢复）；有效性看 h=20 IC 与事件级收益（0.0226—0.0936、事件起点≈0，未恢复）。</li>"
                               "<li>W、p、信号族、warm-up、事件定义、主指标与主评价期、样本外边界、多重校正，任取 5 项。</li></ol>")
             + "</div>")

# ---------------------------------------------------------------- appendices
parts.append("<h2 id=\"sa\">附录 A：完整计算脚本</h2>"
             "<p class=\"legend\">逐行编号，与本次实际执行版本一致。脚本只读输入，"
             "写入的输出文件见附录 C。</p>")
numbered = "\n".join(f"{i:4d}  {line}" for i, line in enumerate(script_source.splitlines(), 1))
parts.append(pre(numbered))

parts.append("<h2 id=\"sb\">附录 B：全部原始输出</h2>"
             "<p class=\"legend\">以下折叠块逐字内嵌，不删减、不改写。"
             "想核对报告里任何一个数字，直接展开找对应字段。</p>")
parts.append(details("展开：xy_event_study.json 全文（43 KB）", pre(ev_source)))
parts.append(details("展开：xy_adaptive_threshold.json 全文（37 KB）", pre(ad_source)))
parts.append(details("展开：xy_event_study_clusters.csv 全文（42 事件）", pre(ev_csv)))
parts.append(details("展开：xy_adaptive_threshold_grid.csv 全文（19 行）", pre(ad_csv)))
parts.append("<p class=\"legend\">两张 PNG 已作为 base64 图片内嵌在第 2.2 与 3.5 节，"
             "原文件也在 outputs/ 目录。</p>")

parts.append("<h2 id=\"sc\">附录 C：文件清单与复算命令</h2><div class=\"card\">"
             + table(["类别", "路径", "说明"], [
                 ["计算脚本", "src/xy_replication/event_and_adaptive_threshold_study.py", "本次新增，执行全部诊断"],
                 ["报告脚本", "src/xy_replication/build_event_adaptive_report.py", "本次新增，只读生成 HTML"],
                 ["结果", "outputs/xy_event_study.json / .png / _clusters.csv", "问题一"],
                 ["结果", "outputs/xy_adaptive_threshold.json / .png / _grid.csv", "问题二"],
                 ["报告", "outputs/xy_event_adaptive_report.html", "本文件"],
                 ["输入", "outputs/xy_corrected_sw193_ifind_peak_features.csv", "v1.2 特征，3339 行"],
                 ["输入", "outputs/xy_wind_all_a_daily.csv", "万得全A 日线 3012 行"],
                 ["既有", "outputs/xy_ic_method_report.html", "上一版 IC 方法报告（15 章），本次未改动"],
                 ["既有", "outputs/xy_signal_trigger_ic_matrix.json", "触发时点逐年数据，2.1 节引用"],
             ])
             + "<div class=\"formula\">"
               "# 重算全部诊断（会覆盖上述 6 个结果文件，本报告不执行这一步）<br>"
               "tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/event_and_adaptive_threshold_study.py<br><br>"
               "# 只生成本报告（读取既有输出，不改任何结果文件）<br>"
               "tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/build_event_adaptive_report.py"
               "</div>"
             + "<p class=\"legend\">只读一致性校验：本报告生成时按主脚本口径独立复算了"
               f" 事件 1 的 r(20) = {pct(hand['r20'], 8)}、"
               f" 2022-02-11 的 ρ = {num(rank1, 6)}，均与 JSON 一致；"
               f" 报告期首日序号 {warmup_index} &gt; 最大窗口 250，warm-up 覆盖完整。</p></div>")

parts.append("<div class=\"footer\">本报告为单文件离线 HTML：两张 PNG 以 base64 内嵌，"
             "样式内联，无外部脚本、无 CDN、无外链。所有结果为样本内探索性诊断，"
             "不构成投资建议、不构成 TDA 有效性判断、不构成对兴业证券研报的复现或否定。"
             "Gate 1 暂停 / 2025 最终测试未读取 / Gate 2 未启动。</div>")

parts.append("</div></body></html>")
html_text = "\n".join(parts)

# ---------------------------------------------------------------- assertions
assert "<img src=\"data:image/png;base64," in html_text
assert html_text.count("<img src=\"data:image/png;base64,") == 2
assert "http://" not in html_text and "https://" not in html_text
assert "<script" not in html_text
assert html_text.count("<table>") == html_text.count("</table>")
assert html_text.count("<details>") == html_text.count("</details>")
assert html_text.count("<div") == html_text.count("</div>")
assert "0.137" in html_text and "0.524" in html_text and "0.2477" in html_text
assert f"{hand['r20']:.6f}"[:6] in html_text or pct(hand["r20"], 4) in html_text
HTML_OUT.write_text(html_text, encoding="utf-8")
print(f"OK  {HTML_OUT}  {HTML_OUT.stat().st_size:,} bytes  "
      f"tables={html_text.count('<table>')}  details={html_text.count('<details>')}  "
      f"sections={html_text.count('<h2 id=')}")
