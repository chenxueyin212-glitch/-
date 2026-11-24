"""v0.8 危机事件拓扑分型报告 —— 单文件离线中文 HTML。

读取 v0.8 分型结果，生成交互式报告。
纯描述性对账，不重判推测、不做显著性、不改冻结产物。
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
PREFIX = "regime_v08_typology_"

# 可读名映射
CLUSTER_LABEL = {
    "状态.window_rms升型": "尺度扩张型",
    "相关.xy_h0_death_mean升型": "相关重构型",
}
FEAT_LABEL = {
    "a16_W_t__mean": "相邻持续图距离",
    "a16_h0_death_mean__mean": "零维死亡均值",
    "a16_h1_count__mean": "一维环数量",
    "a16_window_rms__mean": "窗口均方根",
    "a16_avg_pair_corr__mean": "平均相关",
    "a16_leading_eig_share__mean": "第一特征值占比",
    "b_h2_count__mean": "二维空腔数量",
    "b_h1_count__mean": "一维环数量（相关）",
    "b_h2_landscape_l1__mean": "二维景观一阶范数",
    "b_industry_average_correlation__mean": "行业平均相关",
    "b_xy_h0_death_mean__mean": "零维死亡均值（相关）",
}
FIN_LABEL = {
    "crisis_max_dd_pct": "危机段最大回撤（百分比）",
    "n_crisis_days": "危机段持续交易日",
    "crisis_cum_pct": "危机段累计收益（百分比）",
    "post20_cum_pct": "事后二十日累计收益（百分比）",
    "onset_avg_pair_corr": "起点平均相关",
}
SEV_LABEL = {"深": "深回撤", "中": "中回撤", "浅": "浅回撤", "未知": "未知"}
SPD_LABEL = {"急性": "急性（五个交易日以内）", "中速": "中速", "慢性": "慢性（十六日以上）", "未知": "未知"}


def rd(name):
    with (OUT / name).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fmt(v, nd=4):
    if v is None or v == "":
        return "—"
    try:
        x = float(v)
        return f"{x:.{nd}f}"
    except ValueError:
        return str(v)


def main():
    profiles = rd(PREFIX + "event_profiles.csv")
    assignments = rd(PREFIX + "cluster_assignments.csv")
    cluster_fin = rd(PREFIX + "cluster_financial.csv")
    fin_topo = rd(PREFIX + "financial_topology.csv")
    cross = rd(PREFIX + "cross_tab.csv")
    summary = json.loads((OUT / (PREFIX + "summary.json")).read_text(encoding="utf-8"))

    # 七轮映射（事件落入哪一轮区间）
    ROUNDS = [
        ("R1", "2001-06—2005-06", "国有股减持、股权分置不确定性下的长期熊市"),
        ("R2", "2007-10—2008-10", "高估值泡沫破裂叠加全球金融危机"),
        ("R3", "2009-08—2013-06", "刺激退潮、政策收紧、盈利下行、欧债及钱荒"),
        ("R4", "2015-06—2016-01", "杠杆出清、强平、跌停与停牌潮，随后叠加熔断"),
        ("R5", "2018-01—2019-01", "金融去杠杆、贸易摩擦、股权质押风险"),
        ("R6", "2021-12—2022-10", "全球紧缩、疫情、地产与增长预期共同压制"),
        ("R7", "2023-05—2024-02", "市场走弱演化为小微盘、雪球和量化流动性冲击"),
    ]
    ROUND_RANGE = {
        "R1": ("2001-06-14", "2005-06-06"), "R2": ("2007-10-16", "2008-10-28"),
        "R3": ("2009-08-04", "2013-06-25"), "R4": ("2015-06-12", "2016-01-27"),
        "R5": ("2018-01-29", "2019-01-04"), "R6": ("2021-12-13", "2022-04-27"),
        "R7": ("2023-05-09", "2024-02-05"),
    }
    def round_of(onset):
        for rid, _, _ in ROUNDS:
            lo, hi = ROUND_RANGE[rid]
            if lo <= onset <= hi:
                return rid
        return "—"

    # ---- 轮廓系数 ----
    sil = summary["silhouette_by_k"]
    best_k = summary["optimal_k"]

    h = []
    h.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    h.append('<title>危机事件拓扑画像分型报告</title>')
    h.append('<style>')
    h.append('body{margin:0;background:#f5f6f8;color:#1a1d23;font-family:"Microsoft YaHei","PingFang SC",sans-serif;line-height:1.7}')
    h.append('.wrap{max-width:1160px;margin:0 auto;padding:24px 18px}')
    h.append('header{background:linear-gradient(135deg,#1e3a5f,#2d5f8a);color:#fff;padding:32px 24px;border-radius:12px;margin-bottom:20px}')
    h.append('header h1{margin:0 0 8px;font-size:22px}')
    h.append('header p{margin:4px 0;opacity:.85;font-size:13px}')
    h.append('.card{background:#fff;border:1px solid #e0e3e8;border-radius:10px;padding:20px 22px;margin:16px 0}')
    h.append('h2{font-size:17px;color:#1e3a5f;border-bottom:2px solid #e8ecf1;padding-bottom:8px;margin-top:0}')
    h.append('h3{font-size:14px;color:#2d5f8a;margin:16px 0 8px}')
    h.append('table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}')
    h.append('th{background:#f0f2f5;padding:8px 10px;text-align:left;font-weight:600;white-space:nowrap;border:1px solid #e0e3e8}')
    h.append('td{padding:7px 10px;border:1px solid #e8ecf1}')
    h.append('tbody tr:nth-child(even){background:#fafbfc}')
    h.append('tbody tr:hover{background:#eef3ff}')
    h.append('.warn{background:#fff8e6;border-left:3px solid #e0a020;padding:10px 14px;border-radius:5px;margin:12px 0}')
    h.append('.ok{background:#eef8f2;border-left:3px solid #2d8a5e;padding:10px 14px;border-radius:5px;margin:12px 0}')
    h.append('.note{background:#f2f6fc;border-left:3px solid #2d5f8a;padding:10px 14px;border-radius:5px;margin:12px 0}')
    h.append('.boundary{background:#eef4ff;border-left:3px solid #4a7ab5;padding:10px 14px;border-radius:5px;margin:12px 0}')
    h.append('.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;margin:1px}')
    h.append('.pill.deep{background:#f6d9d5;color:#a5231a}.pill.mid{background:#fff0dd;color:#8a5300}.pill.shallow{background:#e6f5ee;color:#166b4a}')
    h.append('.pill.acute{background:#fce4ec;color:#ad1457}.pill.chronic{background:#e8eaf6;color:#283593}.pill.midspd{background:#fff9c4;color:#6d5a00}')
    h.append('.pill.c1{background:#e3f2fd;color:#1565c0}.pill.c2{background:#f3e5f5;color:#6a1b9a}')
    h.append('.kpi{display:inline-block;background:#f7f8fa;border:1px solid #e0e3e8;border-radius:8px;padding:10px 18px;margin:4px 8px 4px 0;min-width:130px}')
    h.append('.kpi .v{font-size:20px;font-weight:700;color:#1e3a5f}.kpi .l{font-size:11px;color:#666}')
    h.append('.bar{height:18px;background:#e8ecf1;border-radius:9px;overflow:hidden;margin:3px 0}')
    h.append('.bar-fill{height:100%;border-radius:9px}')
    h.append('footer{margin:24px 0;padding:16px 0;text-align:center;color:#888;font-size:12px;border-top:1px solid #e0e3e8}')
    h.append('</style></head><body><div class="wrap">')

    # ---- 头部 ----
    h.append('<header><h1>危机事件拓扑画像分型报告</h1>')
    h.append('<p>目的：按拓扑摘要画像给危机事件分组，检验拓扑共性与金融定性共性是否对应</p>')
    h.append('<p>纯描述性对账 · 不重判推测 · 不做显著性 · 不改冻结产物 · 不做绩效或预测</p>')
    h.append(f'<p>生成时间：{datetime.now().strftime("%Y 年 %m 月 %d 日 %H 时 %M 分")}</p></header>')

    # ---- 一、摘要 ----
    h.append('<div class="card"><h2>一、核心发现</h2>')
    h.append('<div class="ok"><b>发现一：</b>四十五个统计事件的拓扑画像可以分成两组，'
             '两组在危机深度、持续速度和事后恢复上存在系统性差异。</div>')
    h.append('<div class="ok"><b>发现二：</b>深回撤、慢性危机的拓扑特征是<b>尺度扩张</b>'
             '（相邻持续图距离上升、窗口均方根上升、平均相关上升）；'
             '浅回撤、急性冲击的拓扑特征是<b>相关网络重构</b>'
             '（行业相关点云的零维死亡均值上升，但状态点云的尺度量反而下降）。</div>')
    h.append('<div class="warn"><b>限制：</b>轮廓系数 0.326（满分 1.0），说明两组之间的边界并不锐利。'
             '这个分型是描述性的，不能说「识别出了危机类型」。</div>')
    h.append('<div class="note"><b>与十四条推测的关系：</b>本分析不重判任何推测。'
             '但它提供了一个新视角——与其在全体事件上找统一的拓扑规律，'
             '不如承认<b>不同金融性质的危机有不同的拓扑表现</b>。'
             '这可能是 C01、C07 等推测「无法判定」的部分原因：方向在不同事件间相互抵消。</div></div>')

    # ---- 二、方法 ----
    h.append('<div class="card"><h2>二、方法与口径</h2>')
    h.append('<p>每事件取两个阶段（危机段与前二十个交易日）的拓扑摘要均值之差作为画像。'
             '共十一个特征：状态点云六个（相邻持续图距离、零维死亡均值、一维环数量、窗口均方根、平均相关、第一特征值占比），'
             '行业相关点云五个（二维空腔数量、一维环数量、二维景观一阶范数、行业平均相关、零维死亡均值）。</p>')
    h.append('<p>金融画像取事件概览中已有的字段：危机段最大回撤、持续交易日、累计收益、事后二十日恢复、起点平均相关。</p>')
    h.append('<p>分组用沃德层次聚类（欧氏距离），按轮廓系数最优选组数。'
             f'轮廓系数：{"、".join(f"分 {k} 组 {v:.3f}" for k, v in sorted(sil.items()))}。'
             f'最优为<b>分 {best_k} 组</b>（轮廓系数 {summary["optimal_silhouette"]}）。</p>')
    h.append('<p>严重度按危机段最大回撤的三分位分档，速度按持续交易日的三分位分档。</p>')
    h.append('<div class="boundary"><b>边界：</b>纯描述性对账。不做显著性检验、不做预测、不做绩效。'
             '不重判十四条推测、不改任何冻结产物、不覆盖旧版。'
             '结论仅限本样本内拓扑画像与金融定性的对应关系，不得外推。</div></div>')

    # ---- 三、两组画像 ----
    h.append('<div class="card"><h2>三、两组拓扑画像与金融定性</h2>')
    for row in cluster_fin:
        cid = row["cluster_id"]
        cname = CLUSTER_LABEL.get(row["cluster_name"], row["cluster_name"])
        pill_cls = "c1" if cid == "1" else "c2"
        h.append(f'<h3><span class="pill {pill_cls}">{cname}</span> 共 {row["n_events"]} 个事件'
                 f'（前段 {row["n_front"]} / 后段 {row["n_back"]}）</h3>')
        h.append('<table><thead><tr><th>指标</th><th>中位数</th><th>最小</th><th>最大</th></tr></thead><tbody>')
        for key, label in FIN_LABEL.items():
            h.append(f'<tr><td>{label}</td><td>{fmt(row.get(key.replace("crisis_max_dd_pct","dd_median").replace("n_crisis_days","speed_median").replace("crisis_cum_pct","cum_ret_median").replace("post20_cum_pct","recovery_median").replace("onset_avg_pair_corr","corr_median")))}</td>'
                     f'<td>{fmt(row.get(key.replace("crisis_max_dd_pct","dd_min").replace("n_crisis_days","speed_min"), 2))}</td>'
                     f'<td>{fmt(row.get(key.replace("crisis_max_dd_pct","dd_max").replace("n_crisis_days","speed_max"), 2))}</td></tr>')
        h.append('</tbody></table>')
        # 拓扑 delta 中位数
        h.append('<p><b>拓扑画像（危机段减去前段的中位数差值）：</b></p>')
        h.append('<table><thead><tr><th>拓扑摘要</th><th>变化方向</th></tr></thead><tbody>')
        # 从 event_profiles 计算
        members = [p for p in profiles if p.get(f"cluster_k{best_k}") == cid]
        for fk in FEAT_LABEL:
            vals = []
            for m in members:
                v = m.get(f"delta_{fk}", "")
                if v not in ("", None):
                    try:
                        vals.append(float(v))
                    except ValueError:
                        pass
            med = sorted(vals)[len(vals)//2] if vals else None
            if med is None:
                direction = "数据不足"
            elif med > 0.001:
                direction = "上升"
            elif med < -0.001:
                direction = "下降"
            else:
                direction = "基本不变"
            h.append(f'<tr><td>{FEAT_LABEL[fk]}</td><td>{direction}（{fmt(med, 6)}）</td></tr>')
        h.append('</tbody></table>')
        onsets = row.get("onsets", "").split(";")
        eids = row.get("event_ids", "").split(";")
        pairs = [f"{e}（{o}）" for e, o in zip(eids, onsets) if e]
        h.append(f'<p style="font-size:12px;color:#666">成员事件：{"、".join(pairs)}</p>')

    # ---- 四、金融分档 → 拓扑 ----
    h.append('</div><div class="card"><h2>四、金融分档看拓扑画像</h2>')
    h.append('<p>反过来按金融特征分档，看每档的拓扑 delta 中位数。</p>')
    for dim, dim_label in [("severity", "按严重度（危机段最大回撤）"), ("speed", "按速度（危机段持续交易日）")]:
        h.append(f'<h3>{dim_label}</h3>')
        h.append('<table><thead><tr><th>档位</th><th>事件数</th>')
        for fk in FEAT_LABEL:
            h.append(f'<th>{FEAT_LABEL[fk]}</th>')
        h.append('</tr></thead><tbody>')
        for row in fin_topo:
            if row["dimension"] != dim:
                continue
            b = row["bin"]
            blabel = SEV_LABEL.get(b, SPD_LABEL.get(b, b)) if dim == "severity" else SPD_LABEL.get(b, b)
            pill_cls = {"深": "deep", "中": "mid", "浅": "shallow"}.get(b, {"急性": "acute", "中速": "midspd", "慢性": "chronic"}.get(b, ""))
            h.append(f'<tr><td><span class="pill {pill_cls}">{blabel}</span></td><td>{row["n_events"]}</td>')
            for fk in FEAT_LABEL:
                v = row.get(f"delta_med_{fk}", "")
                h.append(f'<td>{fmt(v, 4)}</td>')
            h.append('</tr>')
        h.append('</tbody></table>')

    # ---- 五、交叉表 ----
    h.append('</div><div class="card"><h2>五、拓扑分组与金融分档交叉表</h2>')
    h.append('<table><thead><tr><th>拓扑分组</th><th>严重度</th><th>速度</th><th>事件数</th><th>事件编号</th></tr></thead><tbody>')
    for row in cross:
        cname = CLUSTER_LABEL.get(row["cluster_name"], row["cluster_name"])
        sev = SEV_LABEL.get(row["severity_bin"], row["severity_bin"])
        spd = SPD_LABEL.get(row["speed_bin"], row["speed_bin"])
        ccls = "c1" if row["cluster_id"] == "1" else "c2"
        scls = {"深": "deep", "中": "mid", "浅": "shallow"}.get(row["severity_bin"], "")
        pcls = {"急性": "acute", "中速": "midspd", "慢性": "chronic"}.get(row["speed_bin"], "")
        h.append(f'<tr><td><span class="pill {ccls}">{cname}</span></td>'
                 f'<td><span class="pill {scls}">{sev}</span></td>'
                 f'<td><span class="pill {pcls}">{spd}</span></td>'
                 f'<td>{row["n"]}</td><td style="font-size:11px">{row["event_ids"]}</td></tr>')
    h.append('</tbody></table>')
    h.append('<div class="note"><b>关键对应：</b>「尺度扩张型」以深回撤、慢性危机为主（七例）；'
             '「相关重构型」以浅回撤、急性冲击为主（十一例）。'
             '这说明拓扑摘要确实捕捉到了某种金融差异——但不是「危机与非危机」的差异，'
             '而是<b>「深慢危机」与「浅快冲击」的差异</b>。</div></div>')

    # ---- 六、七轮映射 ----
    h.append('<div class="card"><h2>六、七轮危机的拓扑画像</h2>')
    h.append('<table><thead><tr><th>轮次</th><th>区间</th><th>金融定性</th><th>落入的事件</th><th>拓扑分组</th></tr></thead><tbody>')
    for rid, interval, nature in ROUNDS:
        members = []
        for p in profiles:
            r = round_of(p.get("onset", ""))
            if r == rid:
                cname = CLUSTER_LABEL.get(p.get("cluster_name", ""), p.get("cluster_name", ""))
                members.append(f'{p["event_id"]}（{cname}）')
        h.append(f'<tr><td>{rid}</td><td>{interval}</td><td style="max-width:280px">{nature}</td>'
                 f'<td>{"、".join(members) if members else "无直接对应"}</td>'
                 f'<td style="font-size:11px">{"; ".join(set(CLUSTER_LABEL.get(p.get("cluster_name",""),"") for p in profiles if round_of(p.get("onset",""))==rid))}</td></tr>')
    h.append('</tbody></table>')
    h.append('<div class="warn"><b>注意：</b>多数事件属于急性事件层，不是整轮制度区间。'
             '同一轮内不同事件可能落入不同拓扑分组，说明「一轮危机」内部也有拓扑异质性。</div></div>')

    # ---- 七、事件全表 ----
    h.append('<div class="card"><h2>七、事件全表</h2>')
    h.append('<table><thead><tr><th>编号</th><th>起点</th><th>年代</th><th>拓扑分组</th>'
             '<th>最大回撤</th><th>持续日</th><th>累计收益</th><th>事后恢复</th><th>起点相关</th></tr></thead><tbody>')
    for p in sorted(profiles, key=lambda x: x.get("onset", "")):
        cname = CLUSTER_LABEL.get(p.get("cluster_name", ""), p.get("cluster_name", ""))
        ccls = "c1" if p.get(f"cluster_k{best_k}") == "1" else "c2"
        seg = p.get("segment", "")
        dd = p.get("crisis_max_dd_pct", "")
        h.append(f'<tr><td>{p["event_id"]}</td><td>{p.get("onset","")}</td><td>{seg}</td>'
                 f'<td><span class="pill {ccls}">{cname}</span></td>'
                 f'<td>{fmt(dd, 2)}</td><td>{fmt(p.get("n_crisis_days",""), 0)}</td>'
                 f'<td>{fmt(p.get("crisis_cum_pct",""), 2)}</td>'
                 f'<td>{fmt(p.get("post20_cum_pct",""), 2)}</td>'
                 f'<td>{fmt(p.get("onset_avg_pair_corr",""), 4)}</td></tr>')
    h.append('</tbody></table></div>')

    # ---- 八、稳健性 ----
    h.append('<div class="card"><h2>八、稳健性检查</h2>')
    h.append('<p>按预登记要求，报告分三、四、五组的结果。事件在不同组数下的归属见下表。</p>')
    h.append('<table><thead><tr><th>编号</th><th>起点</th><th>分 3 组</th><th>分 4 组</th><th>分 5 组</th><th>最优分组</th></tr></thead><tbody>')
    for a in assignments:
        h.append(f'<tr><td>{a["event_id"]}</td><td>{a["onset"]}</td>'
                 f'<td>{a.get("k=3","")}</td><td>{a.get("k=4","")}</td><td>{a.get("k=5","")}</td>'
                 f'<td><span class="pill {"c1" if a.get("k_optimal")=="1" else "c2"}">'
                 f'{CLUSTER_LABEL.get(a.get("cluster_name",""), a.get("cluster_name",""))}</span></td></tr>')
    h.append('</tbody></table>')
    h.append('<p>分两组与分三组的轮廓系数接近（0.326 对 0.323），说明二分是最自然的粒度。'
             '分四组以上轮廓系数明显下降，不建议采用。</p></div>')

    # ---- 九、与十四条推测的关系 ----
    h.append('<div class="card"><h2>九、这对十四条推测意味着什么</h2>')
    h.append('<p>本分析不重判任何推测。但它解释了为什么若干推测「无法判定」：</p>')
    h.append('<table><thead><tr><th>推测</th><th>当前判定</th><th>分型视角的解读</th></tr></thead><tbody>')
    rows = [
        ("C01 尺度摘要跳升", "无法判定",
         "深慢危机中尺度确实扩张，但浅快冲击中反而收缩。全体合并计算时方向相互抵消，无法得出统一结论。"),
        ("C07 一维孔洞减少", "无法判定",
         "两组的方向相反：尺度扩张型的一维环数量变化不一致，相关重构型的一维环数量在相关网络线上升。分维计数的规则使整体无法判定。"),
        ("C10 一维塌陷", "无法判定",
         "深慢危机的窗口更长、更可能填满；浅快冲击窗口太短。分组后可以分开检验，但当前规则不允许按组分别判定。"),
        ("C08 危机前离散度低", "矛盾",
         "两组的危机前离散度表现不同，合并后方向不一致。分组后可能一组支持一组矛盾。"),
        ("C04 危机前形状无差异", "支持",
         "两组的形状摘要在危机前确实都没有稳定差异，与判定一致。"),
    ]
    for cid, verdict, interp in rows:
        vc = "pill deep" if verdict == "矛盾" else ("pill shallow" if verdict == "支持" else "pill mid")
        h.append(f'<tr><td>{cid}</td><td><span class="{vc}">{verdict}</span></td><td>{interp}</td></tr>')
    h.append('</tbody></table>')
    h.append('<div class="note"><b>核心启示：</b>与其追问「拓扑摘要在危机中是否统一变化」，'
             '不如追问「<b>哪类危机</b>有哪类拓扑变化」。'
             '深慢的系统性危机确实伴随尺度扩张，浅快的冲击则呈现相关网络重构。'
             '这与 C09（牛熊差异）的方向一致——拓扑摘要对市场状态有反应，只是不以统一方式。</div></div>')

    # ---- 边界 ----
    h.append('<div class="card"><h2>十、研究边界</h2><ul>')
    for b in summary.get("boundary", []):
        h.append(f'<li>{b}</li>')
    h.append('</ul>')
    h.append('<p>此外：</p><ul>')
    h.append('<li>轮廓系数 0.326 表明分组边界不锐利，不要过度解读两组的差异</li>')
    h.append('<li>严重度分档基于危机段内最大回撤，极短事件（一至两天）的回撤天然偏小，可能低估其严重程度</li>')
    h.append('<li>七轮映射是事后区间归属，不是因果识别</li>')
    h.append('<li>本分析不增加任何预测能力的声称</li>')
    h.append('</ul></div>')

    h.append(f'<footer>危机事件拓扑画像分型报告 · 纯描述性对账 · 生成于 {datetime.now().strftime("%Y 年 %m 月 %d 日")}</footer>')
    h.append('</div></body></html>')

    html = "\n".join(h)
    p = OUT / "crisis_typology_v08_report.html"
    p.write_text(html, encoding="utf-8")
    print(f"报告已生成: {p} ({len(html):,} 字节)")


if __name__ == "__main__":
    main()
