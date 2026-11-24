"""Build a single-file offline close-reading report for Baitinger & Flegel (2021).

Read-only: the script embeds the extracted PDF text/tables and page images that
were produced earlier. It does not rerun any experiment and does not modify any
result file.
"""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "third_party" / "phti_paper"
OUT = ROOT / "outputs"
HTML_OUT = OUT / "phti_close_reading.html"


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def img_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def table(headers, rows, cls: str = "") -> str:
    h = "".join(f"<th>{esc(c)}</th>" for c in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>'


def fold(title: str, body: str) -> str:
    return f"<details><summary>{esc(title)}</summary>{body}</details>"


CSS = """
:root{--ink:#1c2126;--muted:#5c6672;--line:#e0ddd4;--bg:#fbfaf7;--panel:#fff;
--accent:#185FA5;--warn:#a8442a;--good:#1c7a55;--soft:#f2efe8}
*{box-sizing:border-box}
body{margin:0;padding:0 0 80px;background:var(--bg);color:var(--ink);
font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.75;font-size:15px}
.wrap{max-width:1080px;margin:0 auto;padding:0 26px}
header{background:linear-gradient(135deg,#12365c,#185FA5);color:#fff;padding:38px 0 30px;margin-bottom:26px}
header .wrap{padding:0 26px}
h1{font-size:27px;margin:0 0 10px;line-height:1.35}
h2{font-size:20px;margin:34px 0 14px;padding-bottom:8px;border-bottom:2px solid var(--accent)}
h3{font-size:16px;margin:22px 0 10px;color:#12365c}
p{margin:10px 0}
small,.muted{color:var(--muted)}
code{background:var(--soft);padding:1px 5px;border-radius:4px;font-size:13px}
pre{background:#20262e;color:#eef2f6;padding:14px 16px;border-radius:8px;overflow:auto;font-size:12.5px;line-height:1.6}
table{border-collapse:collapse;width:100%;margin:12px 0 18px;background:var(--panel);font-size:13.5px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#eef2f7;font-weight:600}
tbody tr:nth-child(even){background:#fcfcfa}
.pill{display:inline-block;background:#e8eef6;color:#12365c;border-radius:20px;padding:2px 11px;font-size:12px;margin:2px 4px 2px 0}
.pill.w{background:#fae9e4;color:#8a3520}
.pill.g{background:#e4f2eb;color:#1c7a55}
.box{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--accent);
border-radius:6px;padding:12px 16px;margin:14px 0}
.box.warn{border-left-color:var(--warn);background:#fff8f5}
.box.good{border-left-color:var(--good);background:#f5fbf8}
.formula{background:#f4f6f9;border:1px solid #d8dee6;border-radius:6px;padding:12px 16px;
margin:12px 0;font-family:"Cambria Math",Georgia,serif;font-size:16px;overflow-x:auto}
.toc{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 18px;
columns:2;column-gap:28px;margin:16px 0}
.toc a{color:var(--accent);text-decoration:none;display:block;font-size:13.5px;padding:2px 0}
.toc a:hover{text-decoration:underline}
details{background:var(--panel);border:1px solid var(--line);border-radius:6px;margin:10px 0;padding:8px 14px}
summary{cursor:pointer;font-weight:600;color:#12365c;font-size:14px}
figure{margin:16px 0;text-align:center}
figure img{max-width:100%;border:1px solid var(--line);border-radius:6px;background:#fff}
figcaption{font-size:12.5px;color:var(--muted);margin-top:6px}
abbr[title]{border-bottom:1px dotted var(--accent);cursor:help}
.tag{font-size:11.5px;padding:1px 7px;border-radius:4px;font-weight:600;white-space:nowrap}
.tag.src{background:#e4f2eb;color:#1c7a55}
.tag.add{background:#fae9e4;color:#8a3520}
.tag.chk{background:#e8eef6;color:#12365c}
ul,ol{padding-left:22px}
li{margin:5px 0}
.footer{border-top:1px solid var(--line);margin-top:38px;padding-top:14px;font-size:12.5px;color:var(--muted)}
.kv{display:grid;grid-template-columns:190px 1fr;gap:4px 14px;font-size:13.5px}
.kv div:nth-child(odd){color:var(--muted)}
"""


def build() -> str:
    parts: list[str] = []
    A = parts.append

    A(f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PHTI 原文精读 · Baitinger &amp; Flegel (2021)</title>
<style>{CSS}</style></head><body>
<header><div class="wrap">
<h1>PHTI 原文精读：The better turbulence index?</h1>
<div>Baitinger, E. &amp; Flegel, S. (2021), <i>Financial Markets and Portfolio Management</i> 35:277–308 ·
DOI 10.1007/s11408-020-00377-x · 原文 32 页</div>
<div style="margin-top:10px">
<span class="pill">单文件离线</span><span class="pill">原文数字逐页核对</span>
<span class="pill">公式 / 符号表 / 自测题</span><span class="pill w">含复现歧义清单</span></div>
</div></header><div class="wrap">""")

    # ---------------- 0 ----------------
    A("<h2 id='s0'>0. 阅读说明与来源标注</h2>")
    A("""<div class="box"><b>三类内容严格分开：</b>
<span class="tag src">原文</span> 论文正文/附录/表格里的原话与数字；
<span class="tag chk">核对</span> 本次从 PDF 原页图像或表格 JSON 逐字复核的结果；
<span class="tag add">补充</span> 整理者（本次）为标准统计/拓扑知识、实现建议或批判，<b>不属于论文内容</b>。
凡涉及「A 股怎么复现」的判断，一律标为 <span class="tag add">补充</span>。</div>""")
    A(table(["项", "内容"], [
        ["原文文件", "<code>E:/s11408-020-00377-x.pdf</code>（32 页，7.88 MB）"],
        ["提取方式", "PDF 工具 <code>-f md</code> 全文（69 KB）、<code>-f md-plain</code> 版面识别（89 KB）、<code>-f table --table-format json</code> 9 张表、<code>-f png --dpi 130</code> 32 页图像"],
        ["已逐页核对", "第 12 页表 2、第 15 页表 3、第 19 页表 4、第 20 页表 5、第 22/23 页图 5/6 文本层、第 30 页公式 (7)(8) 与附录 B 定义"],
        ["本地副本", "<code>tda_project/third_party/phti_paper/</code>（<code>phti_full.md</code>、<code>phti_layout.md</code>、<code>tables/</code>、<code>pages/</code>）"],
        ["页码约定", "本报告写「第 N 页」= <b>PDF 文件页序</b>（从 1 起）。括号内印刷页码比它大 273（如第 15 页 = 印刷 291）"],
        ["本报告状态", "只读整理；未重跑任何策略、未改任何既有结果文件、未读取 2025 测试集绩效"],
    ]))
    A("""<div class="toc">
<a href="#s1">1. 一句话结论与论文身份</a>
<a href="#s2">2. 符号表</a>
<a href="#s3">3. 数据与目标变量</a>
<a href="#s4">4. 拓扑基础：点云 → VR → 持续图</a>
<a href="#s5">5. 原始 PHTI：相邻持续图的 Wasserstein 距离</a>
<a href="#s6">6. (60,60,60) 规则与因果时间对齐</a>
<a href="#s7">7. 表 2 仓位规则与组合收益公式</a>
<a href="#s8">8. 三个对照基准：买入持有 / OTI / VIX</a>
<a href="#s9">9. 表 3：样本外结果全表</a>
<a href="#s10">10. 归因分析：收益弱、波动强</a>
<a href="#s11">11. 稳健性：25 格参数网格</a>
<a href="#s12">12. 论文的局限与折扣</a>
<a href="#s13">13. 与此前研究梳理逐条核对</a>
<a href="#s14">14. A 股复现映射表</a>
<a href="#s15">15. 复现歧义清单与预登记摘要</a>
<a href="#s16">16. 坑位、自测题与下一步</a>
<a href="#sa">附录 A：关键页原图</a>
<a href="#sb">附录 B：原文方法步骤逐字摘录</a>
</div>""")

    # ---------------- 1 ----------------
    A("<h2 id='s1'>1. 一句话结论与论文身份</h2>")
    A("""<p><span class="tag src">原文</span> 论文提出 <b>PHTI</b>（persistent homology-based turbulence index）：
用<b>相邻两天持续拓扑图之间的 Wasserstein 距离</b>度量市场结构变化，再用 (60,60,60) 规则把它变成
<b>月末 → 次月</b>的股债仓位信号。样本外 1991-06—2019-12 共 <b>343 个月度 S&amp;P 500 收益</b>，
在「极端保护」策略下 PHTI(10) 年化 10.11% / 波动 10.64% / 夏普 0.70 / 最大回撤 33.41%，
优于买入持有 8.76% / 14.08% / 0.43 / 52.56%，也优于 OTI 与 VIX。</p>""")
    A("""<div class="box good"><b>论文自己怎么收口：</b><span class="tag src">原文</span>
第 4.2 节明确说， turbulence 指标「大体上是未来收益的糟糕预测器」，
唯一例外是 PHTI(10) 在 10% 水平显著；而 PHTI(30) 对<b>未来波动率</b>在 1% 水平显著。
所以作者把价值主要归到 <b>波动率择时</b>，不是收益方向预测。
<span class="tag add">补充</span> 这一点决定了 A 股复现时不能只报净值/夏普，必须同时报
「信号 vs 下期收益」和「信号 vs 下期波动」两条回归，以及 IC / 事件级指标。</div>""")

    # ---------------- 2 ----------------
    A("<h2 id='s2'>2. 符号表</h2>")
    A(table(["符号", "含义", "出处"], [
        ["<i>X</i><sub>t</sub>", "t 日的状态点云：过去 60 个交易日的行业日收益向量，每点 ∈ ℝ<sup>K</sup>", "第 2/3.4 节 <span class='tag src'>原文</span>"],
        ["<i>K</i>", "行业数，取 10 或 30（对应 PHTI(10) / PHTI(30)）", "第 2 节 <span class='tag src'>原文</span>"],
        ["δ", "Vietoris–Rips 过滤阈值（距离参数）", "公式 (7)"],
        ["VR(<i>X</i>, δ)", "由点云按 δ 构造的 Vietoris–Rips 复形", "附录 B"],
        ["<i>H</i><sub>i</sub>", "第 i 维同调；<i>H</i><sub>0</sub>=连通分支，<i>H</i><sub>1</sub>=环/孔洞", "第 3.2 节、附录 B"],
        ["(<i>a</i>, <i>b</i>)", "拓扑特征的出生 δ 与死亡 δ", "附录 B"],
        ["<i>P</i><sub>t</sub><sup>i</sup>", "t 日第 i 维持续图（含对角线约定）", "公式 (1)(8)"],
        ["<i>W</i><sub>t</sub>", "原始 PHTI = similarity(<i>P</i><sub>t</sub>, <i>P</i><sub>t−1</sub>)，h=1", "公式 (1)"],
        ["<i>W</i><sub>p</sub>", "p 阶 Wasserstein 距离，内范数取 L<sub>∞</sub>", "公式 (8)"],
        ["<abbr title='用当月及之前 60 个月末值，把当前值映射成五分位'>TI<sup>w</sup><sub>i,t</sub></abbr>", "第 i 个 turbulence 指标在 t 月末给出的股票仓位权重", "公式 (2)、表 2"],
        ["<i>R</i><sup>P</sup><sub>t+1</sub>", "组合在 t+1 月的收益", "公式 (2)"],
        ["<i>d</i><sub>t</sub>", "OTI 原始值（Mahalanobis 型距离指标）", "公式 (3)"],
        ["γ", "CRRA 风险厌恶系数，论文用 3 与 9", "公式 (4)、表 3"],
        ["CER(γ)", "确定性等价收益", "公式 (4)、表 3"],
    ]))

    # ---------------- 3 ----------------
    A("<h2 id='s3'>3. 数据与目标变量</h2>")
    A(table(["环节", "原文口径 <span class='tag src'>原文</span>", "备注"], [
        ["输入数据", "Kenneth R. French 数据图书馆：<b>10</b> 与 <b>30</b> 个美国行业组合的<b>日度市值加权总收益</b>", "表 1 列 10 个行业；表 10（第 29 页）列 30 个行业"],
        ["目标变量", "<b>S&amp;P 500 价格指数</b>；信号作用于该市场", "第 2 节；价格指数，不含股息"],
        ["现金", "短期国库券 T-Bill 月收益（Amit Goyal 网页）", "第 11 页脚注 21"],
        ["限制因素", "VIX 起点 1986-01；VIX 由 3 段序列拼接（实时 / 回算 / VXO）", "第 4 页脚注 8"],
        ["warm-up", "首个 60 月滚动窗口再 + 约 6 个月（60 日窗口 + 60 日 SMA）", "第 4 页"],
        ["样本外", "<b>1991-06 至 2019-12，343 个月度 S&amp;P 500 收益</b>；首窗结束 1991-05，首个仓位用于 1991-06", "第 4、14 页"],
        ["实现语言", "R", "第 4 页脚注 9"],
    ]))
    A("""<div class="box warn"><b>容易被忽略：</b><span class="tag add">补充</span>
「样本外」在这里<b>不是</b>独立训练/验证/最终测试三段切分，而是「所有量都只用当时及以前的信息滚动计算」。
它是一种<b>因果滚动回测</b>；参数（60/60/60、五分位档位、K=10/30）是在看完全文结果后写定的，
论文用第 4.3 节的参数网格来缓解数据挖掘质疑，但没有做预登记，也没有留出一段完全没有参与过写作决策的测试期。</div>""")

    # ---------------- 4 ----------------
    A("<h2 id='s4'>4. 拓扑基础：点云 → VR → 持续图</h2>")
    A("""<p><span class="tag src">原文</span> 第 3.2 节与附录 B：给定点云 <i>X</i>={x<sub>1</sub>,…,x<sub>n</sub>} ⊂ ℝ<sup>d</sup>
和阈值 δ&gt;0，Vietoris–Rips 复形定义为「任意子集是单形，当且仅当其中任意两点距离 ≤ δ」：</p>""")
    A("""<div class="formula">d(x<sub>i</sub>, x<sub>j</sub>) ≤ δ &nbsp; ∀ i, j ∈ {1,…,n} &nbsp;&nbsp; (7)</div>""")
    A("""<p>δ 从 0 增大时复形嵌套：VR(X,δ) ⊂ VR(X,δ′)（δ≤δ′），构成 filtration；
对每一维取同调 <i>H</i><sub>i</sub>，每个非零同调类存在区间 [a,b]，a=出生、b=死亡，
全部 (a,b) 组成持续图 <i>P</i><sup>i</sup>；平凡生成元出生即死亡，落在正对角线上。</p>""")
    A("""<div class="box"><b>金融含义（论文自己的解释，第 3.3 节）：</b>
安静期行业收益点彼此靠近 → <i>H</i><sub>0</sub> 特征（连通所需距离）短、数量多且呈指数式分布；
动荡期收益散开 → <i>H</i><sub>0</sub> 距离变长、<i>H</i><sub>1</sub> 孔洞在更大的 δ 出生且寿命更长。
第 8/10 页图 2/3 用「美国金融 + 建筑」两个行业 60 日收益（单位 <b>%</b>，δ=1）展示了这一对比：
安静期窗口 2007-03-07—05-31，动荡期窗口 2008-09-05—11-28，方差分别为 2006–2008 年月末 60 日窗口的最小/最大值。</div>""")
    A("""<p><span class="tag add">补充</span> 这里 <b>一个点 = 一个交易日</b>，坐标 = 该日 K 个行业的收益；
正式计算是 10 维或 30 维，不是图 2/3 里为了可视化用的 2 维。
这与兴业证券「一个点 = 一个行业、距离 = 收益相关」是<b>完全不同的点云</b>，两条线不能混。</p>""")

    # ---------------- 5 ----------------
    A("<h2 id='s5'>5. 原始 PHTI：相邻持续图的 Wasserstein 距离</h2>")
    A("""<div class="formula">W<sub>t</sub> = similarity(P<sub>t</sub>, P<sub>t−h</sub>), &nbsp; h = 1 &nbsp;&nbsp; (1)</div>""")
    A("""<p><span class="tag src">原文</span> 第 9–10 页：<i>P</i><sub>t</sub> 可看作三列矩阵
（维度编号、出生 δ、死亡 δ）；<b>与前一天的持续图比较</b>；<i>W</i><sub>t</sub> 越大表示结构越不相似，
被解释为体制切换或动荡概率上升。脚注 20：<b>W 只算到第一维</b>（即 <i>H</i><sub>0</sub> 与 <i>H</i><sub>1</sub>），
作者称更高维「计算越来越贵，且经验上不改善 PHTI 表现」。</p>""")
    A("""<p>附录 B（第 30 页）给出的严格定义，已逐字核对原页图像：</p>""")
    A("""<div class="formula">W<sub>p</sub>(P<sub>i</sub><sup>1</sup>, P<sub>i</sub><sup>2</sup>)
= inf<sub>φ</sub> [ Σ<sub>x∈P<sub>i</sub><sup>1</sup></sub> ‖x − φ(x)‖<sub>∞</sub><sup>p</sup> ]<sup>1/p</sup> &nbsp;&nbsp; (8)</div>""")
    A("""<p>其中 φ 是两图之间的<b>所有双射</b>（bijections）；
对角线按约定属于持续图，用来吸收「出生即死亡」的平凡类。</p>""")
    A("""<div class="box warn"><b>四个原文没有交代、但复现必须自己定的歧义</b> <span class="tag add">补充</span>
<ol>
<li><b>p 没有给值。</b>公式写「p-th Wasserstein」，全文没有说 p=1 还是 p=2。这是复现时第一个必须冻结的参数。</li>
<li><b>「双射」与点数不等矛盾。</b>相邻两天的持续图点数一般不同，严格双射不存在；
标准做法是<b>增广对角线</b>（允许点匹配到自身在对角线上的投影，代价 = 半持久 (d−b)/2），
再做最优指派。论文写了「对角线属于持续图」，但没写匹配规则。</li>
<li><b><i>H</i><sub>0</sub> 的 essential class</b>（死亡 δ = ∞）如何处理没有写。常见做法是剔除该点；
若保留，L<sub>∞</sub> 距离会发散。</li>
<li><b>收益尺度未归一。</b>图 2/3 的坐标是「returns in %」，δ=1 即 1 个百分点；
W 的量纲是收益百分数，因此高波动期 W 天然变大 —— 这可能只是<b>波动放大</b>而不是拓扑变化，
论文没有做尺度归一的消融。</li>
</ol>
本报告第 15 节把这些歧义写成 A 股复现的预登记项；<b>它们是复现设计，不是论文事实</b>。</div>""")
    A("""<p><span class="tag add">补充</span> 还有一点值得强调：<i>P</i><sub>t</sub> 与 <i>P</i><sub>t−1</sub>
来自两个<b>重叠 59 天</b>的滚动窗口，所以 <i>W</i><sub>t</sub> 度量的是「窗口往前挪一天，拓扑结构变了多少」，
不是两个分离时段的距离。这与 Souto (2023) 代码里「分离窗口却标在相邻日期」的前视错位是两回事。</p>""")

    # ---------------- 6 ----------------
    A("<h2 id='s6'>6. (60,60,60) 规则与因果时间对齐</h2>")
    A("""<p><span class="tag src">原文</span> 第 11 页把步骤重列了一遍（Step 1–5），下表逐字对齐：</p>""")
    A(table(["步", "原文步骤", "时点 / 数据边界"], [
        ["1", "用 60 个交易日收益的滚动窗口，逐日计算 <i>P</i><sub>t</sub>（10 或 30 个行业）", "用到 t 日收盘为止"],
        ["2", "逐日按公式 (1) 算 <i>W</i><sub>t</sub>", "用到 t 与 t−1"],
        ["3", "对 <i>W</i><sub>t</sub> 做 <b>60 日简单移动平均</b>", "只用过去 60 日"],
        ["4", "降频到月：<b>只保留月末</b>的平滑值，其余丢弃；这条月度序列就是 PHTI", "月末收盘可得"],
        ["5", "把当月 PHTI 与 <b>60 个月末值</b>的滚动窗口比较，按表 2 得出<b>下月</b>仓位", "t 月末决定 t+1 月"],
    ]))
    A("""<div class="formula">t−60日 … t日收盘 → W<sub>t</sub> → SMA60 → 月末值 PHTI<sub>m</sub>
→ 与 [m−59 … m] 共 60 个月末值比分位 → 仓位 w<sub>m</sub> → 作用于 m+1 月收益</div>""")
    A("""<div class="box"><b>为什么这条链是因果的</b> <span class="tag chk">核对</span>：
公式 (2) 明确写 <i>R</i><sup>P</sup><sub>t+1</sub> 只由 t 时点的 <i>TI</i><sup>w</sup><sub>i,t</sub> 决定，
且第 11 页原文逐字写「<i>TI</i><sup>w</sup><sub>i,t</sub> is solely based on information up to t」。
第 14 页给出可核对的锚点：第一个 60 月窗口结束于 <b>1991-05</b>，第一个仓位作用于 <b>1991-06</b>。</div>""")
    A("""<p><span class="tag add">补充</span> 「60 个月末值窗口」有两种读法：含当月共 60 个，或过去 60 个 + 当前第 61 个。
按 1986-01 起点、约 6 个月 warm-up、首窗结束 1991-05 反推，<b>含当月共 60 个</b>更自洽。
A 股复现会把它作为主口径，并把「过去 60 个 + 当前」列为敏感性，两种都披露、不按结果反选。</p>""")
    A("""<div class="box warn"><b>论文没有报的东西</b> <span class="tag add">补充</span>：
交易成本、换手率、信号触发次数/误报事件数、事件级提前量、执行价（收盘 vs 次日开盘）、
月度收益是否含股息、以及「月末值」遇到非交易日/停牌如何处理。公式 (2) 是无摩擦的。</div>""")

    # ---------------- 7 ----------------
    A("<h2 id='s7'>7. 表 2 仓位规则与组合收益公式</h2>")
    A(table(["turbulence 五分位", "极端保护 WCP (%)", "灵活暴露 FE (%)", "灵活暴露+杠杆 FEL (%)"], [
        ["第 1 档（最低）", "100", "100", "120"],
        ["第 2 档", "100", "80", "110"],
        ["第 3 档", "100", "60", "90"],
        ["第 4 档", "100", "40", "60"],
        ["第 5 档（最高）", "<b>0</b>", "20", "20"],
    ]))
    A("""<div class="formula">R<sup>P</sup><sub>t+1</sub>
= TI<sup>w</sup><sub>i,t</sub> · R<sup>SP500</sup><sub>t+1</sub>
+ (1 − TI<sup>w</sup><sub>i,t</sub>) · R<sup>TBill</sup><sub>t+1</sub> &nbsp;&nbsp; (2)</div>""")
    A("""<p><span class="tag src">原文</span> 组合始终满仓（股票 + 现金）；杠杆档 <i>w</i>&gt;1 时，
现金权重为负，等于按 T-Bill 利率融资，所以作者说「leverage costs of negative Treasury Bill return」。</p>""")
    A("""<div class="box"><b>数值例子（整理者按公式 (2) 手算，非论文例子）</b> <span class="tag add">补充</span>：
若某月末 PHTI 落入第 5 档、下月 S&amp;P 500 跌 −8%、T-Bill 月收益 +0.2%：
<ul><li>极端保护：w=0 → 组合 = 0×(−8%) + 1×0.2% = <b>+0.2%</b>；</li>
<li>灵活暴露：w=0.2 → 0.2×(−8%) + 0.8×0.2% = <b>−1.44%</b>；</li>
<li>杠杆档在第 1 档 w=1.2、下月涨 +3%：1.2×3% + (−0.2)×0.2% = <b>+3.56%</b>。</li></ul>
可见「极端保护」只押最高分位那一个尾部，其余四档全仓不动；这正是它换手最低、也最容易把一次危机包装成一次正确的地方。</div>""")
    A("""<p><span class="tag src">原文</span> 表 3 之外还有 CER（确定性等价收益）指标：</p>""")
    A("""<div class="formula">CER = [ (1−γ) · T<sup>−1</sup> · Σ<sub>t</sub> U(1+r<sub>t</sub>) ]<sup>1/(1−γ)</sup> − 1,
&nbsp; U(W) = W<sup>1−γ</sup>/(1−γ) &nbsp;&nbsp; (4)</div>""")

    # ---------------- 8 ----------------
    A("<h2 id='s8'>8. 三个对照基准</h2>")
    A(table(["基准", "构造", "与 PHTI 的关系"], [
        ["买入持有", "S&amp;P 500 月度买入持有", "表 3 的 Benchmark 列"],
        ["<abbr title='Original Turbulence Index, Chow et al. (1999)'>OTI</abbr>",
         "公式 (3)：<i>d</i><sub>t</sub> = (y<sub>t</sub>−μ)<sup>T</sup> Σ<sup>−1</sup> (y<sub>t</sub>−μ)；μ、Σ 用过去 60 个交易日估计；同样套 (60,60,60) 规则",
         "非 TDA 的一阶/二阶矩基准；OTI(10)/OTI(30)"],
        ["VIX", "60 日 SMA → 月末 → 60 月滚动分位（只有 (60,60) 两步，因为没有窗口参数）", "前瞻性波动基准；由 3 段序列拼接"],
    ]))
    A("""<p><span class="tag src">原文</span> 第 13 页脚注 23：分位阈值用<b>滚动经验窗口</b>，
沿用 Kritzman &amp; Li (2010)，<b>不</b>用 Chow et al. (1999) 的卡方理论分位。
<span class="tag add">补充</span> 这个选择很关键：它让分位是因果的，但也让「第 5 档」在历史上
永远约占 20%，无法区分「真的极端」与「相对最近 5 年偏高」。</p>""")

    # ---------------- 9 ----------------
    A("<h2 id='s9'>9. 表 3：样本外结果全表</h2>")
    A("<p><span class='tag chk'>核对</span> 以下数字取自第 15 页表格 JSON 与页面图像，逐格一致。单位：除 SR 与偏度外均为 %。</p>")
    A(table(["面板 / 指标", "Benchmark", "PHTI(10)", "PHTI(30)", "OTI(10)", "OTI(30)", "VIX"], [
        ["<b>Panel A 极端保护</b> μ", "8.76", "<b>10.11</b>", "9.82", "8.01", "7.13", "6.54"],
        ["σ", "14.08", "<b>10.64</b>", "10.76", "11.84", "11.68", "9.97"],
        ["SR", "0.43", "<b>0.70</b>", "0.66", "0.45", "0.39", "0.39"],
        ["max DD", "52.56", "<b>33.41</b>", "35.08", "39.93", "42.69", "38.04"],
        ["min ret", "−16.94", "−11.00", "−11.00", "−14.58", "−14.58", "−8.20"],
        ["Skewness", "−0.64", "−0.21", "−0.21", "−0.50", "−0.53", "−0.20"],
        ["CER(3)", "5.48", "<b>8.27</b>", "7.93", "5.73", "4.92", "4.97"],
        ["CER(9)", "−1.52", "<b>4.50</b>", "4.09", "0.94", "0.26", "1.77"],
        ["<b>Panel B 灵活暴露</b> μ", "8.76", "7.46", "7.30", "5.84", "5.85", "6.16"],
        ["σ", "14.08", "8.20", "8.50", "8.97", "8.76", "7.91"],
        ["SR", "0.43", "0.59", "0.55", "0.36", "0.37", "0.45"],
        ["max DD", "52.56", "21.36", "24.83", "34.78", "34.52", "32.84"],
        ["min ret", "−16.94", "−8.20", "−7.30", "−10.99", "−8.79", "−7.25"],
        ["Skewness", "−0.64", "0.09", "−0.22", "−0.54", "−0.39", "−0.35"],
        ["CER(3)", "5.48", "6.40", "6.14", "4.56", "4.64", "5.17"],
        ["CER(9)", "−1.52", "4.28", "3.80", "1.86", "2.13", "3.14"],
        ["<b>Panel C 灵活+杠杆</b> μ", "8.76", "9.21", "9.23", "7.27", "7.13", "6.97"],
        ["σ", "14.08", "10.69", "11.18", "11.77", "11.61", "10.09"],
        ["SR", "0.43", "0.61", "0.59", "0.39", "0.39", "0.43"],
        ["max DD", "52.56", "30.74", "33.82", "43.98", "44.68", "42.34"],
        ["min ret", "−16.94", "−9.84", "−10.12", "−13.20", "−12.09", "−9.01"],
        ["Skewness", "−0.64", "0.04", "−0.23", "−0.55", "−0.45", "−0.43"],
        ["CER(3)", "5.48", "7.37", "7.20", "5.02", "4.96", "5.34"],
        ["CER(9)", "−1.52", "3.71", "3.06", "0.27", "0.44", "1.96"],
    ]))
    A("""<div class="box warn"><b>读表要点</b> <span class="tag add">补充</span>：
① 只有 Panel A（极端保护）出现「收益和波动同时改善」；Panel B 不带杠杆时
<b>所有主动策略的平均收益都低于买入持有</b>——降低波动不等于赚钱。
② VIX 在 min ret（−8.20%）和偏度上反而最好，说明「谁的下行尾最薄」和「谁夏普最高」不是同一问题。
③ 这些是<b>无成本、无换手约束</b>的月度净值；A 股复现必须补成本与换手。</div>""")

    # ---------------- 10 ----------------
    A("<h2 id='s10'>10. 归因分析：收益弱、波动强</h2>")
    A("""<div class="formula">R<sup>SP500</sup><sub>t+1</sub> = α + β<sub>1</sub> TI<sup>w</sup><sub>i,t</sub>
+ β<sub>2</sub> R<sup>SP500</sup><sub>t</sub> + ε<sub>t+1</sub> &nbsp;&nbsp; (5)</div>""")
    A("""<div class="formula">V<sup>SP500</sup><sub>t+1</sub> = α + β<sub>1</sub> TI<sup>w</sup><sub>i,t</sub>
+ β<sub>2</sub> V<sup>SP500</sup><sub>t</sub> + ε<sub>t+1</sub> &nbsp;&nbsp; (6)</div>""")
    A("""<p><span class="tag src">原文</span> <i>V</i> 是「t+1 月内所有日收益的标准差」；两个回归都加了同期滞后项控制自相关；
只报 worst-case protection 的 0/1 信号（其余放附录表 6–9）。
表 4/5 脚注：*** 1%、** 5%、* 10%；F-stat 是整体显著性检验，脚注写
「在两/三/四变量情形下 F-stat ≥ 2.32 / 2.11 / 1.96 才达 10% 显著」，
并声明「本表中没有任何一个回归模型在统计上显著」。</p>""")
    A(table(["回归", "关键结果", "解读 <span class='tag src'>原文</span>"], [
        ["表 4：未来<b>收益</b>", "PHTI(10) 单变量 coeff <b>0.0084</b>、t = <b>1.760</b>（* 10%）；多变量 0.0083 / t=1.733、0.0085 / t=1.727；OTI(10) 0.0029 / t=0.514；VIX −0.0003 / t=−0.059",
         "唯一在 10% 水平显著的收益预测；其余大多不显著且部分符号相反"],
        ["表 5：未来<b>波动</b>", "PHTI(30) coeff <b>−0.0017</b>、t = <b>−3.283</b>（*** 1%）；PHTI(10) −0.0008 / t=−1.698（* 10%）；VIX −0.0011 / t=−2.143（** 5%）；OTI(10) −0.0005 / t=−0.919",
         "PHTI(30) 波动预测最强，VIX 次之；OTI 在控制滞后波动后无增量"],
    ]))
    A("""<div class="box good"><b>整篇论文最有价值的一步</b> <span class="tag add">补充</span>：
它没有停在「夏普变高了」，而是拆开问改善来自收益还是波动。
结论是主要来自<b>波动率择时</b>。这也解释了为什么 Panel B（逐档降仓）平均收益反而低——
降仓在波动大的月份确实降了波动，但代价是放弃风险溢价。
<span class="tag add">补充</span> 我们前几轮把兴业线的评价从「年化」改成「IC + 事件级」，是同一条思路。</div>""")

    # ---------------- 11 ----------------
    A("<h2 id='s11'>11. 稳健性：25 格参数网格</h2>")
    A("""<p><span class="tag src">原文</span> 第 4.3 节与图 5/6：把 <b>窗口长度</b> 与 <b>SMA 长度</b>
各自从 20 到 60、步长 10 变化（5×5 = 25 格），对每种策略记录「相对买入持有的夏普差」。
图 5 给 WCP 与 FE 下 OTI(10) / PHTI(10) 的对比，图 6 给 FEL 与 VIX。</p>""")
    A("""<p><span class="tag chk">核对</span> 按第 22 页图 5 文本层逐格读出 PHTI(10) 在 WCP 下的 25 个夏普差：</p>""")
    A(table(["Window \\ SMA", "20", "30", "40", "50", "60"], [
        ["20", "+0.16", "+0.23", "+0.13", "+0.21", "+0.26"],
        ["30", "+0.11", "+0.22", "+0.05", "+0.12", "+0.11"],
        ["40", "−0.03", "+0.17", "+0.08", "+0.07", "+0.17"],
        ["50", "+0.12", "+0.24", "+0.11", "+0.11", "+0.11"],
        ["60", "0.00", "+0.12", "+0.01", "+0.13", "+0.13"],
    ]))
    A("""<p>25 格中 <b>23 格为正、1 格为零、1 格为负</b>，与原文「almost all SMA–Window combinations」一致；
OTI(10) 在 WCP 下多数为负、FE 下几乎全负。
<span class="tag add">补充</span> 但要注意：这 25 格<b>是在看到主结果之后做的稳定性检查，不是预登记</b>，
且 25 次检验未做多重比较校正；它降低了「单参数凑出来」的疑虑，不能替代独立样本外测试。</p>""")

    # ---------------- 12 ----------------
    A("<h2 id='s12'>12. 论文的局限与折扣</h2>")
    A(table(["#", "折扣 <span class='tag add'>补充</span>", "影响"], [
        ["1", "<b>无尺度归一消融</b>：W 用百分数收益的欧氏距离，波动放大会机械抬升 W", "「拓扑变化」与「只是波动变大」无法分离；而这恰是它自称的优势场景"],
        ["2", "<b>无 H₀/H₁ 消融</b>：脚注只说算到第一维更省时，没拆开看哪一维贡献", "不知道是连通性（≈波动/离散度）还是孔洞（≈相关结构）在起作用"],
        ["3", "<b>无成本、无换手、无执行价</b>：公式 (2) 无摩擦", "极端保护 5 档从 100% 到 0% 再回 100%，真实换手与冲击成本可能吞掉超额"],
        ["4", "<b>「样本外」= 因果滚动，不是独立三段切分</b>；参数与档位由作者在全样本期间内写定", "没有一段完全未参与研究决策的封存测试期"],
        ["5", "<b>尾部依赖 / 相关性未被直接度量</b>：论文只展示图 2/3 的定性对比", "机制解释停留在叙事"],
        ["6", "<b>S&amp;P 500 用价格指数、行业组合用总收益</b>，两者口径不一致", "股息再投资的处理不明"],
        ["7", "<b>VIX 由三段序列拼接</b>（VXO 1986–1989、回算 1990–2003、实时 2003–2019）", "对照基准自身有构造断点，作者脚注承认但说「两者高度相关，应不影响结论」"],
        ["8", "<b>未报事件级指标</b>：触发几次、误报几次、提前多少、一次危机被算成几个月", "月频下「一次危机」可能被重复计成多个正确月份"],
        ["9", "<b>W 的 p、对角线匹配、H₀ 无穷点未交代</b>（第 5 节）", "精确复现不可能，只能做「合理实现 + 敏感性」"],
        ["10", "<b>结论是波动率择时，不是危机预警</b>", "不能把它当作「提前预测崩盘」的证据；与本项目 Gate 0 的危机标签不是同一目标"],
    ]))

    # ---------------- 13 ----------------
    A("<h2 id='s13'>13. 与此前研究梳理逐条核对</h2>")
    A("""<p>上一轮答复依据 <code>潘炯铠的持续同调量化研究梳理.html</code> 附录 A 的精读记录。
本次拿到 PDF 原文后逐条核对如下：</p>""")
    A(table(["此前表述", "核对结果", "说明"], [
        ["点 = 交易日，60 日滚动状态点云，VR 算 H₀/H₁", "<span class='tag chk'>一致</span>", "第 3.4 节 + 脚注 20；正式计算 10/30 维"],
        ["不用景观范数，用相邻两日持续图 Wasserstein 距离", "<span class='tag chk'>一致</span>", "公式 (1)(8)；此前未说明内范数是 L∞、p 未指定"],
        ["60 日 SMA → 只留月末 → 与 60 个月末值比五分位 → 下月仓位", "<span class='tag chk'>一致</span>", "第 11 页 Step 1–5；本次补上「含当月 60 个」的推断"],
        ["仓位 100/80/60/40/20%，极端保护第 5 档 0%", "<span class='tag chk'>一致</span>", "表 2；本次补齐杠杆档 120/110/90/60/20%"],
        ["表 3 数字 8.76→10.11、52.56→33.41 等", "<span class='tag chk'>一致</span>", "第 15 页表格 JSON 与原页图像逐格一致"],
        ["收益预测 PHTI(10) t=1.760（10%）；波动预测 PHTI(30) t=−3.283（1%）", "<span class='tag chk'>一致</span>", "表 4/表 5 原页图像逐字核对"],
        ["OTI/VIX 真基准、六类指标、窗口与 SMA 20–60 敏感性", "<span class='tag chk'>一致</span>", "本次补上图 5 的 25 格具体数值"],
        ["S&amp;P 500 价格指数、VIX 多段拼接", "<span class='tag chk'>一致</span>", "第 2 节、第 4 页脚注 8"],
        ["「样本外只是滚动因果计算，没有独立三段切分」", "<span class='tag chk'>一致</span>", "第 4 页与第 14 页"],
        ["「原始收益未做尺度归一，W 可能只是波动放大」", "<span class='tag chk'>一致且更强</span>", "第 8/10 页图坐标明确写 returns in %，且全文无归一化步骤"],
        ["<b>此前未提及的新细节</b>", "<span class='tag add'>补充</span>", "W 为 L∞ 内范数、p 未给、双射与点数不等的矛盾、H₀ 无穷点、含股息/不含股息口径不一致、无换手成本、表 4/5 脚注声明「无任何回归整体显著」、CER 公式与 γ=3/9"],
    ]))

    # ---------------- 14 ----------------
    A("<h2 id='s14'>14. A 股复现映射表</h2>")
    A("""<p><span class="tag add">补充</span> 以下<b>全部是本次整理者的复现设计</b>，不是论文内容，也不是已跑出的结果。
「差异等级」表示与原文的可比程度：A=概念一致、B=近似代理、C=不可消除的差异。</p>""")
    A(table(["原文环节", "A 股可得数据（已审计）", "差异", "备注"], [
        ["10 / 30 个美国行业组合日总收益", "申万一级行业指数日收盘：p16（16 行业，2005-01-04—2026-11-03，5283 天全满）、p27（27 行业，2014-02-21—2026-11-03，3070 天全满）", "C", "行业数量与分类体系不同；且申万是<b>价格指数</b>，不含股息"],
        ["S&amp;P 500 价格指数", "沪深300 000300（2005-01-04—2026-11-04，5302 行）；稳健：万得全A 881001.WI（2012-12-31—2025-05-30，3012 行）、Gate 0 冻结合成指数", "B", "主标的拟用 000300，与「大盘价格指数」概念最近"],
        ["T-Bill 月收益", "<b>本地无</b>国债/货币基金收益序列", "C", "主口径拟设现金收益 = 0，另做年化 2% 敏感性；杠杆档因无融资利率不实现"],
        ["VIX", "<b>本地无</b>期权隐含波动率", "C", "拟用「过去 20 日已实现波动率」作波动基准，明确标注不等于 VIX（非前瞻）"],
        ["OTI（Mahalanobis）", "可由同一行业面板完整实现", "A", "60 日窗口估 μ、Σ，同样 (60,60,60)，是非 TDA 的关键对照"],
        ["月度交易日历", "trade_calendar 8812 天；p16 有 263 个月末", "A", "月末 = 该月最后一个有完整行业数据的交易日"],
        ["样本外长度 343 个月", "p16：约 2005-07 起有月末值，扣 60 月窗口后开发期约 2010-07—2024-12（≈174 个月）；p27 首信号约 2019-08（≈65 个月）", "C", "<b>样本长度约为原文一半或更少</b>，统计功效显著更低"],
        ["1991-06 起样本外", "2025-01 起按项目纪律封存、不读取", "C", "新线沿用 Gate 0 的时间外纪律，避免用测试集调参"],
    ]))
    A("""<div class="box warn"><b>最重要的一句话</b>：这不是「精确复现」，而是
<b>把 PHTI 的方法链移植到 A 股行业面板</b>。行业分类、股息口径、标的、现金、波动基准、样本长度都有不可消除的差异；
因此结果无论正负，都只能说明「这条链在 A 股这份数据上如何」，不能证伪或证实原文。</div>""")

    # ---------------- 15 ----------------
    A("<h2 id='s15'>15. 复现歧义清单与预登记摘要</h2>")
    A("""<p><span class="tag add">补充</span> 以下项目在<b>看任何绩效之前</b>写进独立配置文件
<code>tda_project/config/phti_replication.toml</code>；全部披露、不按结果反选。</p>""")
    A(table(["#", "歧义 / 决策", "主口径（冻结）", "敏感性 / 对照"], [
        ["1", "Wasserstein 阶数 p", "p = 1（与 W<sub>1</sub> 常用定义一致）", "p = 2、bottleneck（p=∞）作对照"],
        ["2", "内范数", "L<sub>∞</sub>（严格照公式 8）", "L<sub>2</sub> 作对照，检验是否只是范数选择"],
        ["3", "点数不等 / 对角线", "增广对角线 + 匈牙利算法最优指派；点→对角线代价 = (d−b)/2（L∞ 下的半持久）", "仅有限点一对一（不足补零）作实现对照，记录差异"],
        ["4", "H₀ 的 death=∞ 点", "剔除 essential class", "替换为 filtration 上界的 2 倍作对照"],
        ["5", "持续图维度", "H₀ + H₁（照脚注 20）", "仅 H₀ / 仅 H₁ 的<b>消融</b>（原文没做，本项目补）"],
        ["6", "点云收益口径", "行业日<b>对数收益</b>（与 Gate 0 拓扑输入一致）；组合收益用简单收益", "原始百分数简单收益（更贴近原文图 2/3）"],
        ["7", "尺度归一", "原始收益（忠实原文）", "<b>按 60 日窗口逐维标准化</b>后再算 W —— 专门检验「W 是否只是波动放大」"],
        ["8", "历史分位窗口", "含当月共 60 个月末值，midrank 分位", "过去 60 个 + 当前值（共 61）"],
        ["9", "行业面板", "p16（16 行业，2005 起）主分析；p27（27 行业，2014 起）稳健性", "两面板各自独立，不拼接变维坐标、不补 0"],
        ["10", "仓位规则", "表 2 三档全跑（WCP / FE / FEL）", "FEL 因无融资利率，只作公式展示与 0 利率敏感性，不作主结论"],
        ["11", "交易成本", "主口径每边 0.1%（与兴业线一致）", "零成本（对齐原文）与 0.3% 两边"],
        ["12", "评价", "月度：年化/波动/夏普/回撤/CER；<b>另报时序 IC、收益与波动回归、事件级触发/误报/提前量、换手、区块自助区间</b>", "与买入持有、OTI、RV 基准对照；稳健性 5×5 网格全披露 + 联合校正"],
        ["13", "时间边界", "开发期至 2024-12-31；<b>2025-01 起封存，不读取、不调参</b>", "2025 测试仅在设计与参数冻结、且经讨论后统一读取一次"],
    ]))

    # ---------------- 16 ----------------
    A("<h2 id='s16'>16. 坑位、自测题与下一步</h2>")
    A("""<ol>
<li><b>混淆两条点云</b>：PHTI 点=交易日/坐标=行业收益；兴业点=行业/距离=相关。二者不是同一实验。</li>
<li><b>把夏普改善读成收益预测</b>：表 4 说明收益预测只在 10% 水平显著，表 5 说明价值主要在波动。</li>
<li><b>把 (60,60,60) 的三个 60 记混</b>：60 <u>交易日</u>窗口、60 <u>交易日</u> SMA、60 <u>月</u>末历史窗口。</li>
<li><b>忘了月末→次月</b>：月末信号作用于 m+1 月，任何时候都不可以用当月收益给当月信号打分。</li>
<li><b>把「五分位」当绝对阈值</b>：滚动 60 月经验分位永远是相对量，语义是「相对近 5 年偏高」。</li>
<li><b>忽略尺度</b>：W 随收益振幅线性放大；不做标准化消融就无法排除「只是波动」。</li>
<li><b>忽略点数不等</b>：公式 (8) 写「双射」，实现必须处理对角线，否则复现根本跑不通。</li>
<li><b>忽略重复计数</b>：月频下连续几个月落在第 5 档，是一次危机被记成多次「正确」。</li>
<li><b>把原文结果当作危机预警证据</b>：它的标签是「波动/回撤体制」，不是 Gate 0 的 −10%/20 日危机标签。</li>
<li><b>拿 A 股结果反推原文对错</b>：行业分类、股息、样本长度全不同，只能判「本面板上如何」。</li>
</ol>""")
    A("<h3>自测题（答案可折叠）</h3>")
    for q, a in [
        ("① W<sub>t</sub> 比较的是哪两张持续图？", "P<sub>t</sub> 与 P<sub>t−1</sub>；两个 60 日窗口重叠 59 天，度量「窗口挪一天带来的拓扑变化」。"),
        ("② 表 3 Panel B 里 PHTI(10) 的夏普 0.59 高于基准 0.43，能说它赚得更多吗？", "不能。Panel B 平均收益 7.46% < 基准 8.76%；夏普改善来自波动从 14.08% 降到 8.20%。"),
        ("③ 公式 (8) 的内范数是什么？p 等于多少？", "内范数是 L∞；<b>p 原文没有给值</b>，这是复现必须自行冻结的歧义。"),
        ("④ 第 5 档仓位在三种策略下分别是多少？", "极端保护 0%、灵活暴露 20%、灵活+杠杆 20%。"),
        ("⑤ 若某月末信号落入第 5 档，它作用于哪个月的收益？", "下一个月。首窗结束 1991-05 → 首个仓位用于 1991-06。"),
        ("⑥ A 股没有 VIX，直接用「过去 20 日已实现波动率」当对照，结论该怎么表述？", "只能说「与一个事后波动代理比较」，不能说「与 VIX 比较」；它不是前瞻指标，语义不同。"),
    ]:
        A(fold(q, f"<p>{a}</p>"))

    A("""<div class="box"><b>本次已完成 / 下一步</b>
<ul><li>✅ 原文定位、全文与表格提取、关键页图像逐字核对</li>
<li>✅ 数据可行性审计（p16 5283 天 / p27 3070 天 / 000300 5302 天 / 263 个月末）</li>
<li>✅ 复现预登记配置与工程管线（状态见 <code>outputs/phti_engineering_acceptance.json</code>）</li>
<li>⬜ <b>正式绩效回测尚未运行</b>：按项目纪律，需先与你确认行业面板、标的/现金口径与 2025 封存边界，再统一执行</li></ul>
<b>Gate 1 仍暂停、2025 最终测试未读取、Gate 2 未启动</b>；本条 PHTI 线是独立的新支线，不改动 Gate 0/1 任何冻结文件。</div>""")

    # ---------------- appendix A ----------------
    A("<h2 id='sa'>附录 A：关键页原图（base64 内嵌）</h2>")
    for fname, cap in [
        ("page-0012.png", "第 12 页（印刷 288）：表 2 仓位规则"),
        ("page-0015.png", "第 15 页（印刷 291）：表 3 样本外结果"),
        ("page-0019_readable.png", "第 19 页（印刷 295）：表 4 未来收益回归"),
        ("page-0020_readable.png", "第 20 页（印刷 296）：表 5 未来波动回归"),
        ("page-0030.png", "第 30 页（印刷 306）：附录 B 公式 (7)(8)"),
    ]:
        p = PAPER / "pages" / fname
        A(f'<figure><img src="data:image/png;base64,{img_b64(p)}" alt="{esc(cap)}">'
          f'<figcaption>{esc(cap)} · 来源：E:/s11408-020-00377-x.pdf</figcaption></figure>')

    # ---------------- appendix B ----------------
    A("<h2 id='sb'>附录 B：原文方法步骤逐字摘录</h2>")
    steps = """Step 1 Using a rolling window of 60-day return data for 10 or 30 sectors, calculate P_t on a daily basis.
Step 2 Calculate W_t according to Eq. 1 on a daily basis.
Step 3 Smooth W_t with a moving average of 60 days. The resulting time series is the smoothed W_t on a daily basis.
Step 4 Convert the time series to a monthly frequency by considering only month end values of the smoothed daily W_t time series. (All non-month-end values are dropped.) The resulting monthly time series is the PHTI.
Step 5 The asset allocation for the next month is derived by contrasting the latest PHTI value with the last 60 PHTI values according to the rules in Table 2."""
    A(f"<pre><code>{esc(steps)}</code></pre>")
    A("""<p>另附两条脚注原文：</p>
<pre><code>20 The interested reader is referred to the "Appendix" for a detailed and mathematical discussion of the
Wasserstein-Distance. We calculated W up to the first dimension. Calculating W for higher dimension gets
increasingly time consuming and, in our experience, does not meaningfully improve the performance of the PHTI.

23 By using a trailing empirical window for quintile assignment, we follow the methodology of Kritzman and Li
(2010). This approach deviates from Chow et al. (1999). They use theoretical quintile borders based on the
assumption that d_t follows a chi-square distribution.</code></pre>""")
    A(fold("展开：表 3 原始表格 JSON（page_015_table_002.json）",
           f"<pre><code>{esc((PAPER / 'tables' / 'page_015_table_002.json').read_text(encoding='utf-8'))}</code></pre>"))
    A(fold("展开：表 2 原始表格 JSON（page_012_table_001.json）",
           f"<pre><code>{esc((PAPER / 'tables' / 'page_012_table_001.json').read_text(encoding='utf-8'))}</code></pre>"))

    A("""<div class="footer">本报告为单文件离线 HTML：5 张原页图像以 base64 内嵌，样式内联，无外链、无脚本。
所有原文数字来自 <code>third_party/phti_paper/</code> 下的 PDF 提取产物与原页图像；
所有「A 股复现」内容均为整理者补充的设计，不是论文结论，也不是已跑出的绩效。
生成脚本：<code>tda_project/src/phti_replication/build_phti_close_reading.py</code>（只读打包）。</div>""")
    A("</div></body></html>")
    return "\n".join(parts)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    text = build()
    assert "http://" not in text and "https://" not in text
    assert "<script" not in text
    assert text.count("<table") == text.count("</table>")
    assert text.count("<details>") == text.count("</details>")
    assert text.count("<div") == text.count("</div>"), (
        text.count("<div"), text.count("</div>"))
    HTML_OUT.write_text(text, encoding="utf-8")
    print(json.dumps({
        "output": str(HTML_OUT),
        "bytes": len(text.encode("utf-8")),
        "sections": text.count("<h2 id="),
        "tables": text.count("<table"),
        "details": text.count("<details>"),
        "embedded_images": text.count("data:image/png;base64,"),
    }, ensure_ascii=False, indent=2))
