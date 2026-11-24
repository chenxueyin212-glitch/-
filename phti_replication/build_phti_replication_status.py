"""Build the A-share PHTI replication design + engineering acceptance report.

Single-file offline HTML, read-only: embeds the preregistered config and the
acceptance JSON verbatim. No experiment is run and no existing output is changed.
"""
from __future__ import annotations

import html
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "phti_replication.toml"
ACC = ROOT / "outputs" / "phti_engineering_acceptance.json"
OUT = ROOT / "outputs" / "phti_replication_status.html"


def e(x) -> str:
    return html.escape(str(x), quote=True)


def table(headers, rows) -> str:
    h = "".join(f"<th>{e(c)}</th>" for c in headers)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"


def fold(title, body) -> str:
    return f"<details><summary>{e(title)}</summary>{body}</details>"


CSS = """
:root{--ink:#1c2126;--muted:#5c6672;--line:#e0ddd4;--bg:#fbfaf7;--accent:#185FA5;--warn:#a8442a;--good:#1c7a55}
*{box-sizing:border-box}body{margin:0 0 70px;background:var(--bg);color:var(--ink);
font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.72;font-size:15px}
.wrap{max-width:1050px;margin:0 auto;padding:0 26px}
header{background:linear-gradient(135deg,#12365c,#185FA5);color:#fff;padding:34px 0 26px;margin-bottom:22px}
h1{font-size:26px;margin:0 0 8px}h2{font-size:19px;margin:30px 0 12px;padding-bottom:7px;border-bottom:2px solid var(--accent)}
h3{font-size:16px;margin:20px 0 8px;color:#12365c}p{margin:9px 0}
code{background:#f2efe8;padding:1px 5px;border-radius:4px;font-size:13px}
pre{background:#20262e;color:#eef2f6;padding:13px 15px;border-radius:8px;overflow:auto;font-size:12px;line-height:1.55;max-height:520px}
table{border-collapse:collapse;width:100%;margin:11px 0 17px;background:#fff;font-size:13.5px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#eef2f7}tbody tr:nth-child(even){background:#fcfcfa}
.box{background:#fff;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:6px;padding:11px 15px;margin:13px 0}
.box.warn{border-left-color:var(--warn);background:#fff8f5}.box.good{border-left-color:var(--good);background:#f5fbf8}
.formula{background:#f4f6f9;border:1px solid #d8dee6;border-radius:6px;padding:11px 15px;margin:11px 0;font-family:Georgia,serif;font-size:15px}
.pill{display:inline-block;background:#e8eef6;color:#12365c;border-radius:20px;padding:2px 10px;font-size:12px;margin:2px 3px}
.pill.w{background:#fae9e4;color:#8a3520}.pill.g{background:#e4f2eb;color:#1c7a55}
details{background:#fff;border:1px solid var(--line);border-radius:6px;margin:9px 0;padding:8px 14px}
summary{cursor:pointer;font-weight:600;color:#12365c;font-size:14px}
ul,ol{padding-left:22px}li{margin:5px 0}.muted{color:var(--muted)}
.tag{font-size:11.5px;padding:1px 7px;border-radius:4px;font-weight:600;white-space:nowrap}
.tag.add{background:#fae9e4;color:#8a3520}.tag.ok{background:#e4f2eb;color:#1c7a55}
.footer{border-top:1px solid var(--line);margin-top:34px;padding-top:13px;font-size:12.5px;color:var(--muted)}
"""


