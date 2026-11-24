"""Build the integrated single-file offline Chinese v0.7 context report.

The report preserves the v0.5 crisis history, 47-event structure, conjectures,
references and frozen historical judgements, while using the accepted v0.6 early
curves through the v0.7 integrated export.  No persistent homology, statistical
test, verdict or performance result is recomputed.  Visible labels use Chinese
full names; engineering field names and original English names stay on hover.
"""
from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
PREFIX = "crisis_context_v07_"
REPORT = OUT / (PREFIX + "report.html")

chart = json.loads((OUT / (PREFIX + "chart_data.json")).read_text(encoding="utf-8"))
manifest = json.loads((OUT / (PREFIX + "manifest.json")).read_text(encoding="utf-8"))
integration = json.loads((OUT / "regime_v07_integration_manifest.json").read_text(encoding="utf-8"))
early_audit = json.loads((OUT / "regime_v06_early_input_audit.json").read_text(encoding="utf-8"))
assert all(integration["validation"].values()), "第七版整合宽表验收未全部通过"
assert all(manifest["validation"].values()), "第七版上下文导出验收未全部通过"

# 八·补：十四条推测一览。推测原文来自第一版判定文件（含提出时依据），
# 判定与实测数字只读第五版判定层产物，不在本脚本重新计算。
claims_v01 = {v["id"]: v["claim"] for v in json.loads(
    (OUT / "regime_conjecture_verdicts.json").read_text(encoding="utf-8"))["verdicts"]}
verdicts_v05 = json.loads((OUT / "regime_v05_verdicts.json").read_text(encoding="utf-8"))
conj_v05 = {c["id"]: c for c in verdicts_v05["conjectures"]}
with (OUT / "regime_v05_conclusion_ledger.csv").open(encoding="utf-8-sig", newline="") as _fh:
    ledger_v05 = {r["id"]: r for r in csv.DictReader(_fh)}
assert len(conj_v05) == 14 and set(conj_v05) == set(claims_v01) == set(ledger_v05)
for _cid, _c in conj_v05.items():
    # 判定引擎沿用旧字段名 v0_3_verdict，其值即本版（第五版）判定；与台账逐条核对
    assert _c["v0_3_verdict"] == ledger_v05[_cid]["v0_5_verdict"], _cid


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def rd(name):
    with (OUT / (PREFIX + name)).open("r", encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r)


ov = chart["overview"]
centers = chart["centers"]
phases = chart["phases"]
judge = chart["judgement"]
sample = chart["sample"]
stat = [r for r in ov if r["event_source"] != "外部金融定性危机"]
front = [r for r in stat if r["event_source"] == "前段新增急性事件"]
back = [r for r in stat if r["event_source"] == "后段冻结统计事件"]
ext = [r for r in ov if r["event_source"] == "外部金融定性危机"]

# 早期事件覆盖审计：只读取冻结宽表的首个／末个有效日期与事件窗内的
# 有效行数，不重算任何持续同调摘要。目的不是补数，而是把「面板未覆盖」、
# 「结构性无定义」与「覆盖期内待核空值」在展示层分开。
with (OUT / "regime_v07_split_wide.csv").open(encoding="utf-8-sig", newline="") as _fh:
    _wide_for_coverage = list(csv.DictReader(_fh))
metric_coverage = {}
for _k in chart["core_metrics"]:
    _dates = [r["date"] for r in _wide_for_coverage if r.get(_k, "") != ""]
    assert _dates, "摘要指标在冻结宽表中完全无有效日期：" + _k
    metric_coverage[_k] = {
        "first": min(_dates), "last": max(_dates), "valid_days": len(_dates),
    }

LINE_KEYS = {
    "a16": [k for k in chart["core_metrics"] if k.startswith("a16_")],
    "a27": [k for k in chart["core_metrics"] if k.startswith("a27_")],
    "b": [k for k in chart["core_metrics"] if k.startswith("b_")],
}
event_coverage = {}
for _e in chart["events"]:
    event_coverage[_e["event_id"]] = {
        _g: sum(
            any(f(r.get(k)) is not None for k in _keys)
            for r in _e["rows"]
        )
        for _g, _keys in LINE_KEYS.items()
    }

_front_events = sorted(
    (e for e in chart["events"] if e["event_source"] == "前段新增急性事件"),
    key=lambda e: e["onset"],
)
_front_a16 = [event_coverage[e["event_id"]]["a16"] for e in _front_events]
_front_b = [event_coverage[e["event_id"]]["b"] for e in _front_events]
assert len(_front_events) == 28
assert all(
    event_coverage[e["event_id"]]["a16"] == len(e["rows"])
    for e in _front_events
), "第七版统一 01—28 的十六行业摘要均应逐日整窗组覆盖"
assert all(
    event_coverage[e["event_id"]]["b"] == len(e["rows"])
    for e in _front_events
), "第七版统一 01—28 的行业相关点云均应逐日整窗组覆盖"
assert all(
    event_coverage[e["event_id"]]["a27"] == 0 for e in _front_events
), "前段完整二十七行业仍未补算，不得伪造"
assert event_coverage["126"]["a16"] == 44 and event_coverage["126"]["a27"] == 0
assert event_coverage["126"]["b"] == len(next(e for e in _front_events if e["event_id"] == "126")["rows"])
_front_unexplained_gaps = []
for _e in _front_events:
    for _k, _meta in metric_coverage.items():
        for _r in _e["rows"]:
            if f(_r.get(_k)) is not None:
                continue
            if _k == "a16_h1_birth_mean" and _r.get("a16_h1_count") == "0":
                continue
            if _r["date"] < _meta["first"] or _r["date"] > _meta["last"]:
                continue
            _front_unexplained_gaps.append((_e["event_id"], _r["date"], _k))
assert not _front_unexplained_gaps, \
    "前段事件出现覆盖期内待核空值，不得将其笼统写成未覆盖"

obs = {
    "n_stat": len(stat),
    "crisis_up": sum((f(r["crisis_cum_pct"]) or 0) > 0 for r in stat),
    "post_down": sum((f(r["post20_cum_pct"]) or 0) < 0 for r in stat),
    "w_post_gt_crisis": sum(
        a is not None and b is not None and a > b for a, b in
        ((f(r["a16_W_t_post20_mean"]), f(r["a16_W_t_crisis_mean"])) for r in stat)),
    "w_post_gt_pre": sum(
        a is not None and b is not None and a > b for a, b in
        ((f(r["a16_W_t_post20_mean"]), f(r["a16_W_t_pre20_mean"])) for r in stat)),
    "w_crisis_gt_pre": sum(
        a is not None and b is not None and a > b for a, b in
        ((f(r["a16_W_t_crisis_mean"]), f(r["a16_W_t_pre20_mean"])) for r in stat)),
    "peak_in_post": sum(
        f(r["a16_W_t_peak_offset_from_onset"]) is not None
        and f(r["a16_W_t_peak_offset_from_onset"]) >= f(r["n_crisis_days"]) for r in stat),
    "peak_in_pre": sum(
        f(r["a16_W_t_peak_offset_from_onset"]) is not None
        and f(r["a16_W_t_peak_offset_from_onset"]) < 0 for r in stat),
    "mean_pre": sum(f(r["pre20_cum_pct"]) or 0 for r in stat) / len(stat),
    "mean_crisis": sum(f(r["crisis_cum_pct"]) or 0 for r in stat) / len(stat),
    "mean_post": sum(f(r["post20_cum_pct"]) or 0 for r in stat) / len(stat),
    "front_crisis_days": sum(int(r["n_crisis_days"]) for r in front),
    "back_crisis_days": sum(int(r["n_crisis_days"]) for r in back),
    "front_with_summary": sum(int(r["a16_summary_available_days"]) for r in front),
    "h2_crisis_gt_pre": sum(
        a is not None and b is not None and a > b for a, b in
        ((f(r["b_h2_count_crisis_mean"]), f(r["b_h2_count_pre20_mean"])) for r in stat)),
}
obs["peak_in_crisis"] = obs["n_stat"] - obs["peak_in_post"] - obs["peak_in_pre"]

# 统一展示编号只存在于本报告，不改写任何冻结事件编号、标签或判定输入。
# 45 个统计事件与 2 个外部锚点一起按开始日期排序，编号 01—47。
EVENT_ORDER = sorted(
    ov, key=lambda r: (r["onset"], r["event_source"] == "外部金融定性危机",
                       int(r["event_id"])))
EVENT_ID_TO_DISPLAY = {r["event_id"]: f"{i:02d}" for i, r in enumerate(EVENT_ORDER, 1)}
EVENT_BY_ID = {r["event_id"]: r for r in EVENT_ORDER}
assert len(EVENT_ORDER) == len(EVENT_ID_TO_DISPLAY) == 47
assert [EVENT_ID_TO_DISPLAY[str(i)] for i in range(101, 129)] == [f"{i:02d}" for i in range(1, 29)]
assert EVENT_ID_TO_DISPLAY["18"] == "43" and EVENT_ID_TO_DISPLAY["19"] == "47"

# 每条统计段只挂靠到公开讨论的市场背景；组名不是新的独立危机计数。
def _ids(a, b):
    return [str(i) for i in range(a, b + 1)]


EVENT_GROUP = {}
for _eid in _ids(102, 104):
    EVENT_GROUP[_eid] = "R1A"
for _eid in _ids(105, 113):
    EVENT_GROUP[_eid] = "R1B"
for _eid in ("116", "117", "118"):
    EVENT_GROUP[_eid] = "R2A"
EVENT_GROUP.update({
    "101": "G2001", "114": "G2006", "115": "A530", "119": "R2C",
    "120": "R2D", "121": "G2009", "122": "R3A", "123": "R3A",
    "124": "R3B", "125": "R3B", "126": "R3B", "127": "R3C", "128": "R3C",
    "1": "R4A", "2": "R4B", "3": "A201602", "4": "A201604",
    "5": "R5", "6": "R5", "7": "R5", "8": "A2019",
    "9": "A2020A", "10": "A2020B", "11": "S2021", "12": "R6A", "13": "R6B",
    "14": "R7A", "18": "R7B", "15": "A202410", "16": "S202412",
    "17": "A202503", "19": "A202504",
})
assert set(EVENT_GROUP) == set(EVENT_BY_ID), "有事件未配置金融背景组"

GROUP_TEXT = {
    "G2001": ("2001 年初牛市末端调整", "高位回撤；没有找到该统计段的独立公认命名，不能把六月后的政策冲击倒填为当日已知成因。"),
    "R1A": ("2001 年国有股减持冲击", "国有股按市价减持引发供给与流通股东补偿担忧，是 2001—2005 长熊的前段。"),
    "R1B": ("2001—2005 股权分置长熊", "股权分置、非流通股悬置与补偿不确定性持续压制估值；每一段不是独立危机。"),
    "G2006": ("2006 年股改后牛市中段调整", "股改后上升趋势中的快速回撤；未找到该统计段独立、公认的危机命名。"),
    "A530": ("2007 年 5·30 印花税冲击", "牛市内印花税率调整与高位获利盘共同触发的急性政策冲击，不等于长期熊市。"),
    "R2A": ("2007—2008 高估值泡沫破裂前中段", "高估值、宏观紧缩、再融资与限售股解禁压力叠加，随后受到全球金融危机放大。"),
    "R2C": ("2008 年全球金融海啸主跌段", "美国次贷危机升级为全球金融海啸，外部盈利冲击与内部估值出清共振。"),
    "R2D": ("2008 年末政策修复期高波动", "政策托底和刺激预期带来反弹，但盈利下行与余波仍造成急性回撤；不是新一轮独立危机。"),
    "G2009": ("2009 年初刺激后修复期回撤", "危机后修复进程中的高波动调整，不能仅凭阈值切段认定新危机。"),
    "R3A": ("2009 年刺激退潮与政策转向", "四万亿刺激边际效应减弱、政策微调与扩容预期共同压制风险偏好。"),
    "R3B": ("2010 年紧缩、地产调控与欧债冲击", "通胀和地产调控带来紧缩预期，欧债危机与盈利下修进一步压制估值。"),
    "R3C": ("2011 年通胀紧缩、盈利下修与欧债", "货币紧缩、增长放缓和欧债危机延续慢性下跌；后段还应以 2013 年钱荒单独补充。"),
    "R4A": ("2015 年杠杆牛破灭与两轮股灾", "场内外杠杆出清、强平、跌停与停牌造成流动性螺旋，八月汇改与贬值预期再触发恐慌。"),
    "R4B": ("2015 年末至 2016 年初熔断与汇率压力", "熔断机制、既有涨跌停与恐慌交易相互放大，叠加大额贬值与全球风险偏好下降。"),
    "A201602": ("2016 年 2 月二次探底与资金收紧", "此前讨论归因于降准预期落空、资金面骤紧与风险资产分流；公开材料主要覆盖窗口末端。"),
    "A201604": ("2016 年春季信用与监管冲击", "信用违约打破刚兑预期、监管收紧和增长表态共同压低风险偏好，更像调整而非独立大危机。"),
    "R5": ("2018 年去杠杆、贸易摩擦与股权质押", "内部金融去杠杆与外部贸易摩擦双杀，股权质押平仓风险把小盘与民企融资压力反馈到市场。"),
    "A2019": ("2019 年 5 月贸易摩擦反复", "外部谈判反复造成短期风险溢价跳升，未形成与 2018 年同等级的新增长熊。"),
    "A2020A": ("2020 年初国内新冠疫情冲击", "疫情与封锁造成盈利和交易不确定性，节后集中释放恐慌，是典型外生急性事件。"),
    "A2020B": ("2020 年 3 月全球疫情与流动性冲击", "全球疫情扩散、风险资产抛售和美元流动性紧张共同传导至 A 股。"),
    "S2021": ("2021 年核心资产抱团瓦解", "实际利率上行与拥挤持仓反转引发高估值核心资产杀估值，属结构性危机，不等于全市场危机。"),
    "R6A": ("2022 年上半年多重宏观冲击", "全球紧缩、俄乌冲突、疫情与地产和增长预期共同压制，估值与盈利预期同时承压。"),
    "R6B": ("2022 年 9—10 月紧缩与贬值压力", "美联储鹰派、人民币贬值与资金流出预期加剧存量市场调整。"),
    "R7A": ("2023 年末至 2024 年初流动性冲击前段", "市场持续走弱后，雪球敲入、期货贴水和量化去杠杆开始形成负反馈，是第七轮末端的前段。"),
    "R7B": ("2024 年 2 月小微盘流动性危机", "雪球、对冲成本、杠杆中性策略平仓与小微盘低流动性形成踩踏，宽基指数低估真实伤害。"),
    "A202410": ("2024 年 10 月政策脉冲后的高位兑现", "九月末政策驱动急涨后，高位获利兑现与杠杆约束引发剧烈分化，不单独认定为长期危机。"),
    "S202412": ("2024 年 12 月小微盘结构性去杠杆", "退市新规临近、风险名单舆情、年末风格切换与前期巨大涨幅共同触发小微盘调整。"),
    "A202503": ("2025 年 3 月风险偏好收缩", "该统计段起点早于四月关税落地，不能倒填成因；可描述为外部不确定性下的预期转弱，窗口末端与关税崩盘重叠。"),
    "A202504": ("2025 年 4 月对等关税黑色星期一", "美国所谓对等关税引发全球风险资产急跌，A 股出现大面积跌停；随后政策托底并快速修复。"),
}
assert set(GROUP_TEXT) == set(EVENT_GROUP.values()), "金融背景组说明不完整"

diag = judge["diagnostic"]
cmp = judge["compare"]
gc = diag["gained_cells"]
cr = diag["group_composition"]["crisis_in_primary"]
nr = diag["group_composition"]["normal_proxy"]
era = diag["era_scale_a16"]

CSS = r"""
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
.wrap{max-width:1360px;margin:0 auto;padding:28px 20px 80px}
header h1{font-size:25px;margin:0 0 6px;letter-spacing:.3px}
header .sub{color:var(--muted);font-size:13px}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 6px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:10px 16px;min-width:138px}
.kpi b{display:block;font-size:21px;line-height:1.25;font-variant-numeric:tabular-nums}
.kpi span{color:var(--muted);font-size:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:20px 22px;margin:16px 0}
.card h2{font-size:17px;margin:0 0 12px;padding-bottom:9px;border-bottom:1px solid var(--line)}
.card h3{font-size:14px;margin:20px 0 8px;color:var(--muted)}
p{margin:8px 0}
.small{font-size:12.5px;color:var(--muted)}
.warn{background:#fff8e6;border-left:3px solid #e0a020;padding:10px 14px;border-radius:5px}
.boundary{background:#eef4ff;border-left:3px solid var(--blue);padding:10px 14px;border-radius:5px}
.leak{background:#fff4f1;border-left:4px solid #d93026;padding:11px 15px;border-radius:0 6px 6px 0;margin:14px 0}
.note{background:#f2f6fc;border-left:3px solid var(--blue);padding:10px 14px;border-radius:5px}
.ok{background:#eef8f2;border-left:3px solid var(--down);padding:10px 14px;border-radius:5px}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{background:#f7f8fa;position:sticky;top:0;z-index:2;cursor:pointer;user-select:none;font-weight:600;color:#3d4450}
th:hover{background:#eef1f6}
th .arw{color:var(--muted);font-weight:400;margin-left:3px}
td.num,th.num{text-align:right;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
tbody tr:nth-child(even){background:#fafbfc}
tbody tr:hover{background:#eef3ff}
tr.row-crisis{background:var(--crisis)!important}
tr.row-crisis:hover{background:#ffe4e0!important}
tr.row-external{background:#fff6e8}
tr.row-external:hover{background:#ffedcf!important}
tr.row-quiet td{color:#8a9099}
.pos{color:var(--up);font-weight:600}
.neg{color:var(--down);font-weight:600}
.scroll{overflow:auto;max-height:520px;border:1px solid var(--line);border-radius:7px}
.scroll.tall{max-height:700px}
a{color:var(--blue);text-decoration:none}
a:hover{text-decoration:underline}
select,input[type=text]{border:1px solid var(--line);border-radius:6px;padding:5px 9px;background:#fff;
 color:var(--ink);font-size:13px;margin-right:8px}
select{max-width:480px}
.ctrl{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:10px 0 14px}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;background:var(--chip);color:#4a5260}
.pill.front{background:#e6edfb;color:#254a9e}
.pill.back{background:#e8f0ff;color:#2b4f9e}
.pill.ext{background:#ffe0b2;color:#8a4b00}
.pill.no{background:#f6d9d5;color:#a5231a}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:2px 0 8px}
.legend i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:5px;border-radius:2px}
.chartbox{border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:#fff;margin:10px 0}
.empty-state{padding:34px 22px;text-align:center;color:var(--muted);background:#fafbfc;
 border:1px dashed var(--line);border-radius:7px;line-height:1.9}
.empty-state b{color:var(--ink)}
.coverage-line{display:block;margin-top:5px;padding:5px 8px;background:#f5f7fa;border-radius:5px}
svg{display:block;width:100%;height:auto}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:980px){.grid2{grid-template-columns:1fr}}
.mtable{width:100%;border-collapse:collapse;font-size:12.5px}
.mtable th,.mtable td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}
.mtable th{background:#f0f2f5;font-weight:600;white-space:nowrap}
.mtable td{white-space:normal}
.mtable tr:nth-child(even) td{background:#fafbfc}
.dict dt{font-weight:600;margin-top:9px;font-size:12.5px}
.dict dd{margin:2px 0 0 14px;color:#4a5260;font-size:12.5px}
footer{color:var(--muted);font-size:12px;border-top:1px solid var(--line);margin-top:26px;padding-top:14px}
details{margin:10px 0}
summary{cursor:pointer;font-weight:600;color:var(--blue);padding:6px 0}
/* 概念分线增补章节 */
.concept h3{font-size:14.5px;margin:22px 0 8px;color:var(--ink);
 padding-left:9px;border-left:3px solid var(--purple)}
.concept ol,.concept ul{padding-left:22px;margin:8px 0}
.concept li{margin:6px 0}
.formula{background:#f7f8fa;border:1px solid var(--line);border-radius:6px;
 padding:9px 13px;margin:9px 0;line-height:1.95;font-size:13px}
.pill.src{background:#e8f0ff;color:#2b4f9e}
.pill.add{background:#f2e9fb;color:#6b33b3}
.pill.ours{background:#e6f5ee;color:#166b4a}
.pill.name{background:#fff0dd;color:#8a5300}
.pill.sup{background:#e6f5ee;color:#166b4a}
.pill.con{background:#f6d9d5;color:#a5231a}
.conjdetail{border-top:1px solid var(--line);padding:4px 0 10px}
.conjdetail summary{line-height:1.7}
.conjdetail .basis{background:#f7f9fc;border:1px solid var(--line);border-radius:6px;padding:10px 14px;margin:8px 0}
.conjdetail .basis p{margin:7px 0;line-height:1.85}
.reflinks{white-space:nowrap}
.reflist{padding-left:28px}
.reflist li{margin:9px 0;line-height:1.75;padding-left:4px}
.pill.und{background:#eef1f5;color:#4a5260}
.hov{border-bottom:1px dotted var(--muted);cursor:help}
"""

