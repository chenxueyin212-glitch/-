"""Build a single-file offline HTML report for the crisis ±20-day data export.

Read-only: consumes the all17 chart_data.json / manifest.json / six CSVs
produced by export_crisis_context_all17.py. Includes events 1 / 3 / 16 as
DESCRIPTIVE ONLY. No data is recomputed or scored.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
PREFIX = "crisis_context_v04_all17_"

chart = json.loads((OUT / (PREFIX + "chart_data.json")).read_text(encoding="utf-8"))
manifest = json.loads((OUT / (PREFIX + "manifest.json")).read_text(encoding="utf-8"))
ov = chart["overview"]


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


n_ev = len(ov)
obs = {
    "w_post_gt_crisis": sum(f(r["a16_W_t_post20_mean"]) > f(r["a16_W_t_crisis_mean"]) for r in ov),
    "w_post_gt_pre": sum(f(r["a16_W_t_post20_mean"]) > f(r["a16_W_t_pre20_mean"]) for r in ov),
    "w_crisis_gt_pre": sum(f(r["a16_W_t_crisis_mean"]) > f(r["a16_W_t_pre20_mean"]) for r in ov),
    "crisis_up": sum(f(r["crisis_cum_pct"]) > 0 for r in ov),
    "post_down": sum(f(r["post20_cum_pct"]) < 0 for r in ov),
    "pre_up": sum(f(r["pre20_cum_pct"]) > 0 for r in ov),
    "h2_crisis_gt_pre": sum(f(r["b_h2_count_crisis_mean"]) > f(r["b_h2_count_pre20_mean"]) for r in ov),
    "peak_in_post": sum(int(r["a16_W_t_peak_offset_from_onset"]) >= int(r["n_crisis_days"]) for r in ov),
    "peak_in_pre": sum(int(r["a16_W_t_peak_offset_from_onset"]) < 0 for r in ov),
    "mean_crisis": sum(f(r["crisis_cum_pct"]) for r in ov) / n_ev,
    "mean_post": sum(f(r["post20_cum_pct"]) for r in ov) / n_ev,
    "mean_pre": sum(f(r["pre20_cum_pct"]) for r in ov) / n_ev,
}
_mx = max((f(r["crisis_cum_pct"]), r["event_id"], r["onset"]) for r in ov)
obs["crisis_up_max"] = f"事件 {_mx[1]}（{_mx[2]}，{_mx[0]:+.2f}%）"

files_desc = [
    ("center_day_outcomes.csv", "270 行：每个危机日一行，前后 20 日的行情结果 + 18 个摘要指标的前/中/后均值", "主表"),
    ("event_overview.csv", "17 行：每个事件一行，前 20 / 危机段 / 后 20 三段行情与关键摘要", "事件级去重视图"),
    ("event_phase_metrics.csv", "51 行 = 17 事件 × 3 段：每段行情统计与 18 个摘要的均值/中位数", "分段统计"),
    ("event_windows.csv", "950 行 = 17 × (20 + 事件天数 + 20)：事件窗逐日全字段明细", "逐日明细"),
    ("daily_windows.csv", "11070 行 = 270 × 41：每个危机日为锚的 ±20 交易日逐日全字段明细", "逐日明细（重叠）"),
    ("relative_profile.csv", "2829 行：3 种对齐锚点 × 41 个相对日 × 23 指标的均值/中位/四分位/极值", "剖面统计"),
]
file_rows = []
for suffix, desc, tag in files_desc:
    name = PREFIX + suffix
    meta = manifest["files"][name]
    file_rows.append(
        f'<tr><td><a href="{name}" download>{name}</a></td><td>{tag}</td>'
        f'<td class="num">{meta["rows"]}</td><td class="num">{meta["cols"]}</td>'
        f'<td>{html.escape(desc)}</td></tr>')

OBS_HTML = f"""
<div class="obs">
  <p><b>1. 危机标签是前瞻的，不是"正在下跌"。</b>{n_ev} 个事件里有 <b>{obs['crisis_up']}/{n_ev}</b> 个
  危机段累计收益为正（最高为 {obs['crisis_up_max']}），因为冻结标签的定义是"未来 20 个交易日内
  相对 t 日最低累计简单收益 ≤ −10%"。所以危机段里价格上涨完全可能，不要把这段当成已实现跌幅。</p>
  <p><b>2. 状态点云·16行业·相邻两日持续图 Wasserstein 距离：危机段通常不是峰值所在。</b>
  单看这个指标，{obs['w_crisis_gt_pre']}/{n_ev} 个事件的危机段均值高于前 20 日（这个方向确实抬升），
  但 {obs['w_post_gt_crisis']}/{n_ev} 个事件的后 20 日均值又高于危机段、
  {obs['w_post_gt_pre']}/{n_ev} 个高于前 20 日；整窗峰值 {obs['peak_in_post']}/{n_ev} 个落在后 20 日段、
  {obs['peak_in_pre']}/{n_ev} 个落在前 20 日段、仅 {n_ev - obs['peak_in_post'] - obs['peak_in_pre']}/{n_ev} 个落在危机段内。
  所以"危机中尺度摘要<b>全维同步跳升并见顶</b>"的形态在这张表里看不到，W_t 更像是滞后抬升。
  【整理者推测，未验证】一个可能原因是 w=10 窗口 + 相邻持续图距离带来的机械滞后；本轮没有做任何分解或检验。
  <strong>以上全部是逐格读数，不是显著性检验结果。</strong></p>
  <p><b>3. 后 20 日多为下跌，但不是全部。</b>{n_ev} 个事件后 20 日累计收益 {obs['post_down']}/{n_ev} 个为负；
  {n_ev} 个事件算术平均：前 20 日 {obs['mean_pre']:+.2f}%、危机段 {obs['mean_crisis']:+.2f}%、
  后 20 日 {obs['mean_post']:+.2f}%（等事件权重、未加权、未检验）。</p>
  <p><b>4. 相关网络·H2 二维空腔数量方向混合。</b>危机段均值高于前 20 日的只有 {obs['h2_crisis_gt_pre']}/{n_ev} 个事件，
  其余下降；不存在统一的"危机时 N 上升"形态。</p>
  <p class="warn">以上四条是把表格数字念出来，属于样本内描述。<b>不是检验结果，不是绩效，不构成
  "TDA 对 A 股危机预警有效/无效"的任何推断。</b>270 个日级窗口互相重叠（长事件贡献几十个窗口），
  任何日级平均都会被长事件主导；要看形态请以 17 个事件的去重视图为准。</p>
