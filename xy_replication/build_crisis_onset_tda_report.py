"""Build a self-contained offline HTML report for the high-N / crisis-onset study.

READ-ONLY: this script only reads the four outputs produced by
crisis_onset_tda_study.py and embeds them verbatim.  It does not recompute,
resample, or modify any result file.
"""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
J = json.loads((OUT / "xy_crisis_onset_tda.json").read_text(encoding="utf-8"))
FIG = OUT / "xy_crisis_onset_tda.png"
SCRIPT = ROOT / "src" / "xy_replication" / "crisis_onset_tda_study.py"
EVENT_CSV = OUT / "xy_crisis_events.csv"
GRID_CSV = OUT / "xy_crisis_signal_grid.csv"
HTML_OUT = OUT / "xy_crisis_onset_tda_report.html"

raw_json = (OUT / "xy_crisis_onset_tda.json").read_text(encoding="utf-8")
event_csv = EVENT_CSV.read_text(encoding="utf-8-sig")
grid_csv = GRID_CSV.read_text(encoding="utf-8-sig")
script_src = SCRIPT.read_text(encoding="utf-8")
fig_b64 = base64.b64encode(FIG.read_bytes()).decode("ascii")


def esc(x) -> str:
    return html.escape(str(x), quote=False)


def f(v, d=4):
    if v is None:
        return "—"
    return f"{float(v):.{d}f}"


def pct(v, d=2, sign=True):
    if v is None:
        return "—"
    x = float(v) * 100
    return (f"{x:+.{d}f}%" if sign else f"{x:.{d}f}%")


def num(v, d=4):
    return "—" if v is None else f"{float(v):.{d}f}"


def yn(v):
    if v is None:
        return "—"
    return "是" if v else "否"


def ci(lo, hi, d=4, as_pct=False):
    if lo is None or hi is None:
        return "—"
    if as_pct:
        return f"[{pct(lo, d)}, {pct(hi, d)}]"
    return f"[{num(lo, d)}, {num(hi, d)}]"


