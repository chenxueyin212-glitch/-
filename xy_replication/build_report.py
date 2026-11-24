"""由已审计CSV/JSON生成兴业复现HTML；不在报告层重新计算或挑选结果。"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"


def read_json(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def read_csv(name):
    with (OUT / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def pct(x, digits=2):
    if x in (None, ""):
        return "—"
    return f"{float(x)*100:.{digits}f}%"


def num(x, digits=2):
    if x in (None, ""):
        return "—"
    return f"{float(x):.{digits}f}"


def table(headers, rows, caption=""):
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{caption}'


def source_note(text):
    return f'<p class="source">{text}</p>'


def main() -> None:
    s = read_json("xy_replication_summary.json")
    validation = read_json("xy_validation.json")
    pit_validation = read_json("xy_pit_validation.json")
    corrected = read_json("xy_corrected_comparison.json")
    shape = read_json("xy_landscape_shape_comparison.json")
    latest_name = "supplement_sw193_ifind_peak_v1_2"
    latest_csv = "xy_corrected_sw193_ifind_peak_features.csv"
    latest_json = "xy_corrected_sw193_ifind_peak_feature_summary.json"
    if latest_name not in corrected["report_period_metrics"]:
        latest_name = "supplement_sw193_v1_1"
        latest_csv = "xy_corrected_supplemented_features.csv"
        latest_json = "xy_corrected_supplemented_feature_summary.json"
    assert corrected["overall_pass"] is True
    public_summary = read_json("xy_corrected_feature_summary.json")
    sw193_summary = read_json("xy_corrected_supplemented_feature_summary.json")
    latest_summary = read_json(latest_json)
    public_features = read_csv("xy_corrected_features.csv")
    sw193_features = read_csv("xy_corrected_supplemented_features.csv")
    corrected_features = read_csv(latest_csv)
    assert [r["date"] for r in public_features] == [r["date"] for r in sw193_features] == [r["date"] for r in corrected_features]
    perf = read_csv("xy_performance.csv")
    pit_perf = read_csv("xy_pit_performance.csv")
    signal_stats = read_csv("xy_signal_forward_stats.csv")
    yearly = read_csv("xy_yearly_returns.csv")
    daily = read_csv("xy_daily_returns.csv")
    pmap = {(r["model"], r["execution"], r["period"]): r for r in perf}
    ppmap = {(r["execution"], r["period"]): r for r in pit_perf}
    smap = {(r["model"], r["period"]): r for r in signal_stats}
    main = pmap[("h2_count", "causal_open", "report_sample")]
    main_close = pmap[("h2_count", "report_close", "report_sample")]
    post = pmap[("h2_count", "causal_open", "post_publication")]
    pit_main = ppmap[("causal_open", "report_sample")]
    ref = s["report_reference_standalone"]
    variant_labels = {
        "main_fixed_active124": "初轮主面板（固定活跃124）",
        "defective_legacy_experiment": "缺陷旧实验（仅审计）",
        "corrected_public_v1_0": "修正104行业：公开-only",
        "supplement_sw193_v1_1": "补证券Ⅱ：2016/12—2021/12",
        "supplement_sw193_ifind_peak_v1_2": "证券Ⅱ＋林业峰值窗口",
    }
    reconstruction_rows = []
    for name, label in variant_labels.items():
        m = corrected["report_period_metrics"][name]["full_figure13_window"]
        reconstruction_rows.append([
            label, f"{m['nodes_min']}—{m['nodes_max']}",
            f"{m['h2_max']}（{'、'.join(m['h2_max_dates'])}）",
            f"{m['landscape_l1_max']:.8f}（{'、'.join(m['landscape_max_dates'])}）",
            m["h2_le1_days"],
        ])
    reconstruction_table = table(
        ["数据版本", "节点范围", "H₂峰值（日期）", "景观L₁峰值（日期）", "N≤1日"],
        reconstruction_rows,
        source_note("区间均为2012-12-31至2025-05-30；缺陷旧实验从2014-02-21起。兴业原图峰值约0.014与75—80为图片估读，不是原始逐日数据，不能据此计算精确误差或反选版本。"))
    latest_metric = corrected["report_period_metrics"][latest_name]["full_figure13_window"]

    def shape_cell(version, field, window, digits):
        item = shape["versions"][version][field]["windows"][window]
        return (f"{item['value']:.{digits}f}<br><span class=\"note\">{item['date']}；"
                f"{item['n_nodes']}节点</span>")

    shape_specs = [
        ("H₁｜2015", "h1_landscape_l1", "2015", 6, "约0.04的小尖峰"),
        ("H₁｜2021上半年", "h1_landscape_l1", "2021H1", 6, "最高约0.11"),
        ("H₁｜2021下半年", "h1_landscape_l1", "2021H2", 6, "另有约0.10—0.11尖峰"),
        ("H₁｜2023", "h1_landscape_l1", "2023", 6, "约0.10尖峰"),
        ("H₂｜2015", "h2_landscape_l1", "2015", 8, "约0.002—0.003"),
        ("H₂｜2021上半年", "h2_landscape_l1", "2021H1", 8, "约0.013"),
        ("H₂｜2021下半年", "h2_landscape_l1", "2021H2", 8, "约0.014"),
        ("H₂｜2023", "h2_landscape_l1", "2023", 8, "峰值簇明显低于2021；不精确读数"),
    ]
    shape_rows = []
    for label, field, window, digits, original in shape_specs:
        shape_rows.append([
            label, original,
            shape_cell("corrected_public_v1_0", field, window, digits),
            shape_cell(latest_name, field, window, digits),
        ])
    shape_table = table(
        ["指标/阶段", "兴业截图可见特征（估读）", "公开-only v1.0：本地精确值", "v1.2：本地精确值"],
        shape_rows,
        source_note("本地值为2012-12-31至2025-05-30逐日特征的窗口最大值；原图列仅为用户所给图12/13的视觉估读。没有原文逐日序列，因此不计算曲线相关系数、精确相似度或逐日复现误差。"))

    latest_shape = shape["versions"][latest_name]
    h1_peaks = latest_shape["h1_landscape_l1"]["separated_peaks_60d"][:6]
    h2_peaks = latest_shape["h2_landscape_l1"]["separated_peaks_60d"][:6]
    cluster_rows = [
        [i + 1, h1_peaks[i]["date"], f"{h1_peaks[i]['value']:.6f}",
         h2_peaks[i]["date"], f"{h2_peaks[i]['value']:.8f}"]
        for i in range(min(len(h1_peaks), len(h2_peaks)))
    ]
    peak_cluster_table = table(
        ["按峰值排序", "H₁峰值日期", "H₁景观 L₁", "H₂峰值日期", "H₂景观 L₁"],
        cluster_rows,
        source_note("60日分离峰值：按数值降序取峰，且任意两个入选峰的日期至少相隔60个自然日，避免把同一个峰的连续交易日重复计数。取v1.2在2012-12-31至2025-05-30的前6个，用于核对“2021双主峰＋2023次生峰簇”的形态判断，不是与原文逐日数值比对。"))
    assessment = shape["shape_assessment"]
    shape_assessment_html = (
        "<div class=\"panel\"><b>机器摘要中的形态判断：</b>"
        f"H₁——{assessment['h1']}<br>H₂——{assessment['h2']}<br>"
        f"<span class=\"note\">{assessment['forbidden_inference']}；"
        "图12/13形态对照脚本未计算策略收益（strategy_performance_calculated=false）；第4节另有独立的预登记参数网格。</span></div>")

    peak_date = latest_metric["h2_max_dates"][0]
    peak_nodes = next(int(r["n_nodes"]) for r in corrected_features if r["date"] == peak_date)
    westock = corrected["supplement_audits"]["westock"]
    ifind = corrected["supplement_audits"]["ifind_peak"]
    lineage_table = table(
        ["版本/来源", "实际取得的数据", "进入特征窗口", "仍不能解决的问题"],
        [
            ["v1.0 公开-only｜申万公开trend",
             "修正版2014名单104个代码＋2021名单快照；3,339个特征日",
             "2015-07-01完整窗口100个行业；2021-12-10为102个",
             "公开接口断档不等于指数不存在；不是Wind原始导出"],
            ["v1.1 补证券Ⅱ｜腾讯自选股原始JSON",
             f"801193共{westock['rows']:,}行；实际{westock['actual_range'][0]}至{westock['actual_range'][1]}",
             f"{sw193_summary['supplement_usage']['eligible_industry_days_by_code']['801193']:,}个特征日的有效窗口依赖该补充",
             "2016-12-12以前仍无可批量核验历史；2015年缺口未解决"],
            ["v1.2 再补林业Ⅱ｜iFind完整短窗口表格",
             f"801011在{ifind['actual_close_range'][0]}至{ifind['actual_close_range'][1]}有{ifind['positive_close_days']}个正收盘日",
             f"{latest_summary['supplement_usage']['eligible_industry_days_by_code']['801011']}个峰值附近特征日使用该补充",
             "只覆盖峰值诊断窗口，不是2012—2021完整历史"],
        ],
        source_note("合并规则：申万公开正收盘优先，仅在公开缺失或非正时使用独立补充；不插值、不补周末/假期、不用其他行业替代。三个版本分开保存，不按图形或收益接近程度反选。"))
    overlap = westock["public_overlap"]
    supplement_audit_table = table(
        ["补充源验收", "结果"],
        [
            ["证券Ⅱ公开重叠", f"{overlap['days']}日：35日逐值一致；2018-09-03仅0.01指数点显示精度差，合并仍保留申万公开值"],
            ["证券Ⅱ快照SHA-256", westock["snapshot_sha256"]],
            ["林业Ⅱ短窗口完整性", f"{ifind['calendar_days_checked']}个连续日历日：{ifind['positive_close_days']}个正收盘、{ifind['blank_calendar_days']}个周末/假期空值；无重复、无截断"],
            ["林业Ⅱ快照SHA-256", ifind["snapshot_sha256"]],
        ])

    comparison_rows = [
        ["年化收益", pct(ref["annual_return"]), pct(main_close["annual_return"]), pct(main["annual_return"]), pct(pit_main["annual_return"])],
        ["年化波动", pct(ref["annual_volatility"]), pct(main_close["annual_volatility"]), pct(main["annual_volatility"]), pct(pit_main["annual_volatility"])],
        ["收益风险比", num(ref["return_risk_ratio"]), num(main_close["return_risk_ratio"]), num(main["return_risk_ratio"]), num(pit_main["return_risk_ratio"])],
        ["最大回撤", pct(ref["max_drawdown"]), pct(main_close["max_drawdown"]), pct(main["max_drawdown"]), pct(pit_main["max_drawdown"])],
        ["年均双边换手", num(ref["annual_two_sided_turnover"]), num(main_close["annual_two_sided_turnover"]), num(main["annual_two_sided_turnover"]), num(pit_main["annual_two_sided_turnover"])],
        ["期末净值", "约3.3（读图）", num(1+float(main_close["total_return"]), 3), num(1+float(main["total_return"]), 3), num(1+float(pit_main["total_return"]), 3)],
    ]
    comparison_table = table(
        ["指标", "兴业表1：万得全A", "主面板：报告收盘窗口", "主面板：严格开盘", "缺陷旧实验：仅审计"],
        comparison_rows,
        source_note("原报告：兴业证券，2025-07-08，表1；本地：申万A指801003代理，2015-07-01至2025-05-30，每边成本0.1%。最后一列存在行业代码映射错误，只保留防复发审计，不能作为同期口径证据。"))

    model_order = ["h2_count", "average_correlation", "leading_eigenvalue", "market_oversold", "market_volatility", "h2_landscape_low"]
    model_short = {
        "h2_count": "H2有限区间数≤1", "average_correlation": "平均相关性高极端",
        "leading_eigenvalue": "首特征值占比高极端", "market_oversold": "市场30日超跌",
        "market_volatility": "市场30日高波动", "h2_landscape_low": "H2景观L1低极端",
    }
    mechanism_rows = []
    for model in model_order:
        r = pmap[(model, "causal_open", "report_sample")]
        q = pmap[(model, "causal_open", "post_publication")]
        fs = smap[(model, "report_sample")]
        mechanism_rows.append([model_short[model], fs["raw_signal_days"], pct(r["exposure"]),
                               pct(r["annual_return"]), pct(r["max_drawdown"]), r["n_entries"],
                               pct(q["annual_return"]), pct(q["exposure"])])
    mechanism_table = table(
        ["信号", "报告期原始信号日", "报告期暴露", "报告期年化", "报告期回撤", "入场段数", "发布后年化", "发布后暴露"],
        mechanism_rows,
        source_note("本地计算；统一为t+1开盘进入、t+5开盘退出、4段开盘收益、每边0.1%。普通对照阈值仅用2012-12-31至2015-06-30；零暴露的发布后年化0%不代表有效。"))

    cited_rows = []
    corrected_case_names = ("corrected_public_v1_0", "supplement_sw193_v1_1", latest_name)
    for month in ("2020-03", "2022-04", "2024-02", "2025-01"):
        cases = [corrected["cited_periods"][name][month] for name in corrected_case_names]
        assert all(item == cases[0] for item in cases[1:])
        case = cases[0]
        dates = "、".join(case["le1_dates"]) if case["le1_dates"] else "无"
        cited_rows.append([
            month, f"{case['h2_min']}—{case['h2_max']}", len(case["le1_dates"]),
            f"<details><summary>查看日期</summary>{dates}</details>", "三个修正版一致",
        ])
    cited_table = table(
        ["报告点名时期", "月内H₂最小—最大", "N≤1日", "具体日期", "跨版本核验"], cited_rows,
        source_note("公开-only、补证券Ⅱ、证券Ⅱ＋林业峰值窗口三个修正版结果一致。原报告未公布逐日信号清单；本地空集只表示当前数据与N定义下未出现N≤1，不等于原报告无信号。"))

    sensitivity_rows = []
    for model in ["h2_count", "h2_landscape_low", "h2_betti_0p4", "h2_betti_0p6", "h2_betti_0p8"]:
        r = pmap[(model, "causal_open", "report_sample")]
        sensitivity_label = model_short[model] if model in model_short else {"h2_betti_0p4": "ε=0.4时Betti₂≤1", "h2_betti_0p6": "ε=0.6时Betti₂≤1", "h2_betti_0p8": "ε=0.8时Betti₂≤1"}[model]
        sensitivity_rows.append([sensitivity_label,
                                 pct(r["exposure"]), r["n_entries"], pct(r["annual_return"]), pct(r["max_drawdown"])])
    sensitivity_table = table(["N/低孔洞操作定义", "报告期暴露", "入场段数", "年化收益", "最大回撤"], sensitivity_rows,
                              source_note("固定ε规则几乎全部时间持有，已退化成近似买入持有，不能解释原报告所谓“极端信号较少”。该表是定义敏感性，不是调参竞赛。"))

    bootstrap_rows = []
    labels = {"average_correlation": "平均相关性", "market_oversold": "30日超跌", "market_volatility": "30日波动"}
    for period, plabel in [("report_sample", "报告期"), ("post_publication", "发布后")]:
        for other, olabel in labels.items():
            r = s["bootstrap"][f"h2_minus_{other}_{period}"]
            bootstrap_rows.append([plabel, f"H2 − {olabel}", pct(r["point"]),
                                   f"[{pct(r['ci95'][0])}, {pct(r['ci95'][1])}]"])
    bootstrap_table = table(["区间", "配对差", "年化日均收益差", "20日区块自助95%区间"], bootstrap_rows,
                            source_note("1,000次、seed=20261107；统计量为年化算术日均净收益差，不是CAGR差。全部区间跨零，不能声称拓扑相对普通机制有稳定增量。"))

    main_year = {r["year"]: r for r in yearly if r["period"] == "report_sample"}
    year_rows = []
    for year in sorted(main_year):
        r = main_year[year]
        year_rows.append([year + ("（至5月）" if year == "2025" else ""), pct(r["h2_return_net"]),
                          pct(r["benchmark_return"]), pct(r["exposure"])])
    year_table = table(["年份", "初轮主面板H2", "申万A指代理", "主面板暴露"], year_rows,
                       source_note("初轮固定活跃124序列的历史审计；不是修正版v1.0/v1.1/v1.2的新绩效。"))

    struct_rows = []
    for item in latest_summary["yearly"]:
        struct_rows.append([
            item["year"], item["days"], f"{item['nodes_min']}—{item['nodes_max']}",
            f"{item['h2_min']}—{item['h2_max']}", item["h2_le1_days"],
            f"{item['landscape_l1_max']:.8f}",
        ])
    structure_table = table(
        ["年份", "特征日", "节点范围", "H₂最小—最大", "N≤1日", "景观L₁峰值"], struct_rows,
        source_note("最新修正版v1.2逐日特征；2021-12-13切换分类名单。节点数由当日31个有效正收盘价和非零收益方差共同决定，不等于分类表代码数。"))

    post_note = (f"初轮主面板发布后仅{smap[('h2_count','post_publication')]['raw_signal_days']}个原始信号日，"
                 f"严格开盘年化{pct(post['annual_return'])}、暴露{pct(post['exposure'])}。"
                 "样本太少，不能据此确认或否定长期有效性；缺陷旧实验的发布后结果不再并列展示。")

    main_daily = [r for r in daily if r["model"] == "h2_count" and r["execution"] == "causal_open" and r["period"] == "report_sample"]
    post_daily = [r for r in daily if r["model"] == "h2_count" and r["execution"] == "causal_open" and r["period"] == "post_publication"]
    data = {
        "equity": {"dates": [r["date"] for r in main_daily],
                   "main": [round(float(r["strategy_equity_net"]), 6) for r in main_daily],
                   "benchmark": [round(float(r["benchmark_equity"]), 6) for r in main_daily]},
        "years": {"labels": list(main_year),
                  "main": [round(float(main_year[y]["h2_return_net"])*100, 4) for y in main_year],
                  "benchmark": [round(float(main_year[y]["benchmark_return"])*100, 4) for y in main_year]},
        "structure": {
            "dates": [r["date"] for r in corrected_features],
            "nodes": [int(r["n_nodes"]) for r in corrected_features],
            "h2": [int(r["h2_count"]) for r in corrected_features],
            "publicH2": [int(r["h2_count"]) for r in public_features],
            "publicLandscape": [round(float(r["h2_landscape_l1"]), 10) for r in public_features],
            "sw193Landscape": [round(float(r["h2_landscape_l1"]), 10) for r in sw193_features],
            "latestLandscape": [round(float(r["h2_landscape_l1"]), 10) for r in corrected_features],
        },
        "post": {"dates": [r["date"] for r in post_daily],
                 "main": [round(float(r["strategy_equity_net"]), 6) for r in post_daily],
                 "benchmark": [round(float(r["benchmark_equity"]), 6) for r in post_daily]},
    }

    cv = corrected["validation"]
    # ---- Qualitative relation + preregistered exploratory parameter grid ----
    study = read_json("xy_qualitative_parameter_study.json")
    ev1 = study["event_analysis"]["N_le_1"]
    ev0 = study["event_analysis"]["N_eq_0"]
    gm = study["grid_max"]
    o1 = study["original_reference_from_screenshots"]["table1_sw2_2015_07_2025_05"]
    o2 = study["original_reference_from_screenshots"]["table2_wind_level4_2016_01_2025_05"]
    gm_ratio = gm["annual_return"] / gm["annual_volatility"]

    original_rows = [
        ["区间", "2015/07—2025/05", "2016/01—2025/05", "2015/07—2025/05"],
        ["行业输入", "申万二级（Wind）", "万得四级（Wind）", "修正版公开申万二级 v1.2"],
        ["年化收益率", pct(o1["annual_return"]), pct(o2["annual_return"]), pct(gm["annual_return"])],
        ["年化波动率", pct(o1["annual_volatility"]), pct(o2["annual_volatility"]), pct(gm["annual_volatility"])],
        ["收益风险比", num(o1["return_risk_ratio"]), num(o2["return_risk_ratio"]), num(gm_ratio)],
        ["最大回撤", pct(o1["max_drawdown"]), pct(o2["max_drawdown"]), pct(gm["max_drawdown"])],
        ["年均双边换手", num(o1["annual_two_sided_turnover"]), num(o2["annual_two_sided_turnover"]), num(gm["annual_two_sided_turnover"])],
        ["基准年化收益", pct(o1["benchmark_annual_return"]), pct(o2["benchmark_annual_return"]), "—"],
        ["基准最大回撤", pct(o1["benchmark_max_drawdown"]), pct(o2["benchmark_max_drawdown"]), "—"],
    ]
    original_table = table(
        ["指标", "原文表1：standalone", "原文表2：万得四级稳健性", "本地网格内最高（含选择偏差）"],
        original_rows,
        source_note("前三列数字抄自用户提供的原文截图（非Wind导出、非原始逐日数据）；第四列是本地12格参数网格的最大值，属于同一段报告期上的样本内上界。三套行业输入、区间与执行细节不同，并列只为展示量级，不构成可比绩效对照。"))

    event_rows = [
        ["报告期信号日占比", pct(ev1["signal_day_share"]), pct(ev0["signal_day_share"]), "—"],
        ["事件簇（间隔>10自然日）", ev1["event_clusters"], ev0["event_clusters"], "—"],
        ["事件前20日基准下跌比例", pct(ev1["prior20_negative_share"]), pct(ev0["prior20_negative_share"]), "—"],
        ["事件前20日平均收益", pct(ev1["prior20_mean"]), pct(ev0["prior20_mean"]), "—"],
        ["事件后20日上涨比例", pct(ev1["next20_positive_share"]), pct(ev0["next20_positive_share"]), pct(ev1["unconditional_next20_positive_share"])],
        ["事件后20日平均收益", pct(ev1["next20_mean"]), pct(ev0["next20_mean"]), pct(ev1["unconditional_next20_mean"])],
        ["事件后20日中位收益", pct(ev1["next20_median"]), pct(ev0["next20_median"]), pct(ev1["unconditional_next20_median"])],
        ["事件日行业平均相关性", num(ev1["mean_industry_average_correlation_on_events"], 4), num(ev0["mean_industry_average_correlation_on_events"], 4), num(ev1["mean_industry_average_correlation_all"], 4)],
        ["事件日领先特征值占比", num(ev1["mean_leading_eigenvalue_share_on_events"], 4), num(ev0["mean_leading_eigenvalue_share_on_events"], 4), num(ev1["mean_leading_eigenvalue_share_all"], 4)],
    ]
    event_table = table(
        ["描述性统计", "本地 N≤1", "本地 N=0（更极端）", "无条件基线 / 全样本"],
        event_rows,
        source_note("基准为2015-07-01—2025-05-30的万得全A 881001.WI逐日收盘；前后20均以修正版特征交易日计。这是事件级描述统计，不含成本、不含择时、不含显著性检验或多重比较校正，不是策略绩效。"))

    def grid_rows(benchmark):
        return [
            [r["k"], r["hold_days"], pct(r["annual_return"]), pct(r["annual_volatility"]),
             pct(r["max_drawdown"]), pct(r["exposure"]), r["n_entries"],
             num(r["annual_two_sided_turnover"])]
            for r in study["grid"] if r["benchmark"] == benchmark
        ]

    grid_headers = ["N阈值 k", "延续天数", "年化收益", "年化波动", "最大回撤", "暴露", "建仓次数", "年均双边换手"]
    grid_table = table(grid_headers, grid_rows("881001.WI"),
                       source_note("万得全A逐日、严格开盘、每边0.1%成本、区间独立起算、期末强制平仓。12格全部披露，没有按绩效反选；网格最高值含选择偏差，不能当作策略绩效或复现证据。"))
    proxy_grid_table = table(grid_headers, grid_rows("801003.SW"),
                             source_note("同一网格改用申万A指801003代理，用于隔离基准差异；两套基准的最优格年化接近，说明差异主要不在基准。"))

    # ---- Signal-level IC diagnostics (exploratory; no new strategy result) ----
    ic = read_json("xy_ic_diagnostics.json")
    h20 = next(r for r in ic["horizon_ic"] if r["horizon_days"] == 20)
    ic_daily = next(r for r in ic["h20_binary_and_point_biserial"] if r["threshold_k"] == 1)
    ic_cluster = next(r for r in ic["h20_binary_and_point_biserial"]
                      if r["threshold_k"] == "cluster_deduplicated_N<=1")
    early = next(r for r in ic["N_distribution_drift"] if r["segment"] == "2015-2020")
    late = next(r for r in ic["N_distribution_drift"] if r["segment"] == "2021-2025")

    ic_horizon_table = table(
        ["未来h日", "有效样本", "Pearson IC", "Spearman IC", "20日区块自助95%区间",
         "naive t（无效）", "收盘口径IC", "尾部剔除"],
        [[f"{r['horizon_days']}日", r["n_observations"], num(r["ic_pearson"], 4),
          num(r["ic_spearman"], 4),
          f"[{num(r['ci95_block_bootstrap'][0], 4)}, {num(r['ci95_block_bootstrap'][1], 4)}]",
          num(r["naive_t_invalid"], 2), num(r["ic_pearson_close_to_close"], 4),
          r["n_dropped_tail"]]
         for r in ic["horizon_ic"]],
        source_note("主口径：t日收盘得到N_t，t+1开盘建仓，h日收益=open[t+1+h]/open[t+1]−1；信号s=−N，正IC表示孔洞越少未来收益越高。收盘口径=close[t+h]/close[t]−1仅作敏感性。IC为无量纲相关系数，不是百分比；尾部不足h+1日者剔除、不填零。naive t忽略重叠窗口与N_t自相关，会高估显著性，禁止用于判断。"))

    ic_binary_table = table(
        ["信号定义", "点二列IC", "信号日", "占比", "信号组后20日均值", "相对无条件提升", "信号组上涨比例"],
        [[(f"N≤{r['threshold_k']}" if isinstance(r["threshold_k"], int) else "N≤1且仅簇起点"),
          num(r["ic_point_biserial"], 4), r["signal_days"], pct(r["signal_share"]),
          pct(r["mean_forward20_on"]), pct(r["lift_vs_unconditional"]),
          pct(r["positive_share_on"])]
         for r in ic["h20_binary_and_point_biserial"]],
        source_note("点二列IC与提升度是同一信息的不同尺度；稀疏信号的IC会被√[p(1−p)]机械压小，故不能只看IC。最后一行把389个N≤1信号日压缩为40个独立事件簇起点，IC随之大幅下降，说明日级IC主要来自同一事件的重复计数。"))

    ic_bins_table = table(
        ["N分桶", "样本数", "占比", "后20日均值", "中位数", "上涨比例"],
        [[r["bin"], r["n"], pct(r["share"]), pct(r["mean_forward20"]),
          pct(r["median_forward20"]), pct(r["positive_share"])]
         for r in ic["h20_n_buckets"]],
        source_note(f"无条件后20日均值为{pct(ic['unconditional_forward20_mean'])}。低N桶整体较高，但N=4—10回升、并非严格单调；Spearman IC {num(h20['ic_spearman'], 4)} 明显高于 Pearson IC {num(h20['ic_pearson'], 4)}，说明关系偏秩/阈值型而非线性。"))

    sample_label = {"all_N=0_days": "全部N=0日", "N=0_cluster_starts": "仅N=0簇起点"}
    ret_label = {"close_to_close_20d": "收盘→收盘20日", "open_to_open_20d": "开盘→开盘20日"}
    ic_audit_table = table(
        ["N=0样本定义", "收益定义", "样本数", "后20日均值", "中位数", "上涨比例"],
        [[sample_label[r["sample"]], ret_label[r["return_definition"]], r["n"],
          pct(r["mean"]), pct(r["median"]), pct(r["positive_share"])]
         for r in ic["definition_sensitivity_audit"]],
        source_note("2×2口径审计：改变价格口径几乎不改变结论，改变样本定义（全部信号日 vs 每簇仅第一天）会使均值由约+2.2%翻为约−1.3%。因此上一节的反例是抽样口径效应，不是市场结论。"))

    ic_drift_table = table(
        ["区间", "样本", "N均值", "N中位", "N 10%分位", "N 90%分位", "P(N≤1)"],
        [[r["segment"], r["n"], num(r["mean_N"]), num(r["median_N"]),
          num(r["p10_N"]), num(r["p90_N"]), pct(r["share_N<=1"])]
         for r in ic["N_distribution_drift"]],
        source_note("同一批可用样本（剔除尾部不足20日者）。N整体抬升是节点数从104增至124/131后的结构漂移，不是市场状态本身变好或变坏。"))

    ic_year_table = table(
        ["年份", "样本", "Pearson IC", "Spearman IC", "后20日均值", "N≤1信号日占比"],
        [[r["year"], r["n"], num(r["ic_pearson"], 4), num(r["ic_spearman"], 4),
          pct(r["mean_forward20"]), pct(r["signal_day_share_N<=1"])]
         for r in ic["yearly_ic"]],
        source_note("描述性分年IC：h=20窗口重叠、每年仅约240个观测；2025只有76个重叠日且无N≤1信号，其+0.77属小样本极值，不得当作信号有效证据。"))

    ic_segment_table = table(
        ["区间", "样本", "Pearson IC", "区块自助95%区间", "后20日均值", "N≤1信号日占比"],
        [[r["segment"], r["n"], num(r["ic_pearson"], 4),
          f"[{num(r['ci95_block_bootstrap'][0], 4)}, {num(r['ci95_block_bootstrap'][1], 4)}]",
          pct(r["mean_forward20"]), pct(r["signal_day_share_N<=1"])]
         for r in ic["segment_ic"]],
        source_note("分段IC与分年IC不矛盾：把多年混在一起算一个相关时，跨年的N水平与收益水平差异会互相抵消。两段区间均跨零。"))

    ic_details = (
        "<details><summary>展开：分年IC与分段IC稳定性</summary>"
        + ic_year_table + ic_segment_table + "</details>"
        + "<details><summary>展开：N分布漂移（固定阈值失效的直接证据）</summary>"
        + ic_drift_table + "</details>"
        + "<details><summary>展开：N=0 结论的2×2口径审计</summary>"
        + ic_audit_table + "</details>"
    )

    audit_table = table(["检查", "结果"], [
        ["修正版公开-only", f"{cv['corrected_public_v1_0']['membership_days_recalculated']}日行业会员关系逐日重算；9个关键日期的全部拓扑字段一致"],
        ["修正版补证券Ⅱ", f"{cv['supplement_sw193_v1_1']['membership_days_recalculated']}日会员关系＋{cv['supplement_sw193_v1_1']['provenance_days_recalculated']}日补充来源记录；9个关键日期拓扑一致"],
        ["修正版证券Ⅱ＋林业峰值", f"{cv[latest_name]['membership_days_recalculated']}日会员关系＋{cv[latest_name]['provenance_days_recalculated']}日来源记录；9个关键日期拓扑一致"],
        ["万得全A逐日基准", "3,012行日线，150个月末锚点全部一致；2014-10-31月线HIGH误填2947.91已按MATCH收盘2946.80修正；原始快照SHA-256 5619fbce…"],
        ["预登记网格", "k∈{0,1,2,3}×延续{4,8,12}×两套基准=24格，全部披露；网格最大值标注选择偏差，不用于反选版本"],
        ["信号层IC诊断", "2,391报告日×5个未来期；20日配对区块自助1,000次；簇去重点二列IC、8个N分桶、分年/分段IC、2×2口径审计全部披露；所有自助区间跨零"],
        ["修正版数值与配置", f"三个版本各3,339日，无NaN/Infinity；配置SHA-256：{public_summary['config_sha256'][:12]}… / {sw193_summary['config_sha256'][:12]}… / {latest_summary['config_sha256'][:12]}…"],
        ["图12/13形态对照", "每版报告窗口2,994日；万得全A881001.WI月线150点只作背景；2021-12-31与2025-05-30锚点经短查询复核，不计算截图伪精确相似度"],
        ["初轮主面板历史审计", f"{validation['forward_returns_recalculated']}条前向收益；{validation['daily_positions_recalculated']}条逐日仓位；{validation['performance_groups_recalculated']}组绩效独立重算"],
        ["缺陷旧实验", f"保留{pit_validation['n_features']}日及{pit_validation['performance_groups_recalculated']}组绩效的重算记录，但行业代码映射有错误，不作为兴业同期口径证据"],
        ["数学内核", "24点确定性球面H₂=1；ripser与GUDHI持续图交叉核验通过"],
        ["日期因果", "初轮绩效审计中，原始信号t只进入t+1至t+4收盘段，或t+1开盘至t+5开盘；发布后区间不继承旧信号"],
        ["本轮计算边界", "三个修正版重算行业输入与拓扑特征；确认性策略绩效仍未计算，第4节24格参数网格是预登记的探索性敏感性分析、全披露且不用于反选；未读取、未修改、未评分Gate 1最终测试，Gate 2未启动"],
    ])
    proxy_best = max([r for r in study["grid"] if r["benchmark"] == "801003.SW"],
                     key=lambda r: r["annual_return"])
    qualitative_vars = {
        "signal_share": pct(ev1["signal_day_share"]),
        "event_clusters": ev1["event_clusters"],
        "n0_next20": pct(ev0["next20_mean"]),
        "ev1_next20": pct(ev1["next20_mean"]),
        "grid_max_ann": pct(gm["annual_return"]),
        "grid_max_mdd": pct(gm["max_drawdown"]),
        "grid_max_entries": gm["n_entries"],
        "grid_min_ann": pct(study["grid_min"]["annual_return"]),
        "proxy_best_ann": pct(proxy_best["annual_return"]),
        "mid_exposure": pct(gm["exposure_2021_2023"]),
        "ic_h20": num(h20["ic_pearson"], 4),
        "ic_h20_spearman": num(h20["ic_spearman"], 4),
        "ic_ci": f"[{num(h20['ci95_block_bootstrap'][0], 4)}, {num(h20['ci95_block_bootstrap'][1], 4)}]",
        "ic_daily": num(ic_daily["ic_point_biserial"], 4),
        "ic_cluster": num(ic_cluster["ic_point_biserial"], 4),
        "ic_daily_days": ic_daily["signal_days"],
        "ic_cluster_days": ic_cluster["signal_days"],
        "drift_early_median": num(early["median_N"], 1),
        "drift_late_median": num(late["median_N"], 1),
        "share_early": pct(early["share_N<=1"]),
        "share_late": pct(late["share_N<=1"]),
        "ic_t20": num(h20["naive_t_invalid"], 2),
        "ic_t40": num(next(r for r in ic["horizon_ic"] if r["horizon_days"] == 40)["naive_t_invalid"], 2),
        "ic_year_min": num(min(r["ic_pearson"] for r in ic["yearly_ic"] if r["ic_pearson"] is not None), 2),
        "ic_year_max": num(max(r["ic_pearson"] for r in ic["yearly_ic"] if r["ic_pearson"] is not None), 2),
        "ic_seg_early": num(next(r for r in ic["segment_ic"] if r["segment"] == "2015-2020")["ic_pearson"], 3),
        "ic_seg_late": num(next(r for r in ic["segment_ic"] if r["segment"] == "2021-2025")["ic_pearson"], 3),
        "ic_2025_n": next(r for r in ic["yearly_ic"] if r["year"] == "2025")["n"],
    }
    remaining_gaps_html = "".join(f"<li>{item}</li>" for item in corrected["remaining_gaps"])

    template = Template(r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>兴业证券相关网络 H₁/H₂：公开数据重建、形态对照与差异审计</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
:root{--ink:#172033;--muted:#657086;--line:#dfe4ec;--paper:#f5f7fa;--card:#fff;--blue:#2457a7;--red:#c74343;--green:#16836a;--amber:#a56a09}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.72 "Segoe UI","Microsoft YaHei",sans-serif}.wrap{max-width:1240px;margin:auto;padding:34px 26px 70px}header{padding:30px 34px;background:linear-gradient(135deg,#102c55,#2457a7);color:#fff;border-radius:16px}h1{font-size:30px;line-height:1.3;margin:0 0 10px}h2{font-size:22px;margin:38px 0 14px;border-left:4px solid var(--blue);padding-left:12px}h3{font-size:17px;margin:24px 0 10px}.subtitle{opacity:.88}.badge{display:inline-block;padding:3px 10px;border:1px solid #ffffff66;border-radius:20px;margin:8px 8px 0 0}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}.card,.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}.metric{font-size:25px;font-weight:700}.label{color:var(--muted);font-size:13px}.neg{color:var(--green)}.pos{color:var(--red)}.warn{border-left:4px solid var(--amber);background:#fffaf0}.danger{border-left:4px solid var(--green);background:#f3fbf8}.ok{border-left:4px solid var(--blue);background:#f3f7fd}.chart{height:390px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:8px}.table-wrap{overflow:auto;background:#fff;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}th,td{padding:10px 12px;border-bottom:1px solid #e8ecf2;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#edf2f8;color:#31425c;position:sticky;top:0}.source{font-size:12px;color:var(--muted);margin:8px 2px}.note{color:var(--muted)}.formula{font-family:Georgia,serif;background:#edf2f8;padding:14px;border-radius:8px;text-align:center;font-size:17px}.figures{display:grid;grid-template-columns:1fr 1fr;gap:14px}.figures img{width:100%;border:1px solid var(--line);border-radius:8px;background:#fff}code{background:#eaf0f7;padding:2px 5px;border-radius:4px}pre{background:#10233d;color:#e8eef8;padding:16px;border-radius:10px;overflow:auto;font-size:12px}a{color:var(--blue)}ul{margin-top:8px}.small{font-size:13px}.footer{margin-top:36px;color:var(--muted);font-size:12px}@media(max-width:900px){.grid{grid-template-columns:1fr 1fr}.figures{grid-template-columns:1fr}.wrap{padding:18px 12px}header{padding:24px 20px}.chart{height:330px}}
</style></head><body><main class="wrap">
<header><h1>兴业证券相关网络 H₁/H₂：公开数据重建与复现差异审计</h1><div class="subtitle">《捕捉市场的形状——拓扑数据分析在投资中的应用》｜图12/13/14与案例期核验｜初轮standalone绩效仅作历史审计</div><span class="badge">修正版104行业名单</span><span class="badge">公开-only / 两项独立补充</span><span class="badge">VR / H₁/H₂ / 持久景观</span><span class="badge">三版本独立重算通过</span></header>
<section class="grid">
<div class="card"><div class="label">最新修正版 H₂ 峰值</div><div class="metric">$latest_h2</div><div class="label">$peak_date；当日$peak_nodes个有效节点</div></div>
<div class="card"><div class="label">兴业图14孔洞峰值</div><div class="metric">约75—80</div><div class="label">图片估读；本地仍少20—25个</div></div>
<div class="card"><div class="label">最新修正版景观 L₁ 峰值</div><div class="metric">$latest_landscape</div><div class="label">原图13约0.014；均为2021-06-09</div></div>
<div class="card"><div class="label">独立复核</div><div class="metric">3 × 3,339日</div><div class="label">27个关键日期拓扑重算一致</div></div>
</section>
<div class="panel danger"><b>本轮结论：</b>已经实际重建并补充部分真实行业历史，而不是只比较旧有数据。但在2021年峰值窗口同时补入证券Ⅱ和林业Ⅱ、达到104个有效节点后，H₂峰值仍为55。因此，与原图约75—80的差距不能继续简单归因于这两个行业缺失；剩余差异还涉及Wind原始逐日序列、N的精确实现或收益细节。当前版本不是兴业Wind原始数据，也没有据此给出确认性策略绩效；第4节的参数网格是预先登记、全披露的探索性敏感性分析，不能当作复现成功。</div>
<h2>1. 实际重建了什么：来源、覆盖与版本分离</h2>
<p>修正版先纠正旧实验的代码映射：剔除早已停用的801031，以801192银行Ⅱ替代误用的一级银行801780，补入801222计算机应用Ⅱ，并以801751/801752替代误用的801762/801763。随后分别保留公开-only、仅补证券Ⅱ、证券Ⅱ＋林业峰值窗口三个版本。</p>$lineage_table$supplement_audit_table
<h3>图13/14时间范围内的五版本对照</h3>$reconstruction_table
<div class="panel warn"><b>不能按“更接近原图”反选数据：</b>公开-only修正版的景观峰值较接近0.014；加入真实证券Ⅱ后，H₂峰值仅从54升至55，景观峰值反而下降；再补林业Ⅱ后H₂仍为55。节点增加不保证所有拓扑指标单调接近原文。</div>
<h2>2. 图12/13形态对照与数量级核验</h2>
<div class="panel ok"><b>直接回答：</b>有相似图形，而且H₁的整体相似度高于H₂。H₁在2021上半年与2023年均出现约0.10主峰、2015年出现约0.04小峰；H₂也重现了2021年双峰值簇和2023年次生峰值簇。但局部峰值高度、日期和其他年份并不逐点一致，不能称为精确复现。</div>
<div class="figures"><figure><img src="../third_party/xyquant_images/figure12_h1_landscape.png" alt="兴业图12一维持久景观范数"><figcaption>兴业原图12：一维持久景观范数与万得全A，2012/12—2025/05。</figcaption></figure><figure><img src="xy_h1_landscape_wind_monthly.png" alt="本地H1持久景观与万得全A月线"><figcaption>本地v1.2：H₁逐日景观L₁；万得全A月线仅作背景。</figcaption></figure><figure><img src="../third_party/xyquant_images/figure13_h2_landscape.png" alt="兴业图13二维持久景观范数"><figcaption>兴业原图13：二维持久景观范数与万得全A，2012/12—2025/05。</figcaption></figure><figure><img src="xy_h2_landscape_wind_monthly.png" alt="本地H2持久景观与万得全A月线"><figcaption>本地v1.2：H₂逐日景观L₁；纵轴与原图同为0—0.016以便观察。</figcaption></figure></div>
$shape_table
<h3>主要峰值簇的机器结果：v1.2 的 60 日分离峰</h3>$peak_cluster_table
$shape_assessment_html
<div class="panel warn"><b>景观范数相似 ≠ 孔洞数量已经复现：</b>‖λ‖₁=Σ(d−b)²/4受持久度平方加权，而图14的N是区间数量。图12/13形态接近不会自动消除本地H₂峰值55与原图约75—80之间的差距，也不能据此推出择时收益有效。</div>
<h3>三个修正版的H₁/H₂曲线：全部保留，不反选</h3><figure><img style="width:100%;border:1px solid var(--line);border-radius:8px;background:#fff" src="xy_landscape_three_versions.png" alt="三个修正版H1与H2持久景观"><figcaption class="source">公开-only、补证券Ⅱ、证券Ⅱ＋林业峰值窗口均完整保留。图内版本差异很小，但不能据此忽略原始Wind逐日输入和N定义的缺口。</figcaption></figure>
<p class="source">本地蓝线为逐日拓扑特征；红色基准来自Wind Alice连接器的881001.WI月线MATCH收盘，共150个月末点，仅作视觉背景，与蓝线频率不同，不参与拓扑、信号或收益计算。</p>
<h3>修正版节点数与 H₂ 有限区间数</h3><div id="structure" class="chart"></div>$structure_source
<h3>三个修正版的二维持久景观 L₁</h3><div id="landscape" class="chart"></div>$landscape_source
<details><summary>查看最新修正版逐年节点、H₂和景观峰值</summary>$structure_table</details>
<h2>3. 报告点名的四个时期</h2>$cited_table
<p>2020年3月与2024年2月确实出现低孔洞；2022年4月最小H₂为6、2025年1月最小为4，均未达到N≤1。这是一致与不一致并存的复现记录，不能包装成四期全部命中，也不能据此直接证伪原报告。</p>
<h2>4. 定性关系与预登记参数网格（探索性）</h2>
<div class="panel warn"><b>要回答的问题：</b>不必呆板照搬参数，数据不同，能否通过调参得到"弱一点或类似"的结果。答案是：<b>能调出弱的正收益，但调不出原文的证据结构</b>。网格在查看任何组合绩效之前固定为 N阈值 k∈{0,1,2,3} × 信号延续{4,8,12}个特征日，两套基准共24格全部披露，不按结果反选；网格最大值只标为同一段报告期上的样本内上界。窗口长度仍固定30日：重算20/40日VR拓扑属于另一实验，会再放大自由度。</div>
<div class="figures"><figure><img src="../third_party/xyquant_images/table1_figure15_standalone.png" alt="原文表1与图15"><figcaption>用户提供的原文截图：表1 standalone绩效与图15净值。蓝线呈少数几次陡升＋长时间平台，说明信号极稀疏。</figcaption></figure><figure><img src="../third_party/xyquant_images/table2_wind_l4_robustness.png" alt="原文表2与万得四级行业说明"><figcaption>原文表2：改用<b>万得四级行业</b>做行业定义稳健性，2016/01—2025/05。该行业分类数据本项目没有取得，不能声称复现。</figcaption></figure><figure><img src="../third_party/xyquant_images/figure16_wind_l4_equity.png" alt="原文图16万得四级净值"><figcaption>原文图16：万得四级行业口径净值，同样是稀疏阶跃形态。</figcaption></figure></div>
$original_table
<h3>4.1 原文定性链条，先分清来源</h3>
<ul>
<li><b>原文可见文字（可核实）：</b>"当2维孔洞极少时<b>似乎</b>对应着潜在的反弹"是定性措辞；"极端信号较少出现，一旦反弹往往有短期持续性"是把信号延续4个交易日的理由；表1/表2与图15/16是结果展示。</li>
<li><b>本地观察（本节新增）：</b>修正版 v1.2 在报告期 N≤1 占 $signal_share、共 $event_clusters 个事件簇，远称不上"极端信号较少"；事件前后市场状态、相关结构及24格绩效见下表。</li>
<li><b>我们的推断，原文未确认：</b>普跌时行业收益同步化（平均相关性、领先特征值占比升高）可能使VR复形的高维空洞塌缩。可见原文没有给出这个机制，本项目也不把它写成已验证结论。</li>
</ul>
<h3>4.2 事件级定性核验：有一点弱信号，但更极端的阈值把它推翻</h3>
<figure><img style="width:100%;border:1px solid var(--line);border-radius:8px;background:#fff" src="xy_qualitative_h2_events.png" alt="H2曲线与低孔洞事件"><figcaption class="source">上：修正版v1.2的H₂曲线、N=1阈值与42个事件起点，灰线为万得全A逐日收盘；下：事件前20日与后20日基准收益散点，无成本、无策略，仅描述性。</figcaption></figure>
$event_table
<div class="panel warn"><b>一个口径依赖的反例（4.4节已修正）：</b>在"每个事件簇只取第一天"的事件级口径下，把阈值调到更极端的 N=0，事件日行业平均相关性升到0.6934、领先特征值占比0.7198，但后20日基准收益均值反而为 $n0_next20、上涨比例仅45.7%，低于无条件基线。它确实说明<b>可交易的首次触发时点并不占优</b>；但4.4节的全样本IC、N分桶与2×2口径审计显示，若看全部N=0日，低孔洞<b>状态</b>与后续收益存在弱正向关联。因此不能笼统写成"关系不单调"——结论随"事件如何定义"改变，这种口径敏感性本身就是低频稀疏信号最大的风险之一。</div>
<h3>4.3 预登记参数网格：12格全部披露（万得全A逐日）</h3>
<figure><img style="width:100%;border:1px solid var(--line);border-radius:8px;background:#fff" src="xy_parameter_grid_equity.png" alt="预登记参数网格净值"><figcaption class="source">12条浅色曲线为全部组合，黑线为网格内最高年化（k=2、延续4日）；下方是它的0/1持仓阶梯。本地也有阶跃形态，但建仓次数与出现年份和原文不同。</figcaption></figure>
$grid_table
<details><summary>展开：同一网格改用申万A指801003代理的12格</summary>$proxy_grid_table</details>
<div class="panel danger"><b>调参结论，不粉饰：</b>网格内最高年化 $grid_max_ann（k=2、延续4日），不到原文表1 12.87%的一半；最大回撤 $grid_max_mdd，是原文−16.34%的两倍多；建仓 $grid_max_entries 次，而原图15/16只有约8—10次显著阶跃。最差格为 $grid_min_ann。换成代理基准的最优格也只有 $proxy_best_ann，说明<b>换成真正的万得全A逐日仍救不了绩效，差异主要不在基准</b>。网格最优组合在2021—2023的暴露只有 $mid_exposure，几乎全程空仓，而原文图15/16这几年恰有明显阶跃：信号的时间分布都不一样。更关键的是，这个"最好"的 $grid_max_ann 是从12格里挑出来的，含选择偏差，属于样本内拟合，<b>不能当作复现证据或策略有效性</b>。表2/图16使用万得四级行业，本项目没有该数据，本节不声称复现那一部分。</div>
<h3>4.4 信号层诊断：对低频稀疏信号，IC 比年化更合适</h3>
<div class="panel ok"><b>为什么补这一节：</b>年化是"固定阈值＋仓位规则"的账户结果，不是信号质量的度量。对一年只触发几次的信号，9.8年的复利分母会把少数几次事件摊平；暴露15%与58%的参数格本就不可比；复利还会让收益极度依赖事件发生在哪一年。表格里的年化只因原文表1报的就是年化才保留作对照，不应作为主判据。真正该先问的是：<b>信号能否排序未来收益</b>。这里是<b>时序择时</b>，只有一个市场标的、没有横截面，因此选股意义上的逐期截面RankIC不适用；能算的是时序IC、点二列IC与分桶单调性。</div>
<div class="panel warn"><b>IC本身也有四个陷阱，本节逐一处理：</b>①稀疏二元信号的点二列IC被√[p(1−p)]机械压小，IC小不等于无提升；②h日窗口重叠且N_t强自相关，naive t值会严重高估显著性，故用20日配对区块自助；③392个信号日其实只有42个事件簇，日级观测会把一次事件重复计数，故另算簇去重IC；④IC随年份与N的分布漂移，故报分年、分段与分布漂移，不做单一全样本定论。</div>
<figure><img style="width:100%;border:1px solid var(--line);border-radius:8px;background:#fff" src="xy_ic_diagnostics.png" alt="时序IC、N分桶与分年稳定性"><figcaption class="source">上：五个未来期的Pearson IC与20日区块自助95%区间（每个都跨零）、Spearman点估计；中：按N分桶的未来20日平均收益与无条件基线；下：分年IC，2025仅76个重叠观测。IC为相关系数、无量纲。</figcaption></figure>
<h4>4.4.1 多期时序IC</h4>$ic_horizon_table
<h4>4.4.2 二元信号的点二列IC与提升度</h4>$ic_binary_table
<h4>4.4.3 N分桶：单调性检验</h4>$ic_bins_table
$ic_details
<div class="panel danger"><b>IC给出的答案，比年化更干净、也更不利：</b>
① 20日Pearson IC为 $ic_h20、Spearman为 $ic_h20_spearman，但区块自助95%区间 $ic_ci 跨零；h=1/5/10/40也全部跨零。naive t在h=20为$ic_t20、h=40为$ic_t40，看似显著，却是忽略重叠窗口与自相关的伪显著，禁止使用。<br>
② 日级二元IC $ic_daily（$ic_daily_days个信号日）压缩到$ic_cluster_days个独立簇起点后只剩 $ic_cluster：一次事件被重复包装成几十个日级正确，正是低频信号最该防的膨胀。<br>
③ 分年IC在$ic_year_min到$ic_year_max之间剧烈摆动，分段2015—2020约$ic_seg_early、2021—2025约$ic_seg_late，两段区间也都跨零；2025年该值达$ic_year_max，却只有$ic_2025_n个重叠日且当年无N≤1信号，属小样本极值。<br>
④ 真正解释"年化低"的不是IC弱，而是<b>N的分布漂移</b>：2015—2020中位N=$drift_early_median、P(N≤1)=$share_early；2021—2025中位N=$drift_late_median、P(N≤1)=$share_late。节点数从104增至124/131后，固定的N≤1阈值几乎不再触发，网格最优组合在2021—2023才近乎空仓。<b>IC为正与策略几乎不交易可以同时成立</b>——IC衡量排序信息，年化衡量某个固定阈值规则赚了多少钱，两者不能互相替代。这也说明原文阈值不能照搬到本地重建面板上。</div>
<div class="panel warn"><b>由此修正4.2的判断：</b>4.2的"孔洞越少越反弹不单调"只成立于<b>簇起点</b>口径；2×2审计显示全部N=0日在收盘与开盘两种价格口径下后20日均值都约+2.2%，而35个簇起点在两种口径下都约−1.3%。差异来自"只取事件第一天"的抽样，不是价格口径。准确表述是：<b>低孔洞状态与后续收益有弱正向关联，但可交易的首次触发时点并不占优，且关联不显著、不稳定</b>。这是我们的口径诊断，不是原文结论，也不构成机制证明。</div>
<h2>5. 方法链与尚未确认的 N 定义</h2>
<div class="formula">过去30个简单收益 → ρ<sub>ij</sub> → d<sub>ij</sub>=√[2(1−ρ<sub>ij</sub>)] → VR<sub>ε</sub> → H₂　　｜　　‖λ‖₁=Σ(d<sub>i</sub>−b<sub>i</sub>)²/4</div>
<p>公开全文只写“二维孔洞数量N”，未明确它是全部有限持久区间、固定尺度Betti数，还是经过显著性筛选的孔洞。本项目主解释是有限H₂持久区间数；这个解释尚未获得原作者确认。2024年底本地持久图与原图可见绿色特征在数量级上接近，但不证明逐点一致。</p>
<div class="figures"><figure><img src="../third_party/xyquant_images/persistence_example.png" alt="兴业原报告条形码和持久图"><figcaption>兴业原报告图10/11：行业相关结构条形码与持久图。</figcaption></figure><figure><img src="../third_party/xyquant_images/distance_formula.png" alt="兴业距离公式"><figcaption>兴业原文公式图：直接核实距离定义。</figcaption></figure></div>
<h2>6. 初轮绩效审计：保留结果，但不与修正版混接</h2>
<div class="panel warn"><b>口径提醒：</b>下表和图表均是数据修正之前已完成的初轮历史审计，使用固定活跃124序列与申万A指代理。修正版v1.0/v1.1/v1.2此前未计算策略收益；第4节新增的预登记网格是<b>探索性参数敏感性</b>，基于v1.2与万得全A逐日，不是确认性复现结果，也不用于反选数据版本。缺陷旧实验存在801031/801780/801762/801763误用及801222遗漏，其+0.88%年化只保留用于防复发，不是有效复现证据。</div>$comparison_table
<div class="panel warn"><b>22.99%不是本报告目标：</b>它属于另含信用、汇率、地缘政治、通胀预期和负向泡沫指标的综合择时模型。这里只审计standalone拓扑信号。</div>
<h3>初轮主面板净值与分年表现</h3><div id="equity" class="chart"></div>$equity_source
<div id="years" class="chart"></div><details><summary>查看初轮分年精确值</summary>$year_table</details>
<details><summary>查看初轮普通机制、区块自助区间与N定义敏感性</summary>$mechanism_table$bootstrap_table$sensitivity_table</details>
<h3>初轮发布后独立样本</h3><div id="post" class="chart"></div><p>$post_note</p>$post_source
<h2>7. 工程验收与可复现文件</h2>$audit_table
<h3>关键文件</h3><pre># 修正版计算与独立复核
tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/compute_corrected_features.py --force
tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/compute_corrected_features.py --with-supplement --output-tag sw193_ifind_peak --force
tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/validate_corrected_features.py
tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/compare_landscape_figures.py
python tda_project/src/xy_replication/build_report.py
python tda_project/src/xy_replication/build_standalone_report.py
# 单文件离线版：outputs/xy_replication_report_standalone.html（图片与ECharts内嵌）

# 图12/13形态对照（月线基准只作背景）
outputs/xy_landscape_shape_comparison.json
outputs/xy_h1_landscape_wind_monthly.png / xy_h2_landscape_wind_monthly.png
outputs/xy_landscape_three_versions.png / xy_wind_all_a_monthly.csv

# 定性关系与预登记参数网格（探索性）
python tda_project/src/xy_replication/import_wind_all_a_daily.py
tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/qualitative_parameter_study.py
outputs/xy_wind_all_a_daily.csv / xy_wind_all_a_daily_audit.json
outputs/xy_qualitative_parameter_study.json / xy_qualitative_events.csv / xy_parameter_grid.csv
outputs/xy_qualitative_h2_events.png / xy_parameter_grid_equity.png
third_party/wind/881001WI_day_20121231_20250530.json

# 信号层IC诊断（探索性，不是策略绩效）
tda_project/.venv/Scripts/python.exe tda_project/src/xy_replication/ic_diagnostics.py
outputs/xy_ic_diagnostics.json / xy_ic_diagnostics.png
outputs/xy_ic_bins.csv / xy_ic_by_year.csv
third_party/xyquant_images/table1_figure15_standalone.png
third_party/xyquant_images/table2_wind_l4_robustness.png / figure16_wind_l4_equity.png

# 三版本特征与汇总
outputs/xy_corrected_features.csv
outputs/xy_corrected_supplemented_features.csv
outputs/xy_corrected_sw193_ifind_peak_features.csv
outputs/xy_corrected_comparison.json

# 原始补充快照与导入审计
third_party/westock/pt01801193_day_20121101_20211210.json
third_party/ifind/801011SL_day_20210401_20210630.json
outputs/xy_sw2014_supplement_audit.json / xy_ifind_supplement_audit.json

# 初轮绩效与缺陷实验只作历史审计
outputs/xy_replication_summary.json / xy_validation.json
outputs/xy_pit_sensitivity_summary.json / xy_pit_validation.json</pre>
<h2>8. 证据边界与真正需要补的原始材料</h2><ul>
<li><b>可以确认：</b>距离公式、30日窗口、H₂、N≤1、4日延续和standalone标的来自公开报告；修正版行业会员、补充来源及关键日期拓扑已独立重算。</li>
<li><b>已经缩小但不能闭合的差距：</b>修正代码和补充证券Ⅱ/林业Ⅱ显著改变曲线，却没有把H₂峰值推到原图约75—80；不能把剩余差距全部归因于这两个行业。</li>
$remaining_gaps_html
<li><b>指标口径：</b>4.4节的时序IC弱正但全部区块自助区间跨零；日级IC被事件簇重复计数显著抬高；N的分布漂移使固定N≤1阈值在2021年后几乎不触发。这些是信号层诊断，不构成策略有效性或复现结论；年化只作原文表1的对照，不是主判据。</li>
<li><b>不能外推：</b>本地差异既不证明兴业原报告有误，也不否定相关网络H₂或TDA整体；它与原Gate 1的交易日状态点云H₀/H₁实验是不同点云和不同任务。</li>
<li><b>流程状态：</b>第4节已用万得全A逐日做预登记的探索性参数网格，全部24格披露；其结果只用于判断参数敏感性，不用于反选行业版本、不冒充确认性绩效，也没有回答万得四级行业那一支。Gate 1继续暂停，待用户阅读后再讨论，Gate 2未启动，2025最终测试仍未读取。</li></ul>
<div class="footer">来源：兴业证券经济与金融研究院，报告日期2025-07-08；同花顺公开全文转载2025-07-10（非原PDF，需以机构原文为准）。行业主数据为申万宏源研究公开前端接口；2014版名单经公开分类资料与实际序列交叉核对。证券Ⅱ补充来自腾讯自选股连接器原始JSON，林业Ⅱ峰值窗口来自iFind原始表格；二者均非Wind原始导出。图12/13背景使用Wind Alice连接器881001.WI月线（2014-10-31一处误取HIGH已按MATCH收盘修正）；第4节另导入同一连接器返回的881001.WI逐日K线3,012行，经150个月末锚点核验，用于事件描述与探索性网格，仍非Wind原始导出。表1/表2/图15/图16来自用户补交的原文截图，数字为抄录或图片估读。快照及计算日期2026-11-07；本地特征截至2026-11-03。本报告仅用于研究复现与方法审计。</div>
</main><script>
const DATA=$data_json;
function baseAxis(){return {tooltip:{trigger:"axis"},grid:{left:62,right:62,top:52,bottom:62},dataZoom:[{type:"inside"},{type:"slider",height:18,bottom:18}],legend:{top:8}};}
function line(name,data,color){return {name:name,type:"line",showSymbol:false,data:data,lineStyle:{width:1.7,color:color},itemStyle:{color:color}};}
function make(id,option){const el=document.getElementById(id);if(!window.echarts){el.textContent="图表库未加载，请查看下方表格与CSV。";return;}const c=echarts.init(el);c.setOption(option);window.addEventListener("resize",function(){c.resize();});}
let o=baseAxis();o.xAxis={type:"category",data:DATA.equity.dates};o.yAxis={type:"value",name:"净值",scale:true};o.series=[line("主面板H2",DATA.equity.main,"#2457a7"),line("申万A指代理",DATA.equity.benchmark,"#c8795a")];make("equity",o);
o={tooltip:{trigger:"axis"},grid:{left:62,right:35,top:52,bottom:45},legend:{top:8},xAxis:{type:"category",data:DATA.years.labels},yAxis:{type:"value",name:"收益(%)"},series:[{name:"初轮主面板H2",type:"bar",data:DATA.years.main,itemStyle:{color:"#2457a7"}},{name:"申万A指代理",type:"line",data:DATA.years.benchmark,itemStyle:{color:"#c8795a"}}]};make("years",o);
o=baseAxis();o.xAxis={type:"category",data:DATA.structure.dates};o.yAxis=[{type:"value",name:"节点数",min:0},{type:"value",name:"H2区间数",min:0}];o.series=[line("v1.2节点数",DATA.structure.nodes,"#8795a8"),line("v1.0公开-only H2",DATA.structure.publicH2,"#6b8fb3"),line("v1.2最新H2",DATA.structure.h2,"#2457a7")];o.series[1].yAxisIndex=1;o.series[2].yAxisIndex=1;make("structure",o);
o=baseAxis();o.xAxis={type:"category",data:DATA.structure.dates};o.yAxis={type:"value",name:"H2景观L1",min:0};o.series=[line("v1.0公开-only",DATA.structure.publicLandscape,"#6b8fb3"),line("v1.1补证券Ⅱ",DATA.structure.sw193Landscape,"#a56a09"),line("v1.2证券Ⅱ＋林业峰值",DATA.structure.latestLandscape,"#2457a7")];make("landscape",o);
o=baseAxis();o.xAxis={type:"category",data:DATA.post.dates};o.yAxis={type:"value",name:"净值",scale:true};o.series=[line("初轮主面板H2",DATA.post.main,"#2457a7"),line("申万A指代理",DATA.post.benchmark,"#c8795a")];make("post",o);
</script></body></html>''')
    html = template.substitute(
        latest_h2=latest_metric["h2_max"], peak_date=peak_date, peak_nodes=peak_nodes,
        latest_landscape=f"{latest_metric['landscape_l1_max']:.8f}",
        lineage_table=lineage_table, supplement_audit_table=supplement_audit_table,
        reconstruction_table=reconstruction_table, comparison_table=comparison_table,
        shape_table=shape_table, peak_cluster_table=peak_cluster_table,
        shape_assessment_html=shape_assessment_html,
        original_table=original_table, event_table=event_table,
        grid_table=grid_table, proxy_grid_table=proxy_grid_table,
        ic_horizon_table=ic_horizon_table, ic_binary_table=ic_binary_table,
        ic_bins_table=ic_bins_table, ic_details=ic_details,
        **qualitative_vars,
        mechanism_table=mechanism_table, bootstrap_table=bootstrap_table,
        sensitivity_table=sensitivity_table, cited_table=cited_table, year_table=year_table,
        structure_table=structure_table, audit_table=audit_table,
        remaining_gaps_html=remaining_gaps_html,
        equity_source=source_note("初轮固定活跃124序列；严格开盘、含每边0.1%成本；报告期2015-07-01至2025-05-30。不是修正版绩效。"),
        structure_source=source_note("修正版v1.0与v1.2逐日特征；2021-12-13切换分类名单。2021—2022的节点变化会改变H₂分布，不应把全期当成恒定131或124节点。"),
        landscape_source=source_note("本地按Σ(d−b)²/4精确积分；2012-12-31至2026-11-03。原图13峰值约0.014仅为图片估读，图中不画伪精确的原文逐日序列。"),
        post_note=post_note, post_source=source_note("初轮主面板发布后2025-07-09至2026-11-03；2025-06-01至07-08为隔离过渡段；独立起算，不继承发布前信号。"),
        data_json=json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
    )
    target = OUT / "xy_replication_report.html"
    target.write_text(html, encoding="utf-8")
    print({"report": str(target), "bytes": target.stat().st_size,
           "latest_h2_max": latest_metric["h2_max"],
           "latest_landscape_l1_max": latest_metric["landscape_l1_max"],
           "confirmatory_strategy_performance_calculated": False,
           "exploratory_preregistered_grid_cells": len(study["grid"])})


if __name__ == "__main__":
    main()