JS = r"""
const D = JSON.parse(document.getElementById('payload').textContent);
const $ = id => document.getElementById(id);
const manifest = D.manifest;

/* ---------- 中文全称映射；工程原字段名只在悬停时出现 ---------- */
const CN = {
 'event_id':'统一事件编号','onset':'事件起点','end':'事件结束日','event_onset':'事件起点','event_end':'事件结束日',
 'n_crisis_days':'危机段交易日数','event_source':'事件来源','in_judgement':'是否进入主判据',
 'event_label':'事件中文全称','segment':'所属时段','exclusion_reason':'未进入主判据的原因',
 'onset_future20_worst_pct':'起点起未来二十交易日最低累计收益（%）',
 'onset_worst_date':'起点起最深回撤日','onset_avg_pair_corr':'起点日行业间平均相关系数',
 'pre20_start':'前二十日起始日','pre20_end':'前二十日结束日',
 'post20_start':'后二十日起始日','post20_end':'后二十日结束日',
 'window_first':'窗口首日','window_last':'窗口末日','window_len':'窗口交易日数',
 'pre20_cum_pct':'前二十日累计收益（%）','crisis_cum_pct':'危机段累计收益（%）',
 'post20_cum_pct':'后二十日累计收益（%）','full_window_cum_pct':'全窗口累计收益（%）',
 'crisis_max_dd_pct':'危机段最大回撤（%）','pre20_step_mean_pct':'前二十日日均收益（%）',
 'post20_step_mean_pct':'后二十日日均收益（%）',
 'a16_W_t_peak_offset_from_onset':'状态点云·十六行业·相邻两日持续图威尔斯特拉斯距离·整窗峰值相对起点的交易日偏移',
 'a16_summary_available_days':'状态点云·十六行业·危机段有摘要的交易日数',
 'a16_window_summary_days':'十六行业状态点云·事件窗有摘要的交易日数',
 'a27_window_summary_days':'二十七行业状态点云·事件窗有摘要的交易日数',
 'b_window_summary_days':'行业相关点云·事件窗有摘要的交易日数',
 'coverage_note':'早期事件摘要覆盖结论',
 'center_date':'中心日（样本日）','center_event_id':'中心日所属统一事件编号',
 'center_seq_in_event':'中心日在事件内的序号','offset_trading_days':'相对交易日',
 'window_base_date':'窗口基准日','is_crisis_day':'是否危机日','is_anchor_phase':'是否锚点段',
 'offset_from_onset':'相对事件起点的交易日','offset_from_end':'相对事件结束日的交易日',
 'event_len':'事件交易日数','phase':'阶段','seq_in_event':'事件内第几个交易日',
 'date':'日期','label_session_index':'标签日历序号','wind_session_index':'万得交易日历序号',
 'open':'开盘价','high':'最高价','low':'最低价','close':'收盘价',
 'ret_wind_pct':'相邻万得交易日收益（%）','ret_step_pct':'相邻标签交易日收益（%）',
 'n_wind_sessions_in_step':'这一步跨过的万得交易日数',
 'cum_from_window_base_pct':'相对窗口基准日累计收益（%）',
 'dd_from_window_peak_pct':'相对窗口内最高点的回撤（%）',
 'ret20_step_pct':'过去二十个标签交易日收益（%）',
 'intraday_range_pct':'日内振幅（%）','amount_yi':'全市场成交额（亿元）','amount_source':'成交额来源',
 'close_pct_vs_anchor':'相对锚点日的价格变动（%）',
 'state_v0_primary':'牛熊状态（主口径）','bull_bear_defined':'牛熊状态是否可判定',
 'crisis_in':'是否危机日标签','crisis_in_usable':'危机日是否可判定',
 'crisis_event_id':'所属统一危机事件编号','pre5':'危机前五日标记','pre10':'危机前十日标记',
 'pre20':'危机前二十日标记','pre_vol_type':'危机前波动分型','bear_in_crisis':'熊市兼危机标记',
 'state_degraded':'是否使用降级状态规则','line_a16_present':'十六行业状态点云摘要是否可得',
 'a16_W_t':'状态点云·十六行业·相邻两日持续图威尔斯特拉斯距离',
 'a16_h0_death_mean':'状态点云·十六行业·零维连通分量死亡值均值',
 'a16_h0_death_max':'状态点云·十六行业·零维连通分量死亡值最大值',
 'a16_h1_count':'状态点云·十六行业·一维环数量',
 'a16_h1_birth_mean':'状态点云·十六行业·一维环出生值均值',
 'a16_window_rms':'状态点云·十六行业·窗口收益均方根',
 'a16_avg_pair_corr':'状态点云·十六行业·行业间平均相关系数',
 'a16_leading_eig_share':'状态点云·十六行业·相关矩阵第一特征值占比',
 'a27_W_t':'状态点云·二十七行业·相邻两日持续图威尔斯特拉斯距离',
 'a27_h0_death_mean':'状态点云·二十七行业·零维连通分量死亡值均值',
 'a27_h1_count':'状态点云·二十七行业·一维环数量',
 'a27_avg_pair_corr':'状态点云·二十七行业·行业间平均相关系数',
 'b_h2_count':'相关网络·二维空腔数量',
 'b_h1_count':'相关网络·一维环数量',
 'b_h2_landscape_l1':'相关网络·二维空腔持续景观一阶范数',
 'b_industry_average_correlation':'相关网络·行业间平均相关系数',
 'b_correlation_leading_eigenvalue_share':'相关网络·相关矩阵第一特征值占比',
 'b_xy_h0_death_mean':'相关网络·零维连通分量死亡值均值',
 'pre10_cum_pct':'前十日累计收益（%）','pre5_cum_pct':'前五日累计收益（%）',
 'post10_cum_pct':'后十日累计收益（%）','post5_cum_pct':'后五日累计收益（%）',
 'post20_max_dd_pct':'后二十日最大回撤（%）','pre20_max_dd_pct':'前二十日最大回撤（%）',
 'pre20_worst_day_pct':'前二十日最差单日（%）','post20_best_day_pct':'后二十日最好单日（%）',
 'pre20_close_min':'前二十日最低收盘价','post20_close_max':'后二十日最高收盘价',
 'n_skipped_wind_sessions_pre20':'前二十日跨过的额外万得交易日数',
 'n_skipped_wind_sessions_post20':'后二十日跨过的额外万得交易日数',
 'cum_ret_pct':'区间累计收益（%）','step_mean_pct':'区间日均收益（%）',
 'max_dd_pct':'区间最大回撤（%）','worst_day_pct':'区间最差单日（%）',
 'best_day_pct':'区间最好单日（%）','close_first':'区间首日收盘价',
 'close_last':'区间末日收盘价','close_min':'区间最低收盘价','close_max':'区间最高收盘价',
 'amount_yi_mean':'区间日均成交额（亿元）','n_trading_days':'区间交易日数',
 'start_date':'起始日','end_date':'结束日',
 'anchor':'对齐锚点','anchor_date':'锚点日期','metric':'指标','n':'样本数',
 'mean':'均值','median':'中位数','p25':'第二十五百分位','p75':'第七十五百分位',
 'min':'最小值','max':'最大值','std':'标准差',
 'frozen_crisis_in_at_anchor':'锚点日冻结危机标记',
 'future20_worst_cum_pct_from_anchor':'锚点起未来二十交易日最低累计收益（%）',
 'why_not_in_frozen_label':'未触发冻结标签的原因',
 'crisis_tier':'危机层级（两层标签）','relation_to_seven_rounds':'与七轮市场级区间的关系',
 'severity_only_anchor':'锚点语义与事后时序参照用途','benchmark_note':'基准口径差异',
 'financial_qualification':'金融定性','evidence_grade':'证据等级',
 'source_1':'出处一','source_2':'出处二','source_3':'出处三',
 'round_id':'轮次编号','user_interval':'用户给出的年月区间',
 'peak_date':'精确峰值日','trough_date':'精确谷底日',
 'peak_high':'峰值日盘中最高点','trough_low':'谷底日盘中最低点',
 'intraday_drawdown_pct':'盘中峰谷回撤（%）','nature':'该轮市场性质',
 'calendar_days_in_interval':'区间自然日数',
 'crisis_in_days_tier2_descriptive':'区间内第二层急性事件天数（仅描述）',
 'a16_valid_days_inside':'区间内十六行业状态点云摘要有效天数',
 'a27_valid_days_inside':'区间内二十七行业状态点云摘要有效天数',
 'b_valid_days_inside':'区间内相关网络摘要有效天数',
 'a16_W_t_median_inside':'区间内相邻两日持续图威尔斯特拉斯距离中位数',
 'a16_W_t_median_outside':'区间外相邻两日持续图威尔斯特拉斯距离中位数',
 'b_h2_count_median_inside':'区间内二维空腔数量中位数',
 'b_h2_count_median_outside':'区间外二维空腔数量中位数',
 'price_basis':'价格口径','semantics':'端点语义','forbidden':'禁止用途',
 'protocol':'预登记方案','id':'推测编号',
 'v0_3_verdict':'第三版判定','v0_4_verdict':'第四版判定','v0_5_verdict':'第五版判定',
 'changed_vs_v0_3':'与第三版相比是否变化','changed_vs_v0_4':'与第四版相比是否变化',
 'boundary':'边界说明',
 'n_a':'危机组样本数','n_b':'常态组样本数','median_a':'危机组中位数',
 'median_b':'常态组中位数','delta':'两组中位数之差','std_effect':'标准化效应',
 'ci_lo':'置信区间下界','ci_hi':'置信区间上界','ci_crosses_zero':'置信区间是否跨零',
 'p_raw':'未校正显著性概率','p_bonferroni_pass':'是否通过邦费罗尼校正',
 'degenerate':'是否退化格','version':'版本','line':'点云分线','panel':'行业面板',
 'window':'时间窗口','state':'状态组','summary':'摘要指标','class':'指标类别',
 'version_invariant':'是否版本不变量'
};
const SUF = {
 '_peak_offset_from_onset':'·整窗峰值相对起点的交易日偏移',
 '__post_minus_pre':'·后二十日减前二十日',
 '__pre20_mean':'·前二十日均值','__post20_mean':'·后二十日均值',
 '__at_center':'·中心日当天','_pre20_mean':'·前二十日均值',
 '_crisis_mean':'·危机段均值','_post20_mean':'·后二十日均值',
 '__mean':'·均值','__median':'·中位数','_mean':'·均值','_median':'·中位数',
 '_median_inside':'·区间内中位数','_median_outside':'·区间外中位数'
};
const SUF_KEYS = Object.keys(SUF).sort((a,b)=>b.length-a.length);
function cn(k){
  if(CN[k]) return CN[k];
  for(const s of SUF_KEYS){
    if(k.endsWith(s)){
      const base=k.slice(0,-s.length);
      return (CN[base]||base)+SUF[s];
    }
  }
  return k;
}
const CN_STATE={
 'bull':'牛市','bear':'熊市','fuzzy':'模糊','bear_turn':'熊市转折',
 'bull_adjustment':'牛市调整','undefined_warmup':'未定义（预热期）',
 'undefined_after_2025_05_30':'未定义（旧查询终点之后，第五版已补齐行情）',
 'undefined':'未定义','crisis_in':'危机中','bear_in_crisis':'熊市兼危机',
 'pre_low_vol':'危机前低波动','pre_high_vol':'危机前高波动',
 'normal_baseline':'常态基线','overheat':'过热','oversold':'超冷',
 'low':'低波动','high':'高波动','front':'前段','back':'后段',
 'pre20':'危机前二十日','crisis':'危机段','post20':'危机后二十日',
 '1':'是','0':'否','':'缺失'
};
const CN_ANCHOR={
 'center_day':'每个危机日','event_onset':'事件起点',
 'event_end':'事件结束日','external_crisis':'外部公认危机锚点'
};
const FIX=[
 [/\bTDA\b/g,'持续同调'],[/\bWind\b/g,'万得'],[/\bTDX\b/g,'通达信'],
 [/\bPHTI\b/g,'原文波动率择时指标'],[/\bNaN\b/g,'缺失值'],
 [/\bv0\.1\b/g,'第一版'],[/\bv0\.2\b/g,'第二版'],[/\bv0\.3\b/g,'第三版'],
 [/\bv0\.4\b/g,'第四版'],[/\bv0\.5\b/g,'第五版'],
 [/\bv0\.6\b/g,'第六版'],[/\bv0\.7\b/g,'第七版'],
 [/\bGate\s*1\b/g,'第一道闸门'],[/\bGate\s*2\b/g,'第二道闸门'],
 [/\bPR-AUC\b/g,'精确率召回率曲线下面积'],[/\bIC\b/g,'信息系数'],
 [/\bSharpe\b/g,'夏普比率'],[/\bMA250\b/g,'二百五十日移动平均'],
 [/\bOHLC\b/g,'开高低收'],[/\bCSV\b/g,'数据文件'],[/\bJSON\b/g,'数据交换文件'],
 [/\bHTML\b/g,'网页文件'],[/\bbootstrap\b/g,'自助法'],[/\bBonferroni\b/g,'邦费罗尼校正'],
 [/\bWasserstein\b/g,'威尔斯特拉斯'],[/\bH0\b/g,'零维'],[/\bH1\b/g,'一维'],[/\bH2\b/g,'二维'],
 [/\bA16\b/g,'十六行业状态点云'],[/\ba16\b/g,'十六行业状态点云'],
 [/\bB-line\b/g,'相关网络线'],[/\bA-line\b/g,'状态点云线'],
 [/\bundefined\b/g,'未定义'],[/\bbear\b/g,'熊市'],
 [/\bNIFD\b/g,'国家金融与发展实验室'],[/\bEX-POST\b/g,'事后'],
 [/\bhigh\/low\b/g,'最高价与最低价'],[/\bhigh\b/g,'最高价'],[/\blow\b/g,'最低价'],
 [/\bA\/B\b/g,'甲乙级'],[/\bA\b/g,'甲级'],[/\bB\b/g,'乙级'],[/\bC\b/g,'丙级'],
 [/\b\d{4}Q\d\b/g,'季度报告'],[/\bDMA\b/g,'多空收益互换'],
 [/\bVIX\b/g,'波动率指数'],[/\bETF\b/g,'交易型开放式指数基金'],
 [/\bV\s*型反弹/g,'快速反弹'],[/\bV\s*型修复/g,'快速修复'],[/\bV\s*型/g,'快速']
];
function zh(v){
  let s=String(v==null?'':v);
  for(const [re,rep] of FIX) s=s.replace(re,rep);
  return s;
}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function isNum(v){
  if(v===''||v==null) return false;
  const s=String(v).trim();
  if(s===''||/^(\d{4}-\d{2}-\d{2})$/.test(s)) return false;
  return /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(s) && isFinite(Number(s));
}
const EVENT_ID_FIELDS=new Set(['event_id','center_event_id','crisis_event_id']);
function displayEid(v){
  const raw=String(v==null?'':v);
  return D.event_id_lookup[raw]||raw;
}
function cellText(k,v){
  const raw=String(v==null?'':v);
  if(raw==='') return '—';
  if(EVENT_ID_FIELDS.has(k)) return displayEid(raw);
  if(k==='event_label'){
    return zh(raw).replace(/编号 (\d+)/,(m,n)=>'统一编号 '+displayEid(n)+'（工程原编号 '+n+'）');
  }
  if(k==='exclusion_reason'){
    return zh(raw).replace('事件 3 与事件 16','工程原编号 3 与 16（统一 31 与 45）');
  }
  if(k==='state_v0_primary'||k==='pre_vol_type'||k==='phase'||k==='segment'
     ||k==='in_judgement'||k==='is_crisis_day'||k==='is_anchor_phase'
     ||k==='bull_bear_defined'||k==='bear_in_crisis'||k==='state_degraded'
     ||k==='line_a16_present'||k==='crisis_in'||k==='crisis_in_usable'
     ||k==='pre5'||k==='pre10'||k==='pre20'
     ||k==='anchor'||k==='metric'||k==='event_source'){
    if(CN_STATE[raw]) return CN_STATE[raw];
    if(CN_ANCHOR[raw]) return CN_ANCHOR[raw];
    if(CN[raw]) return CN[raw];
  }
  if(k==='id'&&/^C\d+$/.test(raw)) return '第'+String(Number(raw.slice(1)))+'条推测';
  if(k==='round_id'&&/^R\d+$/.test(raw)) return '第'+String(Number(raw.slice(1)))+'轮';
  if(k==='protocol') return '第五版分组核对预登记';
  if(k==='price_basis') return '通达信上证综指盘中最高价与最低价；谷值取峰值日之后最低价';
  if(k==='metric'&&CN[raw]) return CN[raw];
  return zh(raw);
}
function cellClass(k,v){
  if(!isNum(v)) return '';
  const x=Number(v);
  if(/_pct|_delta|^delta$|worst_day/.test(k) && x!==0) return x>0?'pos':'neg';
  return '';
}
function renderTable(el,cols,rows,opt){
  opt=opt||{};
  const st=el._sort||(el._sort={k:null,dir:1});
  let list=rows.slice();
  if(st.k){
    const k=st.k;
    list.sort((a,b)=>{
      const x=a[k],y=b[k];
      if(EVENT_ID_FIELDS.has(k)) return (Number(displayEid(x))-Number(displayEid(y)))*st.dir;
      if(isNum(x)&&isNum(y)) return (Number(x)-Number(y))*st.dir;
      return String(x==null?'':x).localeCompare(String(y==null?'':y),'zh')*st.dir;
    });
  }
  const shown=opt.maxRows?list.slice(0,opt.maxRows):list;
  let h='<table><thead><tr>';
  for(const c of cols){
    h+='<th data-k="'+esc(c)+'" title="原字段名：'+esc(c)+'"'
      +(st.k===c?' class="sorted"':'')+'>'+esc(cn(c))
      +(st.k===c?'<span class="arw">'+(st.dir>0?'▲':'▼')+'</span>':'')+'</th>';
  }
  h+='</tr></thead><tbody>';
  for(const r of shown){
    let cls='';
    if(r.event_source==='外部金融定性危机') cls='row-external';
    if(r.in_judgement==='0'&&r.event_source!=='外部金融定性危机') cls='row-quiet';
    h+='<tr'+(cls?' class="'+cls+'"':'')+'>';
    for(const c of cols){
      const v=r[c], t=cellText(c,v), numeric=isNum(v)&&!EVENT_ID_FIELDS.has(c);
      const original=EVENT_ID_FIELDS.has(c)?'工程原编号：'+String(v)+'；':'';
      h+='<td'+(numeric?' class="num '+cellClass(c,v)+'"':'')
        +' title="'+esc(original)+'原字段名：'+esc(c)+'">'+esc(t)+'</td>';
    }
    h+='</tr>';
  }
  h+='</tbody></table>';
  el.innerHTML=h;
  el.querySelectorAll('th').forEach(th=>{
    th.addEventListener('click',()=>{
      const k=th.dataset.k;
      if(st.k===k) st.dir=-st.dir; else {st.k=k;st.dir=1;}
      renderTable(el,cols,rows,opt);
    });
  });
}
function nf(v){
  const x=Number(v);
  return isFinite(x)?(Math.abs(x)>=1000?x.toFixed(0):x.toFixed(4)):'';
}
function lineChart(series,opt){
  opt=opt||{};
  const W=920,H=300,pad={l:64,r:18,t:18,b:34};
  const xs=series.map(p=>p.x);
  if(!xs.length) return '<svg viewBox="0 0 '+W+' '+H+'"></svg>';
  const vals=[];
  for(const p of series){
    if(p.y!=null) vals.push(p.y);
    if(p.lo!=null) vals.push(p.lo);
    if(p.hi!=null) vals.push(p.hi);
  }
  let lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals);
  if(!isFinite(lo)||!isFinite(hi)){lo=0;hi=1;}
  if(hi===lo){hi=lo+1;}
  const span=hi-lo, padY=span*0.08; lo-=padY; hi+=padY;
  const sx=x=>pad.l+(x-Math.min.apply(null,xs))/(Math.max.apply(null,xs)-Math.min.apply(null,xs)||1)*(W-pad.l-pad.r);
  const sy=y=>pad.t+(hi-y)/(hi-lo)*(H-pad.t-pad.b);
  let s='<svg viewBox="0 0 '+W+' '+H+'" role="img">';
  for(let g=0;g<=4;g++){
    const y=lo+(hi-lo)*g/4, py=sy(y);
    s+='<line x1="'+pad.l+'" y1="'+py+'" x2="'+(W-pad.r)+'" y2="'+py+'" stroke="#e8ebf0"/>';
    s+='<text x="'+(pad.l-8)+'" y="'+(py+4)+'" text-anchor="end" font-size="11" fill="#646a73">'+nf(y)+'</text>';
  }
  if(opt.shade){
    for(const [a,b] of opt.shade){
      const x1=sx(a),x2=sx(b);
      s+='<rect x="'+x1+'" y="'+pad.t+'" width="'+(x2-x1)+'" height="'+(H-pad.t-pad.b)
        +'" fill="#fff1ef" opacity="0.85"/>';
    }
  }
  const band=series.filter(p=>p.lo!=null&&p.hi!=null);
  if(band.length>1){
    let d='M'+sx(band[0].x)+','+sy(band[0].hi);
    for(const p of band.slice(1)) d+=' L'+sx(p.x)+','+sy(p.hi);
    for(const p of band.slice().reverse()) d+=' L'+sx(p.x)+','+sy(p.lo);
    s+='<path d="'+d+' Z" fill="#2b5fcc" opacity="0.14"/>';
  }
  const pts=series.filter(p=>p.y!=null);
  if(pts.length>1){
    const d=pts.map((p,i)=>(i?'L':'M')+sx(p.x)+','+sy(p.y)).join(' ');
    s+='<path d="'+d+'" fill="none" stroke="#2b5fcc" stroke-width="2.2"/>';
  }
  for(const p of pts){
    s+='<circle cx="'+sx(p.x)+'" cy="'+sy(p.y)+'" r="1.8" fill="#2b5fcc"/>';
  }
  const zx=sx(0);
  s+='<line x1="'+zx+'" y1="'+pad.t+'" x2="'+zx+'" y2="'+(H-pad.b)+'" stroke="#d93026" stroke-dasharray="4 3"/>';
  [ -20,-10,0,10,20 ].forEach(t=>{
    const x=sx(t);
    s+='<line x1="'+x+'" y1="'+(H-pad.b)+'" x2="'+x+'" y2="'+(H-pad.b+4)+'" stroke="#8a9099"/>';
    s+='<text x="'+x+'" y="'+(H-pad.b+17)+'" text-anchor="middle" font-size="11" fill="#646a73">'
      +(t>0?'+':'')+t+'</text>';
  });
  s+='<text x="'+(W/2)+'" y="'+(H-3)+'" text-anchor="middle" font-size="11" fill="#646a73">相对交易日</text>';
  s+='</svg>';
  return s;
}
/* ---------- 一、文件清单 ---------- */
(function(){
  const box=$('fileTable');
  const desc=manifest.file_desc;
  let h='<table><thead><tr><th>文件（点击下载）</th><th>用途</th><th class="num">行数</th><th class="num">列数</th><th>说明</th></tr></thead><tbody>';
  for(const d of desc){
    const m=manifest.files[d.name];
    h+='<tr><td><a href="'+esc(d.name)+'" download title="原文件名：'+esc(d.name)+'">'+esc(d.zh)+'</a></td>'
      +'<td>'+esc(d.tag)+'</td><td class="num">'+(m?m.rows:'—')+'</td><td class="num">'+(m?m.cols:'—')+'</td>'
      +'<td>'+esc(d.note)+'</td></tr>';
  }
  box.innerHTML=h+'</tbody></table>';
})();
/* ---------- 三、事件一览 ---------- */
const OV_COLS=['event_id','event_source','segment','in_judgement','onset','end','n_crisis_days',
 'pre20_cum_pct','crisis_cum_pct','post20_cum_pct','crisis_max_dd_pct',
 'onset_future20_worst_pct','a16_W_t_pre20_mean','a16_W_t_crisis_mean','a16_W_t_post20_mean',
 'a16_W_t_peak_offset_from_onset','b_h2_count_crisis_mean','a16_summary_available_days',
 'exclusion_reason'];
renderTable($('ovTable'),OV_COLS,D.overview,{});
/* ---------- 三·补、前段 28 事件 ---------- */
const FRONT_COLS=['event_id','onset','end','n_crisis_days','in_judgement',
 'onset_future20_worst_pct','onset_worst_date','crisis_cum_pct','post20_cum_pct',
 'window_len','a16_window_summary_days','a27_window_summary_days','b_window_summary_days',
 'coverage_note','a16_W_t_crisis_mean','a16_summary_available_days'];
renderTable($('frontTable'),FRONT_COLS,D.overview.filter(r=>r.event_source==='前段新增急性事件'),{});
/* ---------- 三·补二、外部锚点 ---------- */
const EXT_COLS=['event_id','anchor_date','event_label','frozen_crisis_in_at_anchor',
 'future20_worst_cum_pct_from_anchor','why_not_in_frozen_label','crisis_tier',
 'relation_to_seven_rounds','severity_only_anchor','financial_qualification','evidence_grade'];
renderTable($('extTable'),EXT_COLS,D.external_meta,{});
/* ---------- 三·补三、第一层七轮 ---------- */
const TIER_COLS=['round_id','user_interval','peak_date','trough_date','peak_high','trough_low',
 'intraday_drawdown_pct','nature','calendar_days_in_interval',
 'crisis_in_days_tier2_descriptive','a16_valid_days_inside',
 'a16_W_t_median_inside','a16_W_t_median_outside',
 'b_h2_count_median_inside','b_h2_count_median_outside','semantics','forbidden'];
renderTable($('tierTable'),TIER_COLS,D.judgement.tier1,{});
/* ---------- 四、相对日剖面 ---------- */
(function(){
  const a=$('profAnchor'),m=$('profMetric');
  for(const [k,v] of Object.entries(CN_ANCHOR)) a.add(new Option(v,k));
  for(const k of D.metrics) m.add(new Option(cn(k),k));
  m.value='a16_W_t';
  function draw(){
    const rows=D.profile.filter(r=>r.anchor===a.value&&r.metric===m.value)
      .sort((x,y)=>x.offset_trading_days-y.offset_trading_days);
    const series=rows.map(r=>({x:r.offset_trading_days,
      y:r.mean===''?null:Number(r.mean),
      lo:r.p25===''?null:Number(r.p25),
      hi:r.p75===''?null:Number(r.p75)}));
    $('profChart').innerHTML=lineChart(series,{});
    const n=rows.length?rows[0].n:0;
    $('profNote').textContent='当前对齐锚点：'+CN_ANCHOR[a.value]+'；当前指标：'+cn(m.value)
      +'；每个相对日的样本数见「样本数」列（本图均值为 '+n+' 个窗口的算术平均）。'
      +'阴影线为均值，浅色带为第二十五至第七十五百分位。';
  }
  a.onchange=draw; m.onchange=draw; draw();
})();
/* ---------- 五、事件窗逐日查看器 ---------- */
(function(){
  const sel=$('evSelect'),met=$('evMetric');
  D.events.forEach(e=>{
    sel.add(new Option('统一事件 '+displayEid(e.event_id)+'｜'+e.event_source+'｜'+e.onset+' 至 '+e.end,e.event_id));
  });
  const EV_METRICS=Array.from(new Set(['close','ret_step_pct',
    'cum_from_window_base_pct','amount_yi'].concat(D.core_metrics)));
  function cur(){return D.events.find(e=>e.event_id===sel.value)||D.events[0];}
  function blankKind(r,k){
    if(k==='a16_h1_birth_mean'&&String(r.a16_h1_count)==='0') return 'structural';
    const m=D.metric_coverage[k];
    if(m&&(r.date<m.first||r.date>m.last)) return 'uncovered';
    return 'gap';
  }
  function metricAudit(e,k){
    const a={valid:0,uncovered:0,structural:0,gap:0};
    for(const r of e.rows){
      if(isNum(r[k])) a.valid++;
      else a[blankKind(r,k)]++;
    }
    return a;
  }
  function resolveMetric(e,requested){
    const lc=e.line_coverage||{a16:0,a27:0,b:0};
    if(requested.startsWith('a27_')&&lc.a27===0&&lc.a16>0){
      const actual='a16_'+requested.slice(4);
      if(EV_METRICS.includes(actual)) return {requested:requested,actual:actual,fallback:true};
    }
    return {requested:requested,actual:requested,fallback:false};
  }
  function refreshMetricOptions(){
    const current=met.value||'a16_W_t',e=cur();
    met.innerHTML='';
    for(const k of EV_METRICS){
      const a=metricAudit(e,k);
      let suffix='';
      if(a.valid===0&&a.uncovered===e.rows.length) suffix='（本事件未覆盖）';
      else if(a.valid===0&&a.structural===e.rows.length) suffix='（本事件均结构性无定义）';
      else if(a.valid===0) suffix='（本事件无有效值）';
      else if(a.valid<e.rows.length) suffix='（有效 '+a.valid+'／'+e.rows.length+' 行）';
      met.add(new Option(cn(k)+suffix,k));
    }
    met.value=current;
  }
  function emptyChart(e,k,a){
    const m=D.metric_coverage[k];
    let reason='当前指标没有可绘制的有效值。';
    if(a.uncovered===e.rows.length&&m){
      reason+='本事件窗口完全位于该指标实际覆盖期（'+esc(m.first)+' 至 '+esc(m.last)
        +'）之外。当前整合数据没有该窗口的实测值，属于<b>未覆盖</b>，不是导出漏数。';
    }else if(a.structural===e.rows.length){
      reason+='本事件每天的一维环数量均为零，没有有限一维环可供计算平均出生值，属于<b>结构性无定义</b>。';
    }else{
      const parts=[];
      if(a.uncovered) parts.push('未覆盖 '+a.uncovered+' 行');
      if(a.structural) parts.push('零个一维环导致的结构性无定义 '+a.structural+' 行');
      if(a.gap) parts.push('覆盖期内待核空值 '+a.gap+' 行');
      reason+=esc(parts.join('；'))+'。覆盖期内待核空值不能自动解释成未覆盖或数据丢失。';
    }
    return '<div class="empty-state"><b>不绘制空白坐标轴，以免把未覆盖误读成零值。</b><br>'+reason+'</div>';
  }
  function draw(){
    const e=cur(),choice=resolveMetric(e,met.value||'a16_W_t'),k=choice.actual,rows=e.rows,a=metricAudit(e,k);
    if(choice.fallback) met.value=k;
    const series=rows.map(r=>({x:Number(r.offset_from_onset),
      y:isNum(r[k])?Number(r[k]):null}));
    const crisis=rows.filter(r=>r.phase==='crisis').map(r=>Number(r.offset_from_onset));
    const shade=crisis.length?[[Math.min.apply(null,crisis),Math.max.apply(null,crisis)]]:[];
    $('evChart').innerHTML=a.valid?lineChart(series,{shade:shade}):emptyChart(e,k,a);
    const zeros=rows.filter(r=>isNum(r[k])&&Number(r[k])===0).length;
    const lc=e.line_coverage||{a16:0,a27:0,b:0};
    $('evInfo').innerHTML='<b>统一事件 '+esc(displayEid(e.event_id))+'（工程原编号 '+esc(e.event_id)+'）</b>：'+esc(e.event_label)
      +'；起点 '+esc(e.onset)+'，结束 '+esc(e.end)+'，共 '+e.n+' 个危机日；'
      +'窗口 '+esc(rows[0].date)+' 至 '+esc(rows[rows.length-1].date)+'，共 '+rows.length+' 行；'
      +'当前指标有效 '+a.valid+' 行'
      +(a.uncovered?'，未覆盖 '+a.uncovered+' 行':'')
      +(a.structural?'，结构性无定义 '+a.structural+' 行':'')
      +(a.gap?'，覆盖期内待核空值 '+a.gap+' 行':'')
      +(k.endsWith('_count')?'，其中零值 '+zeros+' 行（零是已算出的数量，不是缺失）':'')+'。'
      +(e.in_judgement==='0'?' <span class="pill no">不进主判据</span>':'')
      +(choice.fallback?'<span class="coverage-line"><b>较少行业面板替代展示：</b>你选择的「'+esc(cn(choice.requested))
        +'」在本事件未覆盖，已按用户裁决改用「'+esc(cn(k))+'」。'
        +'这只是十六行业面板的样本内描述，不是二十七行业实测值；两种面板不拼接、不互相冒充，也不据此改动主判据。</span>':'')
      +'<span class="coverage-line"><b>本事件逐日组覆盖：</b>十六行业状态点云 '+lc.a16+'／'+rows.length
      +' 行；二十七行业状态点云 '+lc.a27+'／'+rows.length
      +' 行；行业相关点云 '+lc.b+'／'+rows.length+' 行。'
      +'“组覆盖”指当天至少一项该组摘要有值，不表示每一项指标都有定义。</span>';
    const cols=Array.from(new Set(['date','phase','offset_from_onset','close','ret_step_pct',
      'cum_from_window_base_pct','amount_yi','state_v0_primary','is_crisis_day',
      'a16_W_t','a16_h1_count','a16_avg_pair_corr','a16_window_rms','b_h2_count',
      'b_industry_average_correlation',k]));
    renderTable($('evDetail'),cols,rows,{});
  }
  sel.onchange=function(){refreshMetricOptions();draw();};
  met.onchange=draw;
  refreshMetricOptions();draw();
})();
/* ---------- 六、中心日结果表 ---------- */
(function(){
  const sel=$('ctEvent');
  sel.add(new Option('全部事件','__all__'));
  D.events.forEach(e=>sel.add(new Option('统一事件 '+displayEid(e.event_id)+'（'+e.onset+'）',e.event_id)));
  const cols=D.center_cols.filter(c=>!['event_label','event_source'].includes(c));
  function draw(){
    const rows=sel.value==='__all__'?D.centers:D.centers.filter(r=>r.event_id===sel.value);
    renderTable($('ctTable'),cols,rows,{});
    $('ctCount').textContent='当前显示 '+rows.length+' 行（全部 '+D.centers.length+' 行）。';
  }
  sel.onchange=draw; draw();
})();
/* ---------- 七、事件分段统计 ---------- */
renderTable($('phTable'),D.phase_cols,D.phases,{});
/* ---------- 八、判定层结论 ---------- */
renderTable($('ledgerTable'),D.judgement.ledger_cols,D.judgement.ledger,{});
/* ---------- 十、数据字典 ---------- */
(function(){
  const keys=new Set();
  for(const c of D.center_cols) keys.add(c);
  for(const c of D.phase_cols) keys.add(c);
  for(const c of OV_COLS) keys.add(c);
  for(const c of FRONT_COLS) keys.add(c);
  for(const c of TIER_COLS) keys.add(c);
  for(const c of EXT_COLS) keys.add(c);
  for(const c of D.metrics) keys.add(c);
  for(const c of D.core_metrics) keys.add(c);
  let h='<dl class="dict">';
  for(const k of Array.from(keys).sort()){
    h+='<dt title="原字段名：'+esc(k)+'">'+esc(cn(k))+'</dt>'
      +'<dd>把鼠标移到本条名称或任意表头上，可查看工程数据文件里的原字段名。</dd>';
  }
  $('dictBox').innerHTML=h+'</dl>';
})();
"""