def table(headers, rows, cls=""):
    h = "".join(f"<th>{x}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'


def p(text):
    return f"<p>{text}</p>"


RED, BLUE, GREY = "#B23A48", "#185FA5", "#66727D"
parts = []
A = parts.append

A("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>高 N 与危机前持续摘要：只读诊断报告</title>
<style>
:root{--bg:#fbfaf7;--card:#fff;--ink:#24282e;--muted:#6b737c;--line:#e3e1da;
--red:#B23A48;--blue:#185FA5;--green:#2E7D5B;--amber:#9A6700}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:"Microsoft YaHei","PingFang SC","Source Han Sans SC",system-ui,sans-serif;
line-height:1.75;font-size:15px}
.wrap{max-width:1180px;margin:0 auto;padding:32px 26px 90px}
header{border-bottom:3px solid var(--ink);padding-bottom:18px;margin-bottom:22px}
h1{font-size:27px;margin:0 0 8px;line-height:1.35}
.sub{color:var(--muted);font-size:14px}
h2{font-size:21px;margin:38px 0 14px;padding:7px 0 7px 12px;
border-left:5px solid var(--blue);background:linear-gradient(90deg,#eef3f9,transparent)}
h3{font-size:17px;margin:24px 0 9px;color:#1d3c5c}
h4{font-size:15px;margin:18px 0 6px}
p{margin:9px 0}
.pill{display:inline-block;padding:2px 9px;border-radius:11px;font-size:12px;
background:#eef3f9;color:#1d3c5c;margin-right:6px;border:1px solid #d6e2f0}
.pill.warn{background:#fdf1e8;color:#8a4b12;border-color:#f0d9c0}
.pill.bad{background:#fbecee;color:#8f2d3b;border-color:#efd0d5}
.lead{background:#fff;border:1px solid var(--line);border-left:5px solid var(--red);
border-radius:8px;padding:16px 18px;margin:16px 0}
.box{background:#fff;border:1px solid var(--line);border-radius:8px;padding:14px 18px;margin:14px 0}
.note{background:#f4f7fb;border:1px dashed #c9d8ea;border-radius:8px;padding:12px 16px;
color:#3c4b5c;font-size:14px;margin:12px 0}
.warnbox{background:#fff8f1;border:1px solid #f0d9bd;border-left:5px solid var(--amber);
border-radius:8px;padding:13px 17px;margin:14px 0}
.good{color:var(--green);font-weight:600}
.bad{color:var(--red);font-weight:600}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:13.2px;background:#fff}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f1f3f5;font-weight:600;white-space:nowrap}
tbody tr:nth-child(even){background:#fcfcfb}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.small{font-size:12.5px;color:var(--muted)}
.formula{background:#f6f7f9;border:1px solid var(--line);border-radius:7px;
padding:11px 15px;font-family:"Cambria Math",Georgia,serif;font-size:15px;margin:10px 0;overflow-x:auto}
.toc{background:#fff;border:1px solid var(--line);border-radius:8px;padding:14px 20px;
columns:2;column-gap:34px;font-size:14px}
.toc a{color:#1d3c5c;text-decoration:none;display:block;padding:2px 0}
.toc a:hover{text-decoration:underline}
details{background:#fff;border:1px solid var(--line);border-radius:8px;
padding:9px 14px;margin:9px 0}
summary{cursor:pointer;font-weight:600;color:#1d3c5c}
pre{background:#f7f8fa;border:1px solid var(--line);border-radius:6px;padding:12px;
overflow-x:auto;font-size:11.5px;line-height:1.5;max-height:520px;overflow-y:auto;
font-family:Consolas,"Courier New",monospace;white-space:pre}
code{font-family:Consolas,"Courier New",monospace;background:#f2f4f6;
padding:1px 4px;border-radius:3px;font-size:12.5px}
img{width:100%;border:1px solid var(--line);border-radius:8px;background:#fff}
.footer{margin-top:46px;border-top:1px solid var(--line);padding-top:14px;
color:var(--muted);font-size:12.5px}
ul,ol{margin:8px 0 8px 22px;padding:0}
li{margin:4px 0}
.kv{display:grid;grid-template-columns:190px 1fr;gap:5px 14px;font-size:14px}
.kv b{font-weight:600;color:#3c4b5c}
</style></head><body><div class="wrap">""")

A(f"""<header><h1>高 N 是否预示危机？危机前持续摘要有什么特征？</h1>
<div class="sub">兴业证券复现线 · 只读、样本内、探索性诊断 · 生成于 {esc(J['generated_on'])}</div>
<div style="margin-top:10px">
<span class="pill">单文件离线，无外链</span>
<span class="pill">16 个预登记信号全披露</span>
<span class="pill warn">危机标签使用未来 20 日价格，仅作事后标注</span>
<span class="pill bad">不是 Gate 1 结果</span>
</div></header>""")

A(f"""<div class="lead"><b>先回答两个问题，并纠正一个理解。</b><br><br>
<b>①「N 很低的时候有效」不成立。</b> 前几轮的低 N 结果只在<b>日级</b>成立，去重成 40 个独立事件后
IC 从 0.0913 塌到 <b>0.0131</b>、区间跨零、置换 p≈0.5；改看簇末日 IC 是 <b>−0.0058</b>。
日级那个 0.0913 主要是 319 个簇<b>中间日</b>重复计数撑起来的，不是择时能力。<br><br>
<b>② 高 N 不预示危机，方向甚至是反的。</b> 13 个高 N 信号里
<b>{J['interpretation']['n_high_N_signals_with_precision_lift_above_1']} 个</b>能让「危机标签日」富集
（precision lift 全部 &lt; 1）；唯一 p=0.02 的那格是触发率 23.5% 造成的机械高召回，
联合 max-T <b>p={num(J['joint_max_t_correction']['p_value'],3)}</b>、Bonferroni 单格阈值
<b>{num(J['joint_max_t_correction']['bonferroni_alpha_per_cell'],5)}</b>，不算发现。<br><br>
<b>③ 危机前的持续摘要没有稳定前兆。</b> 12 个拓扑/网络特征在危机起点前 20 日窗口的
标准化偏离，同年匹配置换后 <b>无一通过 Bonferroni</b>。真正与危机相关的是
<b>行业平均相关性 / 领先特征值占比</b>，但它们在危机<b>之后</b>才明显升高
（post−pre = {num(next(r for r in J['pre_vs_post_onset_contrast'] if r['feature']=='industry_average_correlation')['post_minus_pre'],3)}），
属于同步/滞后状态变量，<b>且不需要 TDA</b>。</div>""")

A("""<div class="toc">
<a href="#s0">0. 先纠正：「N 低有效」为什么不能这么理解</a>
<a href="#s1">1. 这次做了什么 / 没做什么</a>
<a href="#s2">2. 危机怎么定义（公式、符号表、前视警告）</a>
<a href="#s3">3. 样本漏斗与 17 个危机事件清单</a>
<a href="#s4">4. 高 N 预警能力：16 格全表</a>
<a href="#s5">5. 为什么「召回 0.938、p=0.02」不是发现</a>
<a href="#s6">6. 漂移如何伪装成预测能力</a>
<a href="#s7">7. N 相对简单相关性有没有增量</a>
<a href="#s8">8. 危机前的持续摘要路径</a>
<a href="#s9">9. 前兆还是同期：危机前 vs 危机后</a>
<a href="#s10">10. 能照着验算的例子</a>
<a href="#s11">11. 坑位清单</a>
<a href="#s12">12. 自测题</a>
<a href="#s13">13. 边界、来源标注与 Gate 状态</a>
<a href="#sa">附录 A：原始 JSON 全文</a>
<a href="#sb">附录 B：两份 CSV 全文</a>
<a href="#sc">附录 C：完整计算脚本</a>
<a href="#sd">附录 D：文件清单与复算命令</a>
</div>""")

# ---------------- 0 ----------------
A("<h2 id=\"s0\">0. 先纠正：「N 低有效」为什么不能这么理解</h2>")
A("""<p>你的原话是「所以 N 很低的时候是有效的」。这个结论<b>不能从已有结果推出</b>。
前几轮诊断里「低 N 看起来有效」只在一个特定口径下成立：把每一个信号<b>日</b>都当成独立观测。
一旦按真实事件去重，效应就消失了。</p>""")
corr_rows = [[esc(x)] for x in J["correction_of_prior_reading"]["evidence"]]
A(table(["已实测的证据（全部来自既有输出文件）"], corr_rows))
A(f"""<div class="box"><b>准确表述</b><p>{esc(J['correction_of_prior_reading']['accurate_statement'])}</p>
<p class="small">英文原文见附录 A 的 <code>correction_of_prior_reading</code>。
这不是「TDA 无效」的判决，只是说在这份本地重建面板上，<b>没有证据</b>表明低 N 的可交易触发时点
能稳定带来超额收益。</p></div>""")
A("""<div class="warnbox"><b>为什么这个纠正会影响你这次的两个新问题：</b>
如果低 N 真的有效，那自然的推论是「高 N 应该预示坏事情」。但既然低 N 的有效性本身主要由
重复计数与年份构成支撑，那么高 N 与危机之间看到的任何相关性，<b>第一嫌疑人也应该是同样的口径假象</b>。
本报告第 5、6 节就是专门拆这个的。</div>""")

# ---------------- 1 ----------------
A("<h2 id=\"s1\">1. 这次做了什么 / 没做什么</h2>")
A(f"""<div class="kv">
<b>性质</b><span>{esc(J['status'])}</span>
<b>只读</b><span>只读既有特征 CSV、万得全A 日线与本地指数库；<b>不修改任何既有输出文件</b></span>
<b>新增文件</b><span>1 个计算脚本、1 个报告脚本、1 份 JSON、2 份 CSV、1 张图、本报告</span>
<b>预登记</b><span>16 个二元信号 + 7 个连续评分，看结果前固定，<b>全披露、不按成绩反选</b></span>
<b>危机标签</b><span>借用 Gate 0 冻结口径，但基准换成兴业线用的万得全A；<b>不是 Gate 1 的封存标签</b></span>
<b>没有做</b><span>没有重跑策略、没有调阈值、没有读 Gate 1 的 2025 最终测试、没有启动 Gate 2</span>
</div>""")
A(f"""<div class="note"><b>关于「危机」这个词的口径风险：</b>项目在 Gate 0 里冻结过一个正式定义
（合成指数未来 20 日最低累计简单收益 ≤ −10%）。本报告主口径沿用<b>同样的阈值与窗口</b>，
但把基准换成万得全A 881001.WI，因为整条兴业复现线此前所有 IC、事件、收益都用这个基准，
换基准会破坏可比性。另给一个按<b>冻结合成指数</b>的敏感性对照（数据截断到 2024-12-31，
并遵守 <code>label_end(t) &lt; 2025-01-01</code>），全程<b>不读取任何 2025 测试行</b>。</div>""")

# ---------------- 2 ----------------
A("<h2 id=\"s2\">2. 危机怎么定义（公式、符号表、前视警告）</h2>")
A("""<h3>2.1 符号表</h3>""")
A(table(["符号", "含义"], [
    ["<code>P_t</code>", "t 日万得全A <b>收盘价</b>（881001.WI）"],
    ["<code>N_t</code>", "t 日 H₂ 有限持久区间数（本项目对兴业 N 的主解释）"],
    ["<code>Y_t</code>", "危机标签；1 = 未来 20 个交易日内出现 ≤ −10% 的累计回撤"],
    ["<code>e</code>", "危机事件起点 = 连续 Y=1 段的第一天"],
    ["<code>L</code>", "提前窗口长度（5 / 10 / 20 交易日），信号必须落在 [e−L, e−1]"],
    ["<code>ρ_t</code>", "N 的因果滚动 midrank 分位，只用 [t−W+1, t] 历史"],
    ["<code>AP</code>", "average precision = 阶梯式 PR-AUC；基线是危机发生率 prevalence"],
    ["<code>z</code>", "特征相对报告期全样本均值的标准化偏离 (x−μ)/σ"],
]))
A("<h3>2.2 标签公式</h3>")
A("""<div class="formula">Y<sub>t</sub> = 1 ⇔ min<sub>j=1..20</sub> ( P<sub>t+j</sub> / P<sub>t</sub> − 1 ) ≤ −10%
<br>ρ<sub>t</sub> = ( #{N<sub>s</sub> &lt; N<sub>t</sub>} + 0.5·#{N<sub>s</sub> = N<sub>t</sub>} ) / W ,  s ∈ [t−W+1, t]</div>""")
A(f"""<p>注意标签取的是 20 日窗口内<b>路径最低点</b>，不是 20 日后的终点收益。
所以一个 Y=1 的日子，20 日后完全可能已经反弹收正——报告第 10 节的 2024-01-25 就是实例
（最低 −12.17%，但 20 日 open-to-open 是 {pct(next(r for r in J['hand_worked_examples'] if r['date']=='2024-01-25')['forward20_open_to_open'],2)}）。
这也解释了为什么 <code>IC(N, r₂₀) = {num(next(r for r in J['N_vs_forward_return_ic'] if r['horizon_days']==20)['ic_N_vs_forward_return'],4)}</code>
与「N 和 Y 的关系」不必同号。</p>""")
A("""<div class="warnbox"><b>⚠️ 前视警告（最重要的一条）</b><p><code>Y_t</code> 是用
<b>未来 20 日价格</b>算出来的，因此它只能是<b>事后标注</b>，绝不能当成 t 日可观测、可交易的信号。
本报告的做法是把 t 日<b>当时可得</b>的拓扑特征当作信号，只评价它是否落在
危机起点的<b>提前窗口 [e−L, e−1]</b> 内，或是否与 Y 富集。这是「预警能力」的描述性评估，
不是回测绩效，也不是可部署系统的证明。</p></div>""")
A(f"""<h3>2.3 三个口径敏感性</h3>""")
cd = J["crisis_definition"]
A(table(["口径", "数值"], [
    ["主：万得全A，−10% / 20 日", f"prevalence = <b>{num(J['data']['prevalence'],5)}</b>（{J['data']['valid_labeled_days']} 个可判定日）"],
    ["阈值 −5%", f"prevalence = {num(cd['sensitivity_prevalence']['-5%'],5)}"],
    ["阈值 −15%", f"prevalence = {num(cd['sensitivity_prevalence']['-15%'],5)}"],
    ["冻结合成指数，−10% / 20 日（≤2024-12-31）",
     f"prevalence = {num(cd['frozen_composite_prevalence'],5)}，{cd['frozen_composite_n_valid']} 个可判定日"],
]))
A(f"""<p class="small">合成指数定义：<code>I_t = I_(t−1)·(1 + 0.5·(r_000001,t + r_399001,t))</code>，
只取两指数共同交易日。该敏感性仅用于确认「结论不依赖某一条指数」，
由于样本期短了约 5 个月，<b>不做严格对照</b>。</p>""")

# ---------------- 3 ----------------
A("<h2 id=\"s3\">3. 样本漏斗与 17 个危机事件清单</h2>")
d = J["data"]
A(table(["阶段", "天数", "说明"], [
    ["特征文件全部行", "3339", "2012-12-31 ～ 2026-11-03"],
    ["截断到基准末日 2025-05-30", str(d["feature_rows_used"]), f"特征日历 {d['first_date']} ～ {d['last_date']}"],
    ["报告期 2015-07-01 ～ 2025-05-30", str(d["report_days"]), "与兴业原报告期一致"],
    ["标签可判定", str(d["valid_labeled_days"]), f"尾部不足 20 日者 {d['undecided_tail_days']} 天记「未定」，不当负例"],
    ["<b>危机标签日 Y=1</b>", str(round(d["prevalence"] * d["valid_labeled_days"])),
     f"prevalence = {num(d['prevalence'],5)}"],
]))
A(f"""<div class="note">{esc(d['calendar_note'])} 本报告沿用特征日历，
与前几轮 IC / 事件 / 簇末日诊断严格可比。</div>""")
A(f"""<p><b>事件规则</b>：连续 Y=1 的日合并；间隔 &gt; 20
个<b>日历日</b>才算新事件。共 {J['event_definition']['n_raw_events']} 段，
其中 <b>{J['event_definition']['n_usable_events']}</b> 段进入事件级统计；
被排除的是 {', '.join(J['event_definition']['left_censored_events'])}
——{esc(J['event_definition']['left_censor_note'])}</p>""")
ev_rows = []
for r in J["crisis_events"]:
    ev_rows.append([
        str(r["event_id"]), r["onset"], r["end"], str(r["label_run_days"]),
        r["label_end_date"] or "—",
        pct(r["worst_cumulative_return_from_onset"], 2),
        r["worst_date"] or "—", str(r["N_at_onset"]),
        num(r["avg_corr_at_onset"], 3),
        "<span class='bad'>左截尾·排除</span>" if r["left_censored_label"] else "纳入",
    ])
A(table(["#", "起点 e", "Y=1 段末", "段长(交易日)", "标签终点", "起点起最差累计收益",
         "最差日", "N 在 e", "平均相关在 e", "状态"], ev_rows))
A(f"""<p><b>直接可见的一件事</b>：16 个可用危机的 <code>N_at_onset</code> 从
{min(r['N_at_onset'] for r in J['crisis_events'] if not r['left_censored_label'])}
到 {max(r['N_at_onset'] for r in J['crisis_events'] if not r['left_censored_label'])}，
散布很宽，没有任何「高 N 才开始危机」的视觉规律；2015-07-01 那次 N=0，
2025-03-07 那次 N=29。<b>危机本身的 N 水平被长期漂移完全盖住。</b></p>""")

# ---------------- 4 ----------------
A("<h2 id=\"s4\">4. 高 N 预警能力：16 格全表</h2>")
pr = J["preregistration"]
A(f"""<p>预登记（看结果前固定）的信号族：</p>
<ul>
<li><b>固定高阈值</b>：N ≥ 15 / 20 / 25 / 30（4 格）——检验「绝对孔洞多」</li>
<li><b>因果滚动高分位</b>：ρ<sub>t</sub> ≥ 0.80 / 0.90 / 0.95，W = 60 / 120 / 250（9 格）
——检验「相对近期偏高」，语义已不同于兴业原文</li>
<li><b>对照</b>：低 N ≤ 1（兴业规则）、平均相关 ≥ P90、领先特征值 ≥ P90（3 格，非 TDA 基线）</li>
</ul>
<p class="small">共 {pr['n_binary_signals']} 个二元信号、{pr['n_continuous_scores']} 个连续评分；
提前窗口 {pr['lead_windows_trading_days']} 交易日；主统计量为 L=20 的事件提前召回与
precision P(Y=1|s=1)。两项置换零分布各 {pr['permutations']} 次：全局循环平移、
<b>同年循环平移</b>（后者控制 N 漂移，是更严格的判据）。区块自助
{pr['bootstrap']['block_days']} 日 / {pr['bootstrap']['repetitions']} 次 / seed {pr['bootstrap']['seed']}。</p>""")
grid_rows = []
for r in J["signal_grid"]:
    fam = {"fixed_high_N": "固定高 N", "causal_rolling_high_quantile": "滚动高分位",
           "control_low_N": "对照·低 N", "control_non_tda": "对照·非 TDA"}[r["family"]]
    lift = r["lift_vs_prevalence"]
    lift_disp = (f"<span class='bad'>{num(lift,3)}</span>" if lift is not None and lift < 1
                 else f"<span class='good'>{num(lift,3)}</span>" if lift is not None else "—")
    grid_rows.append([
        r["signal"].replace("fixed_N_ge_", "fixed N≥").replace("roll_N_", "roll "),
        fam, num(r["trigger_share_valid"], 3),
        num(r["precision"], 4), lift_disp,
        ci(r["ci95_precision"][0], r["ci95_precision"][1], 3),
        num(r["event_lead_recall_L20"], 3),
        num(r["false_alarm_clusters_per_year"], 2),
        num(r["perm_same_year_p_recall_greater"], 3),
    ])
A(table(["信号", "族", "触发率", "P(Y=1│s=1)", "lift", "95% 自助区间",
         "事件召回 L20", "误报簇/年", "同年匹配 p"], grid_rows))
A(f"""<div class="lead"><b>主结果：{J['interpretation']['n_high_N_signals_with_precision_lift_above_1']} / 13
个高 N 信号的 precision lift &gt; 1。</b>
基线 prevalence = {num(J['data']['prevalence'],4)}；固定 N≥20 的 precision 只有
{num(next(r for r in J['signal_grid'] if r['signal']=='fixed_N_ge_20')['precision'],4)}
（lift {num(next(r for r in J['signal_grid'] if r['signal']=='fixed_N_ge_20')['lift_vs_prevalence'],3)}），
N≥30 更是 <b>0</b>。也就是说<b>在这份重建面板上，N 越高的日子反而越不容易是「未来 20 日内 −10% 回撤」的日子</b>，
与「高 N 预示危机」的直觉相反。</div>""")
A(f"""<p>连续评分的 PR-AUC（AP）同样说明问题：</p>""")
A(table(["评分", "AP (阶梯 PR-AUC)", "相对 prevalence 的 lift", "与未来 20 日收益的 IC"],
        [[r["score"].replace("score_", ""), num(r["average_precision_prauc"], 4),
          num(r["prauc_lift_vs_prevalence"], 3), num(r["ic_vs_forward20_return"], 4)]
         for r in J["continuous_scores"]]))
A(f"""<p>原始 N 的 AP = {num(next(r for r in J['continuous_scores'] if r['score']=='score_N')['average_precision_prauc'],4)}
<b>低于</b>基线；因果滚动分位 ρ 的 AP =
{num(next(r for r in J['continuous_scores'] if r['score']=='score_roll_rho_W120')['average_precision_prauc'],4)}
≈ 基线（无判别力）；只有 <code>−N</code> 的 AP 高（
{num(next(r for r in J['continuous_scores'] if r['score']=='score_minus_N')['average_precision_prauc'],4)}），
但第 6 节会证明<b>那完全是年份构成造成的假象</b>。</p>""")
A("<h3>4.1 N 与未来收益的 IC（全部跨零）</h3>")
A(table(["h (交易日)", "n", "Pearson IC(N, r_h)", "95% 区块自助区间", "跨零"],
        [[str(r["horizon_days"]), str(r["n"]), num(r["ic_N_vs_forward_return"], 4),
          ci(r["ci95_ic"][0], r["ci95_ic"][1], 4), yn(r["crosses_zero"])]
         for r in J["N_vs_forward_return_ic"]]))
A(f"""<p class="small">h=20 的 IC = {num(next(r for r in J['N_vs_forward_return_ic'] if r['horizon_days']==20)['ic_N_vs_forward_return'],8)}
，与前几轮 <code>−N</code> 的 +0.06629164399006625 <b>逐位对称</b>，可作为口径一致性校验。
五个区间全部跨零，含义见此前「跨零」说明：不排除真实 IC 为 0。</p>""")

# ---------------- 5 ----------------
A("<h2 id=\"s5\">5. 为什么「召回 0.938、p=0.02」不是发现</h2>")
top = J["interpretation"]["top_cell_recall_vs_iid_expectation"]
r80 = next(r for r in J["signal_grid"] if r["signal"] == "roll_N_W120_p80")
A(f"""<p>16 格里唯一同年匹配 p &lt; 0.05 的是 <code>roll_N_W120_p80</code>
（p = {num(r80['perm_same_year_p_recall_greater'],3)}，事件召回 {num(r80['event_lead_recall_L20'],3)}）。
看上去很像「找到了」，但四个检验都指向否：</p>""")
A(table(["检验", "数值", "怎么读"], [
    ["触发率", f"{pct(r80['trigger_share_valid'],1,sign=False)}",
     "每 4 天多就触发一次，20 日窗口里几乎必然有信号"],
    ["独立随机信号的期望召回 <code>1−(1−q)²⁰</code>",
     f"<b>{num(top['iid_expectation'],4)}</b>",
     f"实际 {num(top['actual'],4)} <b>还低于</b>随机期望；高召回是触发率的机械结果"],
    ["同年循环平移的召回零均值", f"{num(r80['null_same_year_recall_mean'],3)}",
     "保留簇结构的 null 本身就有 0.718 召回"],
    ["precision / lift", f"{num(r80['precision'],4)} / {num(r80['lift_vs_prevalence'],3)}",
     f"<b>低于</b>基线 {num(J['data']['prevalence'],4)}：它并不富集危机日"],
    ["precision 95% 区间", ci(r80["ci95_precision"][0], r80["ci95_precision"][1], 3),
     "包含基线；同年匹配 precision p = " + num(r80["perm_same_year_p_precision_greater"], 3)],
    ["误报", f"{num(r80['false_alarm_clusters_per_year'],2)} 簇/年",
     "低误报目标下不可接受"],
    ["<b>联合 max-T</b>", f"<b>p = {num(J['joint_max_t_correction']['p_value'],3)}</b>",
     f"{J['joint_max_t_correction']['n_tests']} 格同时检验，观测 max-T = {num(J['joint_max_t_correction']['observed_max_T'],3)}"],
    ["Bonferroni 单格阈值", f"α = {num(J['joint_max_t_correction']['bonferroni_alpha_per_cell'],5)}",
     f"最小单格 p = {num(J['joint_max_t_correction']['smallest_single_cell_same_year_p'],3)}，远不够"],
]))
A(f"""<div class="warnbox"><b>联合检验怎么做的：</b>
{esc(J['joint_max_t_correction']['method'])}。每一轮置换对<b>所有 16 个信号使用同一组年份平移量</b>，
先算每格的标准化召回 <code>(recall−null_mean)/null_sd</code>，再取 16 格最大值 T；
用 T 的置换分布来校正「挑最小 p」的选择效应。观测 T =
{num(J['joint_max_t_correction']['observed_max_T'],3)}，null 的 T 均值 =
{num(J['joint_max_t_correction']['permutation_null_max_T_mean'],3)}，
p = {num(J['joint_max_t_correction']['p_value'],3)}。
<br><span class="small">局限：{esc(J['joint_max_t_correction']['limitation'])}</span></div>""")
A(f"""<p>另有 {num(J['interpretation']['expected_false_positives_main_recall_test_at_5pct'],2)}
格在 5% 水平下纯随机也期望「显著」；实测 1 格，<b>与随机相符</b>。
第 4 节表里其余 15 格的同年匹配 p 都在
{num(min(r['perm_same_year_p_recall_greater'] for r in J['signal_grid'] if r['signal']!='roll_N_W120_p80'),3)}
以上。</p>""")

# ---------------- 6 ----------------
A("<h2 id=\"s6\">6. 漂移如何伪装成预测能力</h2>")
A(f"""<p>这是整份报告<b>最需要警惕</b>的一节。全样本上 <code>−N</code> 的 AP =
{num(next(r for r in J['continuous_scores'] if r['score']=='score_minus_N')['average_precision_prauc'],4)}
，相对 prevalence 的 lift =
{num(next(r for r in J['continuous_scores'] if r['score']=='score_minus_N')['prauc_lift_vs_prevalence'],3)}
——如果只看这个数，会得出「低 N 预示危机」的结论，甚至反过来当成对第 0 节纠正的推翻。
但把它按时间切开就露馅了：</p>""")
seg_rows = []
for r in J["segment_average_precision"]:
    seg_rows.append([
        r["segment"], str(r["n_days"]), num(r["prevalence"], 4),
        num(r["AP_score_minus_N"], 4), f"<b>{num(r['AP_score_minus_N']/r['prevalence'],3)}</b>",
        num(r["AP_score_avg_corr"], 4), num(r["AP_score_avg_corr"]/r["prevalence"], 3),
        num(r["AP_score_roll_rho_W120"], 4),
    ])
A(table(["区间", "n", "prevalence", "AP(−N)", "−N lift", "AP(平均相关)", "相关 lift", "AP(滚动 ρ)"], seg_rows))
A(f"""<div class="lead"><code>−N</code> 的 lift 从 <b>2015—2020 的
{num(next(r for r in J['segment_average_precision'] if r['segment']=='2015-2020')['AP_score_minus_N']/next(r for r in J['segment_average_precision'] if r['segment']=='2015-2020')['prevalence'],3)}</b>
塌到 <b>2021—2025 的
{num(next(r for r in J['segment_average_precision'] if r['segment']=='2021-2025')['AP_score_minus_N']/next(r for r in J['segment_average_precision'] if r['segment']=='2021-2025')['prevalence'],3)}</b>（≈随机）；
而因果滚动分位 ρ 的 AP 在两段都≈基线。
<b>全样本那个 1.62 倍 lift 不是低 N 有信息，而是「危机多的年份恰好 N 低、N 高的年份恰好危机少」的年份构成效应。</b></div>""")
A("<h3>6.1 分年审计</h3>")
A(table(["年", "可判定日", "Y=1 占比", "N 均值", "N 中位", "ρ(W120) 均值", "corr(N, Y)"],
        [[str(r["year"]), str(r["n_days"]), num(r["crisis_label_share"], 3),
          num(r["mean_N"], 2), num(r["median_N"], 1), num(r["mean_roll_rho_N_W120"], 3),
          num(r["corr_N_vs_crisis_label"], 3)]
         for r in J["by_year_audit"]]))
A(f"""<p>2015 年危机标签占 <b>{num(next(r for r in J['by_year_audit'] if r['year']==2015)['crisis_label_share'],3)}</b>
而 N 均值只有 {num(next(r for r in J['by_year_audit'] if r['year']==2015)['mean_N'],1)}；
2021 年 N 均值 {num(next(r for r in J['by_year_audit'] if r['year']==2021)['mean_N'],1)}
而危机占比 {num(next(r for r in J['by_year_audit'] if r['year']==2021)['crisis_label_share'],3)}。
年内 <code>corr(N,Y)</code> 的符号在 −0.237 ～ +0.55 之间来回变，
<b>没有任何稳定的年内方向</b>。这与上一轮已经固化的结论一致：
N 的抬升不是节点数驱动，而是分布整体位移，固定阈值不可移植。</p>""")

# ---------------- 7 ----------------
A("<h2 id=\"s7\">7. N 相对简单相关性有没有增量</h2>")
inc = J["incremental_value_of_N_beyond_correlation"]
A(f"""<p>既然「行业平均相关性」在两段都有 lift，就要问：<b>加拓扑有没有多给信息？</b>
（这是本项目真正关心的创新点检验。）</p>""")
A(table(["评分 / 分组", "AP 或危机率", "相对基线"], [
    ["<code>AP(平均相关)</code>", num(inc["AP_avg_corr_full"], 4),
     f"lift {num(inc['AP_avg_corr_full']/J['data']['prevalence'],3)}"],
    ["<code>AP(−N)</code>", num(inc["AP_minus_N_full"], 4),
     f"lift {num(inc['AP_minus_N_full']/J['data']['prevalence'],3)}（第 6 节已证伪为漂移）"],
    ["<code>AP(z(相关) + z(N))</code>", num(inc["AP_avg_corr_plus_N_z"], 4), "<span class='bad'>低于相关单独</span>"],
    ["<code>AP(z(相关) − z(N))</code>", num(inc["AP_avg_corr_minus_N_z"], 4), "<span class='bad'>低于相关单独</span>"],
    ["高相关子样本内 <code>AP(N)</code>", num(inc["AP_N_within_corr_high"], 4),
     f"该子样本 prevalence {num(inc['prevalence_within_corr_high'],4)}"],
]))
A(f"""<div class="note">两个符号方向的组合评分<b>都披露</b>，且都<b>没有跑赢</b>单独的平均相关
（{num(inc['AP_avg_corr_full'],4)}）。方向本身未预登记，所以这一节只作探索性增量检查，
<b>不能据此宣称「N 有反向增量」</b>——{esc(inc['direction_caveat'])}。</div>""")
A("<h3>7.1 高相关日子里的 2×2 分层</h3>")
A(table(["条件", "天数", "P(Y=1)"], [
    [f"平均相关 ≥ P90 ({num(inc['corr_p90_threshold'],3)}) 且 N ≥ 子样本中位 ({num(inc['median_N_within_corr_high'],0)})",
     str(inc["n_corr_high_N_high"]), num(inc["P_crisis_given_corr_high_and_N_high"], 4)],
    ["平均相关 ≥ P90 且 N &lt; 中位", str(inc["n_corr_high_N_low"]),
     num(inc["P_crisis_given_corr_high_and_N_low"], 4)],
    ["<b>差值（高 N − 低 N）</b>", "—", f"<b>{pct(inc['difference_highN_minus_lowN'],2)}</b>"],
    ["同年匹配置换 p（双侧）", "—", f"<b>{num(inc['same_year_permutation_p_two_sided'],3)}</b> → 不显著"],
]))
A(f"""<p class="small">注意这里 N 的方向<b>与全样本相反</b>（高 N 组危机率更高 4.80 pct），
这是又一个 Simpson 型翻转，加上 p={num(inc['same_year_permutation_p_two_sided'],3)}，
只能说明「不稳定」，不能当结论。</p>""")

# ---------------- 8 ----------------
A("<h2 id=\"s8\">8. 危机前的持续摘要路径</h2>")
A(f"""<p><b>做法</b>：以 16 个可用危机事件起点 e 为锚点，取 9 个相对时点
（−40 / −30 / −20 / −10 / −5 / 0 / +5 / +10 / +20 交易日），
把每个特征转成报告期全样本的 z 分数，跨事件等权平均；区间用<b>事件级</b> iid 自助
（10 000 次）给，显著性用<b>同年匹配</b>置换（每个真实事件在其同一年内随机抽一个伪起点，
2 000 轮）——后者专门控制第 6 节的年份构成效应。</p>""")
A(f"""<p>主判据是窗口 j ∈ {J['path_window_offsets']} 的每事件均值，再跨事件平均，
12 个特征做 Bonferroni（α = {num(0.05/12,5)}）。</p>""")
ps_rows = []
for r in J["persistence_path_summary"]:
    rel = r["midrank_percentile_reliable"]
    ps_rows.append([
        r["feature"].replace("h2_count", "h2_count (N)"),
        "—" if r["zero_tie_fraction_in_report_period"] is None
        else num(r["zero_tie_fraction_in_report_period"], 3),
        num(r["actual_mean_z_or_fraction_in_window"], 4),
        num(r["same_year_null_mean"], 4),
        num(r["same_year_p_two_sided"], 3),
        yn(r["significant_after_bonferroni_12"]),
        (num(r["actual_mean_midrank_percentile"], 3)
         if rel else f"<span class='bad'>{num(r['actual_mean_midrank_percentile'],3)}（失真）</span>")
        if r["actual_mean_midrank_percentile"] is not None else "—",
    ])
A(table(["特征", "零值占比", "窗口实际均值 z", "同年匹配 null", "p(双侧)", "Bonferroni 后显著", "midrank 分位"], ps_rows))
A(f"""<div class="lead"><b>12 个特征无一显著（Bonferroni 后）。</b>
所有 H₁/H₂ 计数、景观 L¹、最大持续性在危机前的 z 都是<b>轻微偏低</b>
（−0.02 ～ −0.20），但同年匹配 null 也偏低，两者差值都在噪声内
（最小 p = {num(min(r['same_year_p_two_sided'] for r in J['persistence_path_summary'] if r['same_year_p_two_sided'] is not None),3)}）。
换句话说：<b>「危机前 N 会升高」不成立，「危机前 N 会降低」也不成立。</b></div>""")
A("""<div class="warnbox"><b>Betti 分位失真：</b>
<code>h2_betti_0p4 / 0p6 / 0p8</code> 在报告期有极大量 0 值（见「零值占比」列），
midrank 分位会把所有 0 挤到同一个高分位，出现 0.98 / 0.95 / 0.89 这种<b>假象</b>。
这三列的分位数值不可用，请以 z 分数列为准（分别在 −0.024 / −0.118 / +0.127，全部无差异）。</div>""")
A("<h3>8.1 完整事件时间路径（z 均值）</h3>")
offs = [-40, -30, -20, -10, -5, 0, 5, 10, 20]
path_rows = []
for key in list(J["persistence_path"].keys()):
    row = [key.replace("h2_count", "h2_count (N)")]
    for o in offs:
        v = J["persistence_path"][key][str(o)]["mean"]
        row.append(num(v, 3))
    path_rows.append(row)
A(table(["特征"] + [f"j={o}" for o in offs], path_rows))
A(f"""<p><b>读图要点</b>：N（h2_count）在 j=−20 为
{num(J['persistence_path']['h2_count']['-20']['mean'],3)}，j=0 回到
{num(J['persistence_path']['h2_count']['0']['mean'],3)}，看不出「提前升高」；
平均相关在 j=−20 是 {num(J['persistence_path']['industry_average_correlation']['-20']['mean'],3)}，
到 j=+20 跳到 <b>{num(J['persistence_path']['industry_average_correlation']['20']['mean'],3)}</b>
——上升发生在<b>危机之后</b>，见第 9 节。</p>""")
A(f"""<div class="box"><img src="data:image/png;base64,{fig_b64}" alt="四面板诊断图">
<p class="small">(a) N 与危机标签阴影、高 N 日；(b) 16 格信号的「召回 vs 误报」；
(c) 危机前后特征 z 路径；(d) N 在 [−20,0] 窗口的观测值 vs 同年匹配零分布。</p></div>""")

# ---------------- 9 ----------------
A("<h2 id=\"s9\">9. 前兆还是同期：危机前 vs 危机后</h2>")
A("""<p>一个特征要算「预警」，必须在危机<b>之前</b>就偏离；如果只在危机<b>之后</b>升高，
它就是同步或滞后确认变量，对预警系统没有提前量。下表比较
pre = j∈{−20,−10} 的均值、post = j∈{+10,+20} 的均值，差值同样用同年匹配置换检验。</p>""")
A(table(["特征", "危机前 z", "危机后 z", "post − pre", "同年匹配 null", "p(双侧)"],
        [[r["feature"].replace("h2_count", "h2_count (N)"),
          num(r["mean_z_at_j_minus20_minus10"], 3),
          num(r["mean_z_at_j_plus10_plus20"], 3),
          num(r["post_minus_pre"], 3),
          num(r["same_year_null_post_minus_pre"], 3),
          num(r["same_year_p_two_sided"], 3)]
         for r in J["pre_vs_post_onset_contrast"]]))
A(f"""<div class="lead">唯一方向一致且接近边缘的是<b>非 TDA 的两个相关性变量</b>：
平均相关 post−pre = <b>+{num(next(r for r in J['pre_vs_post_onset_contrast'] if r['feature']=='industry_average_correlation')['post_minus_pre'],3)}</b>
（p={num(next(r for r in J['pre_vs_post_onset_contrast'] if r['feature']=='industry_average_correlation')['same_year_p_two_sided'],3)}）、
领先特征值占比 +{num(next(r for r in J['pre_vs_post_onset_contrast'] if r['feature']=='correlation_leading_eigenvalue_share')['post_minus_pre'],3)}
（p={num(next(r for r in J['pre_vs_post_onset_contrast'] if r['feature']=='correlation_leading_eigenvalue_share')['same_year_p_two_sided'],3)}）。
12 个特征同时检验，Bonferroni α={num(0.05/12,5)}，<b>两者都不显著</b>；
且方向明确指向「危机中/危机后市场同步化」，<b>是状态确认而非提前预警</b>。
所有 H₁/H₂ 拓扑特征的 post−pre 都在 ±0.25 内、p ≥ 0.19。</div>""")
A(f"""<p>这也解释了第 4 节里 <code>avg_corr_ge_p90</code> / <code>leading_eig_ge_p90</code>
的 precision 高达 {num(next(r for r in J['signal_grid'] if r['signal']=='avg_corr_ge_p90')['precision'],4)}
（lift {num(next(r for r in J['signal_grid'] if r['signal']=='avg_corr_ge_p90')['lift_vs_prevalence'],2)}）：
它们触发时往往<b>危机已经发生</b>，所以事件提前召回只有
{num(next(r for r in J['signal_grid'] if r['signal']=='avg_corr_ge_p90')['event_lead_recall_L20'],3)}，
同年匹配 precision p =
{num(next(r for r in J['signal_grid'] if r['signal']=='avg_corr_ge_p90')['perm_same_year_p_precision_greater'],3)}。
<b>高精确率 ≠ 能提前报警</b>，而且这两个阈值用了全报告期 P90，本身含未来信息。</p>""")

# ---------------- 10 ----------------
A("<h2 id=\"s10\">10. 能照着验算的例子</h2>")
A("<h3>10.1 五个真实危机日的标签手算</h3>")
A(table(["t", "收盘 P_t", "N_t", "20 日内最差日", "最差收盘", "最差累计收益", "Y_t", "平均相关", "t+1 开盘", "20 日 open→open"],
        [[r["date"], num(r["close_t"], 2), str(r["N_t"]), r["worst_date"],
          num(r["worst_close"], 2), pct(r["worst_cumulative_return"], 2),
          str(r["Y_t"]), num(r["avg_corr"], 3), num(r["open_t_plus_1"], 2),
          pct(r["forward20_open_to_open"], 2)]
         for r in J["hand_worked_examples"]]))
A("""<p>例如 2018-05-21：P_t = 4385.56，未来 20 日最低收盘是 2018-06-19 的 3882.98，
累计收益 = 3882.98/4385.56 − 1 = <b>−11.4599%</b> ≤ −10%，故 Y_t = 1。
再如 <b>2024-01-25</b>：最低累计 −12.17% 使 Y_t = 1，但 20 日后 open→open 已是
<b>+3.27%</b> —— <b>标签看路径最低点，IC 看终点收益，两者不必一致</b>。</p>""")
rho = J["rolling_midrank_example"]
A("<h3>10.2 因果滚动分位手算</h3>")
A(f"""<div class="formula">t = {rho['date']}，N_t = {rho['N']}，W = {rho['W']}，
窗口内 min={rho['window_min']}、max={rho['window_max']}、中位={rho['window_median']}；
less = {rho['less']}，equal = {rho['equal']}
<br>ρ_t = ({rho['less']} + 0.5×{rho['equal']}) / {rho['W']} = <b>{num(rho['rho'],6)}</b>
≥ 0.90 ⇒ 触发（{rho['triggers_p90']}）</div>""")
A(f"""<p class="small">0.5·equal 项是为了处理整数并列：N 是整数，若不用 midrank，
大量相同值会让「低于阈值」的触发率失真。窗口只含 ≤ t 的历史，<b>无前视</b>；
但语义已变成「相对近 120 日偏高」，<b>不再是兴业原文的绝对低孔洞状态</b>。</p>""")

# ---------------- 11 ----------------
A("<h2 id=\"s11\">11. 坑位清单</h2>")
A("""<ol>
<li><b>标签前视</b>：Y_t 用未来 20 日价格定义，只能事后标注；任何「命中率」都不是可交易绩效。</li>
<li><b>路径最低点 ≠ 终点收益</b>：Y=1 与 IC 方向可以不一致（2024-01-25 实例）。</li>
<li><b>漂移伪装</b>：N 中位 3→14、P(N≤1) 28.16%→1.26%；全样本 −N 的 1.62× lift
在 2021—2025 段塌到 0.966×，是年份构成效应。</li>
<li><b>高触发率 → 高召回</b>：q=23.5% 时独立随机信号的 20 日窗口期望召回已达 0.995；
不要只看召回，必须同时看 precision / lift / 误报。</li>
<li><b>多重比较</b>：16 格主检验期望 0.8 格假阳性；单格 p=0.02 需联合 max-T（p=0.144）与
Bonferroni（0.003125）双重校正。</li>
<li><b>同期 ≠ 前兆</b>：平均相关在危机后才跳升，precision 高但提前召回仅 0.25。</li>
<li><b>全样本分位泄漏</b>：avg_corr / leading_eig 的 P90 阈值用了整段报告期，含未来信息；
只有 ρ_t 是严格因果的。</li>
<li><b>Betti 分位失真</b>：大量 0 值使 midrank 分位虚高，必须看 z 分数。</li>
<li><b>左截尾</b>：2015-07-01 是报告期首日且已 Y=1，其危机前窗口不在有标签区间内，已排除。</li>
<li><b>日历差异</b>：特征日历 2994 天 vs Wind 3012 天（18 天差）；既有审计显示换完整日历
20 日 IC 从 0.06629 → 0.06678，不改变结论，但跨研究比较要写清。</li>
<li><b>事件重叠</b>：危机段最长 34 个交易日、事件起点部分相隔不足 40 日，
事件时间路径的观测并不完全独立；区间用事件级自助而非日级 t 检验。</li>
<li><b>置换零分布的局限</b>：循环平移保留年内自相关，但打散了信号簇与危机起点的精确对齐，
是描述性 null，不是形式化因果检验。</li>
</ol>""")

# ---------------- 12 ----------------
A("<h2 id=\"s12\">12. 自测题</h2>")
A("""<details><summary>展开：5 道题与答案</summary><ol>
<li>某信号 precision = 0.0844、prevalence = 0.0983，能说它「富集危机」吗？
<br><b>不能</b>，lift=0.859&lt;1，反而低于随机。</li>
<li>某信号事件召回 0.938、同年匹配 p=0.02，能宣布发现吗？
<br><b>不能</b>：触发率 23.5% 使随机期望召回 0.995；联合 max-T p=0.144；Bonferroni α=0.003125。</li>
<li>全样本 −N 的 PR-AUC lift=1.62，是否推翻第 0 节的纠正？
<br><b>不推翻</b>：2015—2020 为 1.59×、2021—2025 为 0.97×，是年份构成效应；且这是危机标签而非收益。</li>
<li>危机前平均相关 z=+0.158，能说「相关性升高预示危机」吗？
<br><b>不能</b>：同年匹配 null 为 +0.168、p=0.954；真正升高发生在危机后（post−pre=+0.342，p=0.061，未过 Bonferroni）。</li>
<li>「高 N 不预示危机」等于「TDA 无效」吗？
<br><b>不等于</b>。这只说明在这份本地重建面板、这个标签定义、这 16 个预登记规则下没有证据；
N 的精确定义、兴业逐日行业名单与万得四级分类仍未取得。</li>
</ol></details>""")

# ---------------- 13 ----------------
A("<h2 id=\"s13\">13. 边界、来源标注与 Gate 状态</h2>")
A(f"""<div class="kv">
<b>结论性质</b><span>{esc(J['status'])}</span>
<b>不构成</b><span>「TDA 无效」的判决、兴业原文有误的判决、可部署系统的有效性证据</span>
<b>仍未取得</b><span>N 的精确定义、兴业 Wind 逐日行业名单与收益细节、万得四级行业分类及行情</span>
<b>仍未计算</b><span>确认性修正版策略绩效</span>
<b>Gate 状态</b><span><b>Gate 1 仍暂停；2025 最终测试未读取；Gate 2 未启动。</b>
<span class="small">（原文字段：{esc(J['gate_status'])}）</span></span>
</div>""")
A("""<div class="note"><b>来源标注（provenance）</b>
<ul>
<li><b>兴业证券原文内容</b>：仅「N≤1 做多、信号延续 4 日、标的 881001.WI、2015/07—2025/05」等已记录的规则描述。</li>
<li><b>项目冻结协议</b>：−10% / 20 交易日 / 简单收益 / 合成指数定义，来自 <code>config/study.toml</code>
与 <code>outputs/gate0_acceptance.json</code>；本报告只借用阈值与窗口，<b>换了基准</b>。</li>
<li><b>本项目新算出的数值</b>：全部表格与图，来自 <code>crisis_onset_tda_study.py</code> 对既有
CSV/DB 的只读计算。</li>
<li><b>整理者补充的标准统计知识</b>：PR-AUC、区块自助、循环平移置换、max-T 联合校正、
Bonferroni、Simpson 型翻转等解释，<b>不是兴业原文内容，也不是项目实证结论</b>。</li>
</ul></div>""")
A(f"""<p class="small">全部诊断均为<b>样本内</b>；未做样本外切分、未做多重检验以外的选择校正、
未读取任何 Gate 1 开发期 OOF 之外的 2025 测试评分。按约定，Gate 1 的设计要先与你讨论再动。</p>""")

# ---------------- appendices ----------------
A("<h2 id=\"sa\">附录 A：原始 JSON 全文</h2>")
A(f"<details><summary>展开：xy_crisis_onset_tda.json（{len(raw_json):,} 字符）</summary>"
  f"<pre><code>{esc(raw_json)}</code></pre></details>")
A("<h2 id=\"sb\">附录 B：两份 CSV 全文</h2>")
A(f"<details><summary>展开：xy_crisis_events.csv（{len(J['crisis_events'])} 行）</summary>"
  f"<pre><code>{esc(event_csv)}</code></pre></details>")
A(f"<details><summary>展开：xy_crisis_signal_grid.csv（{len(J['signal_grid'])} 行）</summary>"
  f"<pre><code>{esc(grid_csv)}</code></pre></details>")
A("<h2 id=\"sc\">附录 C：完整计算脚本</h2>")
numbered = "\n".join(f"{i:4d}  {line}" for i, line in enumerate(script_src.splitlines(), 1))
A(f"<details><summary>展开：crisis_onset_tda_study.py（{len(script_src.splitlines())} 行）</summary>"
  f"<pre><code>{esc(numbered)}</code></pre></details>")
A("<h2 id=\"sd\">附录 D：文件清单与复算命令</h2>")
A(table(["类别", "路径", "说明"], [
    ["计算脚本", "<code>src/xy_replication/crisis_onset_tda_study.py</code>", "只读诊断，产出 4 个结果文件"],
    ["报告脚本", "<code>src/xy_replication/build_crisis_onset_tda_report.py</code>", "只读打包，不改任何结果文件"],
    ["结果", "<code>outputs/xy_crisis_onset_tda.json</code>", "全部数值与口径声明"],
    ["结果", "<code>outputs/xy_crisis_events.csv</code>", "17 个危机事件逐行"],
    ["结果", "<code>outputs/xy_crisis_signal_grid.csv</code>", "16 格信号逐行"],
    ["结果", "<code>outputs/xy_crisis_onset_tda.png</code>", "四面板图，已内嵌本报告"],
    ["本报告", "<code>outputs/xy_crisis_onset_tda_report.html</code>", "单文件离线"],
    ["输入（未改动）", "<code>outputs/xy_corrected_sw193_ifind_peak_features.csv</code>", "v1.2 修正版特征"],
    ["输入（未改动）", "<code>outputs/xy_wind_all_a_daily.csv</code>", "881001.WI 日线 3012 行"],
    ["输入（未改动）", "<code>a_share_pit/tdx_central.db</code>", "仅读 000001/399001 指数日线作敏感性"],
]))
A("""<div class="formula"># 重算诊断（会覆盖 4 个结果文件，本报告不执行这一步）<br>
tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/crisis_onset_tda_study.py<br><br>
# 只重新生成本报告（读取既有输出，不改任何结果文件）<br>
tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/build_crisis_onset_tda_report.py</div>""")
A(f"""<div class="footer">本报告为单文件离线 HTML：图片以 base64 内嵌、样式内联、无外链、无 JavaScript。
所有数值取自本项目 <code>outputs/</code> 下既有文件；生成时只做只读打包，未重跑实验、未改阈值、未重新抽样。
Gate 1 仍暂停、2025 最终测试未读取、Gate 2 未启动。</div>""")

A("</div></body></html>")

html_text = "\n".join(parts)
# structural assertions
assert html_text.count("<table") == html_text.count("</table>")
assert html_text.count("<details>") == html_text.count("</details>")
assert html_text.count("<div") == html_text.count("</div>")
assert "<img src=\"data:image/png;base64," in html_text
assert "<img src=\"xy_" not in html_text
assert "http://" not in html_text and "https://" not in html_text
assert "<script" not in html_text
assert "${" not in html_text
HTML_OUT.write_text(html_text, encoding="utf-8")
print(f"WROTE {HTML_OUT}  {HTML_OUT.stat().st_size:,} bytes  "
      f"sections={html_text.count('<h2 id=')}  tables={html_text.count('<table')}")