</div>
"""

payload_json = json.dumps(chart, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>危机样本前后 20 交易日逐日数据 · 17 段完整版（描述性对账）</title>
<style>
:root{
  --bg:#f5f6f8; --card:#ffffff; --ink:#1f2329; --muted:#646a73; --line:#e5e7eb;
  --blue:#2b5fcc; --purple:#7a52c7; --orange:#d9822b; --teal:#16827a;
  --up:#c62828; --down:#1b8a5a; --crisis:#fff1ef; --crisisline:#d93026;
  --chip:#f0f2f5;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
 font-size:14px;line-height:1.65}
.wrap{max-width:1320px;margin:0 auto;padding:28px 20px 80px}
header h1{font-size:25px;margin:0 0 6px;letter-spacing:.3px}
header .sub{color:var(--muted);font-size:13px}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 6px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:10px 16px;min-width:132px}
.kpi b{display:block;font-size:21px;line-height:1.25;font-variant-numeric:tabular-nums}
.kpi span{color:var(--muted);font-size:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:20px 22px;margin:16px 0}
.card h2{font-size:17px;margin:0 0 12px;padding-bottom:9px;border-bottom:1px solid var(--line)}
.card h3{font-size:14px;margin:20px 0 8px;color:var(--muted)}
p{margin:8px 0}
code{background:var(--chip);padding:1px 5px;border-radius:4px;font-size:12px;
 font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
.small{font-size:12.5px;color:var(--muted)}
.warn{background:#fff8e6;border-left:3px solid #e0a020;padding:10px 14px;border-radius:5px}
.boundary{background:#eef4ff;border-left:3px solid var(--blue);padding:10px 14px;border-radius:5px}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{background:#f7f8fa;position:sticky;top:0;z-index:2;cursor:pointer;user-select:none;font-weight:600;color:#3d4450}
th:hover{background:#eef1f6}
td.num,th.num{text-align:right;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
tbody tr:nth-child(even){background:#fafbfc}
tbody tr:hover{background:#eef3ff}
tr.row-crisis{background:var(--crisis)!important}
tr.row-crisis:hover{background:#ffe4e0!important}
.pos{color:var(--up);font-weight:600}
.neg{color:var(--down);font-weight:600}
.scroll{overflow:auto;max-height:520px;border:1px solid var(--line);border-radius:7px}
.scroll.wide{max-height:none}
a{color:var(--blue);text-decoration:none}
a:hover{text-decoration:underline}
select,input[type=text]{border:1px solid var(--line);border-radius:6px;padding:5px 9px;background:#fff;
 color:var(--ink);font-size:13px;margin-right:8px}
select{max-width:460px}
#evMetric,#profMetric{max-width:430px}
label.ck{margin-right:14px;font-size:13px;cursor:pointer}
.ctrl{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:10px 0 14px}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;background:var(--chip);color:#4a5260}
.pill.crisis{background:#ffe0dc;color:#a5231a}
.pill.pre20{background:#e6edfb;color:#254a9e}
.pill.post20{background:#e2f3ea;color:#146b46}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:2px 0 8px}
.legend i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:5px;border-radius:2px}
.chartbox{border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:#fff;margin:10px 0}
svg{display:block;width:100%;height:auto}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:980px){.grid2{grid-template-columns:1fr}}
.dict dt{font-weight:600;margin-top:10px;font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
.dict dd{margin:2px 0 0 14px;color:#4a5260;font-size:12.5px}
footer{color:var(--muted);font-size:12px;border-top:1px solid var(--line);margin-top:26px;padding-top:14px}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>危机样本前后 20 交易日 · 17 段完整版逐日全量数据</h1>
  <div class="sub">v0.4 冻结标签 / 真 881001.WI 行情 / v0.3 冻结 w=10 持续摘要 &nbsp;·&nbsp;
  只读描述性导出，不含任何检验、评分或绩效 &nbsp;·&nbsp; 本版补入事件 1 / 3 / 16（仅描述性，不进判定） &nbsp;·&nbsp; 生成于 __GEN__</div>
</header>

<div class="kpis">
  <div class="kpi"><b>270</b><span>危机中日级样本（全部 17 段）</span></div>
  <div class="kpi"><b>17</b><span>危机事件（去重）</span></div>
  <div class="kpi"><b>11,070</b><span>日级 ±20 窗口行</span></div>
  <div class="kpi"><b>950</b><span>事件窗逐日行</span></div>
  <div class="kpi"><b>2015-07-01 → 2025-03-28</b><span>样本区间</span></div>
  <div class="kpi"><b>2025-04-28</b><span>最晚窗口日</span></div>
</div>

<p class="small">本页所有下拉、表头、图例、事件与指标名称均已改为<b>中文全称</b>；
<b>鼠标悬停表头或下拉项可查看对应的 CSV 原字段名</b>。CSV 列名保持原样，方便与脚本、manifest 对照。</p>

<div class="card">
  <h2>一、先把口径钉死（读表之前必看）</h2>
  <div class="boundary">
    <p><b>① "危机中"是前瞻标签，不是已实现的下跌。</b>冻结口径：未来 20 个交易日内，基准相对 t 日
    最低累计简单收益 ≤ −10% 则 Y_t=1。所以"危机段"是"未来会跌"的那些日子，段内出现上涨、
    甚至整段累计为正都是定义内的正常现象。</p>
    <p><b>② 20 天 = 标签交易日历的 20 行</b>（3339 天日历，与危机掩码、TDA 摘要同一套日历），
    不是自然日，也不是 Wind 交易日。Wind 在本报告覆盖区间内有 <b>18 个额外交易日</b>（行业面板缺失），
    这些日不是标签日；因此<b>相邻标签交易日收益</b>（<code>ret_step_pct</code>）是相邻标签日收盘价比值，
    个别步长会跨 2 个 Wind 交易日，明细里有<b>步长内 Wind 交易日数</b>与<b>前后 20 日跨过的 Wind 交易日数</b>可查。</p>
    <p><b>③ 两套点云必须分开读。</b>「状态点云线」（表中以 <code>a16_*</code> / <code>a27_*</code> 开头）
    （点 = 交易日，坐标 = 当日 16/27 个行业收益，w=10；主指标为<b>相邻两日持续图 Wasserstein 距离</b>，
    v0.2 的 p=2 / L∞ 实现）。「相关网络线」（表中以 <code>b_*</code> 开头）是<b>兴业相关网络</b>
    （点 = 申万行业，坐标 = 过去 10 日收益序列，距离 √(2(1−ρ))；
    其中「H2 二维空腔数量」就是兴业口径的 N）。
    两者是不同的拓扑对象，不能互相外推，也不能把一线的结论套到另一线。</p>
    <p><b>④ 价格与收益。</b>万得全 A 真实 881001.WI 日线的开高低收；收益一律为<b>简单收益（%）</b>，
    与市场基准/危机标签口径一致，不是对数收益。<b>窗口累计收益</b>与<b>窗口内回撤</b>
    的基准都是窗口 −20 日的<b>前一个</b>标签日收盘。</p>
    <p><b>⑤ 摘要列是 v0.3 冻结的 w=10 逐日值。</b>v0.4 只换了标签与基准行情，没有重算 TDA，
    所以本页所有摘要数值与 v0.3 判定网格同源，可直接对照。</p>
    <p><b>⑥ 边界。</b>全部窗口最晚 2025-04-28，早于 2025-05-30，<b>未触碰 2025 封存段</b>；
    Gate 1 仍暂停、2025 最终测试集未读取、Gate 2 未启动、PHTI 正式绩效未运行。
    本页没有 bootstrap、p 值、IC、夏普、PR-AUC、仓位或阈值反选。</p>
  </div>
  <h3>两张明细表的"前后 20 天"怎么读</h3>
  <p class="small">· <b>中心日表</b>（270 行）：<b>前 20 日累计收益</b> = 中心日前第 20 个标签日收盘 → 中心日收盘；
  <b>后 20 日累计收益</b> = 中心日收盘 → 后第 20 个标签日收盘。摘要列的「前 20 日均值」
  取中心日前 20 日（不含中心日），「中心日当天」是中心日，「后 20 日均值」取后 20 日（不含中心日）。<br>
  · <b>事件表</b>（17 行）：前 20 段 = [起点−20, 起点−1]，危机段 = [起点, 结束日]，后 20 段 = [结束日+1, 结束日+20]；
  段累计收益以上一段最后一个收盘为起点，三段可复利相接。<br>
  · <b>270 个日级窗口高度重叠</b>：49 天的事件 1、42 天的事件 12 各自贡献几十个窗口。日级平均会被长事件主导，
  要看"是否普遍"请用 17 事件的去重视图；日级明细只供逐日核查。</p>
</div>

<div class="card">
  <h2>二、六个数据文件（与本报告同目录，可直接下载）</h2>
  <div class="scroll"><table><thead><tr><th>文件</th><th>类型</th><th class="num">行数</th><th class="num">列数</th><th>内容</th></tr></thead>
  <tbody>__FILES__</tbody></table></div>
  <p class="small">所有 CSV 均为 UTF-8 with BOM，Excel 直接打开不乱码；
  <code>crisis_context_v04_manifest.json</code> 记录来源、口径、校验与 sha256。
  空单元格 = 该日该指标无值（不是 0）。</p>
</div>

<div class="card">
  <h2>三、17 个事件一览（事件级去重视图）</h2>
  <div class="ctrl"><label class="ck"><input type="checkbox" id="ovColor" checked> 收益着色（涨红 / 跌绿）</label>
  <span class="small">点击表头可排序</span></div>
  <div id="ovTable" class="scroll"></div>
  <p class="small">本版含全部 17 段，事件编号 1–17 连续。其中<b>事件 1 左截断、事件 3 与事件 16 由你指定排除</b>，
  三段只在描述性表格与查看器里出现，<b>不进任何主判据、显著性计数或事件级去重</b>；14 段冻结产物原样保留、未覆盖。
  <b>全窗口累计收益</b>以窗口基准日（前 20 段的前一交易日）收盘为起点。</p>
</div>

<div class="card">
  <h2>三·补、事件 1 / 3 / 16：原来为什么没有，现在补进来了</h2>
  <p><b>原来为什么没有。</b>上一版只导出 14 个判定用事件，冻结口径是层层收窄的：
  17 段冻结危机（270 日）→ 事件 1（2015-07-01）左截断、<code>crisis_in_usable=0</code>，整段不可用 →
  16 段 / 221 日 → 事件 3（2016-02-17）与事件 16（2024-12-12）由你指定排除 →
  <b>14 段 / 214 日</b>进主判据。本版把三段按完全相同的 ±20 交易日口径补进来，
  <b>仅作描述性补全，不进任何主判据、显著性计数或事件级去重</b>；14 段那一套产物原样保留、未覆盖。</p>

  <h3>事件 1｜2015-07-01 至 2015-09-11｜49 个危机中日</h3>
  <p><b>冻结状态：</b>左截断，从来不是可用事件。<b>公开定性：</b>落在 2015 年杠杆牛破灭／股灾的第一轮急跌中段。
  2015-06-12 指数见顶，6/15 起清理场外配资引发踩踏式下跌，出现千股跌停与千股停牌；8/11 汇改人民币贬值触发第二轮恐慌。
  两融余额 2015-06 峰值约 2.27 万亿，三周内缩水约 35%。
  <b>关键限制：</b>起点日 7/1 本身没有被单独命名的事件，这些定性针对的是它所处的整轮股灾。</p>
  <p class="small"><b>出处与证据等级：</b>
  <a href="https://app-web.chnfund.com/wind/202204/t20220428_4049655.html" target="_blank" rel="noopener">中国基金报《星石深度｜熊市的本质和终结》</a>（2022-04-28，C 级）、
  <a href="https://fmr.cfae.cn/CN/Y2022/V0/I12/11" target="_blank" rel="noopener">《深化股市交易制度改革，防范金融风险》</a>（《金融市场研究》2022，A 级）、
  <a href="https://www.uscc.gov/sites/default/files/Research/Issue%20brief%20-%20China%27s%20Stocks%20Fall%20Again.pdf" target="_blank" rel="noopener">USCC 政策简报（2016-01-14，A 级）</a>、
  中央财经大学学报《行业间波动率共同风险分担与特质性风险传染》（A 级）。</p>

  <h3>事件 3｜2016-02-17 至 2016-02-24｜6 个危机中日</h3>
  <p><b>冻结状态：</b>原本属于 16 个可用事件，由你指定排除（D3）。<b>公开定性：</b>2016 年 2 月末二次探底／银行间流动性冲击。
  节后降准预期落空，缴税与逆回购集中到期使资金面骤紧（2/25 隔夜国债逆回购盘中涨逾 500%），叠加一线楼市分流资金、
  人民币贬值预期、注册制与创业板退市风险担忧、公募高仓位被迫减仓；2/29 上证跌 2.86%、创业板跌 6.69%，
  当晚央行宣布 3/1 起普遍下调存款准备金率 0.5 个百分点。
  <b>关键限制：</b>起点 2/17 处在节后反弹段，公开材料密集覆盖的是其 20 日窗口末端的 2/25–2/29 暴跌，
  <b>起点日没有独立命名定性</b>；且这些材料全是机构观点与媒体报道，未找到同行评议的因果识别。</p>
  <p class="small"><b>出处与证据等级：</b>
  <a href="https://m.chinanews.com/wap/detail/chs/zw/7778004.shtml" target="_blank" rel="noopener">中新社《经济观察：降准能"扶起"三月的中国股市吗？》</a>（2016-02-29，C 级含机构采访）、
  <a href="https://cs.com.cn/tzjj/tjdh/201603/t20160305_4917596.html" target="_blank" rel="noopener">中证网《A 股再遭重创触及阶段新低 央行降准改善市场预期》</a>（2016-03-05，C 级）、
  中证网《私募谈暴跌：反弹就此结束？》（2016-02-29，C 级）、经济参考网《沪指涨近 2% 收复 2700 点》（2016-03-01，C 级）。</p>

  <h3>事件 16｜2024-12-12｜1 个危机中日</h3>
  <p><b>冻结状态：</b>原本属于 16 个可用事件，由你指定排除（D3）。<b>公开定性：</b>微盘股年内第三次崩盘／最严退市新规前的结构性去杠杆。
  华尔街见闻明确写「12 月 12 日至 12 月 25 日下跌近 15%」「本次 12 月 12 日以来是年内第三次小微盘的崩盘」；
  财联社写「9 月 24 至 12 月 12 日高位期间累计涨幅近 67%」。成因：退市新规 2025-01-01 正式实施、
  网传退市风险名单引发舆情、年末资金回笼与大小盘切换、获利盘止盈；12/23 微盘股指数跌超 7%、逾 200 股跌停、
  四大行齐创历史新高，证监会当晚答记者问。
  <b>这三段里唯一与公开复盘的崩盘起点日期精确重合的一段</b>，也是定性最扎实的一段。</p>
  <p class="small"><b>出处与证据等级：</b>
  <a href="https://m.cls.cn/detail/1897692" target="_blank" rel="noopener">财联社《微盘股又大跌，这次有何不一样？》</a>（2024-12-23，C 级）、
  <a href="https://wallstreetcn.com/articles/3737875" target="_blank" rel="noopener">华尔街见闻《微盘股的暴跌及日历效应》</a>（C 级，内含国信证券 12 月风格统计，B 级）、
  <a href="https://www.21jingji.com/article/20241224/herald/390b1844e11e7ed62b17340fe1d71f38.html" target="_blank" rel="noopener">21 经济网《最严退市新规将实施》</a>（2024-12-24，C 级）、
  国家金融与发展实验室《监管新规开启 A 股新征程》（A/B 级）。</p>

  <p class="warn"><b>读法边界。</b>证据等级沿用项目内《A 股 vs 美股：危机来临时／牛市／熊市的市场状态对照》的定义：
  A = 同行评议期刊／交易所研究，B = 券商投研，C = 财经媒体。这些定性<b>全部是事后归因、含未来信息</b>，
  不能用于分组、不能进任何显著性检验、不能参与阈值或窗口选择。本页只是把外部材料与统计构造并排陈列，
  并显式登记二者的<b>粒度错配</b>：公开研究按「调整周期／重大事件」命名，不会按这 17 个由
  −10%/20 交易日前瞻阈值切出的起点逐段命名。全部 17 段里，只有事件 11（2021-02-18 抱团瓦解拐点）与
  事件 16（2024-12-12 微盘崩盘起点）与公认事件日期精确重合。</p>
</div>

<div class="card">
  <h2>四、相对日剖面：−20 → +20 的平均形态</h2>
  <div class="ctrl">
    <span>对齐锚点</span>
    <select id="profAnchor">
      <option value="center_day">每个危机日（270 个重叠窗口）</option>
      <option value="event_onset">事件起点（17 个事件）</option>
      <option value="event_end">事件结束日（17 个事件）</option>
    </select>
    <span>指标</span><select id="profMetric"></select>
    <label class="ck"><input type="checkbox" id="profMedian" checked> 叠加中位数</label>
  </div>
  <div class="legend"><span><i style="background:#2b5fcc"></i>均值</span>
    <span><i style="background:#d9822b"></i>中位数</span>
    <span><i style="background:#c9d6f5"></i>第 25～75 百分位区间</span>
    <span>竖虚线 = 锚点当天（相对第 0 个交易日）</span></div>
  <div class="chartbox" id="profChart"></div>
  <p class="small" id="profNote"></p>
  <p class="small">剖面 = 同一相对交易日上把各窗口的该指标取横截面均值/中位数/四分位，
  <b>不是时间序列，也没有做任何检验</b>。「相对锚点日累计价格变动」即相对锚点日收盘的累计涨跌（%）。</p>
</div>

<div class="card">
  <h2>五、事件窗逐日查看器</h2>
  <div class="ctrl">
    <span>事件</span><select id="evSelect"></select>
    <span>下图指标</span><select id="evMetric"></select>
    <label class="ck"><input type="checkbox" id="evZ"> 标准化后叠加「16 行业持续图 Wasserstein 距离」</label>
    <label class="ck"><input type="checkbox" id="evAllCols"> 表格显示全部 18 个核心摘要</label>
  </div>
  <div class="legend"><span><i style="background:#d93026"></i>浅红底 = 危机段</span>
    <span><i style="background:#2b5fcc"></i>蓝色线 = 万得全 A 收盘价</span>
    <span><i style="background:#7a52c7"></i>紫色线 = 所选持续同调摘要</span></div>
  <div class="grid2">
    <div class="chartbox"><div class="small">万得全 A 收盘价（真实 881001.WI 日线）</div><div id="evPriceChart"></div></div>
    <div class="chartbox"><div class="small" id="evMetricTitle">持续同调摘要</div><div id="evMetricChart"></div></div>
  </div>
  <h3>逐日明细（当前事件窗，共 <span id="evRowCount"></span> 行；完整 101 列见「事件窗逐日全字段明细」CSV）</h3>
  <div class="ctrl"><input type="text" id="evSearch" placeholder="按日期筛选，如 2022-03"></div>
  <div id="evTable" class="scroll"></div>
</div>

<div class="card">
  <h2>六、270 个中心日：前后 20 日结果表</h2>
  <div class="ctrl">
    <span>事件</span><select id="ctEvent"><option value="">全部 17 个事件</option></select>
    <input type="text" id="ctSearch" placeholder="按日期筛选">
    <label class="ck"><input type="checkbox" id="ctColor" checked> 收益着色</label>
    <span class="small">点击表头排序；横向滚动查看 43 列</span>
  </div>
  <div id="ctTable" class="scroll"></div>
</div>

<div class="card">
  <h2>七、51 行事件分段统计</h2>
  <div id="phTable" class="scroll"></div>
</div>

<div class="card">
  <h2>八、把数字念出来（描述性观察，不是结论）</h2>
  __OBS__
</div>

<div class="card">
  <h2>九、数据字典（中文名称在前，括号内为 CSV 原字段名）</h2>
  <p class="small">这一节是专门用来对照 CSV 列名的，所以保留原字段名；页面其余部分的下拉、表头、图例一律用中文全称。</p>
  <div class="grid2">
  <dl class="dict">
    <dt>日期 / 标签日历行号 / Wind 序列行号</dt><dd>字段名 <code>date</code>、<code>label_session_index</code>、
    <code>wind_session_index</code>：标签日历日期；该日历中的行号；该日在 Wind 全序列中的行号。</dd>
    <dt>开盘 / 最高 / 最低 / 收盘价</dt><dd>字段名 <code>open</code>、<code>high</code>、<code>low</code>、
    <code>close</code>：真实万得全 A 881001.WI 日线。</dd>
    <dt>相邻 Wind 交易日收益</dt><dd>字段名 <code>ret_wind_pct</code>：相对前一 Wind 交易日的简单收益（%）。</dd>
    <dt>相邻标签交易日收益 / 步长内 Wind 交易日数</dt><dd>字段名 <code>ret_step_pct</code>、
    <code>n_wind_sessions_in_step</code>：相对前一标签日的收盘价比值（%）；该步长跨了几个 Wind 交易日。</dd>
    <dt>窗口累计收益 / 窗口内回撤</dt><dd>字段名 <code>cum_from_window_base_pct</code>、
    <code>dd_from_window_peak_pct</code>：以窗口基准日收盘为起点的累计收益；窗口内自最高收盘的回撤。</dd>
    <dt>二十步累计收益 / 日内振幅 / 全 A 成交额</dt><dd>字段名 <code>ret20_step_pct</code>、
    <code>intraday_range_pct</code>、<code>amount_yi</code>：日内振幅按（最高−最低）/开盘计算，成交额来自全 A 宽度表。</dd>
    <dt>危机日标记 / 事件编号 / 排除标记</dt><dd>字段名 <code>crisis_in_frozen</code>（本版取全部 17 段）、
    <code>crisis_in_judged</code>（14 段判定用）、<code>crisis_event_id</code>、
    <code>event_excluded_by_user</code>：冻结的危机掩码与排除标记。三者不可混用。</dd>
    <dt>牛熊主状态 / 粗状态 / 危机前标记</dt><dd>字段名 <code>state_v0_primary</code>、
    <code>state_coarse_v0</code>、<code>pre5</code>、<code>pre10</code>、<code>pre20</code>。</dd>
  </dl>
  <dl class="dict">
    <dt>状态点云线：16 / 27 行业（字段名以 a16_ / a27_ 开头）</dt>
    <dd>点 = 交易日，坐标 = 当日行业收益，窗口 10 日。主指标「相邻两日持续图 Wasserstein 距离」
    对应 <code>W_t</code>；<code>h0_death_*</code> 是 H0 连通分量死亡值统计；
    <code>h1_count</code> / <code>h1_birth_mean</code> / <code>h1_persistence_*</code> 是 H1 一维环数量与持续性；
    <code>window_rms</code> / <code>window_variance</code> 是窗口收益尺度；
    <code>avg_pair_corr</code> / <code>leading_eig_share</code> 是平均相关与第一特征值占比。</dd>
    <dt>相关网络线：兴业口径（字段名以 b_ 开头）</dt>
    <dd>点 = 申万行业，坐标 = 过去 10 日收益序列。<code>n_nodes</code> 为行业节点数；
    <code>h2_count</code> 为 H2 二维空腔数量（即 N）；<code>h1_count</code> / <code>h1_landscape_l1</code> /
    <code>h2_landscape_l1</code> 为 H1 数量与持续景观 L1 范数；
    <code>industry_average_correlation</code> / <code>correlation_leading_eigenvalue_share</code> 为平均相关与领先特征值占比；
    <code>xy_h0_death_*</code> / <code>components_0p4/0p6/0p8</code> 为 H0 死亡分布与阈值处连通分量数。</dd>
    <dt>中心日结果表的四种后缀</dt>
    <dd>中文表头「前 20 日均值 / 中心日当天 / 后 20 日均值 / 后 20 日减前 20 日」对应
    <code>__pre20_mean</code> / <code>__at_center</code> / <code>__post20_mean</code> / <code>__post_minus_pre</code>。
    全部为原始指标单位，未标准化。</dd>
    <dt>剖面统计文件的「对齐锚点」列</dt><dd>三种取值：每个危机日（270 个重叠窗口）、事件起点（17 个事件）、
    事件结束日（17 个事件）；相对交易日单位为标签交易日，第 0 天即锚点当天。</dd>
  </dl>
  </div>
</div>

<footer>
  只读导出 · 未覆盖 v0.1–v0.4 任何既有产物 · 未修改 config/study.toml ·
  Gate 1 暂停 / 2025 最终测试集未读取 / Gate 2 未启动 / PHTI 正式绩效未运行。<br>
  脚本：src/regime_check/export_crisis_context_all17.py、build_crisis_context_report_all17.py ｜
  校验：crisis_context_v04_all17_manifest.json
</footer>
</div>

<script type="application/json" id="payload">__PAYLOAD__</script>
<script>
const D = JSON.parse(document.getElementById('payload').textContent);
const $ = id => document.getElementById(id);
/* ---------------- 中文全称映射（CSV 原字段名仅作悬停对照） ---------------- */
const CN = {
 /* 状态点云线：点=交易日，坐标=当日行业收益 */
 'a16_W_t':'状态点云·16行业·相邻两日持续图 Wasserstein 距离',
 'a16_h0_death_mean':'状态点云·16行业·H0 连通分量死亡值均值',
 'a16_h0_death_median':'状态点云·16行业·H0 连通分量死亡值中位数',
 'a16_h0_death_max':'状态点云·16行业·H0 连通分量死亡值最大值',
 'a16_h0_death_cv':'状态点云·16行业·H0 死亡值变异系数',
 'a16_h1_count':'状态点云·16行业·H1 一维环数量',
 'a16_h1_birth_mean':'状态点云·16行业·H1 一维环出生值均值',
 'a16_h1_persistence_mean':'状态点云·16行业·H1 一维环持续性均值',
 'a16_window_rms':'状态点云·16行业·窗口收益均方根',
 'a16_window_variance':'状态点云·16行业·窗口收益方差',
 'a16_avg_pair_corr':'状态点云·16行业·行业间平均相关系数',
 'a16_leading_eig_share':'状态点云·16行业·相关矩阵第一特征值占比',
 'a27_W_t':'状态点云·27行业·相邻两日持续图 Wasserstein 距离',
 'a27_h0_death_mean':'状态点云·27行业·H0 连通分量死亡值均值',
 'a27_h1_count':'状态点云·27行业·H1 一维环数量',
 'a27_avg_pair_corr':'状态点云·27行业·行业间平均相关系数',
 /* 相关网络线：点=申万行业，坐标=过去10日收益序列 */
 'b_h2_count':'相关网络·H2 二维空腔数量（兴业口径的 N）',
 'b_h1_count':'相关网络·H1 一维环数量',
 'b_h2_landscape_l1':'相关网络·H2 持续景观 L1 范数',
 'b_h1_landscape_l1':'相关网络·H1 持续景观 L1 范数',
 'b_industry_average_correlation':'相关网络·行业间平均相关系数',
 'b_correlation_leading_eigenvalue_share':'相关网络·相关矩阵第一特征值占比',
 'b_xy_h0_death_mean':'相关网络·H0 连通分量死亡值均值',
 'b_h2_betti_0p4':'相关网络·阈值 0.4 处 H2 空腔数',
 'b_h2_betti_0p6':'相关网络·阈值 0.6 处 H2 空腔数',
 'b_h2_betti_0p8':'相关网络·阈值 0.8 处 H2 空腔数',
 'b_max_h2_persistence':'相关网络·H2 空腔最大持续性',
 'b_xy_h0_death_p90':'相关网络·H0 死亡值第 90 百分位',
 /* 行情与标签 */
 'close_pct_vs_anchor':'相对锚点日累计价格变动（%）',
 'ret_step_pct':'相邻标签交易日收益（%）',
 'ret_wind_pct':'相邻 Wind 交易日收益（%）',
 'intraday_range_pct':'日内振幅（%）',
 'amount_yi':'全 A 成交额（亿元）',
 'frac_above_ma20':'站上 20 日均线的个股占比',
 'dd250_wind':'万得全A 近 250 日回撤',
 'ret':'相邻标签交易日收益（%）',
 'cum':'相对窗口基准日累计收益（%）',
 'close':'收盘价',
 /* 通用列名 */
 'date':'日期','center_date':'中心日（样本日）','event_id':'事件编号',
 'onset':'事件起点','end':'事件结束日','event_onset':'事件起点','event_end':'事件结束日',
 'seq_in_event':'事件内第几个交易日','n_crisis_days':'危机段交易日数',
 'n_trading_days':'交易日数','offset':'相对交易日','offset_trading_days':'相对交易日',
 'phase':'阶段','state':'牛熊状态','crisis_in':'是否危机日',
 'pre20_start':'前20日起始日','post20_end':'后20日结束日',
 'window_first':'窗口首日','window_last':'窗口末日',
 'window_first_date':'窗口首日','window_last_date':'窗口末日',
 'start_date':'起始日','end_date':'结束日',
 'pre20_cum_pct':'前20日累计收益（%）','pre10_cum_pct':'前10日累计收益（%）',
 'pre5_cum_pct':'前5日累计收益（%）','post20_cum_pct':'后20日累计收益（%）',
 'post10_cum_pct':'后10日累计收益（%）','post5_cum_pct':'后5日累计收益（%）',
 'crisis_cum_pct':'危机段累计收益（%）','full_window_cum_pct':'全窗口累计收益（%）',
 'pre20_max_dd_pct':'前20日最大回撤（%）','post20_max_dd_pct':'后20日最大回撤（%）',
 'crisis_max_dd_pct':'危机段最大回撤（%）','pre20_step_mean_pct':'前20日日均收益（%）',
 'post20_step_mean_pct':'后20日日均收益（%）','pre20_worst_day_pct':'前20日最差单日（%）',
 'post20_best_day_pct':'后20日最好单日（%）',
 'pre20_close_min':'前20日最低收盘价','post20_close_max':'后20日最高收盘价',
 'n_skipped_wind_sessions_pre20':'前20日跨过的额外 Wind 交易日数',
 'n_skipped_wind_sessions_post20':'后20日跨过的额外 Wind 交易日数',
 'n_skipped_wind_sessions_in_window':'窗口内跨过的额外 Wind 交易日数',
 'cum_ret_pct':'区间累计收益（%）','step_mean_pct':'区间日均收益（%）',
 'max_dd_pct':'区间最大回撤（%）','worst_day_pct':'区间最差单日（%）',
 'best_day_pct':'区间最好单日（%）','close_first':'区间首日收盘价',
 'close_last':'区间末日收盘价','close_min':'区间最低收盘价','close_max':'区间最高收盘价',
 'amount_yi_mean':'区间日均成交额（亿元）',
 'metric':'指标','anchor':'对齐锚点','mean':'均值','median':'中位数',
 'p25':'第25百分位','p75':'第75百分位','min':'最小值','max':'最大值',
 'std':'标准差','n':'样本数'
};
const SUF = {
 '_pre20_mean':'前20日均值','_crisis_mean':'危机段均值','_post20_mean':'后20日均值',
 '__pre20_mean':'前20日均值','__at_center':'中心日当天','__post20_mean':'后20日均值',
 '__post_minus_pre':'后20日减前20日','__mean':'均值','__median':'中位数',
 '_mean':'均值','_median':'中位数'
};
const SUF_KEYS = Object.keys(SUF).sort((a,b)=>b.length-a.length);
function cn(k){
  if(CN[k]) return CN[k];
  for(const s of SUF_KEYS){
    if(k.endsWith(s)){
      const base=k.slice(0,-s.length);
      return (CN[base]||base)+'·'+SUF[s];
    }
  }
  return k;
}
const CN_PHASE={'pre20':'危机前20日','crisis':'危机段','post20':'危机后20日'};
const CN_STATE={'bull':'牛市','bull_adjustment':'牛市调整','bear':'熊市','bear_turn':'熊市转折',
 'fuzzy':'模糊带','undefined_warmup':'预热期未定义','undefined_after_2025_05_30':'2025-05-30 后未定义'};
const nf = v => (v===null||v===undefined||v===''||!isFinite(Number(v))) ? '' : Number(v);
const isNum = v => typeof v==='number' && isFinite(v);
function smart(v){
  if(!isFinite(v)) return '';
  const a=Math.abs(v);
  if(v===0) return '0';
  if(a>=1000) return v.toFixed(0);
  if(a>=100) return v.toFixed(1);
  if(a>=1) return v.toFixed(2);
  if(a>=0.01) return v.toFixed(3);
  if(a>=0.0001) return v.toFixed(5);
  return v.toExponential(1);
}
function colorCell(v){
  const x=Number(v);
  if(v===''||!isFinite(x)) return '';
  return x>0?'pos':(x<0?'neg':'');
}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

/* ---------- generic SVG line chart ---------- */
function svgChart(cfg){
  const W=940,H=cfg.height||270,ml=70,mr=18,mt=16,mb=36;
  const xs=cfg.x, x0=Math.min(...xs), x1=Math.max(...xs);
  let vals=[];
  cfg.series.forEach(s=>s.values.forEach(v=>{if(isNum(v))vals.push(v)}));
  if(cfg.band){cfg.band.lo.forEach(v=>{if(isNum(v))vals.push(v)});
               cfg.band.hi.forEach(v=>{if(isNum(v))vals.push(v)});}
  if(!vals.length) return '<div class="small">无数据</div>';
  let ymin=Math.min(...vals),ymax=Math.max(...vals);
  if(cfg.zero){ymin=Math.min(ymin,0);ymax=Math.max(ymax,0);}
  if(ymin===ymax){ymax=ymin+Math.abs(ymin||1)*0.1+1e-9;}
  const pad=(ymax-ymin)*0.09; ymin-=pad; ymax+=pad;
  const sx=v=>ml+(v-x0)/((x1-x0)||1)*(W-ml-mr);
  const sy=v=>mt+(ymax-v)/(ymax-ymin)*(H-mt-mb);
  let s=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">`;
  s+=`<rect x="${ml}" y="${mt}" width="${W-ml-mr}" height="${H-mt-mb}" fill="#fff"/>`;
  if(cfg.shade){
    const a=sx(Math.max(cfg.shade[0],x0)),b=sx(Math.min(cfg.shade[1],x1));
    s+=`<rect x="${a}" y="${mt}" width="${Math.max(0,b-a)}" height="${H-mt-mb}" fill="#d93026" opacity="0.09"/>`;
    s+=`<line x1="${a}" y1="${mt}" x2="${a}" y2="${H-mb}" stroke="#d93026" stroke-width="1" stroke-dasharray="3 3" opacity=".55"/>`;
    s+=`<line x1="${b}" y1="${mt}" x2="${b}" y2="${H-mb}" stroke="#d93026" stroke-width="1" stroke-dasharray="3 3" opacity=".55"/>`;
  }
  for(let k=0;k<=4;k++){
    const y=ymin+(ymax-ymin)*k/4, py=sy(y);
    s+=`<line x1="${ml}" y1="${py}" x2="${W-mr}" y2="${py}" stroke="#eceef2" stroke-width="1"/>`;
    s+=`<text x="${ml-8}" y="${py+4}" text-anchor="end" font-size="11" fill="#7a828f">${smart(y)}</text>`;
  }
  if(cfg.zero && ymin<0 && ymax>0){
    s+=`<line x1="${ml}" y1="${sy(0)}" x2="${W-mr}" y2="${sy(0)}" stroke="#9aa3b0" stroke-width="1" stroke-dasharray="4 3"/>`;
  }
  const span=x1-x0, raw=span/8, step=Math.max(1,Math.ceil(raw/5)*5);
  for(let v=Math.ceil(x0/step)*step; v<=x1; v+=step){
    const px=sx(v);
    s+=`<line x1="${px}" y1="${mt}" x2="${px}" y2="${H-mb}" stroke="#f2f3f6" stroke-width="1"/>`;
    s+=`<text x="${px}" y="${H-mb+17}" text-anchor="middle" font-size="11" fill="#7a828f">${v}</text>`;
  }
  if(x0<=0&&x1>=0){
    s+=`<line x1="${sx(0)}" y1="${mt}" x2="${sx(0)}" y2="${H-mb}" stroke="#2b5fcc" stroke-width="1" stroke-dasharray="4 4" opacity=".6"/>`;
  }
  if(cfg.band){
    let up='',dn='';
    cfg.band.hi.forEach((v,i)=>{if(isNum(v))up+=(up?' L':'M')+sx(xs[i])+' '+sy(v)});
    for(let i=cfg.band.lo.length-1;i>=0;i--){const v=cfg.band.lo[i];if(isNum(v))dn+=' L'+sx(xs[i])+' '+sy(v)}
    if(up&&dn)s+=`<path d="${up}${dn} Z" fill="#2b5fcc" opacity="0.10"/>`;
  }
  cfg.series.forEach(se=>{
    let d='';
    se.values.forEach((v,i)=>{if(isNum(v))d+=(d?' L':'M')+sx(xs[i])+' '+sy(v)});
    if(d)s+=`<path d="${d}" fill="none" stroke="${se.color}" stroke-width="${se.width||2}" ${se.dash?'stroke-dasharray="5 4"':''} stroke-linejoin="round"/>`;
  });
  s+=`<line x1="${ml}" y1="${H-mb}" x2="${W-mr}" y2="${H-mb}" stroke="#d9dde4" stroke-width="1"/>`;
  s+=`<text x="${W-mr}" y="${H-6}" text-anchor="end" font-size="11" fill="#7a828f">相对交易日（天，0 = 对齐锚点）</text>`;
  s+='</svg>';
  return s;
}

/* ---------- sortable table ---------- */
function renderTable(el, cols, rows, opt){
  opt=opt||{};
  const st=el._st||(el._st={key:null,dir:1});
  let data=rows.slice();
  if(opt.filter) data=data.filter(opt.filter);
  if(st.key){
    data.sort((a,b)=>{
      const x=Number(a[st.key]),y=Number(b[st.key]);
      if(isFinite(x)&&isFinite(y)) return (x-y)*st.dir;
      return String(a[st.key]||'').localeCompare(String(b[st.key]||''))*st.dir;
    });
  }
  let h='<table><thead><tr>';
  cols.forEach(c=>{h+=`<th class="${opt.numCols&&opt.numCols.includes(c)?'num':''}" data-k="${esc(c)}" title="CSV 原字段名：${esc(c)}">${esc(cn(c))}${st.key===c?(st.dir>0?' ▲':' ▼'):''}</th>`});
  h+='</tr></thead><tbody>';
  data.forEach(r=>{
    const cls=(opt.rowClass&&opt.rowClass(r))||'';
    h+=`<tr class="${cls}">`;
    cols.forEach(c=>{
      const raw=r[c], val=nf(raw);
      let cell = (val===''&&raw!==''&&raw!=null)?esc(raw):(val===''? '' : (opt.raw?String(raw):smart(val)));
      if(c==='phase') cell=`<span class="pill ${esc(raw)}">${esc(CN_PHASE[raw]||raw)}</span>`;
      else if(c==='event_id') cell=`<b>事件 ${esc(raw)}</b>`;
      else if(c==='state') cell=esc(CN_STATE[raw]||raw);
      else if(opt.fmt&&opt.fmt[c]) cell=opt.fmt[c](raw,r);
      const cc=(opt.color&&opt.color.includes(c))?colorCell(raw):'';
      h+=`<td class="${opt.numCols&&opt.numCols.includes(c)?'num ':''}${cc}">${cell}</td>`;
    });
    h+='</tr>';
  });
  h+='</tbody></table>';
  el.innerHTML=h;
  el.querySelectorAll('th').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k;
    if(st.key===k) st.dir*=-1; else {st.key=k;st.dir=1;}
    renderTable(el,cols,rows,opt);
  });
  if(opt.countEl) $(opt.countEl).textContent=data.length;
}

/* ---------- 3. overview ---------- */
const OV_COLS=['event_id','onset','end','n_crisis_days','pre20_cum_pct','crisis_cum_pct','post20_cum_pct',
 'full_window_cum_pct','crisis_max_dd_pct','post20_max_dd_pct',
 'a16_W_t_pre20_mean','a16_W_t_crisis_mean','a16_W_t_post20_mean',
 'a27_W_t_pre20_mean','a27_W_t_crisis_mean','a27_W_t_post20_mean',
 'b_h2_count_pre20_mean','b_h2_count_crisis_mean','b_h2_count_post20_mean',
 'b_industry_average_correlation_pre20_mean','b_industry_average_correlation_crisis_mean',
 'b_industry_average_correlation_post20_mean','n_skipped_wind_sessions_in_window'];
const OV_NUM=OV_COLS.filter(c=>c!=='event_id'&&c!=='onset'&&c!=='end');
const OV_COLOR=['pre20_cum_pct','crisis_cum_pct','post20_cum_pct','full_window_cum_pct',
 'crisis_max_dd_pct','post20_max_dd_pct'];
function drawOverview(){
  renderTable($('ovTable'),OV_COLS,D.overview,{
    numCols:OV_NUM,color:$('ovColor').checked?OV_COLOR:[],
    fmt:{event_id:(v)=>`<b>E${esc(v)}</b>`}});
}
$('ovColor').onchange=drawOverview; drawOverview();

/* ---------- 4. profile ---------- */
const PM=D.metrics;
$('profMetric').innerHTML=PM.map(m=>`<option value="${esc(m)}" title="CSV 原字段名：${esc(m)}">${esc(cn(m))}</option>`).join('');
$('profMetric').value='close_pct_vs_anchor';
const PROF_NOTE={
 center_day:'锚点 = 270 个危机日各自当天（0 = 该样本日）。曲线是 270 个高度重叠窗口的横截面均值，长事件权重更大。',
 event_onset:'锚点 = 17 个事件起点（0 = 危机段第一天）。左右各 20 个标签交易日，事件级去重。',
 event_end:'锚点 = 17 个事件末日（0 = 危机段最后一天）。右侧 20 日即危机结束后的行情。'};
function drawProfile(){
  const a=$('profAnchor').value,m=$('profMetric').value;
  const rec=D.profile.filter(r=>r.anchor===a&&r.metric===m);
  if(!rec.length){$('profChart').innerHTML='<div class="small">无数据</div>';return;}
  const xs=rec.map(r=>Number(r.offset_trading_days));
  const mean=rec.map(r=>nf(r.mean)),med=rec.map(r=>nf(r.median));
  const lo=rec.map(r=>nf(r.p25)),hi=rec.map(r=>nf(r.p75));
  const series=[{name:'mean',color:'#2b5fcc',values:mean,width:2.2}];
  if($('profMedian').checked) series.push({name:'median',color:'#d9822b',values:med,width:1.6,dash:true});
  $('profChart').innerHTML=svgChart({x:xs,series:series,band:{lo:lo,hi:hi},
    zero:(m.indexOf('pct')>=0||m.indexOf('ret')>=0),height:300});
  $('profNote').textContent=PROF_NOTE[a]+' 当前指标：'+cn(m)+'（原字段 '+m+'）；样本数见剖面统计 CSV 的「样本数」列。';
}
['profAnchor','profMetric','profMedian'].forEach(id=>$(id).onchange=drawProfile);
drawProfile();

/* ---------- 5. event viewer ---------- */
const EV_METRICS=D.core_metrics.concat(['a16_window_variance','a16_h0_death_cv','b_h2_betti_0p4',
 'b_h2_betti_0p6','b_h2_betti_0p8','b_max_h2_persistence','b_xy_h0_death_p90','amount_yi',
 'frac_above_ma20','dd250_wind','cum','ret']);
$('evSelect').innerHTML=D.events.map(e=>`<option value="${e.event_id}" title="事件编号 ${e.event_id}">事件 ${e.event_id}｜${e.onset} 至 ${e.end}｜危机段 ${e.n} 个交易日</option>`).join('');
$('evMetric').innerHTML=EV_METRICS.map(m=>`<option value="${esc(m)}" title="CSV 原字段名：${esc(m)}">${esc(cn(m))}</option>`).join('');
$('evMetric').value='a16_W_t';
function zscore(a){
  const v=a.filter(isNum);
  if(!v.length)return a.map(()=>null);
  const m=v.reduce((s,x)=>s+x,0)/v.length;
  const sd=Math.sqrt(v.reduce((s,x)=>s+(x-m)*(x-m),0)/v.length)||1;
  return a.map(x=>isNum(x)?(x-m)/sd:null);
}
function currentEvent(){return D.events.find(e=>e.event_id===$('evSelect').value)||D.events[0];}
const EV_BASE=['date','offset','phase','close','ret','cum','state','a16_W_t','a16_window_rms',
 'a16_avg_pair_corr','a27_W_t','b_h2_count','b_industry_average_correlation','amount_yi','frac_above_ma20'];
function drawEvent(){
  const e=currentEvent(),m=$('evMetric').value,rows=e.rows;
  const xs=rows.map(r=>r.offset);
  $('evPriceChart').innerHTML=svgChart({x:xs,
    series:[{name:'close',color:'#2b5fcc',values:rows.map(r=>r.close),width:2.1}],
    shade:[0,e.n-1],height:250});
  let series,title;
  const mv=rows.map(r=>nf(r[m]));
  if($('evZ').checked){
    series=[{name:cn(m)+'（标准化）',color:'#7a52c7',values:zscore(mv),width:2},
            {name:'16行业持续图 Wasserstein 距离（标准化）',color:'#16827a',
             values:zscore(rows.map(r=>nf(r['a16_W_t']))),width:1.6,dash:true}];
    title=cn(m)+' 与 16 行业持续图 Wasserstein 距离（各自窗内标准化，无单位）';
  }else{
    series=[{name:cn(m),color:'#7a52c7',values:mv,width:2.1}];
    title=cn(m)+'（原始单位）';
  }
  $('evMetricTitle').textContent=title;
  $('evMetricChart').innerHTML=svgChart({x:xs,series:series,shade:[0,e.n-1],height:250});
  const q=$('evSearch').value.trim();
  const cols=$('evAllCols').checked?EV_BASE.concat(D.core_metrics.filter(c=>!EV_BASE.includes(c))):EV_BASE;
  renderTable($('evTable'),cols,rows,{
    numCols:cols.filter(c=>c!=='date'&&c!=='phase'&&c!=='state'),
    color:['ret','cum'],
    rowClass:r=>r.phase==='crisis'?'row-crisis':'',
    filter:r=>!q||r.date.indexOf(q)>=0,
    countEl:'evRowCount',
    fmt:{phase:v=>`<span class="pill ${esc(v)}">${esc(v)}</span>`,
         offset:v=>`${Number(v)>0?'+':''}${v}`}
  });
}
['evSelect','evMetric','evZ','evAllCols'].forEach(id=>$(id).onchange=drawEvent);
$('evSearch').oninput=drawEvent;
drawEvent();

/* ---------- 6. centre-day table ---------- */
const CT_COLS=D.center_cols;
$('ctEvent').innerHTML+='__EV_OPTIONS__';
function drawCenters(){
  const ev=$('ctEvent').value,q=$('ctSearch').value.trim();
  renderTable($('ctTable'),CT_COLS,D.centers,{
    numCols:CT_COLS.filter(c=>c!=='center_date'&&c!=='event_onset'&&c!=='event_end'),
    color:$('ctColor').checked?CT_COLS.filter(c=>c.indexOf('cum_pct')>=0||c.indexOf('dd_pct')>=0||c.indexOf('post_minus_pre')>=0):[],
    filter:r=>(!ev||r.event_id===ev)&&(!q||r.center_date.indexOf(q)>=0),
    fmt:{event_id:v=>`E${esc(v)}`}
  });
}
['ctEvent','ctColor'].forEach(id=>$(id).onchange=drawCenters);
$('ctSearch').oninput=drawCenters;
drawCenters();

/* ---------- 7. phase table ---------- */
const PH_COLS=D.phase_cols;
renderTable($('phTable'),PH_COLS,D.phases,{
  numCols:PH_COLS.filter(c=>c!=='event_id'&&c!=='phase'&&c!=='start_date'&&c!=='end_date'),
  color:PH_COLS.filter(c=>c.indexOf('cum_ret_pct')>=0||c.indexOf('step_mean_pct')>=0),
  rowClass:r=>r.phase==='crisis'?'row-crisis':'',
  fmt:{event_id:v=>`E${esc(v)}`,phase:v=>`<span class="pill ${esc(v)}">${esc(v)}</span>`}
});
</script>
</body>
</html>
"""

ev_options = "".join(
    f'<option value="{e["event_id"]}">事件 {e["event_id"]}｜{e["onset"]} 至 {e["end"]}｜危机段 {e["n"]} 个交易日</option>'
    for e in chart["events"])

out = (HTML
       .replace("__PAYLOAD__", payload_json)
       .replace("__FILES__", "".join(file_rows))
       .replace("__OBS__", OBS_HTML)
       .replace("__GEN__", manifest["generated_at"][:19].replace("T", " "))
       .replace("__EV_OPTIONS__", ev_options))

path = OUT / (PREFIX + "report.html")
path.write_text(out, encoding="utf-8")
print(json.dumps({
    "report": str(path),
    "bytes": path.stat().st_size,
    "html_balanced": out.count("<div") == out.count("</div>"),
    "script_tags": out.count("<script"),
    "placeholders_left": sum(out.count(k) for k in ("__PAYLOAD__", "__FILES__", "__OBS__", "__GEN__", "__EV_OPTIONS__")),
}, ensure_ascii=False, indent=2))