# Chinese descriptions for the downloadable files (file names live in attributes only)
FILE_DESC = [
    ("event_overview.csv", "事件总览数据文件", "事件级去重视图",
     "每个事件一行：前二十日、危机段、后二十日行情与关键摘要；含事件来源与是否进入主判据"),
    ("event_windows.csv", "事件窗逐日全字段明细", "逐日明细",
     "每个事件的前二十日加危机段加后二十日，逐日列出价格、收益、状态与十八项持续同调摘要"),
    ("daily_windows.csv", "中心日前后二十日逐日明细", "逐日明细（互相重叠）",
     "每个危机日为锚的四十一个交易日全字段明细；长事件会贡献多个互相重叠的窗口"),
    ("relative_profile.csv", "相对日剖面统计文件", "剖面统计",
     "四种对齐锚点乘四十一个相对日乘二十二项指标的均值、中位数、四分位与极值"),
    ("event_phase_metrics.csv", "事件分段统计文件", "分段统计",
     "每个事件三个阶段：区间累计收益、日均收益、最大回撤、成交额与十八项摘要均值"),
    ("center_day_outcomes.csv", "中心日结果数据文件", "主表",
     "每个中心日一行：前后二十日行情结果与三项核心摘要的中心日值、前后均值与差值"),
    ("external_crises.csv", "外部公认危机对照文件", "外部定性对照",
     "两次事后公认危机的分层定性、证据等级、出处、冻结标签漏判原因与锚点语义"),
    ("chart_data.json", "报告内嵌数据载荷", "网页内嵌数据",
     "本报告所有图表与表格的原始数据；报告为单文件离线，不依赖外部请求"),
]