def main() -> None:
    cfg = tomllib.loads(CFG.read_text(encoding="utf-8"))
    acc = json.loads(ACC.read_text(encoding="utf-8"))
    p: list[str] = []
    A = p.append

    A(f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A股 PHTI 复现：预登记方案与工程验收</title><style>{CSS}</style></head><body>
<header><div class="wrap"><h1>A 股 PHTI 复现：预登记方案与工程验收</h1>
<div>Baitinger &amp; Flegel (2021) 方法链移植 · 版本 {e(cfg['protocol']['version'])}</div>
<div style="margin-top:9px"><span class="pill">只读设计文件</span>
<span class="pill g">工程验收通过</span><span class="pill w">绩效未计算</span>
<span class="pill w">2025 测试封存未读</span></div></div></header><div class="wrap">""")

    # 1 status
    A("<h2 id='s1'>1. 现在做到哪一步了</h2>")
    A(table(["阶段", "状态", "产物"], [
        ["① 原文精读", "<span class='tag ok'>完成</span> 全文/表格/关键页图像逐字核对，含 5 个复现歧义", "<code>outputs/phti_close_reading.html</code>"],
        ["② 数据可行性审计", "<span class='tag ok'>完成</span> p16 5283 天、p27 3070 天、000300 5302 行、263 个月末", "本报告第 3 节"],
        ["③ 预登记冻结", "<span class='tag ok'>完成</span> 13 类口径、参数、评价与时间边界，看绩效之前写定", "<code>config/phti_replication.toml</code>"],
        ["④ 指标管线 + 工程验收", "<span class='tag ok'>完成</span> Wasserstein 5 项单元测试、因果对齐、确定性复算全过", "<code>outputs/phti_engineering_acceptance.json</code>"],
        ["⑤ <b>正式绩效回测</b>", "<span class='tag add'>未运行</span> 等用户确认 3 个口径后统一执行", "—"],
    ]))
    A("""<div class="box warn"><b>为什么停在这里：</b>项目此前已明确「任何新实验须先与用户讨论设计再执行」。
本轮把设计、代码、指标序列和验收都做完，但<b>没有把任何市场收益与信号拼在一起</b>——
验收脚本从未加载股票指数，也未计算收益、IC、夏普或回归。
这不是拖延，是为了避免重演「未经讨论就跑确认性实验」的流程错误。</div>""")

    # 2 mapping
    A("<h2 id='s2'>2. 原文 → A 股映射（差异等级）</h2>")
    A(table(["原文", "A 股可用", "等级", "说明"], [
        ["10 / 30 个美国行业组合日总收益", "申万一级行业指数日收盘：p16（16 行业，2005 起）、p27（27 行业，2014 起）", "C", "行业数量/分类体系不同；申万为<b>价格指数</b>不含股息"],
        ["S&amp;P 500 价格指数", "沪深300 000300（2005 起）；稳健：万得全A、Gate 0 冻结合成指数", "B", "主标的拟 000300"],
        ["T-Bill 月收益", "本地无国债/货币基金序列", "C", "主口径现金收益 = 0；另做年化 2% 敏感性"],
        ["VIX", "本地无期权隐含波动率", "C", "用过去 20 日<b>已实现</b>波动率代理，明确不是前瞻 VIX"],
        ["OTI（Mahalanobis）", "同行业面板可完整实现", "A", "关键的非 TDA 对照"],
        ["343 个月样本外", "p16 可得约 175 个月（2010-07—2024-12）、p27 约 66 个月", "C", "<b>样本长度约为原文一半或更少</b>"],
        ["1991-06 起样本外", "2025-01 起按项目纪律封存", "C", "不在开发期读取测试集"],
    ]))
    A("""<div class="box"><b>结论：</b>这是<b>方法链移植</b>，不是精确复现。
行业分类、股息口径、标的、现金、波动基准、样本长度都有不可消除的差异；
结果无论正负，都只能说明「这条链在这份 A 股面板上如何」，不能证伪或证实原文。</div>""")

    # 3 preregistration
    A("<h2 id='s3'>3. 预登记：看结果之前冻结的口径</h2>")
    d, pc, sg, pf, ev, tb = (cfg["distance"], cfg["pointcloud"], cfg["signal"],
                             cfg["portfolio"], cfg["evaluation"], cfg["time_boundary"])
    rows = [
        ["1", "Wasserstein 阶数 p", f"p = <b>{e(d['order_p'])}</b>（原文公式写 p-th 但<b>未给值</b>）", "p=2、bottleneck 对照"],
        ["2", "内范数", f"<b>{e(d['internal_norm'])}</b>（严格照公式 8）", "L2 对照"],
        ["3", "点数不等", f"增广对角线 + 匈牙利最优指派，代价 = {e(d['diagonal_cost'])}", "原文只写「双射」，点数不等时严格双射不存在"],
        ["4", "H₀ 无穷死亡点", f"<b>{e(d['essential_class'])}</b>", "替换为 filtration 上界 2 倍"],
        ["5", "维度合并", f"<b>{e(d['combine_dimensions'])}</b>", "拼接成一个图（对应正文「三列矩阵」描述）"],
        ["6", "点云", f"窗口 <b>{e(pc['window_days'])}</b> 交易日、欧氏距离、VR、maxdim={e(pc['maxdim'])}（H₀+H₁）", "H₀/H₁ 消融（原文未做）"],
        ["7", "收益口径", f"拓扑输入 {e(cfg['returns']['pointcloud_input'])}；组合 {e(cfg['returns']['portfolio_return'])}", "原始百分数收益、窗口内逐维标准化"],
        ["8", "尺度归一", "原始收益（忠实原文）", "<b>专门检验 W 是否只是波动放大</b>"],
        ["9", "信号", f"W → {e(sg['sma_days'])} 日 SMA → 月末 → 含当月 {e(sg['history_month_ends'])} 个月末 midrank 分位 → 下月仓位", "「过去 60 + 当前」窗口对照"],
        ["10", "仓位", f"WCP {e(list(pf['worst_case_protection']))} / FE {e(list(pf['flexible_exposure']))} / FEL {e(list(pf['flexible_levered']))}", "FEL 无融资利率，仅展示与 0 利率敏感性"],
        ["11", "标的/成本", f"{e(pf['primary_equity'])}；现金 {e(pf['cash_return'])}；每边成本 {e(pf['cost_per_side'])}", "万得全A、冻结合成指数；零成本/0.3% 对照"],
        ["12", "评价", "原文 8 类 + <b>时序 IC、收益/波动回归、事件级触发/误报/提前量、换手、区块自助、净成本</b>", "买入持有、OTI、RV 基准；5×5 网格全披露 + 联合校正"],
        ["13", "时间边界", f"开发期 ≤ {e(tb['development_end'])}；<b>{e(tb['test_start'])} 起封存</b>", "仅在设计与参数冻结、且讨论后统一读取一次"],
    ]
    A(table(["#", "决策项", "主口径（冻结）", "敏感性 / 备注"], rows))
    A("""<div class="box warn"><b>两个必须记住的原文歧义：</b>
① 公式 (8) 的 <b>p 值全文没给</b>；② 公式写「两图之间的双射」，但相邻两天持续图点数通常不等，
严格双射不存在——所以「精确复现」在数学上就不可实现，只能做「合理实现 + 敏感性全披露」。</div>""")

    # 4 acceptance
    A("<h2 id='s4'>4. 工程验收结果（不含任何绩效）</h2>")
    arows = []
    for key, v in acc["panels"].items():
        arows.append([
            f"<b>{e(key)}</b>（{e(v['role'])}）",
            f"{v['n_industries']} 行业 / {v['aligned_trading_days']} 交易日<br>{e(v['first_date'])} — {e(v['last_date'])}",
            f"{v['daily_W']['n_finite']} 个有限 W（全非负、非常数）<br>首个 W 索引 {v['warmup_checks']['first_finite_W_index']}、首个 SMA 索引 {v['warmup_checks']['first_finite_SMA_index']}",
            f"<b>{v['n_monthly_signals']}</b> 个月度信号<br>{e(v['first_signal_date'])} → {e(v['last_signal_date'])}",
            e(v["quintile_counts"]),
        ])
    A(table(["面板", "数据覆盖", "指标序列", "信号", "五分位计数"], arows))
    A(table(["检查项", "结果"], [
        ["Wasserstein 单元测试（5 例，含已知解析答案）", "<span class='tag ok'>全过</span>"],
        ["warm-up 边界：首个 W = 60、首个 SMA = 119 索引", "<span class='tag ok'>通过</span>"],
        ["月末值 = 该月最后一个完整交易日", "<span class='tag ok'>通过</span>"],
        ["因果：每个信号日严格早于其作用月首日", "<span class='tag ok'>0 违例</span>"],
        ["确定性：前 3 个窗口重算逐位一致", f"<span class='tag ok'>{e(acc['determinism_check']['passed'])}</span>"],
        ["开发期数据是否混入 2025+", "<span class='tag ok'>无</span>"],
        ["是否加载股票指数 / 计算任何绩效", "<span class='tag ok'>否</span>"],
    ]))
    A(f"""<div class="formula">月末 m 的 PHTI<sub>m</sub> = SMA60(W)<sub>该月最后交易日</sub>
→ 与 [m−59 … m] 共 60 个月末值比较 midrank ρ
→ 五分位 q → 表 2 仓位 → 作用于 <b>m+1 月</b>收益</div>""")
    A("""<p class="muted">指标序列已落盘（<code>phti_daily_w_p16.csv</code> /
<code>phti_daily_w_p27.csv</code> / <code>phti_monthly_signals_*.csv</code>），
供正式回测直接读取；这些文件只有信号，没有市场收益，也没有任何评价数字。</p>""")

    # 5 decisions
    A("<h2 id='s5'>5. 需要你拍板的 3 个口径</h2>")
    A("""<p>以下三个问题会改变正式回测的输入，因此必须在看到任何绩效之前定下来。
每项我都给了推荐值；你只要说「按推荐」或指出要改哪一项即可。</p>""")
    A(table(["#", "问题", "推荐（默认）", "其他可选与代价"], [
        ["1", "<b>主行业面板与评价区间</b>",
         "p16 作主分析（16 行业、2005 起、约 175 个月信号），p27 作短样本稳健性（约 66 个月）；两者各自独立，不拼接变维坐标",
         "若只用 p27，样本太短难做 60 月分位；若另造「10 行业合并」，需引入主观分类规则，且会偏离冻结面板"],
        ["2", "<b>权益标的与现金</b>",
         "沪深300 000300（价格指数，2005 起，与 S&amp;P 500 概念最近）；现金收益 = 0；每边成本 0.1%",
         "万得全A 只到 2025-05 且 2012 起，会缩短开发期；冻结合成指数是 Gate 0 口径但与原文「大盘」语义不同；T-Bill 本地无数据"],
        ["3", "<b>2025 测试边界</b>",
         "继续封存：开发期只到 2024-12-31，正式回测也只评价开发期；2025 起等设计冻结并讨论后统一读取一次",
         "若现在读 2025，就失去一段完全未参与决策的时间外样本，且可能与 Gate 0 的封存纪律冲突"],
    ]))
    A("""<div class="box good"><b>你确认后我会一次性执行：</b>
① 三套仓位规则 × 三面板 × 三基准（买入持有 / OTI / RV）；
② 年化、波动、夏普、回撤、CER；③ 时序 IC、公式 (5)(6) 回归、区块自助区间；
④ 事件级触发次数、误报/年、提前量、换手与净成本；
⑤ 尺度归一消融、H₀/H₁ 消融、p 与范数敏感性、5×5 参数网格全披露 + 联合校正。
<b>全部按预登记口径跑，不按结果反选；无论正负都完整披露。</b></div>""")

    # 6 boundaries
    A("<h2 id='s6'>6. 边界声明</h2>")
    A("""<ul>
<li>本线是<b>独立新支线</b>，不修改 <code>config/study.toml</code>（Gate 0 冻结）、不读取 Gate 1 的 OOF 评分、不读取 2025 最终测试、不启动 Gate 2。</li>
<li>兴业复现线（相关网络 H₂、N≤1）与 PHTI（状态点云 H₀/H₁、相邻持续图距离）是<b>两条不同的点云</b>，结论互不外推。</li>
<li>原文是<b>波动率择时</b>，不是危机预警；不能把它的夏普改善当成 Gate 0 危机标签下的同类证据。</li>
<li>本轮所有工作为样本内工程与探索性准备；<b>没有任何有效性结论</b>，也不构成「TDA 无效」或「原文有误」的判决。</li>
<li>N 的精确定义、Wind 逐日行业名单、万得四级分类仍未取得；这些缺口只影响兴业线，不影响本线。</li>
</ul>""")

    A("<h2 id='sa'>附录 A：预登记配置全文</h2>")
    A(f"<pre><code>{e(CFG.read_text(encoding='utf-8'))}</code></pre>")
    A("<h2 id='sb'>附录 B：工程验收 JSON 全文</h2>")
    A(f"<pre><code>{e(json.dumps(acc, ensure_ascii=False, indent=2))}</code></pre>")
    A(fold("展开：生成的信号序列文件清单",
           "<pre><code>" + e("\n".join(acc["outputs"])) + "</code></pre>"))

    A("""<div class="footer">单文件离线 HTML：样式内联，无外链、无脚本、无图片依赖。
生成脚本 <code>tda_project/src/phti_replication/build_phti_replication_status.py</code>（只读打包）；
配置与验收 JSON 逐字内嵌。<b>绩效未计算、2025 测试未读取、Gate 1 暂停、Gate 2 未启动。</b></div>""")
    A("</div></body></html>")

    text = "\n".join(p)
    assert "http://" not in text and "https://" not in text
    assert "<script" not in text
    assert text.count("<table") == text.count("</table>")
    assert text.count("<details>") == text.count("</details>")
    assert text.count("<div") == text.count("</div>")
    OUT.write_text(text, encoding="utf-8")
    print(json.dumps({
        "output": str(OUT), "bytes": len(text.encode("utf-8")),
        "sections": text.count("<h2"), "tables": text.count("<table"),
        "details": text.count("<details>"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
