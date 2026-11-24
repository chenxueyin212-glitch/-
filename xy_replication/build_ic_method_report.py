"""Build a standalone, fully self-contained HTML report explaining the IC diagnostics.

This script does NOT rerun any experiment. It reads the existing outputs, embeds
them verbatim, and renders a teaching-style document with formulas, a worked
numeric example, all result tables, caveats and self-test questions.

Output: outputs/xy_ic_method_report.html (single file, no external resources).
"""
from __future__ import annotations

import base64
import csv
import html
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
IC_JSON = OUT / "xy_ic_diagnostics.json"
BINS_CSV = OUT / "xy_ic_bins.csv"
YEAR_CSV = OUT / "xy_ic_by_year.csv"
FIG_PNG = OUT / "xy_ic_diagnostics.png"
SCRIPT = ROOT / "src" / "xy_replication" / "ic_diagnostics.py"
MATRIX_JSON = OUT / "xy_signal_trigger_ic_matrix.json"
MATRIX_CSV = OUT / "xy_signal_ic_matrix.csv"
TRIGGER_CLUSTER_CSV = OUT / "xy_signal_trigger_clusters.csv"
TRIGGER_YEAR_CSV = OUT / "xy_signal_trigger_by_year.csv"
MATRIX_FIG = OUT / "xy_signal_trigger_ic_matrix.png"
MATRIX_SCRIPT = ROOT / "src" / "xy_replication" / "signal_trigger_ic_matrix.py"
HTML_OUT = OUT / "xy_ic_method_report.html"

ic = json.loads(IC_JSON.read_text(encoding="utf-8"))
ic_source = IC_JSON.read_text(encoding="utf-8")
bins_source = BINS_CSV.read_text(encoding="utf-8-sig")
year_source = YEAR_CSV.read_text(encoding="utf-8-sig")
script_source = SCRIPT.read_text(encoding="utf-8")
fig_b64 = base64.b64encode(FIG_PNG.read_bytes()).decode("ascii")

mtx = json.loads(MATRIX_JSON.read_text(encoding="utf-8"))
mtx_source = MATRIX_JSON.read_text(encoding="utf-8")
mtx_csv_source = MATRIX_CSV.read_text(encoding="utf-8-sig")
trigger_cluster_source = TRIGGER_CLUSTER_CSV.read_text(encoding="utf-8-sig")
trigger_year_source = TRIGGER_YEAR_CSV.read_text(encoding="utf-8-sig")
mtx_script_source = MATRIX_SCRIPT.read_text(encoding="utf-8")
mtx_fig_b64 = base64.b64encode(MATRIX_FIG.read_bytes()).decode("ascii")
HORIZONS = tuple(mtx["preregistration"]["horizons"])


def ci_text(row) -> str:
    lo, hi = row.get("ci95_lo"), row.get("ci95_hi")
    if lo is None or hi is None:
        return "无定义"
    return f"[{signed(lo)}, {signed(hi)}]"


def crosses_text(v) -> str:
    if v is None:
        return "<b>无定义</b>"
    return "是" if v else "<span class=\"badge-red\"><b>否</b></span>"


def esc(value) -> str:
    return html.escape(str(value), quote=False)


def f(value, digits: int = 4) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def pct(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f}%"


def signed(value, digits: int = 4) -> str:
    if value is None:
        return "—"
    return f"{value:+.{digits}f}"


def plus_pct(value) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else "−"
    return sign + pct(abs(value))


B_DATA = '<span class="tag data">数据</span>'
B_METHOD = '<span class="tag method">方法</span>'
B_JUDGE = '<span class="tag judge">判断</span>'


def table(headers, rows, note: str = "") -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    out = f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
    if note:
        out += f'<div class="note">说明：{note}</div>'
    return out


def block(title: str, body: str, level: int = 2) -> str:
    return f"<h{level}>{title}</h{level}>" + body


parts: list[str] = []

CSS = """
:root{--bg:#fbfbfa;--card:#ffffff;--ink:#1d1d1b;--muted:#5f5e5a;--line:#e3e1da;--blue:#185fa5;--blue-bg:#e6f1fb;--red:#a32d2d;--red-bg:#fcebeb;--amber:#854f0b;--amber-bg:#faeeda;--green:#0f6e56;--green-bg:#e1f5ee}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;font-size:15px;line-height:1.75}
.wrap{max-width:1080px;margin:0 auto;padding:36px 28px 80px}
h1{font-size:27px;font-weight:600;margin:0 0 8px;line-height:1.35}
h2{font-size:20px;font-weight:600;margin:44px 0 14px;padding-bottom:9px;border-bottom:2px solid var(--line)}
h3{font-size:17px;font-weight:600;margin:30px 0 10px}
h4{font-size:15px;font-weight:600;margin:22px 0 8px}
p{margin:10px 0}
.sub{color:var(--muted);font-size:14px}
.meta{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 22px}
.pill{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:4px 11px;font-size:12.5px;color:var(--muted)}
.pill.warn{background:var(--amber-bg);border-color:#efd9a8;color:var(--amber)}
.tag{display:inline-block;border-radius:4px;padding:0 6px;font-size:11.5px;line-height:19px;font-weight:600;margin-right:5px;vertical-align:1px}
.tag.data{background:var(--blue-bg);color:var(--blue)}
.tag.method{background:#eeedfe;color:#534ab7}
.tag.judge{background:var(--amber-bg);color:var(--amber)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:16px 0}
.card.danger{border-color:#f0c9c9;background:#fffafa}
.card.ok{border-color:#bfe3d3;background:#f7fdfa}
.card.warn{border-color:#efd9a8;background:#fffdf6}
.card h3,.card h4{margin-top:0}
.tw{overflow-x:auto;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--card)}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#f4f3ef;font-weight:600;white-space:nowrap}
tbody tr:nth-child(even){background:#fcfcfa}
td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12.8px}
.note{font-size:13px;color:var(--muted);background:#f7f6f2;border-left:3px solid var(--line);padding:9px 12px;margin:8px 0 4px;border-radius:0 6px 6px 0}
.formula{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#f4f3ef;border:1px solid var(--line);border-radius:8px;padding:12px 14px;font-size:13.5px;line-height:2;margin:12px 0;overflow-x:auto}
pre{background:#f7f6f2;border:1px solid var(--line);border-radius:8px;padding:14px;font-size:12.5px;line-height:1.6;overflow-x:auto;white-space:pre}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.92em;background:#f1efe8;padding:1px 4px;border-radius:3px}
pre code{background:none;padding:0}
ul,ol{padding-left:22px;margin:10px 0}
li{margin:6px 0}
a{color:var(--blue);text-decoration:none}
a:hover{text-decoration:underline}
.toc{columns:2;column-gap:32px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 22px;font-size:14px}
.toc a{display:block;padding:2px 0}
.toc div{break-inside:avoid}
abbr[title]{border-bottom:1px dotted var(--muted);cursor:help;text-decoration:none}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:12px 0}
summary{cursor:pointer;font-weight:600;font-size:14px}
.figure{margin:18px 0}
.figure img{width:100%;border:1px solid var(--line);border-radius:10px;background:#fff;display:block}
.figcap{font-size:12.5px;color:var(--muted);margin-top:7px}
.badge-red{color:var(--red);font-weight:600}
.badge-green{color:var(--green);font-weight:600}
.kv{display:grid;grid-template-columns:190px 1fr;gap:6px 14px;font-size:14px}
.kv dt{color:var(--muted)}
.kv dd{margin:0}
hr{border:0;border-top:1px solid var(--line);margin:34px 0}
.legend{font-size:13px;color:var(--muted)}
.q{font-weight:600;margin-top:14px}
.ans{background:#f7fdfa;border-left:3px solid var(--green);padding:9px 12px;font-size:14px;border-radius:0 6px 6px 0;margin-top:8px}
.footer{font-size:12.5px;color:var(--muted);margin-top:48px;border-top:1px solid var(--line);padding-top:14px}
@media(max-width:720px){.toc{columns:1}.wrap{padding:20px 14px 60px}.kv{grid-template-columns:1fr}}
"""