# 两套点云只按本工程当前实际构造与实际摘要解释，不用原参考文献的口径定义分线。
CONCEPT = r"""
<section class="card concept">
<h2>一·补、本工程两套点云的分线（一）：当前构造与摘要含义</h2>
<div class="note"><b>本节只按当前工程实现说明：</b>点是什么、坐标怎样取、距离怎样算、
实际输出哪些摘要，都以当前工程实现、第五版判定输入与第六版早期描述性补算为准。两条线当前都取十期收益尺度，
但「十」在两条线里的作用不同：市场状态点云是十个交易日点；
行业相关点云是每个行业的十期收益坐标，需要十一期收盘价计算。</div>

<h3>甲、行业相关点云：点＝申万二级行业</h3>
<p><b>坐标与距离。</b>每天每个数据合格的行业是一个点，坐标是该行业最近十期简单收益序列；
两个行业之间的距离等于「二乘以一减两者收益相关系数」再开平方
<span class="hov" title="工程公式：d_ij = sqrt(2(1-rho_ij))">（悬停看原式）</span>。
节点集合随数据可得性变化：第六版早期实测为六十一至七十四个，第五版后段为六十七至一百三十一个；
早期名单是事后固定的申万二零一四版分类，只用于样本内历史描述；缺失不补零、不回填。</p>
<div class="formula"><b>距离只比较收益序列的协同形态，不直接比较波动幅度。</b>
把收益序列去均值并单位化后，相关距离就是两个标准化方向之间的欧氏距离，取值在零到二之间；
<span class="hov" title="工程原字段名：thresh">距离上限取二点零</span>。
因此，两个行业即使涨跌幅大小不同，只要十期收益的协同形态一致，相关距离仍然很小。</div>
<p><b>零维＝行业逐步合并的层级结构。</b>高相关行业先连成一簇，
零维死亡值对应最小生成树的合并边长，可理解为「要容忍多大的不同步，两个簇才继续合并」。
当前已经实际输出零维死亡值的均值、中位数、最大值、第九十分位数、变异系数、
最大值相对其余中位数的比值，以及三个距离阈值下的连通分量数。
这些摘要描述行业之间的聚合与边缘行业，不是交易日的离群程度。</p>
<p><b>一维＝行业相关几何中的非平凡环。</b>若若干行业沿相关关系接成一条闭合链，
而跨链连接又不足以立即把环填平，就会出现一维持续区间。
它可以用于观察板块梯度或轮动链的几何形态，<b>不是时间周期，也不是简单的三角洞</b>。
当前实际输出一维环数量与一维持续景观一阶范数。</p>
<p><b>二维＝行业相关几何中的高阶空腔。</b>当前实际输出有限二维区间数、
二维持续景观一阶范数、最大二维持久性和三个距离阈值下的二维贝蒂数。
这些量只说明空腔的数量与持续程度；它们不自动对应唯一、固定的金融因果机制，
解释时必须同时披露节点数变化和十期相关估计的不确定性。</p>

<h3>乙、市场状态点云：点＝交易日</h3>
<p><b>坐标与距离。</b>主面板固定使用十六个申万一级行业，稳健性面板使用二十七个。
最近十个交易日每天贡献一个点，坐标是当日十六或二十七个行业的日对数收益；
两点之间使用<b>含量级</b>的欧氏距离，因此收益幅度会直接影响点云形状。</p>
<div class="note"><b>时间顺序在哪里：</b>十个交易日点在维托里斯－里普斯复形里只是一袋无序的点，
零维与一维只描述这袋点的形状。当前另一条时序摘要是<b>相邻两日窗口持续图的威尔斯特拉斯距离</b>：
分别计算零维与一维持续图的二阶距离后相加。进入当前判定的是这个相邻日距离本身，
没有再附加平滑。</div>
<p><b>零维＝哪些交易日的市场状态彼此接近。</b>普通交易日往往靠近原点并较早合并，
极端交易日可能离群并较晚合并。当前实际输出零维死亡值的均值、中位数、最大值、变异系数、
最大值相对其余中位数的比值和给定距离下的连通分量数。
由于欧氏距离含量级，这些量同时也是波动与尾部状态的几何编码，<b>不是板块聚类指标</b>。</p>
<p><b>一维＝市场状态点云中的非平凡回路。</b>当前实际输出一维环数量、平均出生值、
平均持久性和最大持久性，用于观察十个状态点在行业收益空间里是否形成环状结构。
它不是行情周期。还必须注意：当前只有十个点，却有十六或二十七个坐标维度，
点数少于维数会约束一维结构并放大相邻图距离的抽样波动，所以不能把摘要绝对水平当成稳定定律。</p>
</section>

<section class="card concept">
<h2>一·补二、本工程两套点云的分线（二）：当前摘要对照</h2>
<h3>丙、同名摘要不能跨线解释</h3>
<table class="mtable"><thead><tr>
<th>对照项目</th><th>行业相关点云</th><th>市场状态点云</th></tr></thead><tbody>
<tr><th>一个点是什么</th><td>一个申万二级行业</td><td>一个交易日</td></tr>
<tr><th>当前十期尺度怎样使用</th><td>十期简单收益构成每个行业的坐标</td><td>十日的行业收益向量构成十个点</td></tr>
<tr><th>行业面板</th><td>申万二级，早期六十一个至七十四个、后段六十七个至一百三十一个合格节点</td><td>申万一级，固定十六或二十七个坐标</td></tr>
<tr><th>距离</th><td>相关距离，不直接含波动幅度</td><td>欧氏距离，直接含收益幅度</td></tr>
<tr><th>零维回答什么</th><td>行业怎样逐层聚合、哪些行业较边缘</td><td>哪些交易日状态相近、哪些交易日离群</td></tr>
<tr><th>一维回答什么</th><td>行业相关几何里是否有非平凡环</td><td>市场状态几何里是否有非平凡环</td></tr>
<tr><th>二维</th><td>计算空腔数量、持久性与景观范数</td><td>当前不计算，最高只到一维</td></tr>
<tr><th>时间信息在哪里</th><td>十期收益坐标按日期对齐；行业点本身没有先后顺序</td><td>复形丢弃十个交易日的先后顺序；相邻日持续图距离另行描述窗口变化</td></tr>
<tr><th>主要控制变量</th><td>节点数、平均相关、第一特征值占比</td><td>窗口收益均方根、方差、平均相关、第一特征值占比</td></tr>
</tbody></table>

<h3>丁、为什么不能把两条线合成一句「全部上升」</h3>
<div class="leak"><b>行业相关点云：</b>若行业相关性普遍上升，相关距离会整体缩小，
部分环或空腔可能更早被填平，持续景观范数也可能随之缩小；
<b>市场状态点云：</b>若日收益幅度放大，欧氏距离会整体增大，
零维死亡值和相邻日持续图距离可能随之增大。
这只是由当前距离定义得到的几何方向推断，实际是否发生仍须看本工程实测；
但它足以说明，两条线不能共用一个「危机中所有持续摘要同步跳升」的先验。</div>
<div class="note">因此，当前判定按两条线、各个维度和各个摘要分别报告；
同叫「一维数量」或「平均相关」，也不代表它们在两线中回答同一个金融问题。</div>
</section>

<section class="card concept">
<h2>一·补三、当前持续景观一阶范数与相邻图距离怎么读</h2>
<h3>戊、当前计算定义</h3>
<p>持续图里每个点（出生值，死亡值）给一个帐篷函数：
帐篷函数在某一时刻的值＝取较大者（零，取较小者（该时刻减出生值，死亡值减该时刻）），
底为出生值到死亡值的区间、峰高为持久性的一半；
把同一时刻所有帐篷值从大到小排序，第几层景观就取第几大。
因为「逐点取第几大再对各层求和」等于把所有帐篷直接求和，所以
<b>一阶范数 ＝ 各层景观积分之和 ＝ 各帐篷积分之和 ＝ 持久性平方和 ÷ 4</b>
<span class="hov" title="工程公式：||lambda||_1 = sum_k int lambda_k dt = sum_i (d_i-b_i)^2 / 4">（悬停看原式）</span>。</p>
<div class="formula">当前代码里的
<span class="hov" title="工程原字段名：exact_landscape_l1">精确持续景观一阶范数</span>
正是「持久性平方和 ÷ 4」；「精确」指精确积分而非网格采样，
单测用出生值一、死亡值三验证得到一点零。</div>
<p><b>读数时守住三个区别：</b></p>
<ol>
<li>它是<b>单张持续图内部的总拓扑质量</b>，不是两张图之间的差。</li>
<li>它采用<b>平方加权</b>，突出长持久结构、压制短命噪声；孔洞数量则把每个孔洞都计一个，
所以「数量」和「一阶范数」不是同一个摘要。</li>
<li>它与威尔斯特拉斯距离不同：后者是当前市场状态点云里<b>相邻两张持续图的最优匹配代价</b>，
描述窗口变化；一阶范数描述单张图内部的总持续质量。两者不能互相替代。</li>
</ol>

<h3>己、行业相关点云的两个景观范数</h3>
<ul>
<li><b>一维的一阶范数</b>＝当前行业相关点云中所有一维环的持久性平方和再除以四。
它回答这些环合起来有多持久，而不只是有几个环。</li>
<li><b>二维的一阶范数</b>＝当前行业相关点云中二维空腔的持久性平方和再除以四。
<span class="hov" title="工程原字段名：h2_count">空腔数量</span>回答「有几个」，
一阶范数回答「这些空腔合起来有多持久」；平方加权意味着它可能被少数长寿空腔主导。</li>
<li>相关距离不直接含收益幅度，所以景观范数不会仅因波动率放大而机械放大；
但<b>这不等于绝对水平可以无条件跨日期比较</b>。早期节点数从六十一至七十四变化、后段从六十七至一百三十一变化，
十期相关估计误差以及行业集合变化，都会影响环和空腔的数量与持久性，必须并列披露。</li>
</ul>

<div class="note"><span class="pill name">译名约定</span>
按用户指定，本报告把「相邻两日持续图之间的距离」统一译为
<b>威尔斯特拉斯距离</b>
<span class="hov" title="英文原名：Wasserstein distance">（悬停看英文原名）</span>。
以上三节只解释本工程当前点云与摘要，<b>不改动任何数据、标签、判定或统计结果</b>，
也不构成对持续同调有效或无效的推断。</div>
</section>
"""


def pct_s(x, digits=2):
    return f"{x:+.{digits}f}%" if x is not None else "—"


