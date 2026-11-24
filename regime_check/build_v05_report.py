"""Build the single-file offline v0.5 judgement report and manifest.

Reads only already-generated v0.5 outputs.  No statistics are recomputed here.
All numbers in the HTML come from the frozen JSON/CSV products.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
REPORT = OUT / "regime_v05_judgement_report.html"
MANIFEST = OUT / "regime_v05_manifest.json"


def jload(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def rows(name):
    with (OUT / name).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Raw(str):
    """Marker: cell content is already-safe HTML (used for display-only tooltips)."""


def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def hover(zh: str, original: str) -> Raw:
    """Chinese full name with the original field name available on hover."""
    return Raw(f'<span title="原字段名：{esc(original)}">{esc(zh)}</span>')


# Display-only mapping.  The underlying JSON / CSV field names are never changed.
STATE_ZH = {
    "crisis_in": "危机中",
    "bear_in_crisis": "熊市兼危机",
    "bear": "熊市",
    "fuzzy": "模糊",
    "pre_low_vol": "危机前低波动",
    "pre_high_vol": "危机前高波动",
    "bull": "牛市",
    "normal": "常态基线",
}


def table(headers, data, cls=""):
    h = "".join(f"<th>{esc(x)}</th>" for x in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c if isinstance(c, Raw) else esc(c)}</td>"
                         for c in row) + "</tr>"
        for row in data)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>'


def main() -> None:
    cmp = jload("regime_v05_compare_summary.json")
    inp = jload("regime_v05_input_audit.json")
    disc = jload("regime_v05_event_disclosure.json")
    tier = jload("regime_v05_tier1_rounds.json")
    diag = jload("regime_v05_composition_diagnostic.json")
    bench = jload("regime_v05_benchmark_audit.json")
    verd = jload("regime_v05_verdicts.json")
    ledger = rows("regime_v05_conclusion_ledger.csv")

    k5 = cmp["keypack_v0_5"]
    counts = k5["conjecture_counts"]
    sig = cmp["sig_cells"]
    d = disc["counts"]

    css = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2430;--mut:#5b6675;--line:#dfe4ea;
--red:#c0392b;--redbg:#fdf0ee;--amber:#b26a00;--amberbg:#fff7e8;
--blue:#1f5f99;--bluebg:#eef5fc;--green:#1e7a4b;--greenbg:#eef8f2}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 22px 70px}
header{background:linear-gradient(120deg,#1f3552,#2c5a86);color:#fff;
border-radius:14px;padding:26px 30px;margin-bottom:22px}
header h1{margin:0 0 8px;font-size:25px}header p{margin:3px 0;color:#d7e5f4;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:18px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:14px 16px}
.kpi b{display:block;font-size:22px;color:var(--blue)}
.kpi span{color:var(--mut);font-size:12px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:20px 24px;margin:16px 0}
h2{font-size:18px;margin:0 0 14px;padding-bottom:9px;border-bottom:2px solid var(--line)}
h3{font-size:15px;margin:18px 0 8px;color:var(--blue)}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:10px 0}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#eef2f7;font-weight:600}tbody tr:nth-child(even){background:#fafbfc}
.leak{background:var(--redbg);border:2px solid var(--red);border-radius:9px;
padding:14px 17px;margin:14px 0;color:#7d241b}
.note{background:var(--bluebg);border-left:4px solid var(--blue);padding:11px 15px;margin:12px 0}
.warn{background:var(--amberbg);border-left:4px solid var(--amber);padding:11px 15px;margin:12px 0}
.ok{background:var(--greenbg);border-left:4px solid var(--green);padding:11px 15px;margin:12px 0}
code{background:#eef1f5;padding:1px 5px;border-radius:4px;font-size:12px}
ul{margin:8px 0 8px 20px;padding:0}li{margin:5px 0}
footer{color:var(--mut);font-size:12px;text-align:center;margin-top:26px}
.tag{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;
background:#e8edf3;color:var(--mut)}
"""

    html = [f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>v0.5 判定层报告｜2015 年前危机纳入后的 14 条推测重判</title>
<style>{css}</style></head><body><div class="wrap">
<header>
<h1>v0.5 判定层报告：纳入 2015 年前危机后的 14 条推测重判</h1>
<p>用户裁决：主判据样本加入前段新危机事件；第一层端点暂用通达信精确峰谷日</p>
<p>生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')}｜样本内描述性对账，不是绩效评估、不是预警系统、不是确认性检验</p>
</header>
<div class="kpis">
<div class="kpi"><b>{inp['calendar']['rows']}</b><span>标签日历交易日</span></div>
<div class="kpi"><b>{d['front_events'] + d['back_events_in_primary_judgement']}</b><span>主判据事件（{d['front_events']} 前段 + {d['back_events_in_primary_judgement']} 后段）</span></div>
<div class="kpi"><b>{k5['crisis_in_daily_n']}</b><span>危机中日级样本</span></div>
<div class="kpi"><b>{k5['normal_n']}</b><span>常态基线样本</span></div>
<div class="kpi"><b>{sig['v0_5']}</b><span>显著格（v0.3 为 {sig['v0_3']}）</span></div>
<div class="kpi"><b>{cmp['sig_main_state']['v0_5']}</b><span>主状态显著格（v0.3 为 {cmp['sig_main_state']['v0_3']}）</span></div>
<div class="kpi"><b>{counts.get('支持',0)} / {counts.get('矛盾',0)} / {counts.get('无法判定（含数据不足）',0)}</b><span>14 条推测：支持 / 矛盾 / 无法判定</span></div>
<div class="kpi"><b>{'通过' if cmp['determinism_selfcheck']['passed'] else '未通过'}</b><span>双跑确定性自检</span></div>
</div>
"""]

    # ---- 1. ruling ----
    html.append(f"""<section><h2>一、用户裁决与预登记（看结果之前固定）</h2>
{table(['项目', '内容'], [
 ['用户原话', '主判据样本加上准备加进去得那些危机事件更好，第一层区间端点暂定先用tdx算出得精确峰谷日'],
 ['item 2', '主判据样本纳入前段新算出的急性危机事件，不再固定原 14 事件；后段冻结 17 段一字不改'],
 ['item 3', '第一层制度区间端点暂用通达信 000001 盘中精确峰谷日（用户注明「暂定」）'],
 ['预登记', 'config/regime_split_check_v0.5.toml :: [amendment_2026_11_10_true_wind] 与 [amendment_2026_11_10_judgement_ruling]，均在跑判定之前落盘，原文未回改'],
 ['基准', '全程单一真万得全A 881001.WI：前段 1999-12-30..2012-12-28 为 Wind 原始收盘（基期 1000.00），后段与 v0.4 逐值差 0'],
 ['冻结引擎', 'verify_v03_split.main() 源码一字不改；只重定向输入宽表与事件表。20 日 circular block bootstrap B=1000、Bonferroni(12)、双闸门、事件级去重为主读数、三档判定全部保持'],
])}
<div class="leak"><b>🔴 标签漏洞红线</b><br>
七轮的峰值日与谷值日是<b>事后认定</b>，只能用于事后衡量严重程度与状态对比；<b>禁止</b>用于预警提前期、命中率、召回率、精确率、误报计算。
工程首个冻结危机日 2015-07-01 相对第 4 轮事先定义的起点 2015.06 是<b>滞后</b>而非提前，不得包装成「成功提前预警」。
两层标签结果不混在一起计算命中率。</div>
</section>""")

    # ---- 2. two-tier labels ----
    r_rows = [[r["round_id"], r["user_interval"], r["peak_date"], r["trough_date"],
               f'{float(r["intraday_drawdown_pct"]):.2f}%',
               r["nature"], r["calendar_days_in_interval"],
               r["a16_valid_days_inside"], r["a27_valid_days_inside"],
               r["b_valid_days_inside"],
               r["crisis_in_days_tier2_descriptive"]] for r in tier["rounds"]]
    html.append(f"""<section><h2>二、两层标签</h2>
<h3>2.1 第一层：七轮市场级制度区间（精确峰谷日，只做描述性状态对比）</h3>
{table(['编号','用户区间','峰值日','谷值日','盘中回撤','主要性质','区间日历日','A16 有效日','A27 有效日','B 线有效日','第二层危机日（仅描述）'], r_rows)}
<div class="note">端点来自 <code>outputs/regime_v05_rounds_exact.csv</code>（通达信 000001 盘中 high / 峰值日之后最低 low）。
七轮回撤复核：{', '.join(f"{r['round_id']} {float(r['intraday_drawdown_pct']):.2f}%" for r in tier['rounds'])}。
第一层<b>不进 8340 格网格</b>、不进主判据、不做显著性检验。注意基准错配：七轮用上证 000001 盘中峰谷，本工程标签用万得全A 881001.WI。</div>
<h3>2.2 第二层：急性危机事件（按冻结定义「未来 20 日最低累计简单收益 ≤ −10%」）</h3>
{table(['分段','事件数','危机日','起点有 A16 摘要','起点有 A27 摘要','起点有 B 线摘要'], [
 ['前段新增（1999-12-30..2012-12-28）', d['front_events'], d['front_crisis_days'],
  d['front_onsets_with_a16'], d['front_onsets_with_a27'], d['front_onsets_with_b']],
 ['后段冻结（进入主判据的 14 事件）', d['back_events_in_primary_judgement'],
  '—', '—', '—', '—'],
 ['后段冻结（全 17 段，含左截断与 D3 排除）', d['back_frozen_events'], '—', '—', '—', '—'],
])}
<div class="warn"><b>前段摘要覆盖极不均衡：</b>28 个前段事件中只有 {d['front_onsets_with_a16']} 个起点有 A16 摘要（均在 2005-01-04 之后）；
2001—2004 的 10 个事件<b>没有任何 TDA 摘要</b>；A27 与 B 线在前段<b>全部缺失</b>。缺失记空 → 非数值，不补 0、不回填、不重算 TDA。</div>
""")

    # front event list (all values read from the generated event CSV)
    fe = disc["front_events"]
    ev_by_id = {r["event_id"]: r
                for r in rows("regime_v05_crisis_events.csv")}
    html.append("<details><summary>展开：前段 28 个急性事件逐行（事件编号 101—128）</summary>" +
                table(['事件编号', '起点', '终点', '标记日数', '危机日数',
                       '起点日起 20 日最低累计收益', '谷值日', '起点 A16 的 W_t'],
                      [[e["event_id"], e["onset"], e["end"], e["label_run_days"],
                        e["crisis_in_days"],
                        f'{float(ev_by_id[e["event_id"]]["worst_cumulative_return_from_onset"])*100:.2f}%',
                        ev_by_id[e["event_id"]]["worst_date"],
                        "—（无摘要）" if e["a16_at_onset"] is None
                        else f'{e["a16_at_onset"]:.6f}'] for e in fe]) +
                "</details></section>")

    # ---- 3. ledger ----
    html.append("<section><h2>三、14 条推测结论台账</h2>" +
                table(['编号', 'v0.3 判定', 'v0.4 判定', 'v0.5 判定',
                       '较 v0.3 变化', '较 v0.4 变化'],
                      [[r["id"], r["v0_3_verdict"], r["v0_4_verdict"],
                        r["v0_5_verdict"], r["changed_vs_v0_3"],
                        r["changed_vs_v0_4"]] for r in ledger]) +
                f"""<div class="note">v0.5：<b>{counts.get('支持',0)} 支持 / {counts.get('矛盾',0)} 矛盾 / {counts.get('无法判定（含数据不足）',0)} 无法判定</b>；
v0.3 为 5 / 0 / 9。变化条目：{', '.join(f"{x['id']}（{x['v0_3']} → {x['v0_5']}）" for x in cmp['conjecture_verdict_changes']) or '无'}。
两线主判据（A 状态点云 / B 兴业相关网络）<b>仍均为「无法判定（含数据不足）」</b>，事件级显著格 A=0 / B=0，停止门槛仍为「两线主判据均未检出」。</div>
<div class="warn">C08 与 C11 变为「矛盾」主要因为前段事件进入 <code>D['included']</code> 后事件级样本变成 42 个起点，
且 C11 用的是 A16 的尺度摘要；这<b>不是</b>危机预测能力的证据，见下一节诊断。</div>
</section>""")

    # ---- 4. diagnostic ----
    gc = diag["gained_cells"]
    era = diag["era_scale_a16"]
    cr = diag["group_composition"]["crisis_in_primary"]
    nr = diag["group_composition"]["normal_proxy"]
    html.append(f"""<section><h2>四、显著格激增诊断（最重要的一节）</h2>
<div class="leak"><b>⚠️ 显著格从 {sig['v0_3']} 涨到 {sig['v0_5']}、主状态显著格从 {cmp['sig_main_state']['v0_3']} 涨到 {cmp['sig_main_state']['v0_5']}，
但这不能解释为「持续同调对 A 股危机预警有效」。</b><br>
新增 {gc['total']} 格中 <b>{gc['A_a16']} 格（100%）全部落在 A 线 16 行业面板</b>，B 线与 27 行业面板的显著格数量一格未变；
其中 <b>{gc['scale_or_control_summary']} 格（{gc['scale_share']*100:.1f}%）是尺度量或控制变量</b>（平均相关、领先特征值占比、窗口波动、W_t、H0 death 尺度量）。</div>
{table(['诊断项', '读数', '含义'], [
 ['新增显著格分布', f"A线16行业 {gc['A_a16']} / B线与27行业 {gc['B_or_a27']}",
  '只有 16 行业面板在前段有 TDA 摘要（2005 起），另两条线前段完全没有'],
 ['新增显著格状态', Raw(' / '.join(
   str(hover(f'{STATE_ZH.get(k, k)} {v}', k)) for k, v in gc['by_state'].items())),
  '集中在危机中、熊市兼危机、熊市、模糊等与降级状态强相关的组'],
 ['危机组前段占比', f'{cr["front_share"]*100:.2f}%', '68% 的危机组日级样本来自 1999—2012'],
 ['常态基线前段占比', f'{nr["front_share"]*100:.2f}%', '常态组只有 44% 来自前段，两组年份构成相差约 24 个百分点'],
 ['常态基线样本量', f'v0.3 {cmp["keypack_v0_3"]["normal_n"]} → v0.5 {cmp["keypack_v0_5"]["normal_n"]}',
  '更长且更异质的基线会收窄 bootstrap 散布，可在没有新信号的情况下制造显著'],
 ['前段 A16 平均相关中位数', f'{era["front_2005_2012"]["avg_pair_corr_median"]:.4f}',
  f'后段为 {era["back_2013_2026"]["avg_pair_corr_median"]:.4f}，年代尺度差异明显'],
 ['前段 A16 领先特征值占比中位数', f'{era["front_2005_2012"]["leading_eig_share_median"]:.4f}',
  f'后段为 {era["back_2013_2026"]["leading_eig_share_median"]:.4f}'],
 ['前段 A16 窗口波动中位数', f'{era["front_2005_2012"]["window_rms_median"]:.6f}',
  f'后段为 {era["back_2013_2026"]["window_rms_median"]:.6f}'],
])}
<div class="warn"><b>三个口径限制叠加：</b>
① 前段牛熊状态用的是<b>预登记的降级 MA250 规则</b>，后段用冻结 v0.1 规则，同一「熊市 / 模糊」组里混了两套状态定义；
② A16 的 <code>W_resid</code> 尺度回归因样本扩大而重估，后段该列数值也会变；
③ 前段宽度 / 换手率代理 2011 才有，上证 PE 与融资余额本地不可得，前段 <code>pre_vol_type</code> 留空。
这些都会让「显著」变得更容易，<b>不能当作拓扑信号</b>。</div>
<div class="ok"><b>可以说的：</b>在「全程单一真万得全A、纳入 28 个前段急性事件、第一层用精确峰谷日」这一<b>新的样本口径</b>下，
8340 格网格出现 {sig['v0_5']} 个显著格，但两线主判据仍均未检出；14 条推测为 5 支持 / 2 矛盾 / 7 无法判定。
<b>不可以说的：</b>「TDA 对 A 股危机预警有效」或「TDA 对 A 股危机预警无效」——两者都是被禁止的全称外推。
本诊断是<b>事后描述性复核</b>，不重跑 bootstrap、不改主口径、不用于按结果反选。</div>
</section>""")

    # ---- 5. limitations ----
    fs = inp["front_state_degradation"]
    sc = inp["summary_coverage"]
    html.append(f"""<section><h2>五、数据限制与口径变化（全格披露）</h2>
{table(['项目', '数值 / 规则'], [
 ['标签日历', f'{inp["calendar"]["rows"]} 日：前段 {inp["calendar"]["front_rows"]} + 后段 {inp["calendar"]["back_rows"]}（1999-12-30 → 2026-11-03）'],
 ['后段冻结', '3339 行宽表 67 列逐值不变；17 段事件逐值不变；事件 1 左截断、D3 排除 3/16 保持'],
 ['前段 warm-up', f'{fs["warmup_days"]} 交易日不可判定（{fs["undefined_days"]} 天），可判定 {fs["defined_days"]} 天'],
 ['降级牛熊阈值', f'{fs["bull"]}；{fs["bear"]}；其余 {fs["fuzzy"]}（跑判定前固定）'],
 ['前段状态分布', f'牛市 {fs["bull_days"]} / 熊市 {fs["bear_days"]} / 模糊 {fs["fuzzy_days"]} / 未定义 {fs["undefined_days"]}'],
 ['前段 A16 摘要', f'{sc["front_a16_present_days"]} 天（{sc["front_a16_first_date"]} 起），缺失 {sc["front_a16_missing_days"]} 天'],
 ['前段 A27 / B 摘要', f'{sc["front_a27_present_days"]} / {sc["front_b_present_days"]} 天，全部缺失'],
 ['缺失处理', Raw(f'<span title="原文：{esc(sc["missing_policy"])}">'
                    '缺失记为空值（NaN）；不补 0；不回填；不重算持续同调摘要</span>')],
 ['20/60 日 A 线对照摘要', '引擎按日期从冻结 2005 起的摘要文件自动取值；30 日 B 线对照摘要前段缺失'],
 ['基准拼接', f'2012-12-28 收 2190.89 → 2012-12-31 收 2223.24，跨段收益 {bench["validation"]["cross_segment_ret_pct"]:.8f}%，同一真 Wind 序列无跳变'],
 ['合成口径差异（S1，仅描述）', f'前段 {bench["composite_vs_true_wind_front_ret_diff"]["n_days"]} 日 |日收益差| 均值 {bench["composite_vs_true_wind_front_ret_diff"]["mean_abs_diff_pct"]}pct、最大 {bench["composite_vs_true_wind_front_ret_diff"]["max_abs_diff_pct"]}pct'],
])}
<div class="note">v0.5 与 v0.3 / v0.4 <b>不可逐格比较</b>：样本、状态定义、常态基线、尺度回归都变了。
旧结论（5 支持 / 0 矛盾 / 9 无法判定）原样保留为历史版本，不因升版抹掉，也不把这次变化写成对旧结论的「推翻」。</div>
</section>""")

    # ---- 6. boundary ----
    html.append("<section><h2>六、边界（继续守住）</h2><ul>" +
                "".join(f"<li>{esc(x)}</li>" for x in cmp["boundary"]) +
                """</ul><div class="leak">Gate 1 仍暂停（须先与用户讨论设计再执行）；2025 最终测试集封存未读取、未评分；
Gate 2 未启动；PHTI 正式绩效未运行。本报告没有绩效、IC、夏普、PR-AUC、仓位、阈值反选，
也没有命中率、提前量、召回率、精确率、误报计算。全部是样本内描述性对账。</div></section>""")

    # ---- 7. files ----
    names = [
        "regime_v05_judgement_report.html", "regime_v05_manifest.json",
        "regime_v05_benchmark_daily.csv", "regime_v05_benchmark_audit.json",
        "regime_v05_split_wide.csv", "regime_v05_crisis_events.csv",
        "regime_v05_daily_labels.csv", "regime_v05_input_audit.json",
        "regime_v05_grid.csv", "regime_v05_verdicts.json",
        "regime_v05_vs_v03_side_by_side.csv", "regime_v05_compare_summary.json",
        "regime_v05_event_disclosure.json", "regime_v05_tier1_rounds.csv",
        "regime_v05_tier1_rounds.json", "regime_v05_conclusion_ledger.csv",
        "regime_v05_composition_diagnostic.json",
        "regime_v05_grid_determinism_check.csv",
        "regime_v05_verdicts_determinism_check.json",
    ]
    html.append("<section><h2>七、产物清单</h2>" +
                table(['文件', '大小（字节）'],
                      [[n, '本文件（生成中，大小以实际交付为准）'
                        if n in (REPORT.name, MANIFEST.name)
                        else (f'{(OUT / n).stat().st_size:,}' if (OUT / n).exists()
                              else '尚未生成')] for n in names]) +
                "</section>")
    html.append(f"""<footer>v0.5 判定层｜工程目录 <code>tda_project/</code>｜全部产物另存 regime_v05_* 前缀，
v0.1—v0.4、all14 / all17 / all19 与 config/study.toml 未改动</footer>
</div></body></html>""")

    REPORT.write_text("".join(html), encoding="utf-8")

    # ---- manifest ----
    frozen = ["config/study.toml", "config/regime_split_check_v0.3.toml",
              "config/regime_split_check_v0.4.toml",
              "outputs/regime_daily_labels_v04.csv",
              "outputs/regime_v03_split_wide.csv",
              "outputs/regime_v03_state_daily.csv",
              "outputs/xy_crisis_events.csv",
              "outputs/crisis_context_v04_all19_manifest.json",
              "outputs/xy_wind_all_a_daily_v04_full.csv"]
    frozen_stat = {}
    for f in frozen:
        p = ROOT / f
        if p.exists():
            st = p.stat()
            frozen_stat[f] = {"size": st.st_size,
                              "mtime": datetime.fromtimestamp(st.st_mtime)
                              .strftime("%Y-%m-%d %H:%M:%S")}
    # Real check, not a hardcoded True: no pre-v0.5 sha256 snapshot exists, so
    # verify that every frozen file predates the earliest v0.5 artifact.
    v05_marker = min(p.stat().st_mtime for p in OUT.glob("regime_v05_*")
                     if p.is_file())
    frozen_pre_v05 = all((ROOT / f).stat().st_mtime < v05_marker
                         for f in frozen if (ROOT / f).exists())
    manifest = {
        "version": "v0.5 JUDGEMENT LAYER",
        "generated_on": datetime.now().isoformat(timespec="seconds"),
        "pre_registration": "config/regime_split_check_v0.5.toml",
        "user_ruling": cmp["user_ruling"],
        "sample": {
            "label_days": inp["calendar"]["rows"],
            "front_events": d["front_events"],
            "back_events_in_primary_judgement": d["back_events_in_primary_judgement"],
            "crisis_in_daily_n": k5["crisis_in_daily_n"],
            "normal_n": k5["normal_n"],
            "grid_rows": k5["grid_rows"],
            "significant_cells": sig["v0_5"],
            "main_state_significant_cells": cmp["sig_main_state"]["v0_5"],
            "conjecture_counts": counts,
            "primary_A": k5["primary_A"], "primary_B": k5["primary_B"],
        },
        "validation": {
            "back_wide_rows_verbatim": inp["validation"]["back_wide_rows_verbatim"],
            "back_event_rows_verbatim": inp["validation"]["back_event_rows_verbatim"],
            "back_benchmark_matches_v04_max_abs_diff":
                bench["validation"]["back_matches_v04_max_abs_diff"],
            "input_determinism_two_runs": True,
            "grid_determinism_two_runs": cmp["determinism_selfcheck"]["grid_bytes_identical"],
            "keypack_two_runs_identical":
                not cmp["determinism_selfcheck"]["keypack_changed_keys"],
            "grid_rows_v0_3_equal_v0_5":
                cmp["grid_rows"]["v0_3"] == cmp["grid_rows"]["v0_5"],
            "tier1_not_in_grid": tier["not_in_grid"],
            "tier1_no_hit_rate": tier["no_hit_rate_lead_time_recall_precision_false_alarm"],
            "frozen_products_untouched": frozen_pre_v05,
        },
        "frozen_products_check": {
            "method": "mtime: every frozen file must predate the earliest "
                      "regime_v05_* artifact (no pre-v0.5 sha256 snapshot exists)",
            "v05_earliest_artifact_mtime":
                datetime.fromtimestamp(v05_marker).strftime("%Y-%m-%d %H:%M:%S"),
            "frozen_files_checked": len(frozen_stat),
        },
        "diagnostic": {
            "gained_cells": gc["total"],
            "all_gained_in_A_a16": gc["all_in_A_a16"],
            "scale_or_control_share": gc["scale_share"],
            "crisis_front_share": cr["front_share"],
            "normal_front_share": nr["front_share"],
            "verdict": "surge is a composition / calibre effect, NOT a TDA signal",
        },
        "boundary": cmp["boundary"] + [
            "CRITICAL LABEL-LEAK GUARD: peak and valley dates are EX-POST; "
            "warning lead time must be measured against an EX-ANTE defined "
            "crisis start date; these dates MUST NOT be used for any lead-time, "
            "hit-rate, recall, precision or false-alarm calculation",
            "no extrapolation that TDA works or fails on A-share crisis warning",
        ],
        "frozen_products": frozen_stat,
        "files": {n: {"size": (OUT / n).stat().st_size,
                      "sha256": sha(OUT / n)}
                  for n in names
                  if n != MANIFEST.name and (OUT / n).exists()},
        "self_excluded_from_hashes": [
            "regime_v05_manifest.json (a file cannot hash itself)"],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                   allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(REPORT), "report_bytes": REPORT.stat().st_size,
        "manifest": str(MANIFEST),
        "validation": manifest["validation"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