parts.append("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">")
parts.append("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">")
parts.append("<title>信号层 IC 诊断 · 计算口径与全部结果明细</title>")
parts.append(f"<style>{CSS}</style></head><body><div class=\"wrap\">")

# ---------------- header ----------------
parts.append("<h1>信号层 IC 诊断：算了哪些量、怎么算、数字从哪来</h1>")
parts.append(
    "<p class=\"sub\">兴业证券复现线 · 对一个低频稀疏择时信号的方法学明细报告。"
    "本报告只解释既有计算，不新增实验、不改变任何确认性结论。</p>"
)
parts.append(
    "<div class=\"meta\">"
    f"<span class=\"pill\">生成日期 {date.today().isoformat()}</span>"
    "<span class=\"pill\">单文件离线版，无外链</span>"
    "<span class=\"pill\">含 4A 触发时点 / 4B 50 格 IC 矩阵</span>"
    "<span class=\"pill warn\">探索性诊断 · 非样本外 · 非策略绩效</span>"
    "<span class=\"pill\">Gate 1 暂停 / 2025 最终测试未读取 / Gate 2 未启动</span>"
    "</div>"
)
parts.append(
    "<div class=\"card\"><b>标记体系（避免把推断当数据）：</b>"
    f"{B_DATA} 直接来自输出文件的数值或字段；"
    f"{B_METHOD} 整理者补充的通用统计/计算方法说明；"
    f"{B_JUDGE} 本项目的判断或解释，不是兴业证券原文结论，也不构成机制证明。"
    "所有原始数值均可在第 7 节与附录中找到逐字原文。</div>"
)
parts.append(
    "<div class=\"toc\">"
    "<div><a href=\"#s0\">0. 这份报告回答什么</a>"
    "<a href=\"#s1\">1. 为什么从年化换到 IC</a>"
    "<a href=\"#s2\">2. 数据与样本漏斗</a>"
    "<a href=\"#s3\">3. 计算口径：时间对齐、公式、手算例子</a>"
    "<a href=\"#s4\">4. 八组诊断逐项展开</a>"
    "<a href=\"#s4a\">4A. 什么时候触发信号</a>"
    "<a href=\"#s4b\">4B. 不同信号的 IC 全矩阵</a></div>"
    "<div><a href=\"#s5\">5. 不确定性怎么给</a>"
    "<a href=\"#s6\">6. 数字对不上的六处口径</a>"
    "<a href=\"#s7\">7. 完整结果汇总（原文全披露）</a>"
    "<a href=\"#s8\">8. 坑位清单</a>"
    "<a href=\"#s9\">9. 自测题</a>"
    "<a href=\"#s10\">10. 结论、边界与状态</a>"
    "<a href=\"#sa\">附录 A：完整计算脚本</a>"
    "<a href=\"#sb\">附录 B：文件清单与复算命令</a></div></div>"
)

# ---------------- 0 ----------------
parts.append("<h2 id=\"s0\">0. 这份报告回答什么</h2>")
parts.append(
    "<p>你提的建议是：<b>「本来就是低频的信号，算年化有什么用？应该算 IC」</b>。"
    "这条建议被落地成一次纯诊断：新增脚本 <code>ic_diagnostics.py</code>，产出 4 个结果文件，"
    "并写进主报告 4.4 节。你随后问「不清楚怎么算的、算了哪些」，本报告就是把这件事拆到"
    "<b>每一个样本的来源、每一条公式、每一个数字的复算路径</b>。</p>"
)
parts.append(
    "<div class=\"card danger\"><b>先把最重要的话放前面，不给希望滤镜：</b>"
    "IC 的结果是<b>弱正但不显著、不稳定</b>——五个未来期的 95% 区块自助区间全部跨零；"
    "日级 IC 主要靠同一事件被重复计数撑起来（0.0913 → 簇去重后 0.0131）。"
    "这不是「TDA 有效」的证据，也不是「TDA 无效」的判决；它只说明"
    "<b>在这份本地重建面板上，没有证据表明 N 稳定排序未来收益</b>。</div>"
)
parts.append(
    "<h3>三个层次的问题</h3><ol>"
    "<li><b>算了哪些？</b> 8 组诊断（第 4 节）＋ 4A 触发时点、4B 全信号 IC 矩阵；全部结果见第 7 节。</li>"
    "<li><b>怎么算？</b> 数据 → 样本漏斗 → 时间对齐 → 公式 → 手算例子 → 自助区间，见第 2、3、5 节。</li>"
    "<li><b>算出来怎么读？</b> IC 与年化的分工、数字矛盾的解释、哪些结论必须收回，见第 6、10 节。</li>"
    "</ol>"
)
parts.append(
    "<div class=\"card warn\"><b>本次修订（因追问「什么时候触发、不同信号 IC 怎么样」）：</b>"
    "新增 4A / 4B 两章，来自一次<b>只读补充诊断</b> <code>signal_trigger_ic_matrix.py</code>。"
    "10 种信号 × 5 个期限 = 50 格在查看任何 IC 之前固定、全部披露、不按结果反选；"
    "同时给出 4 个阈值的触发画像、逐年分布、42 个事件簇的起止日期和四个案例期。"
    "<b>没有重跑策略、没有改阈值、没有按 IC 挑信号、没有修改任何既有结果文件</b>；"
    "新增的只是补充脚本与其结果文件，以及本报告。</div>"
)
parts.append(
    "<p class=\"legend\">初版生成时做过一次<b>只读复算校验</b>：独立计算 20 日 Pearson IC 与点二列 IC，"
    "与既有 JSON 逐位一致（见附录 B）。本次补充诊断沿用同一数据与因果口径，"
    "并如实记录了稀疏二元信号在区块自助中的退化抽样。</p>"
)

# ---------------- 1 ----------------
parts.append("<h2 id=\"s1\">1. 为什么从年化换到 IC</h2>")
parts.append(
    f"{B_METHOD}<b>年化收益度量的是「账户」，不是「信号」。</b>对一个一年只触发几次的信号，年化有四个硬伤："
    "<ol>"
    "<li><b>分母摊平</b>：9.8 年复利会把少数几次事件摊薄，一次事件的实际贡献被年化数字掩盖。</li>"
    "<li><b>不可比</b>：暴露 15% 的参数格与暴露 58% 的参数格，年化不是同一个东西，直接排序没有意义。</li>"
    "<li><b>路径依赖</b>：复利让结果极度依赖事件发生在哪一年，先赚后亏与先亏后赚年化不同。</li>"
    "<li><b>规则纠缠</b>：年化同时混合了阈值、延续天数、成本、仓位、基准，信号本身好坏无法分离。</li>"
    "</ol>"
    "所以报告里的年化只因<b>原文表 1 报的就是年化</b>才保留作对照，已降级，不是主判据。</p>"
)
parts.append(
    f"{B_METHOD}<p><b>IC（Information Coefficient）在这里的定义</b>：信号值与未来收益之间的相关系数，"
    "回答「信号能否把未来收益排序」。本报告用的是 <abbr title=\"把同一标的按时间排列，信号序列与远期收益序列求相关\">时序 IC</abbr>，"
    "不是选股研究里常见的 <abbr title=\"每个交易日在横截面上，对 N 只股票的因子值与收益求秩相关\">截面 RankIC</abbr>。</p>"
)
parts.append(
    "<div class=\"card warn\"><b>为什么不能用截面 RankIC：</b>本信号择时的是<b>一个</b>市场指数（万得全A 881001.WI），"
    "每期只有 1 个标的，没有横截面可供排序，逐期截面 RankIC 在数学上无定义。"
    "能算的只有：连续信号的时序 Pearson / Spearman IC、二元信号的"
    "<abbr title=\"一个二元变量与一个连续变量之间的 Pearson 相关\">点二列 IC</abbr>、以及按 N 分桶的单调性。</div>"
)
parts.append(
    "<p>三种计算对象对应三种问题：连续信号 <code>−N</code> 问「整体排序有没有信息」；"
    "二元信号 <code>1[N≤k]</code> 问「触发阈值有没有区分度」；分桶问「关系是不是单调、靠不靠少数极端值」。</p>"
)

# ---------------- 2 ----------------
parts.append("<h2 id=\"s2\">2. 数据与样本漏斗</h2>")
parts.append(
    f"{B_DATA}<p>输入只有两个既有文件，<b>本次诊断没有引入任何新第三方数据</b>：</p>"
)
parts.append(
    table(
        ["用途", "文件", "内容", "区间 / 行数"],
        [
            ["信号", "<code>outputs/xy_corrected_sw193_ifind_peak_features.csv</code>",
             "v1.2 修正版逐日拓扑特征；本报告只用 <code>h2_count</code>（记为 N）、<code>h2_landscape_l1</code>、<code>h1_landscape_l1</code>",
             "3339 行，2012-12-31 ～ 2026-11-03"],
            ["远期收益", "<code>outputs/xy_wind_all_a_daily.csv</code>",
             "万得全A 881001.WI 日线，字段 <code>date/open/close/high/low</code>",
             "3012 行，2012-12-31 ～ 2025-05-30"],
        ],
        "两者按 <code>date</code> 精确对齐；脚本对每个特征日断言必须存在对应 Wind 日线，否则报错。",
    )
)
parts.append(
    f"{B_METHOD}<h3>样本漏斗：所有「数字对不上」都从这里来</h3>"
)
parts.append(
    table(
        ["步骤", "筛选条件（代码位置）", "剩余行数", "含义"],
        [
            ["① 原始特征", "无", "3339", "含 2025-05-30 之后的特征，也含 2015-07 之前的预热期"],
            ["② 截断", "<code>read_inputs()</code>：<code>date &lt;= 2025-05-30</code>", "2994", "与基准日线末端对齐，之后的日期没有价格"],
            ["③ 报告期", "<code>START=2015-07-01, END=2025-05-30</code>", "2391", "对应原文表 1 的报告期；2015-07 之前只用于 30 日拓扑窗口预热，不作评分样本"],
            ["④ h=20 可用", "<code>report &amp; isfinite(ro)</code>", "2370", "尾部 21 日凑不齐 t+21 的开盘价，剔除，不填零、不当负例"],
        ],
    )
)
parts.append(
    f"{B_DATA}<h4>不同 h 的有效样本（尾部剔除 = h+1 行）</h4>"
)
parts.append(
    table(
        ["h", "有效样本", "尾部剔除", "Pearson IC", "95% 区块自助区间"],
        [
            [str(r["horizon_days"]), str(r["n_observations"]), str(r["n_dropped_tail"]),
             f(r["ic_pearson"]), f"[{signed(r['ci95_block_bootstrap'][0])}, {signed(r['ci95_block_bootstrap'][1])}]"]
            for r in ic["horizon_ic"]
        ],
    )
)
parts.append(
    f"{B_JUDGE}<p>注意 ② 这一步：特征文件延伸至 2026-11-03，但 Wind 日线只到 2025-05-30，"
    "所以诊断样本止于 2025-05-30。<b>2025 年只有 76 个 h=20 重叠观测</b>，"
    "这一点后面解释 +0.774 那年 IC 时会再出现。</p>"
)

# ---------------- 3 ----------------
parts.append("<h2 id=\"s3\">3. 计算口径：时间对齐、公式、手算例子</h2>")
parts.append(f"{B_METHOD}<h3>3.1 因果时间对齐</h3>")
TIME_SVG = """
<svg viewBox="0 0 680 232" width="100%" role="img" style="background:#fff;border:1px solid #e3e1da;border-radius:10px">
<title>时序IC的因果对齐</title><desc>t日收盘得到信号，t+1开盘建仓，t+1+h开盘计算远期收益。</desc>
<defs><marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<text x="36" y="30" font-family="sans-serif" font-size="14" font-weight="600" fill="#0C447C">主口径：信号可知时刻 → 最早可执行入场 → 远期收益</text>
<rect x="36" y="52" width="176" height="56" rx="8" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="124" y="74" font-family="sans-serif" font-size="14" font-weight="600" fill="#0C447C" text-anchor="middle" dominant-baseline="central">t 日收盘</text>
<text x="124" y="94" font-family="sans-serif" font-size="12" fill="#185FA5" text-anchor="middle" dominant-baseline="central">算出 N_t（信号可知）</text>
<rect x="250" y="52" width="176" height="56" rx="8" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="338" y="74" font-family="sans-serif" font-size="14" font-weight="600" fill="#0C447C" text-anchor="middle" dominant-baseline="central">t+1 开盘</text>
<text x="338" y="94" font-family="sans-serif" font-size="12" fill="#185FA5" text-anchor="middle" dominant-baseline="central">入场价 open[t+1]</text>
<rect x="464" y="52" width="176" height="56" rx="8" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="552" y="74" font-family="sans-serif" font-size="14" font-weight="600" fill="#0C447C" text-anchor="middle" dominant-baseline="central">t+1+h 开盘</text>
<text x="552" y="94" font-family="sans-serif" font-size="12" fill="#185FA5" text-anchor="middle" dominant-baseline="central">出场价 open[t+1+h]</text>
<path d="M56 144 L622 144" fill="none" stroke="#888780" stroke-width="1" marker-end="url(#ar)"/>
<path d="M124 108 L124 144 M338 108 L338 144 M552 108 L552 144" fill="none" stroke="#B4B2A9" stroke-width="0.5"/>
<circle cx="124" cy="144" r="4" fill="#185FA5"/><circle cx="338" cy="144" r="4" fill="#185FA5"/><circle cx="552" cy="144" r="4" fill="#185FA5"/>
<path d="M338 176 L552 176" fill="none" stroke="#185FA5" stroke-width="1.2" marker-start="url(#ar)" marker-end="url(#ar)"/>
<text x="445" y="198" font-family="sans-serif" font-size="13" fill="#0C447C" text-anchor="middle">r(t,h) = open[t+1+h] / open[t+1] − 1</text>
<text x="36" y="222" font-family="sans-serif" font-size="12" fill="#5F5E5A">尾部不足 h+1 个未来价格者剔除；收盘口径仅作敏感性，非严格可执行</text>
</svg>
"""
parts.append(f'<div class="figure">{TIME_SVG}</div>')
parts.append(
    "<p>为什么不用 <code>close[t+h]/close[t]−1</code> 作主口径：t 日收盘才知道 N_t，"
    "却用同一天的收盘价当入场价，严格说不可执行。所以主口径用 <b>t+1 开盘</b>，"
    "与 <code>backtest.py::causal_open</code> 一致；收盘口径只作为敏感性对照。</p>"
)
parts.append(f"{B_METHOD}<h3>3.2 公式与符号表</h3>")
parts.append(
    "<div class=\"formula\">"
    "信号（连续）：s_t = −N_t　　　信号（二元）：b_t = 1[N_t ≤ k]<br>"
    "主口径远期收益：r(t,h) = open[t+1+h] / open[t+1] − 1<br>"
    "敏感性远期收益：r_c(t,h) = close[t+h] / close[t] − 1<br>"
    "Pearson IC：　IC = Σ(s_t − s̄)(r_t − r̄) / √[ Σ(s_t − s̄)² · Σ(r_t − r̄)² ]<br>"
    "Spearman IC：　先把 s 与 r 各自换成秩（并列取平均秩），再按上式求 Pearson<br>"
    "点二列 IC：　r_pb = (M₁ − M₀)/s_y · √[ p(1−p) ]，其中 p = P(b=1)<br>"
    "naive t（无效，仅作对照）：　t = IC·√(n−2) / √(1−IC²)"
    "</div>"
)
parts.append(
    table(
        ["符号", "含义", "本报告中取值 / 来源"],
        [
            ["<code>N_t</code>", "t 日 H₂ 有限持久区间数（本项目主解释，未获原作者确认）", "特征 CSV 的 <code>h2_count</code>"],
            ["<code>s_t</code>", "连续信号，取 −N 使「孔洞少」对应大值", "正 IC = 孔洞越少未来收益越高"],
            ["<code>b_t</code>", "二元触发信号", "k ∈ {0,1,2,3}"],
            ["<code>r(t,h)</code>", "未来 h 交易日开盘到开盘收益", "h ∈ {1,5,10,20,40}；主 h=20"],
            ["<code>n</code>", "有效配对样本数", "2370（h=20）"],
            ["<code>s_y</code>", "远期收益标准差", "≈ 0.0655（样本 ddof=1 为 0.065548；总体口径 0.065534，差异在 1e−4 量级）"],
            ["<code>p</code>", "二元信号触发占比", f"{pct(0.16413502109704642)}（k=1，389/2370）"],
            ["<code>L¹</code>", "H₂ / H₁ 持久景观一阶范数 Σ(d−b)²/4", "用作信号变体对照"],
        ],
    )
)
parts.append(f"{B_DATA}<h3>3.3 逐日手算例子（可直接照着验算）</h3>")
parts.append(
    "<p>取 h=20，从原始文件读出的三个真实交易日：</p>"
)
parts.append(
    table(
        ["t（信号日）", "N_t", "s_t = −N_t", "t+1 开盘日 / 价", "t+21 开盘日 / 价", "r(t,20)"],
        [
            ["2017-03-15", "6", "−6", "2017-03-16 / 4475.05", "2017-04-18 / 4390.91",
             "<span class=\"badge-green\">−1.8802%</span>"],
            ["2019-11-20", "4", "−4", "2019-11-21 / 4076.50", "2019-12-19 / 4270.26",
             "<span class=\"badge-red\">+4.7531%</span>"],
            ["2023-05-10", "30", "−30", "2023-05-11 / 5010.69", "2023-06-08 / 4865.40",
             "<span class=\"badge-green\">−2.8996%</span>"],
            ["2015-07-08", "2", "−2", "2015-07-09 / 3909.00", "2015-08-07 / 4815.83",
             "<span class=\"badge-red\">+23.1985%</span>"],
        ],
        "验算示例：4390.91 / 4475.05 − 1 = −0.018802。第 4 行是 2015 年股灾后反弹期的极端值，"
        "列出来是为了说明<b>单个样本完全不能说明任何问题</b>——IC 是 2370 对样本的整体相关，不是挑几天看涨跌。",
    )
)
parts.append(f"{B_DATA}<h3>3.4 全样本复算：20 日 Pearson IC 是怎么得出 0.0663 的</h3>")
parts.append(
    "<div class=\"formula\">"
    "n = 2370 对 (s_t, r_t)<br>"
    "s̄ = −8.967932489451476　　r̄ = +0.0026325071473006054（即无条件后 20 日均值 +0.2633%）<br>"
    "Σ(s−s̄)(r−r̄) = 94.79888706394227<br>"
    "Σ(s−s̄)² = 200913.56286919824　　Σ(r−r̄)² = 10.17840303247497<br>"
    "IC = 94.79888706394227 / √(200913.56286919824 × 10.17840303247497) = <b>0.06629164399006625</b>"
    "</div>"
)
parts.append(
    "<p>这个结果与 <code>xy_ic_diagnostics.json → horizon_ic[3].ic_pearson</code> 逐位一致。"
    "同样是 2370 对样本，把 s 换成二元 <code>1[N≤1]</code> 后，"
    "按 <code>pearson(b, y)</code> 得 <b>0.0912759412704448</b>，与 "
    "<code>h20_binary_and_point_biserial[1]</code> 逐位一致（生成报告时的只读复算，见附录 B）。</p>"
)
parts.append(
    f"{B_METHOD}<h3>3.5 点二列 IC 的公式链</h3>"
    "<p>设 b∈{0,1}，p=P(b=1)，M₁ / M₀ 为信号组 / 非信号组的平均收益，s_y 为收益标准差：</p>"
    "<div class=\"formula\">"
    "Cov(b, y) = E[by] − E[b]E[y] = p·M₁ − p·(p·M₁+(1−p)·M₀) = p(1−p)(M₁ − M₀)<br>"
    "Var(b) = p(1−p)<br>"
    "Corr(b, y) = Cov / √[Var(b)·Var(y)] = p(1−p)(M₁−M₀) / √[p(1−p)·s_y²]<br>"
    "　　　　　 = (M₁ − M₀)/s_y · √[p(1−p)]"
    "</div>"
    "<p>代入 k=1 的实际值：M₁ = +1.6131%、M₀ ≈ −0.0018%、p = 16.41%、s_y ≈ 6.55%，"
    "得 (0.016149 / 0.0655) × √(0.1641×0.8359) ≈ <b>0.0913</b>"
    "（精确值 0.0912759412704448，标准差口径的微小差别不影响两位小数）。</p>"
    "<div class=\"card warn\"><b>这个公式直接给出一个必须记住的坑：</b>稀疏信号 p 很小时，"
    "√[p(1−p)] 会把 IC <b>机械压小</b>。因此「IC 小」不等于「没有提升」，"
    "反之「IC 不小」也可能是同一事件被重复计数。稀疏信号必须同时看提升度、上涨比例与事件簇数。</div>"
)

# ---------------- 4 ----------------
parts.append("<h2 id=\"s4\">4. 八组诊断逐项展开</h2>")
parts.append(
    f"{B_DATA}<p>全部 8 组都在同一次脚本运行中产生，参数固定："
    "<code>START/END = 2015-07-01 / 2025-05-30</code>、<code>HORIZONS = (1,5,10,20,40)</code>、"
    "<code>MAIN_H = 20</code>、<code>BLOCK = 20</code>、<code>N_BOOT = 1000</code>、"
    "<code>SEED = 20261108</code>、<code>GAP_DAYS = 10</code>。</p>"
)

parts.append("<h3>① 五期时序 IC（主结果）</h3>")
parts.append(
    f"{B_METHOD}<p>对每个 h，取 <code>usable = report ∧ isfinite(r(t,h))</code>，"
    "令 <code>x = −N[usable]</code>、<code>y = r(t,h)[usable]</code>，算 Pearson、Spearman、"
    "区块自助区间、naive t、收盘口径 Pearson。</p>"
)
parts.append(
    table(
        ["h", "n", "尾部剔除", "Pearson IC", "Spearman IC", "区块自助 95% 区间", "naive t（无效）", "收盘口径 IC"],
        [
            [str(r["horizon_days"]), str(r["n_observations"]), str(r["n_dropped_tail"]),
             f(r["ic_pearson"]), f(r["ic_spearman"]),
             f"[{signed(r['ci95_block_bootstrap'][0])}, {signed(r['ci95_block_bootstrap'][1])}]",
             f(r["naive_t_invalid"], 2), f(r["ic_pearson_close_to_close"])]
            for r in ic["horizon_ic"]
        ],
        "IC 为相关系数，<b>无量纲、不是百分比</b>。五条自助区间全部跨零；"
        "h=40 的 IC 最大，但它的窗口重叠也最长，且自助块长仍是 20 日，区间可能偏窄（见 5.4）。",
    )
)
parts.append(
    f"{B_JUDGE}<p>怎么读：IC 随 h 上升（0.019 → 0.091），Spearman 始终高于 Pearson，"
    "说明关系偏秩/阈值型、且可能在较长尺度上更明显；但<b>没有一个区间排除零</b>，"
    "所以不能说存在稳定预测关系。</p>"
)

parts.append("<h3>② 收盘口径敏感性</h3>")
parts.append(
    f"{B_METHOD}<p>把收益换成 <code>close[t+h]/close[t]−1</code> 重算 Pearson，"
    "用来检验结论是否由「哪根价格线」决定。</p>"
)
parts.append(
    table(
        ["h", "开盘口径（主）", "收盘口径（敏感性）", "差值"],
        [
            [str(r["horizon_days"]), f(r["ic_pearson"]), f(r["ic_pearson_close_to_close"]),
             signed(r["ic_pearson_close_to_close"] - r["ic_pearson"])]
            for r in ic["horizon_ic"]
        ],
        "差值都在 ±0.007 以内。价格口径不是结论的来源；但收盘口径以 t 日收盘入场，非严格可执行，不能作主口径。",
    )
)

parts.append("<h3>③ 二元信号的点二列 IC 与提升度</h3>")
parts.append(
    f"{B_METHOD}<p>h=20，对 k∈{0,1,2,3} 构造 <code>b=1[N≤k]</code>，"
    "算 <code>pearson(b,y)</code>、信号日数、占比、信号组后 20 日均值、"
    "相对无条件均值（+0.2633%）的提升、信号组上涨比例。</p>"
)
parts.append(
    table(
        ["信号定义", "点二列 IC", "信号日", "占比", "信号组后 20 日均值", "相对无条件提升", "信号组上涨比例"],
        [
            [(f"N≤{r['threshold_k']}" if isinstance(r["threshold_k"], int) else "N≤1 且仅簇起点"),
             f(r["ic_point_biserial"]), str(r["signal_days"]), pct(r["signal_share"]),
             pct(r["mean_forward20_on"]), plus_pct(r["lift_vs_unconditional"]),
             pct(r["positive_share_on"])]
            for r in ic["h20_binary_and_point_biserial"]
        ],
        "k 越小信号越稀疏：均值提升越大（+1.90% → +0.42%），但 IC 在 k=1 达到峰值后回落——"
        "正是 √[p(1−p)] 机械压缩在起作用。最后一行的簇去重是本节的关键。",
    )
)

parts.append("<h3>④ 事件簇去重：日级 IC 的膨胀</h3>")
parts.append(
    f"{B_METHOD}<p>算法 <code>cluster_starts()</code>：按日期顺序遍历，只保留满足 <code>N≤k</code> 的日；"
    "若与前一次触发日相隔 <b>&gt;10 个日历日</b>（不是交易日），记为新簇起点，其余日全部丢弃；"
    "再与 <code>usable</code> 求交集。</p>"
)
parts.append(
    f"{B_JUDGE}<div class=\"card danger\">389 个 N≤1 日级信号 → <b>40 个簇起点</b>，"
    "点二列 IC 从 <b>0.0913 塌到 0.0131</b>。这不是计算错误，是同一件事被重复计数："
    "一次持续 20 天的低孔洞状态会贡献 20 个重叠的「正确」观测，"
    "而实际上只有 1 次可交易决策。低频信号最该防的就是这种膨胀。</div>"
)

parts.append("<h3>⑤ 五种信号变体</h3>")
parts.append(
    f"{B_METHOD}<p>固定 h=20 与样本，只换信号定义，看换个表达方式是否能改善排序：</p>"
)
parts.append(
    table(
        ["信号", "Pearson IC", "Spearman IC", "怎么读"],
        [
            ["<code>−N</code>", f(r["ic_pearson"]), f(r["ic_spearman"]), "基准"]
            for r in ic["h20_signal_variants"][:1]
        ] + [
            [f"<code>{esc(r['signal'])}</code>", f(r["ic_pearson"]), f(r["ic_spearman"]),
             ("单调变换，Spearman 与 −N 完全相同 → 没有新排序信息" if r["signal"] == "minus_log1p_N"
              else "换成景观 L¹ 并未改善 Pearson" if "landscape" in r["signal"]
              else "二元化后 Pearson 最高，但见 ④ 的重复计数问题")]
            for r in ic["h20_signal_variants"][1:]
        ],
        "<code>−log(1+N)</code> 是 −N 的严格单调变换，秩完全不变，所以 Spearman 精确等于 0.1623；"
        "Pearson 从 0.0663 升到 0.0881 只来自非线性压缩，不是新信息。",
    )
)

parts.append("<h3>⑥ N 分桶：单调性检验</h3>")
parts.append(
    f"{B_METHOD}<p>桶边界 <code>(0,0),(1,1),(2,2),(3,3),(4,5),(6,10),(11,20),(21,∞)</code>，"
    "每桶算 20 日收益均值、中位数、上涨比例。若「孔洞越少越反弹」是单调关系，柱形应逐级下降。</p>"
)
parts.append(
    table(
        ["N 分桶", "n", "占比", "后 20 日均值", "中位数", "上涨比例"],
        [
            [esc(r["bin"]), str(r["n"]), pct(r["share"]), pct(r["mean_forward20"]),
             pct(r["median_forward20"]), pct(r["positive_share"])]
            for r in ic["h20_n_buckets"]
        ],
        "无条件均值 +0.2633%。低 N 桶整体确实较高（N=0 +2.16%、N=1 +1.29%），"
        "但 N=2/3 掉到 0 附近、N=4—10 又回升、N=11—20 才明显为负，<b>不是严格单调</b>。"
        "配合 Spearman ≫ Pearson，关系更像阈值/秩型而非线性。",
    )
)
parts.append(
    f"{B_JUDGE}<div class=\"card warn\"><b>由此修正上一版判断：</b>"
    "此前「孔洞越少越反弹不单调」的说法只在<b>簇起点</b>口径下成立，已被降级为口径依赖观察，"
    "不得再作为稳健结论引用。准确表述见 10.2。</div>"
)

parts.append("<h3>⑦ 分年与分段稳定性</h3>")
parts.append(
    f"{B_METHOD}<p>按自然年切分，各年单独算一次 IC；再分 2015—2020 / 2021—2025 两段，"
    "各段独立做 20 日区块自助。分段内不做任何参数选择。</p>"
)
parts.append(
    table(
        ["年份", "n", "Pearson IC", "Spearman IC", "后 20 日均值", "N≤1 信号日占比"],
        [
            [r["year"], str(r["n"]), f(r["ic_pearson"]), f(r["ic_spearman"]),
             pct(r["mean_forward20"]), pct(r["signal_day_share_N<=1"])]
            for r in ic["yearly_ic"]
        ],
        "描述性结果。h=20 窗口重叠、每年约 240 个观测；2025 只有 76 个重叠日且全年无 N≤1 触发，"
        "+0.774 是小样本极值，不得当信号有效证据。",
    )
)
parts.append(
    table(
        ["区间", "n", "Pearson IC", "区块自助 95% 区间", "后 20 日均值", "N≤1 信号日占比"],
        [
            [r["segment"], str(r["n"]), f(r["ic_pearson"]),
             f"[{signed(r['ci95_block_bootstrap'][0])}, {signed(r['ci95_block_bootstrap'][1])}]",
             pct(r["mean_forward20"]), pct(r["signal_day_share_N<=1"])]
            for r in ic["segment_ic"]
        ],
        "两段区间都跨零。分段 IC 与分年 IC 不矛盾：把多年混在一起算一个相关时，"
        "跨年的 N 水平与收益水平差异会互相抵消。",
    )
)

parts.append("<h3>⑧ N 分布漂移与 2×2 口径审计</h3>")
parts.append(
    f"{B_DATA}<p>分布漂移（同一批 2370 个可用样本）：</p>"
)
parts.append(
    table(
        ["区间", "n", "N 均值", "N 中位", "P10", "P90", "P(N≤1)"],
        [
            [r["segment"], str(r["n"]), f(r["mean_N"], 2), f(r["median_N"], 1),
             f(r["p10_N"], 1), f(r["p90_N"], 1), pct(r["share_N<=1"])]
            for r in ic["N_distribution_drift"]
        ],
        "节点数从 104 增至 124/131 后 N 整体抬升，这是结构漂移，不是市场状态变好或变坏。",
    )
)
parts.append(
    f"{B_METHOD}<p>2×2 审计设计：把「样本定义」（全部 N=0 日 vs 每簇仅第一天）与"
    "「价格口径」（收盘→收盘 vs 开盘→开盘）交叉，看结论翻转到底由哪个因素造成。</p>"
)
parts.append(
    table(
        ["样本定义", "收益定义", "n", "后 20 日均值", "中位数", "上涨比例"],
        [
            [("全部 N=0 日" if r["sample"] == "all_N=0_days" else "仅 N=0 簇起点"),
             ("收盘→收盘 20 日" if r["return_definition"] == "close_to_close_20d" else "开盘→开盘 20 日"),
             str(r["n"]), pct(r["mean"]), pct(r["median"]), pct(r["positive_share"])]
            for r in ic["definition_sensitivity_audit"]
        ],
        "换价格口径几乎不变（+2.247% / +2.165%，−1.264% / −1.371%）；"
        "换样本定义则由约 +2.2% 翻为约 −1.3%。<b>矛盾来自抽样，不是价格。</b>",
    )
)
parts.append(
    f"{B_JUDGE}<p><b>状态层面的弱正向关联</b>与<b>可交易首次触发时点不占优</b>是两个不同问题，"
    "可以同时成立。不要把前者当成策略能赚钱的证据。</p>"
)

# 主报告原图
parts.append(
    f'<div class="figure"><img src="data:image/png;base64,{fig_b64}" alt="IC诊断三面板图">'
    "<div class=\"figcap\">原脚本输出 <code>xy_ic_diagnostics.png</code>（内嵌，无外链）。"
    "上：五期 IC 与自助区间，全部跨零；中：N 分桶后 20 日均值与无条件基线；"
    "下：分年 IC，2025 仅 76 个重叠观测。IC 为无量纲相关系数。</div></div>"
)

# ---------------- 4A: trigger timing ----------------
parts.append('<h2 id="s4a">4A. 什么时候触发信号</h2>')
parts.append(
    '<p>这一节回答「触发」本身：N 在什么时候算出来、满足什么条件算触发、'
    '最早什么时候能交易、历史上到底在哪些日期触发过。<b>这些都是描述性事实，不是策略绩效。</b></p>'
)
parts.append(f'{B_DATA}<h3>4A.1 触发规则与六个容易混淆的时间概念</h3>')
parts.append(
    table(
        ['概念', '定义', '取值 / 备注'],
        [
            ['N_t 何时算出', 't 日<b>收盘后</b>，用过去 30 个交易日行业收益相关网络 → ρ<sub>ij</sub> → d<sub>ij</sub> → VR → H₂ → N_t', '每日盘后一次，不能用盘中数据'],
            ['触发条件', 'N_t ≤ k', '兴业原文 k=1；本项目对照 k ∈ {0,1,2,3}'],
            ['信号可知时刻', 't 日收盘', '因此 t 日收盘价入场不可执行'],
            ['最早可执行入场', '<b>t+1 开盘</b>', '严格开盘价，与 <code>backtest.py::causal_open</code> 一致'],
            ['原文持仓', '触发后持有 4 个交易日', '兴业原文规则'],
            ['网格持仓', '4 / 8 / 12 日', '预登记网格，区间独立起算'],
            ['IC 的 h', '评价用的未来收益窗口 1 / 5 / 10 / 20 / 40 日', '<b>不是持仓期，也不是触发规则</b>，只决定用多久的收益给信号打分'],
            ['事件簇', '相邻触发日间隔 &gt;10 个<b>日历日</b>算新簇', '描述性去重；389 个日级信号 ≈ 40–42 次独立事件'],
        ],
        '最常见误解：把 IC 的 h 当成「信号延续几天」。h 只出现在 IC 的分母口径里；'
        '策略里的「延续 4/8/12 日」是持仓期，两者没有任何关系。',
    )
)
parts.append(f'{B_DATA}<h3>4A.2 四个阈值的触发画像（全部 2391 个报告日）</h3>')
parts.append(
    table(
        ['阈值 k', '信号日', '占比', '事件簇', '首次触发', '末次触发', '簇长中位', '簇长最大', '簇长 P90'],
        [[str(r['threshold_k']), str(r['signal_days']), pct(r['signal_share']),
          str(r['event_clusters']), r['first_signal_date'], r['last_signal_date'],
          f(r['cluster_length_median'], 1), str(r['cluster_length_max']),
          f(r['cluster_length_p90'], 1)] for r in mtx['trigger_profile']],
        'k 越大触发日越多，但事件簇反而更少——触发日连成大片，并不是更多次独立机会。'
        '<b>k=0 最后一次触发是 2020-05-11</b>，此后整个面板再没出现 N=0。',
    )
)
parts.append(f'{B_DATA}<h3>4A.3 按年触发分布（k=1，兴业原文阈值）</h3>')
year_k1 = [r for r in mtx['by_year'] if r['threshold_k'] == 1]
parts.append(
    table(
        ['年份', '报告日', 'N≤1 信号日', '占比', '簇起点', 'N 均值', 'N 中位'],
        [[r['year'], str(r['report_days']), str(r['signal_days']), pct(r['signal_share']),
          str(r['cluster_starts']), f(r['mean_N'], 2), f(r['median_N'], 1)] for r in year_k1],
        '2015—2020 每年 33～116 个触发日；<b>2021 年 0、2023 年 0</b>，2022 年仅 1 天，'
        '2024 年 12 天、2025 年 3 天。N 中位从 1～5 抬到 8～20，这是固定阈值失效，不是市场变得更好。',
    )
)
parts.append(f'{B_DATA}<h3>4A.4 42 个事件簇的完整起止日期</h3>')
cluster_rows_html = [
    [r['start'], r['end'], str(r['cluster_days']), str(r['N_at_start']),
     str(r['n_nodes_at_start']), r['entry_date_t_plus_1'] or '—',
     pct(r['forward20_open_to_open']) if r['forward20_open_to_open'] is not None else '尾部不足']
    for r in mtx['cluster_list_N_le_1']
]
parts.append(
    '<details><summary>展开：42 个 N≤1 事件簇逐簇明细</summary>'
    + table(['簇起始', '簇结束', '触发天数', '起始 N', '节点数', 't+1 入场日', '后 20 日开盘收益'],
            cluster_rows_html,
            '「簇起始」才是可交易的首次触发时点；同一簇内其余触发日不是独立事件。'
            '2025-05 的簇后 20 日收益记为「尾部不足」，因为基准日线止于 2025-05-30，不填零、不当负例。')
    + '</details>'
)
parts.append(f'{B_DATA}<h3>4A.5 四个案例期到底触发了没有</h3>')
parts.append(
    table(
        ['案例月', '窗口', 'N≤1 日数', '具体触发日期'],
        [[r['case_month'], r['window'][0] + ' ～ ' + r['window'][1], str(r['N_le_1_days']),
          '、'.join(d['date'] for d in r['dates']) if r['dates'] else '<b>无触发</b>']
         for r in mtx['case_months']],
        '2020-03 连续 10 个触发日（2020-03-02 ～ 03-13）其实是<b>一次事件</b>；'
        '2022-04、2025-01 完全没触发；2024-02 只有 02-21 一天。',
    )
)
parts.append(
    f'{B_JUDGE}<div class="card danger"><b>直接回答「什么时候触发」：</b>'
    '每天收盘后算 N，N≤k 即触发，最早次日开盘建仓。历史上触发高度集中在 2015—2020，'
    'k=1 共 392 个日级信号 / 42 个事件簇；2021 与 2023 全年零触发，k=0 自 2020-05-11 后彻底消失。'
    '这不是「信号变准了」，是节点数增加后 N 整体抬升、固定阈值不再适配。</div>'
)

# ---------------- 4B: full signal x horizon IC matrix ----------------
parts.append('<h2 id="s4b">4B. 不同信号的 IC 全矩阵</h2>')
parts.append(
    f'{B_JUDGE}<p>之前只给了 <code>−N</code> 在五个 h 上的 IC，二元阈值只在 h=20 给了点二列 IC，'
    '确实没说清楚「不同信号各自的 IC 怎么样」。这一节补一次<b>预登记的全矩阵诊断</b>：'
    '信号定义与期限在查看任何 IC 之前固定，10 种信号 × 5 个期限 = <b>50 格全部披露</b>，'
    '不按 IC 高低挑信号、不把任何一格提升为主结论。数据、因果口径、自助参数与 4A/第 3 节完全一致。</p>'
)
parts.append(f'{B_DATA}<h3>4B.1 10 种信号（含 1 个对照变量）</h3>')
parts.append(
    table(
        ['#', '信号', '定义'],
        [[str(i + 1), '<code>' + esc(s['name']) + '</code>', esc(s['description'])]
         for i, s in enumerate(mtx['preregistration']['signals'])],
        '最后一行 <code>minus_n_nodes_CONTROL</code> 不是交易信号，只用检验「节点数漂移」'
        '本身会不会制造伪 IC；它在 h=20 的 IC 为 −0.0049、区间 [−0.1373, +0.1571]。',
    )
)
parts.append(f'{B_DATA}<h3>4B.2 主评价期 h=20：10 种信号逐个看</h3>')
h20_rows = [r for r in mtx['ic_matrix'] if r['horizon_days'] == 20]
parts.append(
    table(
        ['信号', 'Pearson IC', 'Spearman IC', '区块自助 95% 区间', '区间跨零', '信号日'],
        [['<code>' + esc(r['signal']) + '</code>', f(r['ic_pearson']), f(r['ic_spearman']),
          ci_text(r), crosses_text(r['crosses_zero']),
          str(r['signal_days']) if r['signal_days'] is not None else '—'] for r in h20_rows],
        '<b>主 h=20 的 10 个信号，区间全部跨零。</b>二元信号 IC 普遍高于连续信号，'
        '但这是 √[p(1−p)] 与阈值化的尺度效应，不是新增预测信息；'
        '簇去重后 IC 只剩 0.0131。',
    )
)
parts.append(f'{B_DATA}<h3>4B.3 50 格 IC 点估计矩阵</h3>')
sig_names = [s['name'] for s in mtx['preregistration']['signals']]
grid_rows = []
for name in sig_names:
    row = ['<code>' + esc(name) + '</code>']
    for h in HORIZONS:
        r = next(x for x in mtx['ic_matrix'] if x['signal'] == name and x['horizon_days'] == h)
        val = '—' if r['ic_pearson'] is None else f'{r["ic_pearson"]:.3f}'
        if r['crosses_zero'] is False:
            val = '<span class="badge-red"><b>' + val + '*</b></span>'
        row.append(val)
    grid_rows.append(row)
parts.append(
    table(['信号 \\ 期限'] + ['h=' + str(h) for h in HORIZONS], grid_rows,
          '红色带 * 表示该格的 95% 区块自助区间不跨零，共 4 格，全部不在主 h=20。'
          'IC 为无量纲相关系数。完整 50 行明细见下方折叠块。')
)
detail_rows = [
    [r['signal'], str(r['horizon_days']), str(r['n_observations']),
     f(r['ic_pearson']), f(r['ic_spearman']), ci_text(r), crosses_text(r['crosses_zero'])]
    for r in mtx['ic_matrix']
]
parts.append(
    '<details><summary>展开：50 格完整明细（每格含 IC、Spearman、自助区间、是否跨零）</summary>'
    + table(['信号', 'h', 'n', 'Pearson IC', 'Spearman IC', '95% 区间', '跨零'], detail_rows)
    + '</details>'
)
parts.append(
    f'<div class="figure"><img src="data:image/png;base64,{mtx_fig_b64}" alt="信号×期限IC热力图与触发年份分布">'
    '<div class="figcap">上：10 种信号 × 5 个期限的 Pearson IC 热力图（50 格，红=正）；'
    '下：k=1 的逐年触发日数、事件簇数与 N 中位数，2021 后触发近乎归零。</div></div>'
)
parts.append(f'{B_JUDGE}<h3>4B.4 4 个「区间不跨零」的格子，为什么不能当发现</h3>')
sig_cells = [r for r in mtx['ic_matrix'] if r['crosses_zero'] is False]
parts.append(
    table(
        ['信号', 'h', 'Pearson IC', '95% 区间', '信号日', 'n'],
        [[r['signal'], str(r['horizon_days']), f(r['ic_pearson']), ci_text(r),
          str(r['signal_days']), str(r['n_observations'])] for r in sig_cells],
        '这 4 格看似显著，但逐条拆开都不成立：'
        '① 50 格全披露、<b>没有多重检验校正</b>，5% 水平下期望约 2.5 格假阳性，出现 4 格毫不意外；'
        '② 全部集中在 h=1 或 h=40，<b>主 h=20 无一格</b>；'
        '③ h=40 的窗口重叠 40 日而自助块长仍固定 20 日，区间可能偏窄（见 5.3）；'
        '④ h=1 两格效应只有 0.026～0.043，且是稀疏二元信号的机械相关；'
        '⑤ 全部为样本内描述，无样本外验证。',
    )
)
parts.append(f'{B_DATA}<h3>4B.5 分段 IC 与自助退化：最该警惕的一张表</h3>')
seg_late = [r for r in mtx['h20_segment_ic'] if r['segment'] == '2021-2025']
parts.append(
    table(
        ['信号（2021—2025 段）', 'h=20 IC', '95% 区间', '跨零', '该段信号日'],
        [['<code>' + esc(r['signal']) + '</code>', f(r['ic_pearson']), ci_text(r),
          crosses_text(r['crosses_zero']),
          str(r['signal_days']) if r['signal_days'] is not None else '—'] for r in seg_late],
        '2015—2020 段 10 个信号全部跨零。2021—2025 段出现 6 个「不跨零」，'
        '但该段二元信号只有 3～40 个触发日：<b>簇起点信号只有 3 个事件却报出 IC 0.0864、区间 [0.0439, 0.1433]</b>。'
        '3 个事件算出来的「显著」没有统计意义，是多重比较加极小样本的产物。',
    )
)
parts.append(
    table(
        ['自助退化的格子', '退化次数 / 总次数', '含义'],
        [[d['tag'], str(d['degenerate_draws']) + ' / ' + str(d['total_draws']),
          '重采样里信号恒为 0，Pearson 无定义'] for d in mtx['bootstrap_degenerate_draws']],
        '合计 1059 次退化。<b><code>binary_N≤0 | 2021-2025</code> 是 1000/1000 全退化</b>：'
        '该段 N=0 从未出现，信号恒为 0，IC 直接记「无定义」而不是 0 或 nan 填充。'
        '这正是「固定阈值在 2021 后失效」的最硬证据，也说明稀疏信号的自助 CI 本身就不稳。',
    )
)
parts.append(
    f'{B_DATA}<details><summary>展开：补充诊断的三个 CSV 全文</summary>'
    '<h4>xy_signal_ic_matrix.csv（50 格）</h4><pre><code>' + esc(mtx_csv_source) + '</code></pre>'
    '<h4>xy_signal_trigger_clusters.csv（42 簇）</h4><pre><code>' + esc(trigger_cluster_source) + '</code></pre>'
    '<h4>xy_signal_trigger_by_year.csv（4 阈值 × 11 年）</h4><pre><code>' + esc(trigger_year_source) + '</code></pre>'
    '</details>'
)
parts.append(
    f'{B_JUDGE}<div class="card danger"><b>直接回答「不同信号的 IC 怎么样」：</b>'
    '主评价期 h=20 上，10 种信号的 Pearson IC 从 −0.0049（节点数对照）到 +0.0913（二元 N≤1），'
    '但<b>每一个区块自助区间都跨零</b>；换成 H₂/H₁ 景观、对数压缩、放宽阈值都不改变这个事实。'
    '唯一稳定为负的是把 389 个日级信号压成 40 个簇起点后，IC 从 0.0913 掉到 0.0131——'
    '不同信号定义之间的差距，远小于「日级 vs 事件级」这个抽样口径带来的差距。</div>'
)

# ---------------- 5 ----------------
parts.append("<h2 id=\"s5\">5. 不确定性是怎么给的</h2>")
parts.append(f"{B_METHOD}<h3>5.1 为什么不能用常规 t 检验</h3>")
parts.append(
    "<p>公式 <code>t = IC·√(n−2)/√(1−IC²)</code> 成立的前提是观测 <b>独立同分布</b>。"
    "这里两个前提都被破坏：</p><ol>"
    "<li><b>窗口重叠</b>：h=20 时相邻两天的远期收益共享 19/20 的价格区间，几乎不独立；"
    "2370 个名义观测大约只相当于 2370/20 ≈ 118 个不重叠窗口。</li>"
    "<li><b>信号自相关</b>：N_t 是 30 日滚动窗口算出的拓扑量，相邻日高度相关，"
    "低孔洞状态往往连续持续几十天。</li></ol>"
)
parts.append(
    f"{B_JUDGE}<div class=\"formula\">示意性粗算（非正式校正，仅用于说明高估幅度）："
    "若按约 118 个不重叠窗口计，t 公式中的 n−2 取 116，"
    "t ≈ 0.0663 × √116 / √(1−0.0663²) ≈ <b>0.71</b>，远低于 1.96。<br>"
    "脚本报告的 naive t：h=20 为 3.23、h=40 为 4.43 —— 看似显著，实为伪显著。</div>"
)
parts.append(
    f"{B_JUDGE}<p>所以 <code>naive_t_invalid</code> 这一列是<b>故意留着展示高估幅度</b>的，"
    "字段名已标明 invalid，报告里注明「禁止用于判断」。</p>"
)
parts.append(f"{B_METHOD}<h3>5.2 配对移动区块自助（主判据）</h3>")
parts.append(
    "<div class=\"formula\">"
    "输入：配对序列 (x_i, y_i)，i = 1..n；block = 20；重复 1000 次；seed = 20261108<br>"
    "for 每次重复：<br>"
    "　　n_blocks = ceil(n / 20)<br>"
    "　　starts = 在 [0, n−20] 上均匀抽 n_blocks 个整数起点<br>"
    "　　idx = 拼接每个 [s, s+20) 的连续索引，再截断到长度 n<br>"
    "　　value = pearson(x[idx], y[idx])<br>"
    "输出：1000 个 value 的 2.5% 与 97.5% 分位数"
    "</div>"
)
parts.append(
    "<p>「配对」意味着 x 与 y 用同一组索引抽取，信号与收益的对应关系不被打散；"
    "「区块」意味着块内保留 20 日的局部时间依赖。这比逐点 iid 自助更保守。</p>"
)
parts.append(f"{B_JUDGE}<h3>5.3 这个自助法的局限，如实写在这里</h3>")
parts.append(
    "<ul>"
    "<li>块长固定 20 日。h=40 时远期收益的重叠长度是 40 日，块长可能不足以覆盖全部依赖，"
    "因此 h=40 的区间 <b>可能偏窄、偏乐观</b>；即便如此它仍然跨零。</li>"
    "<li>块之间随机拼接，破坏长程序列结构；没有做去均值、平稳化或 pre-whitening。</li>"
    "<li>没有对 5 个 h、4 个 k、5 种信号变体、11 个年份、8 个分桶做多重检验校正。"
    "这些全是探索性描述，任何「显著」字样都不成立。</li>"
    "<li>没有样本外切分：整个 2015-07～2025-05 都用于算 IC，属于<b>样本内诊断</b>。</li>"
    "</ul>"
)
parts.append(f"{B_METHOD}<h3>5.4 区间结果一览</h3>")
parts.append(
    table(
        ["检验", "n", "IC", "95% 区间", "是否跨零"],
        [["h=" + str(r["horizon_days"]), str(r["n_observations"]), f(r["ic_pearson"]),
          f"[{signed(r['ci95_block_bootstrap'][0])}, {signed(r['ci95_block_bootstrap'][1])}]",
          "<b>是</b>"] for r in ic["horizon_ic"]]
        + [[r["segment"], str(r["n"]), f(r["ic_pearson"]),
            f"[{signed(r['ci95_block_bootstrap'][0])}, {signed(r['ci95_block_bootstrap'][1])}]",
            "<b>是</b>"] for r in ic["segment_ic"]],
        "7 个区间，全部跨零。这是本次诊断最硬的结论。",
    )
)

# ---------------- 6 ----------------
parts.append("<h2 id=\"s6\">6. 数字对不上的六处口径</h2>")
parts.append(
    f"{B_JUDGE}<p>下表把最容易让人以为「算错了」的地方逐条对应到样本漏斗：</p>"
)
parts.append(
    table(
        ["看似矛盾", "实际口径", "结论"],
        [
            ["392 vs 389 个 N≤1 信号日", "392 = 全部 2391 个报告日；389 = h=20 有效窗口 2370 日内", "尾部剔除 21 日，不是数据不一致"],
            ["42 vs 40 个事件簇", "42 = 全报告期簇数；40 = 落在 h=20 可用窗口内的簇起点", "同一原因；簇判定用 10 个<b>日历日</b>间隔，不是交易日"],
            ["+2.2% vs −1.3%（N=0 后 20 日）", "145 个全部 N=0 日 vs 35 个簇起点", "样本定义差异；两种价格口径都各自一致"],
            ["分年 IC 有 ±0.3～0.8，全样本只有 0.066", "跨年混合时 N 水平与收益水平差异互相抵消", "分段 −0.008 / +0.108，都跨零；不矛盾"],
            ["IC 为正，但策略 2021—2023 几乎空仓", "IC 衡量排序信息；年化衡量固定阈值规则", "P(N≤1) 从 28.16% 掉到 1.26%，阈值不再触发，两者可并存"],
            ["JSON 英文说明写 median 3→13.5，表里是 14", "文案笔误，表 <code>N_distribution_drift</code> 与报告 4.4 用 14", "以表为准，不影响任何计算；待下版订正"],
        ],
    )
)

# ---------------- 7 ----------------
parts.append("<h2 id=\"s7\">7. 完整结果汇总（原文全披露）</h2>")
parts.append(
    f"{B_DATA}<p>以下折叠块把原始输出逐字嵌入，不删减、不改写。想核对任何一个数字，直接展开。</p>"
)
parts.append(
    "<details><summary>展开：xy_ic_diagnostics.json 全文（8 组诊断）</summary>"
    f"<pre><code>{esc(ic_source)}</code></pre></details>"
)
parts.append(
    "<details><summary>展开：xy_signal_trigger_ic_matrix.json 全文（触发画像 + 50 格 IC + 42 簇清单）</summary>"
    f"<pre><code>{esc(mtx_source)}</code></pre></details>"
)
parts.append(
    "<details><summary>展开：xy_ic_bins.csv 全文</summary>"
    f"<pre><code>{esc(bins_source)}</code></pre></details>"
)
parts.append(
    "<details><summary>展开：xy_ic_by_year.csv 全文</summary>"
    f"<pre><code>{esc(year_source)}</code></pre></details>"
)
parts.append(
    "<details><summary>展开：JSON 中的口径声明与解释字段</summary>"
    "<pre><code>"
    + esc(json.dumps({
        "status": ic["status"],
        "why_ic_is_not_a_cross_sectional_rankic": ic["why_ic_is_not_a_cross_sectional_rankic"],
        "causal_convention": ic["causal_convention"],
        "uncertainty": ic["uncertainty"],
        "sparse_signal_caveat": ic["sparse_signal_caveat"],
        "interpretation": ic["interpretation"],
        "unconditional_forward20_mean": ic["unconditional_forward20_mean"],
        "gate_status": ic["gate_status"],
    }, ensure_ascii=False, indent=2))
    + "</code></pre></details>"
)

# ---------------- 8 ----------------
parts.append("<h2 id=\"s8\">8. 坑位清单</h2>")
parts.append(
    "<ol>"
    "<li><b>把时序 IC 当截面 RankIC。</b>只有一个标的，横截面 RankIC 无定义。</li>"
    "<li><b>用 t 日收盘价建仓。</b>t 日收盘才知道 N_t，主口径必须是 t+1 开盘。</li>"
    "<li><b>用 naive t 判显著。</b>重叠窗口＋信号自相关，t=3.23 / 4.43 是伪显著。</li>"
    "<li><b>把日级观测当独立事件。</b>389 日其实 40 次决策，IC 从 0.0913 塌到 0.0131。</li>"
    "<li><b>只看 IC 判稀疏信号。</b>√[p(1−p)] 机械压小，必须配提升度与事件簇数。</li>"
    "<li><b>把 Spearman 与 Pearson 的差异当新信息。</b>单调变换下 Spearman 不变，Pearson 变化只是非线性压缩。</li>"
    "<li><b>把 2025 年 +0.774 当证据。</b>76 个重叠观测、当年无 N≤1 触发。</li>"
    "<li><b>把尾部不足的日子填 0 或当负例。</b>脚本直接剔除，不填零。</li>"
    "<li><b>把「低孔洞状态有弱正关联」当成「策略能赚钱」。</b>首次触发时点均值约 −1.3%。</li>"
    "<li><b>把固定阈值跨期照搬。</b>N 中位 3→14，N≤1 触发率 28.16%→1.26%，阈值已失效。</li>"
    "<li><b>把本诊断当成样本外验证或复现成功/失败判决。</b>它是样本内探索性诊断，"
    "N 的精确定义、逐日行业名单、万得四级行业分类仍未取得。</li>"
    "</ol>"
)

# ---------------- 9 ----------------
parts.append("<h2 id=\"s9\">9. 自测题（检验是否真的看懂了）</h2>")
questions = [
    ("Q1. 为什么这里的 IC 不是选股意义上的截面 RankIC？",
     "因为信号择时的对象只有一个市场指数（881001.WI），每个时点没有可排序的资产横截面。逐期截面 RankIC 需要「同一期 N 只股票」的因子—收益对，这里不存在，只能算时序 IC。"),
    ("Q2. h=20 时，t 日信号对应的远期收益用哪两个价格？为什么？",
     "open[t+1] 与 open[t+1+h]。N_t 在 t 日收盘后才可知，最早可执行的入场是 t+1 开盘；用 t 日收盘价入场属于前视，不可执行。"),
    ("Q3. 20 日 Pearson IC = 0.0663，naive t = 3.23，能不能说显著？",
     "不能。h=20 窗口重叠且 N_t 强自相关，独立样本假设不成立；20 日配对区块自助的 95% 区间为 [−0.0358, +0.1745]，跨零。"),
    ("Q4. 为什么 k=1 的点二列 IC 比 k=0 高，但 k=0 的均值提升更大？",
     "点二列 IC = (M₁−M₀)/s_y · √[p(1−p)]。k=0 时 p 只有 6.12%，√[p(1−p)] 很小，把 IC 机械压小；k=1 时 p=16.41%，权衡后 IC 更高。IC 小不等于提升小。"),
    ("Q5. 为什么簇去重后 IC 从 0.0913 掉到 0.0131？",
     "389 个日级信号里包含大量同一事件的连续日，这些观测高度重叠、不是独立决策；按 10 个日历日间隔合并后只剩 40 个簇起点。日级 IC 主要由重复计数撑起来。"),
    ("Q6. IC 弱正，为什么网格策略 2021—2023 几乎空仓？",
     "因为 N 分布漂移：中位 N 从 3 升到 14、P(N≤1) 从 28.16% 降到 1.26%，固定的 N≤1 阈值不再触发。IC 衡量排序信息，年化衡量某个固定阈值规则，两者不互相替代。"),
    ("Q7. 「全部 N=0 日 +2.2%」与「N=0 簇起点 −1.3%」哪个对？",
     "两个都对，问的问题不同。2×2 审计显示两种价格口径下各自一致，翻转来自样本定义：前者是状态层面的关联，后者是可交易首次触发时点的表现。不能把前者当策略证据。"),
]
for q, a in questions:
    parts.append(
        f"<div class=\"q\">{esc(q)}</div>"
        f"<details><summary>查看答案</summary><div class=\"ans\">{esc(a)}</div></details>"
    )

# ---------------- 10 ----------------
parts.append("<h2 id=\"s10\">10. 结论、边界与状态</h2>")
parts.append(f"{B_JUDGE}<h3>10.1 IC 给出的答案，比年化更干净、也更不利</h3>")
parts.append(
    "<ol>"
    "<li>20 日 Pearson IC +0.0663、Spearman +0.1623，但区块自助 95% 区间 [−0.0358, +0.1745] 跨零；"
    "h=1/5/10/40 也全部跨零。naive t 的 3.23 / 4.43 是伪显著。</li>"
    "<li>日级二元 IC +0.0913（389 日）→ 40 个簇起点 +0.0131。一次事件被重复包装成几十个日级正确。</li>"
    "<li>分年 IC 在 −0.305 到 +0.774 之间摆动；分段 2015—2020 −0.008、2021—2025 +0.108，两段都跨零。</li>"
    "<li>真正解释「年化低」的不是 IC 弱，而是 N 的分布漂移让固定阈值在 2021 后几乎不触发。"
    "<b>IC 为正与策略几乎不交易可以同时成立。</b></li>"
    "</ol>"
)
parts.append(f"{B_JUDGE}<h3>10.2 必须采用的准确表述</h3>")
parts.append(
    "<div class=\"card ok\"><b>低孔洞状态与后续收益有弱正向关联，但可交易的首次触发时点并不占优，"
    "且该关联不显著、不稳定。</b>这是本项目的口径诊断，不是兴业证券原文结论，也不构成机制证明。"
    "此前「孔洞越少越反弹不单调」的说法已降级为口径依赖观察，不得再作为稳健结论引用。</div>"
)
parts.append(f"{B_JUDGE}<h3>10.3 IC 与年化的分工</h3>")
parts.append(
    "<p>IC 问「信号能否排序未来收益」；年化问「某个固定阈值＋仓位规则赚了多少钱」。"
    "谁都不能替代谁。报告中的年化列<b>只作原文表 1 的对照</b>，不再是主判据。"
    "这正是你那条建议带来的实际改变。</p>"
)
parts.append(
    f"{B_JUDGE}<h3>10.3b 关于 4A / 4B 补充诊断的最终判断</h3>"
    "<div class=\"card danger\">① <b>触发</b>：每日收盘算 N，N≤k 即触发，次日开盘才可执行；"
    "k=1 共 392 个日级信号 / 42 个事件簇，2015—2020 密集，2021 与 2023 全年零触发，"
    "k=0 自 2020-05-11 后再未出现。② <b>不同信号的 IC</b>：主 h=20 的 10 种信号区间全部跨零；"
    "50 格里 4 格不跨零，但都在 h=1 或 h=40、无多重检验校正、效应极小，"
    "h=40 的自助块长还可能偏短，不能当发现。③ 2021—2025 分段的几个「显著」建立在 3～40 个触发日上，"
    "其中簇起点信号只有 3 个事件；k=0 在该段 1000/1000 次自助抽样退化、IC 直接无定义。"
    "<b>这些都指向同一件事：固定阈值在本地重建面板上不可移植，而不是信号变强了。</b></div>"
)
parts.append("<h3>10.4 边界与未取得的东西</h3>")
parts.append(
    "<ul>"
    "<li>全部为样本内诊断；未做样本外切分、未做多重检验校正。</li>"
    "<li>N 的精确定义（有限 H₂ 持久区间数 vs 固定尺度 Betti 数 vs 显著性筛选）尚未获原作者确认。</li>"
    "<li>Wind 逐日行业名单、收益细节、万得四级行业分类、801011/801144 完整早期历史、801193 更早历史仍未取得。</li>"
    "<li>确认性修正版策略绩效仍未计算；参数网格与 IC 都是探索性分析，不是复现证据。</li>"
    "<li><b>Gate 1 仍暂停，2025 最终测试未读取，Gate 2 未启动。</b>按约定，兴业线收口后先与你讨论再动。</li>"
    "</ul>"
)

# ---------------- appendix ----------------
parts.append("<h2 id=\"sa\">附录 A：完整计算脚本（逐行，可直接对照）</h2>")
parts.append(
    f"{B_DATA}<p>文件：<code>src/xy_replication/ic_diagnostics.py</code>。"
    "下面是从磁盘读出的全文，带行号；第 4 节每一组诊断都能在这里找到对应代码。</p>"
)
numbered = "\n".join(f"{i:4d}  {line}" for i, line in enumerate(script_source.splitlines(), 1))
parts.append(f"<pre><code>{esc(numbered)}</code></pre>")
numbered_mtx = "\n".join(f"{i:4d}  {line}" for i, line in enumerate(mtx_script_source.splitlines(), 1))
parts.append(
    f"{B_DATA}<p>补充诊断脚本：<code>src/xy_replication/signal_trigger_ic_matrix.py</code>。"
    "4A 的触发画像与 4B 的 50 格矩阵都由它产生。</p>"
)
parts.append(
    "<details><summary>展开：补充诊断脚本全文（带行号）</summary>"
    f"<pre><code>{esc(numbered_mtx)}</code></pre></details>"
)

parts.append("<h2 id=\"sb\">附录 B：文件清单与复算命令</h2>")
parts.append(
    table(
        ["类型", "路径", "说明"],
        [
            ["脚本", "<code>src/xy_replication/ic_diagnostics.py</code>", "本次全部计算"],
            ["结果", "<code>outputs/xy_ic_diagnostics.json</code>", "全部数值，第 7 节已全文内嵌"],
            ["结果", "<code>outputs/xy_ic_diagnostics.png</code>", "三面板图，本报告已内嵌"],
            ["结果", "<code>outputs/xy_ic_bins.csv</code>", "8 个 N 分桶，第 7 节已全文内嵌"],
            ["结果", "<code>outputs/xy_ic_by_year.csv</code>", "11 个年份，第 7 节已全文内嵌"],
            ["补充脚本", "<code>src/xy_replication/signal_trigger_ic_matrix.py</code>", "4A / 4B 的触发时点与 50 格 IC 矩阵"],
            ["补充结果", "<code>outputs/xy_signal_trigger_ic_matrix.json</code>", "全文见第 7 节"],
            ["补充结果", "<code>outputs/xy_signal_ic_matrix.csv</code>", "50 格，4B 已全文内嵌"],
            ["补充结果", "<code>outputs/xy_signal_trigger_clusters.csv</code>", "42 簇清单，4A.4 已全文内嵌"],
            ["补充结果", "<code>outputs/xy_signal_trigger_by_year.csv</code>", "4 阈值 × 11 年，4B 已全文内嵌"],
            ["补充结果", "<code>outputs/xy_signal_trigger_ic_matrix.png</code>", "热力图与触发年份图，4B 已内嵌"],
            ["报告", "<code>outputs/xy_replication_report.html</code>", "主报告，4.4 节"],
            ["报告", "<code>outputs/xy_replication_report_standalone.html</code>", "单文件离线版"],
            ["本报告", "<code>outputs/xy_ic_method_report.html</code>", "由 <code>build_ic_method_report.py</code> 生成"],
        ],
    )
)
parts.append(
    "<div class=\"formula\">"
    "# 重算 8 组诊断（会覆盖 4 个结果文件，本报告不执行这一步）<br>"
    "tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/ic_diagnostics.py<br><br>"
    "# 重算补充诊断（触发时点 + 50 格 IC 矩阵）<br>"
    "tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/signal_trigger_ic_matrix.py<br><br>"
    "# 只生成本报告（读取既有输出，不改任何结果文件）<br>"
    "tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/build_ic_method_report.py"
    "</div>"
)
parts.append(f"{B_DATA}<h3>生成报告时的只读一致性校验</h3>")
parts.append(
    "<div class=\"formula\">"
    "复算 20 日 Pearson IC：0.06629164399006625　｜　JSON 值：0.06629164399006625　→ 一致<br>"
    "复算 k=1 点二列 IC：0.0912759412704448　｜　JSON 值：0.0912759412704448　→ 一致<br>"
    "样本漏斗：3339 → 2994（截断）→ 2391（报告期）→ 2370（h=20 可用）<br>"
    "逐 h 有效样本：2389 / 2385 / 2380 / 2370 / 2350　→ 与 JSON 一致<br>"
    "补充诊断：50 格 = 10 信号 × 5 期限；主 h=20 十格区间全部跨零；"
    "不跨零 4 格；自助退化 1059 次（其中 k=0 的 2021—2025 段 1000/1000 无定义）<br>"
    "触发画像：k=1 共 392 信号日 / 42 簇；k=0 末次触发 2020-05-11；2021、2023 年 k=1 零触发"
    "</div>"
)
parts.append(
    "<div class=\"footer\">本报告为单文件离线 HTML：两张图片以 base64 内嵌，样式内联，"
    "无 CDN、无外部脚本、无网络请求。所有数字取自既有输出文件；解释性文字已按"
    "「数据 / 方法 / 判断」标记来源。生成脚本与本报告均未修改任何既有结果文件。</div>"
)

parts.append("</div></body></html>")

html_text = "\n".join(parts)
HTML_OUT.write_text(html_text, encoding="utf-8")

# stand-alone assertions
assert "<img src=\"data:image/png;base64," in html_text
assert "<img src=\"xy_" not in html_text
assert "src=\"http" not in html_text and "href=\"http" not in html_text
assert "<link" not in html_text and "<script" not in html_text
print(json.dumps({
    "output": str(HTML_OUT),
    "bytes": HTML_OUT.stat().st_size,
    "embedded_png_bytes": FIG_PNG.stat().st_size,
    "external_links": 0,
    "ic_h20_check": ic["horizon_ic"][3]["ic_pearson"],
    "point_biserial_check": ic["h20_binary_and_point_biserial"][1]["ic_point_biserial"],
}, ensure_ascii=False, indent=2))