# ---------------------------------------------------------------------------
# 八·补：十四条推测的判定与关键实测表现一览
# 推测文字为第一版原文的中文化整理（原文连提出时依据一并保留在悬停里）；
# 「本版关键实测」列的全部数字由第五版判定文件的 evidence 字段直接格式化，
# 不手抄、不重算；判定以第五版结论台账为准。
# ---------------------------------------------------------------------------
CLAIM_ZH = {
    "C01": "危机中尺度摘要（相邻持续图距离、持续景观范数、零维死亡时间、一维出生与寿命）随已实现波动上升",
    "C02": "危机中尺度摘要几乎可被二十日已实现波动、平均相关与第一特征值占比解释，无独立结构信息",
    "C03": "危机中尺度摘要的峰值滞后于危机起点",
    "C04": "危机前形状摘要与常态无稳定差异",
    "C05": "缩量型危机前尺度摘要落最低分位（对应原文最差保护仓位的满仓档）",
    "C06": "放量型危机前尺度摘要已偏高",
    "C07": "危机中一维孔洞数量下降",
    "C08": "危机前零维死亡时间的离散度低、边长整齐",
    "C09": "牛市与熊市在尺度水平、共同因子强度、防御/成长双簇上存在差异",
    "C10": "窗口填满后一维、二维孔洞趋于消失（一维塌陷）",
    "C11": "爆发初期六十日混合窗口制造长寿命零维与假一维环",
    "C12": "相关网络空腔数在危机前处于中高位",
    "C13": "危机中摘要被停牌稀释平滑、涨跌停削顶污染",
    "C14": "相邻持续图距离的变化率／跨簇重配对比例领先危机",
}
NOTE_ZH = {
    "C01": "只约束状态点云的逐日尺度量；相关网络景观范数单列；提出时形态对照的高相关不作证据。",
    "C02": "沿用第一版单侧规则；解释比例低反而反驳「距离只是波动代理」，该规则盲区已登记，本版不升级结论。",
    "C03": "峰值滞后含机械成分（窗内取最大必落窗内）；两面板不合并计数。",
    "C04": "分线分别计数，不报混合格数。",
    "C05": "只按方向判，显著性单列；不能读成「缩量分型已证实可交易」。",
    "C06": "只按方向判，显著性单列。",
    "C07": "按状态点云一维／相关网络一维／相关网络二维分维计数，禁止合并不同维孔洞；显著须同时过原始概率与区间双闸门。",
    "C08": "第三版为无法判定；本版前段事件进入后按六格方向规则判为矛盾，属样本内方向对账，不是预测证据。",
    "C09": "十格差非零部分是机械结果（牛熊定义本身含价格与波动）；双簇属相关网络零维语义。",
    "C10": "第三口径被二十日标签窗截断，不是事件总长度。",
    "C11": "第三版为无法判定；本版事件级样本扩为四十二个起点后判为矛盾；不是预测能力证据。",
    "C12": "「低空腔有效」与「高空腔预示危机」此前均已否证；空腔数受节点数漂移影响。",
    "C13": "两条线都受影响但机制不同；不把近似量当机制证据。",
    "C14": "探索性猜想，按规格不升级为主结论；跨簇重配对属相关网络语义，本判定只测距离变化率。",
}
# 金融依据与拓扑映射是整理者基于公开文献作出的机制说明，不是本版实测结果。
# 参考文献只支持其明确研究的市场机制或方法，不替十四条推测预设成立。
FIN_BASIS = {
    "C01": "危机中的强制去杠杆、保证金上调和流动性螺旋，会放大价格波动并增强共同抛售；熊市中的极端相关性也有高于牛市的经验证据。因此，“市场更动荡”是尺度摘要可能上升的金融背景，而不是拓扑学本身的证明。",
    "C02": "危机期价格、波动率与相关性并非彼此独立：高波动会改变未经调整的相关系数，融资约束与共同平仓又会让不同资产受到同一资金流冲击。因此，持续摘要可能主要重复波动率、平均相关和共同因子强度已经表达的信息；但这不是“必然没有增量”的定理。",
    "C03": "把事后价格峰值作为危机开始参照日时，价格由升转降通常早于强制抛售、融资收缩和流动性恶化完全展开。危机压力需要时间在板块和参与者之间传导，所以最剧烈的市场结构变化可能晚于最初峰值；金融拓扑文献也区分危机前趋势与危机主峰，但所用日期和点云并不等同于本工程。",
    "C04": "资产价格可以在脆弱性积累阶段仍显得平静，因为杠杆、共同持仓和融资依赖未必立即反映为收益或波动。可是，已有金融拓扑研究在特定市场和参数下报告过危机前信号，所以“危机前形状与常态没有稳定差异”应被视为待检验的保守零假设，而非学界共识。",
    "C05": "低成交量下跌可能反映买方退出和市场深度不足：即使没有恐慌性放量，少量卖单也可能持续压低价格，融资约束也能在交易清淡时形成压力。价量文献支持成交量与价格波动存在系统关系，却没有证明“所有缩量危机前的尺度摘要都处最低分位”。",
    "C06": "高位换手、投资者分歧扩大或强制交易，可能使成交量与价格波动在危机前同步抬升。放量也不等于流动性充裕，因为恐慌交易放大成交量的同时，市场深度可能正在恶化；但上涨和投机狂热同样会放量，所以放量不是危机专属条件。",
    "C07": "危机中的共同抛售和避险交易会使行业收益更受单一市场因子支配，熊市极端相关性上升为此提供了经验背景。不过，危机初期的板块冲击不均、流动性传导先后和轮动也可能暂时增强异质性，因此“一维孔洞必然减少”不是无条件规律。",
    "C08": "如果杠杆和关联仓位在表面平静中积累，价格可能暂时表现为低波动、行业差异收窄；金融连通性研究支持关联结构随系统性风险变化，却没有推出“危机前边长必然整齐”。这条推测的金融依据较弱，主要是对“平静中积累脆弱性”的几何外推。",
    "C09": "牛熊状态不仅对应收益方向不同，也对应风险偏好、资金流和相关性结构不同；极端负收益下的相关性高于正收益，牛熊区间也有专门的识别研究。防御与成长板块对利率、盈利预期和风险偏好的敏感性不同，因此在熊市中形成相对分离的板块群组具有金融直觉。",
    "C10": "当危机状态填满整个窗口，市场往往已从冲击初期的局部分化进入共同去杠杆和流动性传导阶段，行业同步性可能更强。相关性上升和多元化失效支持这一背景；但若危机内部仍有强烈板块轮动或政策驱动的分化，孔洞就不必消失。",
    "C11": "爆发初期是旧常态与危机状态并存的过渡期，强制抛售和流动性恶化尚未必然扩散到所有行业，因此其几何结构可能不同于完全危机期。不过，“六十日混合窗口必然制造假环”不是金融文献结论；当前十日窗口检验的是同类混合机制，不是六十日参数复现。",
    "C12": "危机前金融机构和板块间的连通性可能上升，风险可经共同持仓与融资链传播；但连通性高并不等于二维空腔多，空腔反而要求局部缺少足够连接。因此，“空腔数在危机前处中高位”只是复杂网络类比，没有可直接套用的金融定律。",
    "C13": "涨跌停可能推迟价格发现、干扰交易，并把部分波动推到后续交易日；停牌则使成分股价格暂时不更新。两者都可能使观察到的行业收益偏离无约束交易下的市场价格，因而存在污染持续摘要的金融机制；但行业指数受到的是成分股约束的间接影响。",
    "C14": "如果危机是融资、持仓与板块联动逐步重组的结果，结构变化的速度可能比结构水平更早反应。连通性和金融拓扑预警研究为这种可能性提供背景；但外生冲击可以无预警跳变，现有文献并不保证变化率或跨簇重配对必然领先危机。",
}
TOPO_MAP = {
    "C01": "市场状态点云使用含收益幅度的欧氏距离，极端日更离群，零维死亡值和相邻日持续图距离容易随尺度扩张。行业相关点云已除去收益幅度，其景观范数不应被默认同步上升；文献中的危机景观结果不能替代本工程的方向检验。",
    "C02": "当前复形只使用点间距离，因此窗口波动、平均相关与第一特征值占比确实可能解释距离矩阵的大部分变化。另一方面，环和空腔仍可能保留成对相关之外的高阶组合信息；解释比例低会反驳“只是波动代理”，但也并不自动证明具有预测价值。",
    "C03": "滚动窗口逐日用危机状态替换常态状态，尺度或相邻图距离的最大值可能等足够多的危机日进入窗口后才出现。因此观测到的滞后会混合金融传导、事后参照日和窗口取最大值的机械成分，不能全部解释为市场反应迟缓。",
    "C04": "形状摘要试图识别不完全由幅度解释的群组、环和空腔变化。危机前没有显著差异，既可能意味着没有稳定结构前兆，也可能来自样本量不足、十日窗口过短或估计噪声；当前检验不能在这几种解释之间作出因果区分。",
    "C05": "若缩量阶段同时表现为行业收益幅度小、状态点彼此接近，市场状态点云会更紧凑，尺度摘要偏低是可理解的几何推论。但当前点云不直接读取成交量，缩量分型来自外部市场状态，不能说是持续同调自己识别了缩量。",
    "C06": "只有放量同时伴随更大的行业收益幅度或更频繁的状态跳变，含量级距离与相邻持续图距离才会偏高；若成交量放大而收益形态不变，当前两套点云都不会仅因成交量本身而变化。这是该推测必须保留的测量边界。",
    "C07": "行业相关点云中，更强同步会缩短跨行业距离并增加捷径边，一些一维环会更早被三角形填掉；市场状态点云中，共同因子占主导也可能把状态压向低维。但瞬态板块分化同样能够造环，所以必须分线、分阶段实测。",
    "C08": "零维死亡时间的离散度低，表示各点或行业的合并尺度更接近。它是相对离散度：低值既可能来自低波动平静，也可能来自整体同步紧张，必须结合死亡值水平、平均相关和共同因子强度解读，不能单独等同于“危机前整齐”。",
    "C09": "尺度水平与第一特征值占比分别刻画波动幅度和共同因子主导程度；行业相关点云零维的合并层级可描述防御与成长是否形成相对独立的簇。但“双簇”只是候选几何解释，不等于已经识别了资金流或资产配置的因果机制。",
    "C10": "行业相关点云中，更多跨簇捷径边会把一维环和二维空腔填实；市场状态点云中，如果危机日沿少数共同因子轴排列，环结构也会减少。窗口填满程度同时是样本构造条件，不能当成一个独立于窗口规则的金融变量。",
    "C11": "混合窗口把两类市场状态放进同一坐标系，离群日常会拉长零维死亡；两组状态之间的偶然闭合路径也可能形成一维环。环是否长寿取决于点间距离而不是“危机”名称，且持续景观水平会随窗口和嵌入参数变化，必须披露参数敏感性。",
    "C12": "二维空腔计数依赖当天行业节点数、相关估计和滤值，节点增加本身就能改变可形成的空腔数量。它可以描述相关几何中的高阶空洞，却不能直接翻译成风险敞口、杠杆水平或危机概率，更不能跨节点数不变的假定之外直接比较。",
    "C13": "本工程使用行业指数而不是单只股票，影响路径是成分股交易约束先改变行业收益，再改变点云。停牌可能降低有效截面并造成虚假的同步或平滑，涨跌停可能压缩当日收益极值并延后状态跳变；没有直接字段时，不能把摘要变化归因于这一机制。",
    "C14": "相邻持续图距离的变化率捕捉结构改变是否正在加速，跨簇重配对描述行业是否离开旧群组并加入新群组；两者都可能区分“高但稳定”与“正在失稳”。当前判定只实际检验了距离变化率，跨簇重配对仍是未检验的探索方向。",
}
EVIDENCE_GRADE = {
    "C01": "中等：金融机制明确，摘要方向依构造",
    "C02": "中等：共享通道明确，独立信息待检验",
    "C03": "中等：危机演化支持，窗口机械成分强",
    "C04": "探索性：不同文献与市场存在不同结果",
    "C05": "较弱：价量关系仅提供间接依据",
    "C06": "较弱至中等：价量与流动性提供间接依据",
    "C07": "中等：共同因子支持，但方向可以反转",
    "C08": "较弱：主要是连通性与平静期的类比",
    "C09": "中等：牛熊状态与下行相关性有文献支持",
    "C10": "中等：同步化支持，但不是拓扑定理",
    "C11": "较弱至中等：过渡期合理，假环属几何猜想",
    "C12": "较弱：高维空腔没有直接金融定律",
    "C13": "较强的机制依据：行业指数传导仍待实测",
    "C14": "探索性：预警文献仅为间接背景",
}
CONJ_REFS = {
    "C01": [1, 4, 6, 12], "C02": [5, 10, 12], "C03": [1, 3, 6],
    "C04": [1, 3, 10], "C05": [6, 7, 8], "C06": [6, 8],
    "C07": [2, 4, 6], "C08": [5, 10, 12], "C09": [4, 9, 10],
    "C10": [2, 4, 6], "C11": [6, 12, 13], "C12": [2, 10],
    "C13": [11], "C14": [1, 3, 10],
}
# 编号、年份、中文题名、中文出版信息、原始完整引文（悬停）、核验链接。
REFS = [
    (1, 2018, "金融时间序列的拓扑数据分析：危机景观", "《物理学A》第491卷，820—834页", "Gidea, Marian; Katz, Yuri (2018). Topological data analysis of financial time series: Landscapes of crashes. Physica A 491: 820-834. DOI: 10.1016/j.physa.2017.09.028", "https://doi.org/10.1016/j.physa.2017.09.028"),
    (2, 2021, "运用拓扑数据分析与持续同调分析新加坡及中国台湾股票市场", "《物理学前沿》第九卷，文章编号572216", "Yen, Peter Tsung-Wen; Cheong, Siew Ann (2021). Using Topological Data Analysis (TDA) and Persistent Homology to Analyze the Stock Markets in Singapore and Taiwan. Frontiers in Physics 9: 572216. DOI: 10.3389/fphy.2021.572216", "https://doi.org/10.3389/fphy.2021.572216"),
    (3, 2022, "利用持续同调识别金融危机的预警信号", "《物理学A》第586卷，文章编号126459", "Ismail, Mohd Sabri; Md Noorani, Mohd Salmi; Ismail, Munira; Abdul Razak, Fatimah; Alias, Mohd Almie (2022). Early warning signals of financial crises using persistent homology. Physica A 586: 126459. DOI: 10.1016/j.physa.2021.126459", "https://doi.org/10.1016/j.physa.2021.126459"),
    (4, 2001, "国际股票市场的极端相关性", "《金融学杂志》第56卷第2期，649—676页", "Longin, Francois; Solnik, Bruno (2001). Extreme Correlation of International Equity Markets. Journal of Finance 56(2): 649-676. DOI: 10.1111/0022-1082.00340", "https://doi.org/10.1111/0022-1082.00340"),
    (5, 2002, "没有传染，只有相互依赖：衡量股票市场联动", "《金融学杂志》第57卷第5期，2223—2261页", "Forbes, Kristin J.; Rigobon, Roberto (2002). No Contagion, Only Interdependence: Measuring Stock Market Comovements. Journal of Finance 57(5): 2223-2261. DOI: 10.1111/0022-1082.00494", "https://doi.org/10.1111/0022-1082.00494"),
    (6, 2009, "市场流动性与融资流动性", "《金融研究评论》第22卷第6期，2201—2238页", "Brunnermeier, Markus K.; Pedersen, Lasse Heje (2009). Market Liquidity and Funding Liquidity. Review of Financial Studies 22(6): 2201-2238. DOI: 10.1093/rfs/hhn098", "https://doi.org/10.1093/rfs/hhn098"),
    (7, 1987, "价格变化与成交量之间的关系：研究综述", "《金融与定量分析杂志》第22卷第1期，109—126页", "Karpoff, Jonathan M. (1987). The Relation between Price Changes and Trading Volume: A Survey. Journal of Financial and Quantitative Analysis 22(1): 109-126. DOI: 10.2307/2330874", "https://doi.org/10.2307/2330874"),
    (8, 1992, "股票价格与成交量", "《金融研究评论》第5卷第2期，199—242页", "Gallant, A. Ronald; Rossi, Peter E.; Tauchen, George (1992). Stock Prices and Volume. Review of Financial Studies 5(2): 199-242. DOI: 10.1093/rfs/5.2.199", "https://doi.org/10.1093/rfs/5.2.199"),
    (9, 2003, "分析牛市与熊市的一个简明框架", "《应用计量经济学杂志》第18卷第1期，23—46页", "Pagan, Adrian R.; Sossounov, Kirill A. (2003). A simple framework for analysing bull and bear markets. Journal of Applied Econometrics 18(1): 23-46. DOI: 10.1002/jae.664", "https://doi.org/10.1002/jae.664"),
    (10, 2012, "金融与保险部门连通性和系统性风险的计量测度", "《金融经济学杂志》第104卷第3期，535—559页", "Billio, Monica; Getmansky, Mila; Lo, Andrew W.; Pelizzon, Loriana (2012). Econometric measures of connectedness and systemic risk in the finance and insurance sectors. Journal of Financial Economics 104(3): 535-559. DOI: 10.1016/j.jfineco.2011.12.010", "https://doi.org/10.1016/j.jfineco.2011.12.010"),
    (11, 1997, "价格限制的表现：来自东京证券交易所的证据", "《金融学杂志》第52卷第2期，885—901页", "Kim, Kenneth A.; Rhee, S. Ghon (1997). Price Limit Performance: Evidence from the Tokyo Stock Exchange. Journal of Finance 52(2): 885-901. DOI: 10.1111/j.1540-6261.1997.tb04827.x", "https://doi.org/10.1111/j.1540-6261.1997.tb04827.x"),
    (12, 2015, "使用持续景观的统计拓扑数据分析", "《机器学习研究学报》第16卷，77—102页", "Bubenik, Peter (2015). Statistical Topological Data Analysis using Persistence Landscapes. Journal of Machine Learning Research 16: 77-102", "https://www.jmlr.org/papers/v16/bubenik15a.html"),
    (13, 2021, "时间分辨的市场不稳定性拓扑数据分析", "《物理学A》第571卷，文章编号125816", "Katz, Yuri A.; Biem, Alain (2021). Time-resolved topological data analysis of market instabilities. Physica A 571: 125816. DOI: 10.1016/j.physa.2021.125816", "https://doi.org/10.1016/j.physa.2021.125816"),
]
DIR_ZH = {"up": "上升", "down": "下降", "flat": "持平"}


def _perf_c03(e):
    a, b = e["a16"], e["a27"]
    return (f"事件级峰值滞后中位数：十六行业 {a['median']:g} 个交易日"
            f"（{a['n']} 个事件，自助区间 {a['boot']['ci_lo']:.1f}—{a['boot']['ci_hi']:.1f}，不跨零）；"
            f"二十七行业 {b['median']:g} 日（{b['n']} 个事件，"
            f"区间 {b['boot']['ci_lo']:.1f}—{b['boot']['ci_hi']:.1f}）")


def _perf_c07(e):
    a = e["A_H1"]["cells"]
    return (f"状态点云一维数量：十六行业{DIR_ZH[a[0]['direction']]}"
            f"（原始概率 {a[0]['p_raw']:g} 但区间跨零）、"
            f"二十七行业{DIR_ZH[a[1]['direction']]}（概率 {a[1]['p_raw']:g}）；"
            f"相关网络一维{DIR_ZH[e['B_H1']['cells'][0]['direction']]}、"
            f"二维{DIR_ZH[e['B_H2']['cells'][0]['direction']]}，均不显著")


def _perf_c09(e):
    d = {x["key"]: x["diff"] for x in e["A_bull_bear_10_cells"]}
    return (f"牛熊十格差全部非零：平均相关差十六行业 {d['a16|avg_pair_corr']:+.3f}／"
            f"二十七行业 {d['a27|avg_pair_corr']:+.3f}；第一特征值占比差十六行业 "
            f"{d['a16|leading_eig_share']:+.3f}／二十七行业 {d['a27|leading_eig_share']:+.3f}；"
            "相关网络零维防御/成长双簇本版首次可描述")


def _perf_c10(e):
    l1 = e["J3"]["L1"]
    return ("按各线自身窗口与三种长度口径重判：能填满窗口的事件数随窗口变长迅速减少"
            f"（长度口径一：10 日 {l1['10']} 个、30 日 {l1['30']} 个、60 日 {l1['60']} 个）")


def _perf_c11(e):
    d = {x["key"]: x for x in e["cells"]}
    return (f"事件级四格：十六行业一维数量增量 {d['a16|h1_count']['delta']:+g} 且显著"
            f"（与推测方向相反）；十六行业零维最大死亡增量 "
            f"{d['a16|h0_death_max']['delta']:+.4f} 不显著；二十七行业两格均不显著")


PERF = {
    "C01": lambda e: (
        f"两面板六个尺度量：方向 {e['A_scale6_up']}/6 上升，过双闸门 {e['A_scale6_sig']} 格；"
        "相关网络两个持续景观范数单列："
        + ("均" + DIR_ZH[e["B_landscape_separate"][0]["direction"]]
           if len({x["direction"] for x in e["B_landscape_separate"]}) == 1
           else "、".join(DIR_ZH[x["direction"]] for x in e["B_landscape_separate"]))
        + f"，显著 {sum(1 for x in e['B_landscape_separate'] if x['sig'])} 格"),
    "C02": lambda e: (
        f"尺度摘要被窗口波动＋平均相关＋第一特征值占比解释的比例：十六行业 "
        f"{e['R2_on_scale_corr_eig']['a16']:.3f}、二十七行业 "
        f"{e['R2_on_scale_corr_eig']['a27']:.3f}；危机中残差方向十六行业"
        + DIR_ZH[e["W_resid_crisis_in"][0]["direction"]] + "／二十七行业"
        + DIR_ZH[e["W_resid_crisis_in"][1]["direction"]] + "，均不显著"),
    "C03": _perf_c03,
    "C04": lambda e: (
        f"危机前形状摘要显著格：状态点云 {e['A_sig']}/{e['A_shape']} 格；"
        f"相关网络 {e['B_sig']}/{e['B_shape']} 格（均为零）"),
    "C05": lambda e: (
        f"危机前低波动组六个尺度量：方向 {e['n_low_down']}/6 下降，显著 {e['n_sig']} 格"),
    "C06": lambda e: (
        f"危机前高波动组六个尺度量：{e['n_high_up']}/6 上升"
        f"（两个距离与两个零维死亡均值），显著 {e['n_sig']} 格"),
    "C07": _perf_c07,
    "C08": lambda e: (
        "危机前五/十/二十日乘两面板共六格零维死亡离散度："
        f"下降 {sum(1 for x in e['cells'] if x['direction'] == 'down')} 格、"
        f"上升 {sum(1 for x in e['cells'] if x['direction'] == 'up')} 格，"
        f"显著 {sum(1 for x in e['cells'] if x['sig'])} 格"),
    "C09": _perf_c09,
    "C10": _perf_c10,
    "C11": _perf_c11,
    "C12": lambda e: (
        f"危机中空腔数方向{DIR_ZH[e['N_crisis_in']]}；按冻结规格不设方向假设"),
    "C13": lambda e: "本地无直接停牌/涨跌停字段，本版未测",
    "C14": lambda e: (
        f"距离变化率：十六行业增量 {e['a16']['delta']:+.5f}（概率 {e['a16']['p']:g}）、"
        f"二十七行业 {e['a27']['delta']:+.5f}（概率 {e['a27']['p']:g}），均不显著"),
}
LINE_ZH = {("A",): "状态点云", ("B",): "相关网络", ("A", "B"): "两线",
           ("市场层/中性",): "市场层"}


def _verdict_pill(v):
    cls = "sup" if v == "支持" else ("con" if v == "矛盾" else "und")
    return f'<span class="pill {cls}">{html.escape(v)}</span>'


def _ref_links(cid):
    links = "".join(f'<a href="#ref{k}" title="转到参考文献 {k}">〔{k}〕</a>' for k in CONJ_REFS[cid])
    return '<span class="reflinks">参考文献：' + links + '</span>'


def _reference_list():
    items = []
    for rid, year, zh_title, pub, original, url in REFS:
        items.append(
            f'<li id="ref{rid}" value="{rid}"><span class="hov" title="原始完整引文：'
            + html.escape(original, quote=True) + '"><b>' + html.escape(zh_title)
            + '</b></span>，' + str(year) + '年，' + html.escape(pub) + '。'
            + '<a href="' + html.escape(url, quote=True)
            + '" target="_blank" rel="noopener" title="打开已核验的原始出处">查看原始出处</a>。</li>')
    assert len(items) == 13
    return '<ol class="reflist">' + "".join(items) + '</ol>'


def conjecture_section():
    rows = []
    details = []
    for cid in sorted(conj_v05):
        c = conj_v05[cid]
        verdict = ledger_v05[cid]["v0_5_verdict"]
        perf = PERF[cid](c["evidence"])
        cid_zh = f"第 {int(cid[1:])} 条"
        rows.append(
            '<tr><th title="工程原编号：' + cid + '">' + cid_zh + "</th>"
            '<td><span class="hov" title="第一版推测原文（含提出时依据）：'
            + html.escape(claims_v01[cid], quote=True) + '">'
            + html.escape(CLAIM_ZH[cid]) + "</span></td>"
            "<td>" + LINE_ZH[tuple(c["lines"])] + "</td>"
            "<td>" + _verdict_pill(verdict) + "</td>"
            "<td>" + html.escape(perf) + "</td>"
            "<td>" + html.escape(NOTE_ZH[cid]) + "</td></tr>")
        details.append(
            '<details class="conjdetail" id="detail' + cid + '"><summary><span title="工程原编号：'
            + cid + '">' + cid_zh + '</span>　'
            + html.escape(CLAIM_ZH[cid]) + '　' + _verdict_pill(verdict) + '</summary>'
            '<div class="basis"><p><b>金融依据：</b>' + html.escape(FIN_BASIS[cid]) + '</p>'
            '<p><b>拓扑摘要如何对应：</b>' + html.escape(TOPO_MAP[cid]) + '</p>'
            '<p><b>依据强弱：</b>' + html.escape(EVIDENCE_GRADE[cid]) + '。'
            + _ref_links(cid) + '</p>'
            '<p><b>第五版关键实测：</b>' + html.escape(perf) + '</p>'
            '<p><b>判定读法：</b>' + html.escape(NOTE_ZH[cid]) + '</p></div></details>')
    assert len(rows) == len(details) == 14
    counts = verdicts_v05["conjecture_counts"]
    assert sum(counts.values()) == 14
    return (
        '<section class="card" id="conjectures"><h2>先行阅读、十四条推测：金融依据、拓扑含义与第五版冻结检验</h2>'
        '<div class="note"><b>这一节放在报告前部，先说明“为什么提出、现在检验成什么样”。</b>'
        '每条推测分三层：金融文献或市场机制提供背景；整理者把该背景映射为当前点云的可检验方向；'
        '第五版本地样本给出实际判定。三层不可互相替代，<b>引用文献不等于该条推测已在本项目成立</b>。'
        '当前点云构造仍以后面三节工程口径为准，参考文献不用于重新定义点云。</div>'
        '<h3>甲、十四条推测与第五版结果速览</h3>'
        '<div class="note"><b>怎么读这张表：</b>推测列是提出时表述的中文化整理，'
        '悬停可看第一版原文（含提出时的依据，那些数字不是本版结果）；'
        '「本版关键实测」列的全部数字直接取自第五版判定层产物，未在本报告重算。'
        '判定口径：状态组中位数减常态基线中位数；二十日循环区块自助一千次、双侧百分之九十五区间；'
        '邦费罗尼十二重校正；原始概率小于阈值且区间不跨零须同时满足（双闸门）；事件级去重为主读数。'
        '第五版合计：<b>' + " / ".join(f"{k} {v}" for k, v in counts.items()) + '</b>；'
        '两条线主判据仍均为「无法判定（含数据不足）」。'
        '本表全部为样本内描述性对账，<b>不构成对持续同调有效或无效的推断</b>。</div>'
        '<div class="scroll"><table class="mtable"><thead><tr>'
        "<th>编号</th><th>推测（提出时表述）</th><th>涉及线</th><th>第五版判定</th>"
        "<th>第五版关键实测</th><th>读法与备注</th></tr></thead><tbody>"
        + "".join(rows) + '</tbody></table></div>'
        '<h3>乙、逐条展开：金融机制、拓扑映射、依据强弱与文献</h3>'
        '<div class="warn">点击每条推测展开。文献主要支持波动、相关性、流动性、成交量或网络连通性的背景；'
        '凡是具体到零维离散度、一维环、二维空腔或变化率的固定方向，只要没有直接文献依据，均明确标为外推或探索。</div>'
        + "".join(details) +
        '<h3>丙、参考文献（十三篇，均已核对题名、年份与出处）</h3>'
        '<div class="note">为保持正文中文展示，作者原名、英文题名与完整原始引文放在各条文献的悬停中；'
        '点击“查看原始出处”可打开出版方或期刊页面。链接需要联网，不影响报告其余内容离线阅读。</div>'
        + _reference_list() + '</section>')


def crisis_background_section():
    """前置危机史：只读整理，不重定义标签，也不制造逐段独立因果。"""
    rounds = [
        {
            "name": "第一轮｜2001—2005 制度性长熊",
            "date": "2001-06-14 → 2005-06-06", "dd": "−55.5439%", "ids": "统一 02—13",
            "kind": "股权分置与国有股减持背景下的制度性、政策性长期熊市。",
            "cause": "国有股按市价减持触发供给扩张与流通股东权益补偿担忧；减持叫停后，非流通股悬置和补偿不确定性仍未消失，估值长期承压。",
            "harm": "伤害主要不是一次单日崩盘，而是多年阴跌、成交萎缩与财富持续缩水；经济高增长与股市长期下行并存，说明宏观增长不能自动抵消制度性风险折价。",
            "src": '<a href="https://www.pbcsf.tsinghua.edu.cn/__local/2/8D/BF/5B2906725D8247333002A83695D_77ECA550_E3FB9.pdf" target="_blank" rel="noopener">股权分置改革学术研究</a>、<a href="https://epaper.cs.com.cn/zgzqb/html/2010-12/01/nw.D110000zgzqb_20101201_1-T14.htm" target="_blank" rel="noopener">中国证券报历史复盘</a>',
        },
        {
            "name": "第二轮｜2007—2008 泡沫破裂与全球金融危机",
            "date": "2007-10-16 → 2008-10-28", "dd": "−72.8132%", "ids": "统一 16—20",
            "kind": "高估值泡沫破裂叠加全球系统性金融危机，是七轮中峰谷回撤最深的一轮。",
            "cause": "前期估值过高，国内紧缩、巨额再融资预期和限售股解禁削弱承接力；美国次贷危机升级为全球金融海啸后，盈利预期与风险溢价进一步恶化。",
            "harm": "估值与盈利预期双杀，权重、周期和高估值板块大幅缩水；多次政策托底后市场才见底，说明政策底不等于市场底。",
            "src": '<a href="https://www.fundmarket.com.cn/upfiles/images/2017-04/201704171720412136.pdf" target="_blank" rel="noopener">二零零八年基金市场发展综述</a>、<a href="http://news.cnnb.com.cn/system/2009/01/01/005942914.shtml" target="_blank" rel="noopener">当年市场复盘</a>',
        },
        {
            "name": "第三轮｜2009—2013 刺激退潮后的慢性长熊",
            "date": "2009-08-04 → 2013-06-25", "dd": "−46.8187%", "ids": "统一 22—28",
            "kind": "刺激退出、通胀紧缩、盈利下行与欧债危机共同形成的慢性长熊，末端叠加钱荒。",
            "cause": "四万亿刺激边际效应减弱，货币政策回归紧缩，融资扩容与增长下修持续压制估值；欧债危机反复，二零一三年六月银行间流动性冲击又把压力传至股票。",
            "harm": "主要伤害是长时间阴跌和估值中枢下移；钱荒阶段则表现为货币利率飙升、银行股急跌和跨市场流动性传染。",
            "src": '<a href="https://caifuhao.eastmoney.com/news/20240207113207046124060" target="_blank" rel="noopener">历次熊市复盘（非一手研究，需核实原文）</a>、<a href="https://jingji.cntv.cn/2013/06/26/ARTI1372212945540167.shtml" target="_blank" rel="noopener">央视网钱荒复盘</a>',
        },
        {
            "name": "第四轮｜2015—2016 杠杆出清与熔断冲击",
            "date": "2015-06-12 → 2016-01-27", "dd": "−49.0498%", "ids": "统一 29—31",
            "kind": "杠杆清算型流动性危机，随后叠加汇率波动与熔断制度冲击。",
            "cause": "场内外杠杆在上涨中自我强化，清理配资后转为强平与赎回的负反馈；二零一六年熔断与既有涨跌停、隔夜交易限制相互作用，放大挤向出口的动机。",
            "harm": "反复大面积跌停和停牌使卖出与价格发现受阻，融资账户、私募产品和高估值成长风格损失集中；官方复盘同时指出系统性风险曾凸显，但采取措施后避免了进一步蔓延。",
            "src": '<a href="https://www.csrc.gov.cn/csrc/c100028/c1001876/content.shtml" target="_blank" rel="noopener">中国证监会异常波动复盘</a>、<a href="https://www.thepaper.cn/newsdetail_forward_7118859" target="_blank" rel="noopener">股灾与流动性复盘</a>',
        },
        {
            "name": "第五轮｜2018 去杠杆、贸易摩擦与股权质押",
            "date": "2018-01-29 → 2019-01-04", "dd": "−31.9518%", "ids": "统一 33—35",
            "kind": "内部金融去杠杆与外部贸易摩擦叠加的大级别市场危机。",
            "cause": "资管与信用收缩压低风险偏好，贸易摩擦反复抬升风险溢价；大股东高比例质押在下跌中触及平仓线，形成股票下跌与融资收缩的反馈。",
            "harm": "中小市值、民营企业与高质押公司承压更集中，市场不仅承受估值下降，也承受融资可得性下降和被动卖出压力。",
            "src": '<a href="https://caifuhao.eastmoney.com/news/20240207113207046124060" target="_blank" rel="noopener">历次熊市复盘（非一手研究，需核实原文）</a>',
        },
        {
            "name": "第六轮｜2021 年末—2022 多重宏观冲击",
            "date": "2021-12-13 → 2022-04-27（九月—十月另有子事件）", "dd": "−22.7906%", "ids": "统一 40—41",
            "kind": "全球紧缩、疫情、地产与增长预期共同压制的市场级调整。",
            "cause": "美联储紧缩提高折现率，俄乌冲突推升避险情绪与成本压力，国内疫情和地产调整削弱盈利预期；九月—十月又受到鹰派政策与人民币贬值影响。",
            "harm": "成长和高估值板块对折现率更敏感，宽基回撤之外还出现明显的风格伤害；这是多重冲击叠加，不宜归因成单一新闻。",
            "src": '此前七轮框架讨论＋本工程通达信峰谷复核；本行不额外宣称单一因果识别',
        },
        {
            "name": "第七轮｜2023—2024 小微盘流动性危机",
            "date": "2023-05-09 → 2024-02-05", "dd": "−22.9269%", "ids": "统一 42—43（43 为外部锚点）",
            "kind": "市场持续走弱最终演化为小微盘、雪球和量化策略的结构性流动性冲击。",
            "cause": "雪球集中敲入后期货贴水与对冲成本上升，杠杆中性策略降仓和平仓，小微盘承接不足又放大价格下跌，形成同质化交易的负反馈。",
            "harm": "伤害高度集中在小微盘和量化拥挤持仓，单看上证会明显低估；托底资金扩展至中小盘交易型开放式指数基金后，负反馈缓解并出现快速修复。",
            "src": '<a href="http://www.nifd.cn/Uploads/SeriesReport/747846f4-bac1-48dd-9d31-e4a3ace2f8fa.pdf" target="_blank" rel="noopener">国家金融与发展实验室季度报告</a>、<a href="https://www.howbuy.com/news/2024-12-30/5828681.html" target="_blank" rel="noopener">量化策略年度复盘（机构观点）</a>',
        },
    ]
    out = [
        '<section class="card" id="crisis-background"><h2>先行阅读·危机史、金融定性、成因与伤害</h2>',
        '<div class="leak"><b>先解决“到底有几次”。</b>本报告共有 <b>47 个条目</b>＝45 个统计事件＋2 个外部描述性锚点。'
        '它们<b>不是 47 次相互独立的金融危机</b>：45 个统计事件由同一急性阈值机械切段，多个段可以属于同一轮危机。'
        '此前讨论的七轮是市场级区间；急性崩盘、钱荒、熔断、外生冲击和结构性危机应另行拆分阅读，两个层次不能混算。</div>',
        '<div class="note"><b>统一编号规则。</b>全部 47 条按开始日期编为 <b>01—47</b>：前段工程原编号 101—128 对应统一 01—28；'
        '后段工程原编号 1—17 与两个外部锚点按日期插入，对应统一 29—47。'
        '其中统一 43＝工程原编号 18（2024-02-05），统一 47＝工程原编号 19（2025-04-07）。'
        '统一编号只用于本报告展示；数据文件、标签与判定仍使用工程原编号，末尾总表保留一一映射。</div>',
        '<h3>甲、四种金融定性不能混为一谈</h3>',
        '<table class="mtable"><thead><tr><th>类型</th><th>识别重点</th><th>读法边界</th></tr></thead><tbody>'
        '<tr><th>技术性熊市</th><td>宽基指数从局部峰值回撤达到百分之二十</td><td>只是价格口径，百分之二十不是自然定律</td></tr>'
        '<tr><th>大级别市场危机</th><td>回撤更深，或同时出现市场宽度、流动性和融资链条恶化</td><td>长熊与快速崩盘仍应分开</td></tr>'
        '<tr><th>急性崩盘／流动性冲击</th><td>短期异常下跌并伴随跌停、停牌、强平或交易机制失灵</td><td>总回撤可以不到百分之二十</td></tr>'
        '<tr><th>结构性危机</th><td>小微盘、成长或核心资产等某一风格深跌，宽基相对平稳</td><td>不能只用上证判断伤害，也不能直接称金融体系危机</td></tr>'
        '</tbody></table>',
        '<p class="warn"><b>股市危机不等于金融体系系统性危机。</b>后者还要求银行、信用、支付或跨市场功能出现更广障碍。'
        '以下“成因”是此前讨论与公开资料形成的事后解释，不参与分组、标签、阈值或判定。</p>',
        '<h3>乙、七轮市场级区间：定性、成因与伤害</h3>',
        '<p class="small">区间与回撤均为本工程用通达信上证综指 000001 盘中最高价、峰值后最低价复核的值；'
        '与本报告万得全A统计段的基准不同，不能逐值混用。点击每轮可展开。</p>',
    ]
    for i, r in enumerate(rounds, 1):
        out.append(
            f'<details class="conjdetail" id="crisis-round-{i}"><summary>{html.escape(r["name"])}｜'
            f'{html.escape(r["date"])}｜{html.escape(r["dd"])}</summary>'
            '<div class="basis">'
            f'<p><b>金融定性：</b>{html.escape(r["kind"])}</p>'
            f'<p><b>主要成因：</b>{html.escape(r["cause"])}</p>'
            f'<p><b>主要伤害：</b>{html.escape(r["harm"])}</p>'
            f'<p><b>本报告关联条目：</b>{html.escape(r["ids"])}。关系统计段是同一轮内的子样本，不是新增独立危机。</p>'
            f'<p><b>公开来源：</b>{r["src"]}。</p></div></details>')

    acute = [
        ("统一 01｜2001 年初高位调整", "牛市末段的急性统计段", "高估值与制度不确定性背景；没有独立公认事件名，不能以后来六月的政策倒填当日成因。", "以本表实测收益和回撤为准，不额外追加媒体伤害数字。"),
        ("统一 14｜2006 年牛市中段调整", "股改后上升趋势中的回撤", "未找到该统计段的独立公认危机命名。", "更像牛市内快速调整，不能升格成新一轮市场危机。"),
        ("统一 15｜2007 年 5·30", "牛市内急性政策冲击", "印花税率调整与高位获利盘共同作用。", "短期普跌和交易拥挤突出，但不等于二零零七年十月后的长期熊市。"),
        ("无统计编号｜2013 年 6 月钱荒", "第三轮长熊末端的银行间流动性子事件", "同业期限错配、监管去杠杆与流动性预期骤紧，货币利率冲击传导至股票。", "金融板块与宽基快速下跌，体现跨市场流动性传染。当前 45 个统计事件在 2012 年末至 2015 年中存在重算空白，因此本节补入但不新增编号、不改样本。"),
        ("统一 31｜2016 年 2 月", "熊市中的二次探底与资金面冲击", "此前讨论归因于降准预期落空、资金收紧与风险资产分流；公开材料主要覆盖窗口末端。", "属于第四轮后的余波，证据以机构观点和媒体复盘为主，不能写成已识别因果。"),
        ("统一 32｜2016 年春季", "信用与监管冲击下的调整", "信用违约、刚兑预期变化、监管收紧与增长表态共同压低风险偏好。", "更接近中级调整，不宜因触发统计阈值就命名为独立股灾。"),
        ("统一 36｜2019 年 5 月", "贸易摩擦反复的急性外生冲击", "谈判反复抬升风险溢价，此前修复行情中的获利盘放大波动。", "短期伤害明显，但未形成与 2018 年同等级的新增长熊。"),
        ("统一 37—38｜2020 年 2—3 月", "新冠疫情的外生急性危机", "国内疫情首先冲击盈利与交易预期，随后全球疫情、风险资产抛售与美元流动性紧张共同传导。", "恐慌下跌与流动性压力突出，但不宜把两个阶段的驱动完全等同。"),
        ("统一 39｜2021 年 2—3 月", "核心资产抱团瓦解的结构性危机", "实际利率上行、估值过高与拥挤持仓反转，引发机构重仓风格杀估值。", "核心资产与高估值赛道伤害大于上证，宽基本身不能完整反映。"),
        ("统一 44｜2024 年 10 月", "政策脉冲后的高位兑现", "九月末急涨后获利回吐、交易拥挤和杠杆约束共同造成高位分化。", "属于高波动调整；统计段收益甚至可以为正，真实伤害要看后续最低收益而非段内收益。"),
        ("统一 45｜2024 年 12 月", "小微盘结构性去杠杆", "退市新规临近、风险名单舆情、年末风格切换与前期涨幅过大共同作用。", "伤害集中于小微盘；此前公开复盘与该统计段起点较精确重合，但仍属事后归因。"),
        ("统一 46—47｜2025 年 3—4 月", "风险偏好收缩与对等关税黑色星期一", "统一 46 的起点早于关税落地，不能倒填成因；统一 47 才是事后认定的关税崩盘锚点。", "统一 47 出现大面积跌停并随后快速修复；两个条目相关但不等同，47 仍为外部锚点、不进主判据。"),
    ]
    out.append('<h3>丙、需要单独阅读的急性与结构性事件</h3>')
    out.append('<div class="scroll"><table class="mtable"><thead><tr><th>条目／事件</th><th>金融定性</th><th>主要成因</th><th>主要伤害与边界</th></tr></thead><tbody>')
    for row in acute:
        out.append('<tr>' + ''.join(f'<td>{html.escape(x)}</td>' for x in row) + '</tr>')
    out.append('</tbody></table></div>')
    out.append(
        '<p class="small">本节公开背景来源沿用此前核查材料；没有独立公认命名的统计段只保留“所属背景”。'
        '媒体与机构复盘属于非一手归因，需核实原文，不能与监管文件或同行评议因果识别等同。</p>')

    out.append('<h3>丁、47 个条目：统一编号、背景归属与工程实测伤害</h3>')
    out.append(
        '<div class="note">伤害数值直接读取本报告事件总表，不在本节重算。'
        '“段内累计”是急性统计标签段的累计收益，可能为正；“起点后二十日最低”才显示前瞻阈值所见的最深累计收益。'
        '两个外部锚点只有单日，段内收益就是锚点日收益。所有数值基准均为万得全A，单位为百分比。</div>')
    out.append('<div class="scroll tall"><table class="mtable"><thead><tr>'
               '<th>统一编号</th><th>工程原编号</th><th>开始日</th><th>结束日</th><th>来源</th>'
               '<th>金融背景归属（不是独立危机计数）</th><th>段内累计</th><th>段内最大回撤</th>'
               '<th>起点后二十日最低</th><th>是否进主判据</th></tr></thead><tbody>')
    for r in EVENT_ORDER:
        eid = r["event_id"]
        src = {"前段新增急性事件": "前段统计", "后段冻结统计事件": "后段统计",
               "外部金融定性危机": "外部锚点"}[r["event_source"]]
        vals = [
            EVENT_ID_TO_DISPLAY[eid], eid, r["onset"], r["end"], src,
            GROUP_TEXT[EVENT_GROUP[eid]][0], r["crisis_cum_pct"], r["crisis_max_dd_pct"],
            r["onset_future20_worst_pct"], "是" if r["in_judgement"] == "1" else "否",
        ]
        out.append('<tr>' + ''.join(f'<td>{html.escape(v)}</td>' for v in vals) + '</tr>')
    out.append('</tbody></table></div>')
    out.append(
        '<div class="warn"><b>为什么没有把 2012 年末至 2015 年中硬塞成新事件：</b>'
        '第五版预登记只向前补算至二零一二年底，后段十七段逐字保留；这三年半仍是统计标签重算空白。'
        '因此钱荒等重要事件可以在危机史中说明，但不能未经升版预登记就加入 45 个统计事件或改变判定。</div>')
    out.append('</section>')
    return "".join(out)


def early_acceptance_section():
    """Carry the sixth-version engineering evidence into the integrated report."""
    a16 = early_audit["a16"]
    a16ov = early_audit["a16_overlap"]
    b = early_audit["b"]
    bov = early_audit["b_overlap"]
    det = early_audit["b_determinism"]
    rows = [
        ("十六行业早期完整计算", f"{a16['rows']} 行，{a16['windows']} 个十日窗口；独立完整双跑逐字节一致"),
        ("十六行业同面板重叠验收", f"形状 {a16ov['compared_shape_dates']} 日、相邻图距离 {a16ov['compared_W_dates']} 日；最大绝对差 {a16ov['max_abs_diff']:.6f}"),
        ("行业相关点云重叠验收", f"一维／二维与零维各 {bov['xy_dates']} 日；最大绝对差 {max(bov['xy_max_abs_diff'], bov['h0_max_abs_diff']):.6f}；节点名单差异 {len(bov['node_list_mismatch_dates'])} 日"),
        ("固定二十四日独立复算", f"一维／二维最大绝对差 {det['xy_max_abs_diff']:.6f}；零维最大绝对差 {det['h0_max_abs_diff']:.6f}"),
        ("最小生成树交叉核对", f"与持续同调零维死亡值最大绝对差 {det['mst_vs_ripser_max_abs_diff']:.12f}，低于跨实现容差 0.000001"),
        ("早期行业资格与坐标", f"{b['eligible_days']} 个合格日，资格不足 {b['ineligible_days']} 日；逐日 {b['n_nodes_min']}—{b['n_nodes_max']} 个节点；十一期收盘价生成十期简单收益"),
        ("旧元数据勘误", f"旧清单曾误写为九个收益；实际恒为十期，费雪变换标准误 {b['fisher_z_standard_error']:.6f}；该勘误不改变任何既有拓扑数值"),
    ]
    body = "".join('<tr><th>' + html.escape(k) + '</th><td>' + html.escape(v) + '</td></tr>'
                   for k, v in rows)
    return (
        '<section class="card"><h2>三·补一·血缘、第六版早期补算的工程验收</h2>'
        '<div class="note">这一节保留第六版的计算证据，说明早期曲线不是展示层伪造或跨面板替代。'
        '它只证明计算、重叠衔接和确定性验收正确，<b>不证明任何金融推测成立</b>。</div>'
        '<table class="mtable"><thead><tr><th>验收项目</th><th>已验收实际读数</th></tr></thead><tbody>'
        + body + '</tbody></table>'
        '<div class="warn"><b>接缝预热与首次失败如实保留：</b>第六版首次重叠验收发现旧十六行业文件的九个形状预热日'
        '及一个额外距离预热日为空。追加修订只豁免这些由旧计算起点造成的空白；自旧首个有效日起，'
        '数值和空值掩码仍严格一致。第七版沿用该已验收衔接，不回填旧预热空白，也不宣称首次运行即通过。</div>'
        '</section>')


def build():
    mfiles = manifest["files"]
    for d in FILE_DESC:
        if PREFIX + d[0] not in mfiles:
            raise RuntimeError("文件清单缺失：" + d[0])

    payload_obj = dict(chart)
    payload_obj["integration"] = {
        "version": integration["version"],
        "validation": integration["validation"],
        "calendar": integration["calendar"],
        "output": integration["output"],
        "historical_judgement": "第五版 5 支持／2 矛盾／7 无法判定；第七版未重判",
    }
    payload_obj["overview"] = EVENT_ORDER
    payload_obj["events"] = sorted(chart["events"], key=lambda e: EVENT_ID_TO_DISPLAY[e["event_id"]])
    for _e in payload_obj["events"]:
        _e["line_coverage"] = event_coverage[_e["event_id"]]
    for _r in payload_obj["overview"]:
        _cov = event_coverage[_r["event_id"]]
        for _g in ("a16", "a27", "b"):
            _r[_g + "_window_summary_days"] = _cov[_g]
        if _r["event_source"] == "前段新增急性事件":
            if (_cov["a16"] == int(_r["window_len"])
                    and _cov["b"] == int(_r["window_len"]) and _cov["a27"] == 0):
                _r["coverage_note"] = (
                    "第六版真实补算已接入：十六行业与行业相关点云整窗组覆盖；"
                    "完整二十七行业仍未覆盖，不跨面板拼接")
            else:
                _r["coverage_note"] = "早期摘要覆盖与第七版验收不符；须逐行核查，不得解释为一般缺失"
        else:
            _r["coverage_note"] = ""
    _e126 = next(e for e in payload_obj["events"] if e["event_id"] == "126")
    _birth_blank = [r for r in _e126["rows"] if r["a16_h1_birth_mean"] == ""]
    assert len(_birth_blank) == 29
    assert all(r["a16_h1_count"] == "0" for r in _birth_blank), \
        "统一事件 26 的平均出生值空白必须全部能由零个一维环解释"
    payload_obj["metric_coverage"] = metric_coverage
    payload_obj["early_coverage_audit"] = {
        "front_a16_none_events": 0,
        "front_a16_full_window_events": 28,
        "front_a27_none_events": 28,
        "front_b_none_events": 0,
        "front_b_full_window_events": 28,
        "source": "第六版真实补算经第七版只读整合；未重判十四条推测",
        "front_within_coverage_unexplained_gap_rows": len(_front_unexplained_gaps),
        "event_26_original_126": {
            "window_rows": len(_e126["rows"]),
            "a16_group_covered_rows": event_coverage["126"]["a16"],
            "a27_group_covered_rows": event_coverage["126"]["a27"],
            "b_group_covered_rows": event_coverage["126"]["b"],
            "a16_h1_birth_structural_blank_rows": len(_birth_blank),
        },
        "actual_first_dates": {
            "a16_summary": metric_coverage["a16_h0_death_mean"]["first"],
            "a16_diagram_distance": metric_coverage["a16_W_t"]["first"],
            "a27_summary": metric_coverage["a27_h0_death_mean"]["first"],
            "a27_diagram_distance": metric_coverage["a27_W_t"]["first"],
            "b_summary": metric_coverage["b_h0_death_mean"]["first"]
                if "b_h0_death_mean" in metric_coverage
                else metric_coverage["b_xy_h0_death_mean"]["first"],
        },
    }
    payload_obj["event_id_lookup"] = EVENT_ID_TO_DISPLAY
    payload_obj["event_id_map"] = [
        {"display_id": EVENT_ID_TO_DISPLAY[r["event_id"]], "event_id": r["event_id"],
         "onset": r["onset"], "event_source": r["event_source"],
         "background": GROUP_TEXT[EVENT_GROUP[r["event_id"]]][0]}
        for r in EVENT_ORDER
    ]
    payload_obj["file_desc"] = [
        {"name": PREFIX + n, "zh": zh, "tag": tag, "note": note}
        for n, zh, tag, note in FILE_DESC
    ]
    manifest_min = {"files": mfiles, "file_desc": payload_obj["file_desc"],
                    "validation": manifest["validation"],
                    "sample": manifest["sample"]}
    payload_obj["manifest"] = manifest_min
    payload_json = json.dumps(payload_obj, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False).replace("</", "<\\/")

    assert sample["center_days"] == sample["crisis_days"] + sample["external_anchors"], \
        "不变式：中心日 = 危机日 + 外部锚点；事件总数卡片不得再复用 center_days"
    K = [
        ("标签日历", f"{sample['calendar_days']} 天"),
        ("统计事件", f"{sample['front_events']} 前段 + {sample['back_events']} 后段"),
        ("危机日", f"{sample['crisis_days']} 天"),
        ("事件条目", f"47 = {sample['front_events'] + sample['back_events']} 统计 + 2 锚点"),
        ("第五版主判据（冻结）", f"{sample['events_in_judgement']} 个事件"),
        ("日级窗口", f"{sample['daily_window_rows']:,} 行"),
        ("事件窗", f"{sample['event_window_rows']:,} 行"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><b>{v}</b><span>{k}</span></div>' for k, v in K)

    front_rows = []
    for r in front:
        front_rows.append([
            r["event_id"], r["onset"], r["end"], r["n_crisis_days"],
            r["onset_future20_worst_pct"] + "%", r["onset_worst_date"],
            r["crisis_cum_pct"] + "%", r["post20_cum_pct"] + "%",
            r["a16_summary_available_days"],
        ])

    diag_rows = [
        ["新增显著格", f"{gc['total']} 格（同时丢失 {gc['lost']} 格）",
         "第五版 490 格对第三版 151 格的净变化"],
        ["新增格所在面板", f"十六行业状态点云 {gc['A_a16']} 格／相关网络与二十七行业 {gc['B_or_a27']} 格",
         "全部集中在唯一有前段摘要的那条线"],
        ["新增格中尺度量与控制变量", f"{gc['scale_or_control_summary']} 格（{gc['scale_share']*100:.2f}%）",
         "平均相关、领先特征值占比、窗口波动、相邻持续图距离等"],
        ["危机组前段占比", f"{cr['front_share']*100:.2f}%（{cr['front_1999_2012']} / {cr['n']} 天）",
         "危机组样本大量来自一九九九至二零一二年"],
        ["常态基线前段占比", f"{nr['front_share']*100:.2f}%（{nr['front_1999_2012']} / {nr['n']} 天）",
         "两组年份构成相差约二十四个百分点"],
        ["常态基线样本量", f"第三版 {cmp['keypack_v0_3']['normal_n']} → 第五版 {cmp['keypack_v0_5']['normal_n']} 天",
         "更长且更异质的基线会收窄自助法散布，可在没有新信号时制造显著"],
        ["前段十六行业平均相关中位数", f"{era['front_2005_2012']['avg_pair_corr_median']:.4f}",
         f"后段为 {era['back_2013_2026']['avg_pair_corr_median']:.4f}，年代尺度差异明显"],
        ["前段十六行业领先特征值占比中位数", f"{era['front_2005_2012']['leading_eig_share_median']:.4f}",
         f"后段为 {era['back_2013_2026']['leading_eig_share_median']:.4f}"],
        ["前段十六行业窗口收益均方根中位数", f"{era['front_2005_2012']['window_rms_median']:.6f}",
         f"后段为 {era['back_2013_2026']['window_rms_median']:.6f}"],
    ]
    diag_html = "".join(
        "<tr><th>" + html.escape(a) + "</th><td>" + html.escape(b) +
        "</td><td>" + html.escape(c) + "</td></tr>" for a, b, c in diag_rows)

    verdict_counts = cmp["keypack_v0_5"]["conjecture_counts"]
    verdict_html = "".join(
        f'<div class="kpi"><b>{v}</b><span>{k}</span></div>'
        for k, v in verdict_counts.items())

    parts = []
    parts.append('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append('<title>第七版危机上下文整合报告</title>')
    parts.append('<style>' + CSS + '</style></head><body><div class="wrap">')
    parts.append(
        '<header><h1>第七版危机上下文整合报告</h1>'
        '<div class="sub">四十七个条目＝四十五个统计危机事件＋两个外部描述性锚点，统一编号 01—47，前后二十交易日全量逐格罗列。'
        '单文件离线、只读，无外部脚本或样式依赖；公开出处链接需联网打开，不影响本报告自身阅读。'
        '全部为样本内描述性对账。读表前建议先看「危机史、金融定性、成因与伤害」，再看十四条推测与两套点云解释。</div></header>')
    parts.append('<div class="kpis">' + kpi_html + '</div>')

    # ---- 一 ----
    parts.append('<section class="card"><h2>一、先把口径钉死（读表之前必看）</h2>')
    parts.append(
        '<div class="note"><b>本报告是什么：</b>这是第五版完整危机上下文与第六版早期真实补算的整合版，'
        '不是两份网页的首尾拼接。同一份报告保留四十七个事件、危机史、十四条推测及文献，'
        '并把第六版已验收的十六行业与行业相关点云早期摘要嵌入对应曲线。'
        '它用于样本内描述性对账，不是绩效回测、不是信息系数、不是精确率召回率曲线下面积。'
        '<b>第五版判定仅作冻结历史展示；第七版没有重判，也没有新增提前量、命中率、召回率、精确率或误报数值。</b></div>')
    parts.append('<table class="mtable"><thead><tr><th>口径项目</th><th>本报告采用的口径</th></tr></thead><tbody>'
                 '<tr><th>标签日历</th><td>六千四百八十三个交易日，自一九九九年十二月三十日至二零二六年十一月三日；'
                 '前段三千一百四十四天＋后段三千三百三十九天。</td></tr>'
                 '<tr><th>市场基准</th><td>全程单一真万得全A 指数日线，前段用原始收盘价，不反向递推、不缩放、不补零。</td></tr>'
                 '<tr><th>急性统计标签（用于分组）</th><td>沿用冻结定义：未来二十个交易日内，相对当日最低累计简单收益不高于负百分之十。'
                 '它只用于构造和筛选第二层急性统计事件，<b>不是危机开始参照日的定义</b>；'
                 '也不等于「正在下跌」或峰谷回撤百分之二十的制度区间。</td></tr>'
                 '<tr><th>统计事件与统一编号</th><td>四十五段：后段十七段冻结统计事件＋前段二十八段按同一冻结定义新算的急性事件。'
                 '再加两个外部锚点共四十七条，按日期统一编号零一至四十七；共七百三十七个危机日。</td></tr>'
                 '<tr><th>进入主判据</th><td>四十二个事件：前段二十八段＋后段十四段。统一事件二十九因起点左截断整段不可判定；'
                 '统一事件三十一与四十五为第三版时用户指定排除；统一四十三与四十七两个外部锚点一律不进判定。</td></tr>'
                 '<tr><th>外部锚点</th><td>二零二四年二月五日小微盘流动性危机、二零二五年四月七日对等关税黑色星期一，'
                 '统一编号四十三与四十七（工程原编号十八与十九），各为单日锚点，仅作描述性对照。</td></tr>'
                 '<tr><th>二十日的含义</th><td>二十个<b>标签交易日</b>。万得序列在后段另有二十个额外交易日，'
                 '行业面板在这些日子缺失，因此同时披露「相邻标签交易日收益」与「相邻万得交易日收益」，'
                 '并列出每一步跨过的额外交易日数。</td></tr>'
                 '<tr><th>早期摘要的实际覆盖起点</th><td>第六版真实补算接入后，十六行业十日点云形状摘要首日为二零零零年一月十七日，'
                 '相邻日持续图距离首日为二零零零年一月十八日；行业相关点云摘要首日为二零零零年二月二十八日。'
                 '二十七行业形状摘要首日仍为二零一四年三月七日，相邻日持续图距离首日为二零一四年三月十日。'
                 '二零零五年一月四日起的十六行业同面板冻结段仍保留旧计算起点的预热空白，不用新值倒填。</td></tr>'
                 '<tr><th>前段整合与缺失处理</th><td>前段三千一百四十四行取第六版已验收描述性宽表，后段三千三百三十九行逐字段保留第五版。'
                 '二十八个早期事件的十六行业与行业相关点云均为整窗组覆盖，覆盖期内待核空值为零；'
                 '完整二十七行业早期仍未补算并全部留空。市场宽度自二零一一年一月四日起才有；市盈率与融资余额本地不可得。'
                 '<b>未覆盖与结构性无定义保持空值，不补零、不回填；真实计算的零个环或零个空腔保留为零。</b></td></tr>'
                 '<tr><th>早期较少行业与较少节点口径</th><td>十六行业和二十七行业始终分线，不把十六行业数值写入二十七行业字段。'
                 '早期行业相关点云使用事后固定的申万二零一四版二级行业名单，每日六十一个至七十四个合格节点，'
                 '只用于样本内历史描述，不冒充各早期交易日当时实时可知的名单，也不改第五版主判据。</td></tr>'
                 '<tr><th>前段牛熊状态</th><td>使用预登记的降级二百五十日移动平均规则；后段沿用冻结规则。'
                 '两者定义不同，同一「熊市／模糊」组里混了两套状态定义，已在第八节列为口径限制。</td></tr>'
                 '<tr><th>后段状态列</th><td>后段状态列按冻结要求逐值照抄，其中保留一个历史遗留取值，'
                 '中文显示为「未定义（旧查询终点之后，第五版已补齐行情）」；行情与标签已补齐，该状态列未改。</td></tr>'
                 '</tbody></table>')
    parts.append(
        '<div class="note"><b>推测检验的时序口径（二零二六年十一月十一日用户确认）：</b>'
        '本报告的目的在于事后检验十四条推测。七轮市场级区间以<b>事后认定的峰值日作为危机开始参照日</b>，'
        '谷底日用于描述区间终点与严重程度；两段外部公认危机以事后认定的崩盘日作为该急性事件的开始参照日。'
        '持续摘要相对这些日期的提前或滞后，<b>可以用于样本内描述性时序对账与推测检验</b>。</div>'
        '<div class="note"><b>与急性统计标签的区别：</b>事后峰值日或崩盘日回答「围绕哪一天检验提前或滞后」；'
        '冻结的未来二十日急性阈值回答「哪些日期和事件进入第二层统计分组」。'
        '二者是不同用途的两套口径，急性统计标签段的第一天不因此改称为危机开始参照日。'
        '这里的「提前量」是事后研究口径，不表示当时已经知道危机将要开始，也不直接等于实时预警能力；'
        '若另行评价实时预警绩效，须另设当时可知的危机开始定义并独立计算。'
        '第一层制度区间与第二层急性事件分别报告，不合并成一组命中统计。</div>')
    parts.append('</section>')

    # ---- 先行阅读：危机史、统一编号与金融定性（只读展示） ----
    parts.append(crisis_background_section())

    # ---- 先行阅读：十四条推测、金融依据与参考文献（由第八节后移至此） ----
    parts.append(conjecture_section())

    # ---- 一·补 / 一·补二 / 一·补三：当前两套点云与摘要的工程口径 ----
    parts.append(CONCEPT)

    # ---- 二 ----
    parts.append('<section class="card"><h2>二、八个数据文件（与本报告同目录，可直接下载）</h2>')
    parts.append('<p class="small">为与磁盘产物对应，文件名保留工程标识，鼠标悬停链接可查看原文件名；'
                 '报告正文与表头一律使用中文全称。</p>')
    parts.append('<div class="scroll" id="fileTable"></div></section>')

    # ---- 三 ----
    parts.append('<section class="card"><h2>三、四十七个事件一览（事件级去重视图）</h2>')
    parts.append('<p class="small">点击表头排序；数值列中红色为正、绿色为负（中国市场价格习惯）。'
                 '「是否进入主判据」为否的行以浅灰显示，外部锚点行以浅橙显示。</p>')
    parts.append('<div class="scroll tall" id="ovTable"></div></section>')

    # ---- 三·补 ----
    parts.append('<section class="card"><h2>三·补、前段二十八个急性事件逐行（统一编号 01—28；工程原编号 101—128）</h2>')
    parts.append('<p class="small">这些事件是第五版按冻结定义在二零一二年底之前新识别的急性危机，'
                 '用户裁决将它们纳入主判据。它们在旧版工程里完全缺席，原因不是行情缺失，'
                 '而是旧标签日历自二零一二年十二月三十一日起。</p>')
    parts.append('<div class="scroll tall" id="frontTable"></div>')
    parts.append('<div class="ok"><b>第六版早期真实补算已完整接入：</b>'
                 '统一零一至二十八的十六行业状态点云与行业相关点云均为整窗组覆盖；'
                 '完整二十七行业状态点云仍全部未覆盖。这里不是把十六行业或行业相关点云冒充二十七行业，'
                 '也不是把两份报告简单拼接，而是以同一六十七列结构按日期整合。'
                 '逐项扫描前段二十八事件的十八项展示摘要，剔除未覆盖与零个一维环导致的结构性无定义后，'
                 '覆盖期内待核空值为零行。表内三列覆盖天数按整个事件窗逐日统计，'
                 '“组覆盖”指当天至少一项该组指标有值，不表示每项指标都有数学定义。</div>')
    parts.append('<div class="warn"><b>早期行业相关点云的历史分类限制：</b>'
                 '第六版使用事后固定的申万二零一四版二级行业名单，每日六十一个至七十四个合格节点。'
                 '这能真实补出当前算法下的历史描述曲线，但不能冒充当时实时可知的行业分类；'
                 '逐日节点数与资格审计仍以第六版产物为准。第七版只整合，不重新计算持续同调。</div>')
    parts.append('<p class="small">前段共二十八事件、四百六十七个危机日；'
                 '两条已补线均为二十八比二十八整窗覆盖。'
                 f'前段危机段内十六行业相邻图距离有效 {obs["front_with_summary"]} 天；'
                 '形状摘要与相邻距离预热规则不同，不能把这两个有效天数混为一谈。</p>')
    parts.append('</section>')

    # ---- 三·补一·血缘：第六版工程验收证据 ----
    parts.append(early_acceptance_section())

    # ---- 三·补二 ----
    ext_rows = rd("external_crises.csv")
    src_links = []
    for r in ext_rows:
        links = []
        for i, key in enumerate(("source_1", "source_2", "source_3"), start=1):
            url = r.get(key, "")
            if url:
                links.append('<a href="' + html.escape(url, quote=True) +
                             '" target="_blank" rel="noopener" title="原出处链接">' +
                             f'统一事件 {EVENT_ID_TO_DISPLAY[r["event_id"]]} 出处{["一", "二", "三"][i-1]}</a>')
        src_links.append(" · ".join(links))
    parts.append('<section class="card"><h2>三·补二、两次金融定性／实证研究公认的危机（仅描述性）</h2>')
    parts.append('<div class="scroll" id="extTable"></div>')
    parts.append('<p class="small">公开出处：' + "；".join(src_links) +
                 '。证据等级为整理者依据来源类型所作的标注，不代表同行评议结论。</p>')
    parts.append(
        '<div class="leak"><b>为什么冻结标签漏判：</b>二零二四年二月五日与二零二五年四月七日的'
        '「锚点起未来二十交易日最低累计收益」分别为正百分之四点三九八三与正百分之一点零零零四——'
        '崩盘当日恰好就是未来二十日的最低点，随后快速反弹。'
        '前瞻阈值因此<b>系统性漏掉「单日崩盘＋快速反弹」型危机</b>。'
        '这两次锚点不写入任何掩码、标签、判定、显著性计数或事件级去重；'
        '它们是事后认定的急性事件开始参照日，可用于推测检验中的提前／滞后对账。'
        '这种事后提前量不代表实时预警绩效，本版也未据此计算命中率等数值。</div>')
    parts.append('</section>')

    # ---- 三·补三 ----
    parts.append('<section class="card"><h2>三·补三、两层标签与第一层七轮精确峰谷（事后口径）</h2>')
    parts.append('<p>第一层是七个市场级制度区间，按上证综指盘中峰谷划定，'
                 '端点「暂定」采用通达信算出的精确峰谷日。按二零二六年十一月十一日用户确认的推测检验口径，'
                 '<b>峰值日是事后危机开始参照日</b>，谷底日用于描述区间终点与严重程度。'
                 '第二层是急性事件，即本报告四十五段统计危机与两段外部锚点。'
                 '两层分别对照，不合并成一组命中统计。</p>')
    parts.append('<div class="scroll" id="tierTable"></div>')
    parts.append('<div class="warn">表中「区间内第二层急性事件天数」只是描述性重叠计数，'
                 '不直接称为实时检出或召回。峰值日可作为事后推测检验的开始参照；'
                 '由此得到的提前或滞后只用于样本内时序核对。</div>')
    parts.append('</section>')

    # ---- 四 ----
    parts.append('<section class="card"><h2>四、相对日剖面：负二十至正二十的平均形态</h2>')
    parts.append('<div class="ctrl"><label>对齐锚点</label><select id="profAnchor"></select>'
                 '<label>观察指标</label><select id="profMetric"></select></div>')
    parts.append('<div class="chartbox" id="profChart"></div>')
    parts.append('<p class="small" id="profNote"></p>')
    parts.append('<div class="legend"><span><i style="background:#2b5fcc"></i>均值</span>'
                 '<span><i style="background:#a9c0ea"></i>第二十五至第七十五百分位</span>'
                 '<span><i style="background:#d93026"></i>锚点日（相对交易日零）</span></div>')
    parts.append('<div class="note">剖面是把大量互相重叠的窗口按相对日作算术平均，'
                 '属于<b>逐格读数</b>，不是显著性检验。前段缺少摘要的日子自动不进入该指标的均值，'
                 '因此不同指标的样本数会不同。</div>')
    parts.append('</section>')

    # ---- 五 ----
    parts.append('<section class="card"><h2>五、事件窗逐日查看器</h2>')
    parts.append('<div class="ctrl"><label>选择事件</label><select id="evSelect"></select>'
                 '<label>曲线指标</label><select id="evMetric"></select></div>')
    parts.append('<div class="note"><b>早期状态点云怎么选：</b>二十七行业未覆盖而十六行业有摘要时，'
                 '选择任一二十七行业指标会自动改用对应的十六行业同名摘要，并在下方标明「较少行业面板替代展示」。'
                 '这不会把十六行业数据写进二十七行业字段，也不会改变覆盖天数或主判据。</div>')
    parts.append('<p class="small" id="evInfo"></p>')
    parts.append('<div class="chartbox" id="evChart"></div>')
    parts.append('<div class="legend"><span><i style="background:#fff1ef"></i>危机段（浅红底）</span>'
                 '<span><i style="background:#d93026"></i>事件起点（相对交易日零）</span></div>')
    parts.append('<div class="note">环或空腔的<b>数量为零</b>表示当天已经完成持续同调计算、'
                 '没有发现相应维数的有限持续区间，<b>不是数据缺失</b>。'
                 '一维环数量为零时，一维环平均出生值没有定义，单列为“结构性无定义”。'
                 '指标实际覆盖期之外的空白单列为“未覆盖”；只有覆盖期之内、又不能由零个环解释的空白，'
                 '才列为“覆盖期内待核空值”。<b>全窗没有有效值时不再绘制空白坐标轴</b>，'
                 '以免把未覆盖误读成数值为零。下方逐日明细保留原始空值，不补零、不回填。</div>')
    parts.append('<h3>逐日明细（当前事件窗）</h3>')
    parts.append('<div class="scroll" id="evDetail"></div>')
    parts.append('</section>')

    # ---- 六 ----
    parts.append('<section class="card"><h2>六、七百三十九个中心日：前后二十日结果表</h2>')
    parts.append('<div class="ctrl"><label>按事件筛选</label><select id="ctEvent"></select>'
                 '<span class="small" id="ctCount"></span></div>')
    parts.append('<div class="scroll tall" id="ctTable"></div>')
    parts.append('<p class="small">七百三十七统计危机日＋两个外部锚点。'
                 '判定层网格实际使用的危机组日级样本为六百七十八天，差额逐项可核：'
                 '统一事件二十九（工程原编号一）起点左截断四十九天、统一事件三十一与四十五（工程原编号三与十六）共七天（用户指定排除）、'
                 '统一事件零一（工程原编号一百零一）有三天因状态预热未定义，合计五十九天。'
                 '本表按日历完整罗列，不按判定样本筛选。</p>')
    parts.append('</section>')

    # ---- 七 ----
    parts.append('<section class="card"><h2>七、一百四十一行事件分段统计</h2>')
    parts.append('<p class="small">四十七个事件乘三个阶段：危机前二十日、危机段、危机后二十日。</p>')
    parts.append('<div class="scroll tall" id="phTable"></div></section>')

    # ---- 八 ----
    parts.append('<section class="card"><h2>八、第五版冻结历史判定与显著格激增诊断（第七版未重判）</h2>')
    parts.append('<div class="warn"><b>版本边界：</b>本节所有判定、显著格与年代构成诊断均原样读取第五版冻结产物。'
                 '第七版只增加第六版早期描述性曲线，并重新汇总展示表格；没有把这些新摘要送入判定引擎。'
                 '因此本节不能被解读为第七版的新检验结果，五条支持、两条矛盾、七条无法判定也没有被重新评分。</div>')
    parts.append('<h3>十四条推测的逐条历史结论</h3>')
    parts.append('<div class="scroll" id="ledgerTable"></div>')
    parts.append('<div class="kpis">' + verdict_html + '</div>')
    parts.append(
        '<p>主判据甲与乙<b>均为「无法判定（含数据不足）」</b>；'
        f'八千三百四十格网格中显著格 {cmp["sig_cells"]["v0_3"]} → '
        f'<b>{cmp["sig_cells"]["v0_5"]}</b>，主状态显著格 '
        f'{cmp["sig_main_state"]["v0_3"]} → <b>{cmp["sig_main_state"]["v0_5"]}</b>。</p>')
    parts.append('<h3>显著格激增的来源诊断</h3>')
    parts.append('<table class="mtable"><thead><tr><th>诊断项</th><th>读数</th><th>含义</th></tr>'
                 '</thead><tbody>' + diag_html + '</tbody></table>')
    parts.append('<div class="warn"><b>三个口径限制叠加：</b>'
                 '① 前段牛熊用预登记降级规则、后段用冻结规则，同一状态组里混了两套定义；'
                 '② 十六行业状态点云的尺度回归因样本扩大而重估；'
                 '③ 前段宽度、市盈率与融资余额不足，牛熊规则降级并全格披露。'
                 '这些都会让「显著」变得更容易，<b>不能当作拓扑信号</b>。</div>')
    parts.append('<div class="ok"><b>可以说的：</b>在「全程单一真万得全A、纳入二十八个前段急性事件、'
                 '第一层用精确峰谷日」这一新样本口径下，八千三百四十格出现四百九十个显著格，'
                 '但两条线的主判据仍均未检出；十四条推测为五条支持、两条矛盾、七条无法判定。'
                 '<b>不可以说的：</b>「持续同调对 A 股危机预警有效」或「无效」——两者都是被禁止的全称外推。'
                 '本诊断是事后描述性复核，不重跑自助法、不改主口径、不按结果反选。</div>')
    parts.append('<div class="note">第五版与第三版、第四版<b>不可逐格比较</b>：'
                 '样本、状态定义、常态基线、尺度回归都变了。旧结论（五条支持／零条矛盾／九条无法判定）'
                 '原样保留为历史版本，不因升版抹掉，也不把这次变化写成对旧结论的推翻。</div>')
    parts.append('</section>')

    # ---- 九 ----
    parts.append('<section class="card"><h2>九、把数字念出来（描述性观察，不是结论）</h2>')
    parts.append('<div class="boundary">'
                 f'<p><b>一、急性统计标签使用未来收益，不是危机开始参照日，也不是「正在下跌」。</b>'
                 f'{obs["n_stat"]} 个统计事件里有 <b>{obs["crisis_up"]}</b> 个危机段累计收益为正，'
                 '因为冻结标签看的是未来二十日的最低累计收益。'
                 '所以危机段里价格上涨完全可能，不要把这段当成已实现跌幅；'
                 '该标签只负责第二层分组，开始参照日仍按上述事后峰谷或崩盘日口径确定。</p>'
                 f'<p><b>二、相邻两日持续图威尔斯特拉斯距离：危机段通常不是峰值所在。</b>'
                 f'危机段均值高于前二十日的事件有 {obs["w_crisis_gt_pre"]} 个，'
                 f'但后二十日均值又高于危机段的有 {obs["w_post_gt_crisis"]} 个、'
                 f'高于前二十日的有 {obs["w_post_gt_pre"]} 个；'
                 f'整窗峰值 {obs["peak_in_post"]} 个落在后二十日、'
                 f'{obs["peak_in_pre"]} 个落在前二十日、仅 {obs["peak_in_crisis"]} 个落在危机段内。'
                 '「危机中尺度摘要全维同步跳升并见顶」的形态在这张表里看不到；'
                 '该距离更像是滞后抬升。<b>以上全部是逐格读数，不是显著性检验结果。</b></p>'
                 f'<p><b>三、后二十日多为下跌，但不是全部。</b>'
                 f'{obs["post_down"]}/{obs["n_stat"]} 个事件后二十日累计收益为负；'
                 f'等事件权重的算术平均：前二十日 {pct_s(obs["mean_pre"])}、'
                 f'危机段 {pct_s(obs["mean_crisis"])}、后二十日 {pct_s(obs["mean_post"])}'
                 '（未加权、未检验）。</p>'
                 f'<p><b>四、相关网络二维空腔数量方向混合。</b>'
                 f'危机段均值高于前二十日的只有 {obs["h2_crisis_gt_pre"]}/{obs["n_stat"]} 个事件，'
                 '不存在统一的「危机时空腔数量上升」形态；'
                 '第六版前段摘要现已接入，但早期节点数较少且使用事后固定分类，'
                 '跨年代比较必须同时披露节点构成，不能把数值变化直接解释为纯拓扑效应。</p>'
                 f'<p><b>五、前段事件占了本次新增样本的大头。</b>'
                 f'前段 {len(front)} 个事件贡献 {obs["front_crisis_days"]} 个危机日，'
                 f'后段冻结 {len(back)} 个事件贡献 {obs["back_crisis_days"]} 个危机日。'
                 '这正是第八节「年代构成效应」的样本基础。</p>'
                 '<p class="warn">以上是把表格数字念出来，属于样本内描述。'
                 '<b>不是检验结果，不是绩效，不构成对持续同调有效或无效的任何推断。</b>'
                 '七百三十九个日级窗口互相重叠（长事件贡献几十个窗口），不可当成独立样本计数。</p>'
                 '</div></section>')

    # ---- 十 ----
    parts.append('<section class="card"><h2>十、数据字典（中文全称在前，工程原字段名仅作悬停对照）</h2>')
    parts.append('<p class="small">把鼠标移到任意表头上，可看到该列在工程数据文件里的原字段名；'
                 '下方字典同时列出中文全称与原字段名，便于和外部数据文件核对。'
                 '正文与表头一律不出现英文缩写或英文代号。</p>')
    parts.append('<div id="dictBox"></div></section>')

    # ---- 十一 ----
    parts.append('<section class="card"><h2>十一、边界（继续守住）</h2><ul>')
    boundaries = [
        "只读整合：第七版未重算持续同调、未改任何冻结标签、掩码、判定或规格；第五版与第六版旧产物一字未动。",
        "前段三千一百四十四行取第六版已验收摘要，后段三千三百三十九行逐字段保留第五版；前段标签、状态和事件编号均不变。",
        "早期行业相关点云采用事后固定的申万二零一四版二级行业名单，只用于样本内历史描述；完整二十七行业早期仍留空，不跨面板冒充。",
        "第五版五条支持、两条矛盾、七条无法判定只作冻结历史展示；第七版没有运行显著性检验或十四条推测重判。",
        "第一道闸门仍暂停，须先与用户讨论设计再执行；二零二五年最终测试集封存未读取、未评分；第二道闸门未启动；原文波动率择时指标的正式绩效未运行。",
        "本报告没有绩效、信息系数、夏普比率、精确率召回率曲线下面积、仓位或阈值反选；本版补充危机史并统一展示编号，未新增命中率、提前量、召回率、精确率或误报数值。", 
        "按二零二六年十一月十一日用户确认的推测检验口径，事后认定的危机开始日可用于样本内提前／滞后对账；这种事后提前量不代表实时预警绩效。",
        "两层标签分别报告，不合并成一组命中统计；第五版与第三／第四版不可逐格比较。",
        "两个外部锚点不写入掩码或标签、不重算持续同调、不进判定／显著性／事件级去重。",
        "前段未覆盖值一律记空值，不补零、不回填；未覆盖、结构性无定义与覆盖期内待核空值分别披露；宽度、市盈率与融资余额的不足已全格披露。", 
        "全部为样本内描述性对账，不得外推为「持续同调对 A 股危机预警有效」或「无效」。",
    ]
    parts.append("".join("<li>" + html.escape(x) + "</li>" for x in boundaries))
    parts.append('</ul><div class="leak">本版第一层区间端点为「暂定」口径；'
                 '若后续要改成用户原文的年月区间，必须另升版预登记，'
                 '绝不可按已经看到的结果反选口径。</div></section>')

    _t = manifest["generated_at"]
    _zh_time = (f"{_t[0:4]} 年 {int(_t[5:7])} 月 {int(_t[8:10])} 日 "
                f"{_t[11:19]}")
    parts.append('<footer>第七版危机上下文整合报告 · 生成于 ' + _zh_time +
                 ' · 第五版判定数字来自冻结产物；第七版仅更新描述性汇总，不重算持续同调、显著性或推测判定。</footer>')
    parts.append('</div>')
    parts.append('<script id="payload" type="application/json">' + payload_json + '</script>')
    parts.append('<script>' + JS + '</script>')
    parts.append('</body></html>')

    REPORT.write_text("".join(parts), encoding="utf-8")
    print(json.dumps({
        "report": str(REPORT), "bytes": REPORT.stat().st_size,
        "events": len(ov), "centers": len(centers),
        "validation_all_true": all(manifest["validation"].values()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
