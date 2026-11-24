# -*- coding: utf-8 -*-
"""
v0.17 产品栈条件下的拓扑条件增量检验 报告生成
（crisis_topology_increment_v017_report.html）
离线单文件、全中文、可见文本零拉丁（工程字段只放悬停 title）。
"""
import html as h
import json

import pandas as pd

BASE = "."
OUT = f"{BASE}/outputs"

l1 = pd.read_csv(f"{OUT}/regime_v017_conditional_auc.csv")
arms = pd.read_csv(f"{OUT}/regime_v017_account_arms.csv")
manifest = json.load(open(f"{OUT}/regime_v017_manifest.json", encoding="utf-8"))

for c in ("auc_raw", "auc_star", "directed_auc", "ci_low", "ci_high",
          "auc_box", "auc_combined", "delta_auc", "delta_ci_low", "delta_ci_high",
          "q_directed", "q_delta"):
    l1[c] = pd.to_numeric(l1[c], errors="coerce")
for c in ("net_reference", "e2e_p4_p3_total", "e2e_p1_p3_total", "false_cost_total",
          "diff_p4_p3_median_switched", "alarm_day_share", "false_days_per_year"):
    arms[c] = pd.to_numeric(arms[c], errors="coerce")

main = l1[l1["contrast"] == "主对比·真警报对假警报"].copy()
sec = l1[l1["contrast"] == "次对比·真警报对常态"].copy()
bare = l1[l1["contrast"] == "参照·老标准邻近对常态"].copy()

c0 = arms[arms["arm"] == "C0"].iloc[0]
c1 = arms[arms["arm"] == "C1"].iloc[0]
c2 = arms[arms["arm"] == "C2"].iloc[0]


def fnum(x, nd=2):
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x:,.{nd}f}"


def fnd(x, nd=4):
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x:.{nd}f}"


out = []
def a(s):
    out.append(s)

a('<html><head><meta charset="utf-8"><title>拓扑条件增量检验 · v0.17</title><style>')
a('body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#f7f8fa;color:#222;margin:0;padding:28px 5%;}'
  'h1{font-size:25px;margin:0 0 6px} h2{font-size:19px;margin:30px 0 10px;border-left:4px solid #4a6fa5;padding-left:10px;}'
  'h3{font-size:15px;margin:18px 0 8px;color:#444;}'
  '.meta{color:#777;font-size:12.5px;margin-bottom:18px;line-height:1.9;}'
  '.tiles{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0;}'
  '.tile{background:#fff;border:1px solid #e3e6ec;border-radius:10px;padding:14px 18px;min-width:150px;flex:1;}'
  '.tile .nm{font-size:12px;color:#888;} .tile .vl{font-size:26px;font-weight:700;margin:4px 0;}'
  '.tile .sm{font-size:11.5px;color:#999;} .vl.mid{color:#b25a00;} .vl.good{color:#2a7a4b;} .vl.ok{color:#2a7a4b;} .vl.bad{color:#b23a3a;}'
  '.warn{background:#fff7f0;border:1px solid #f0c9a8;border-radius:10px;padding:14px 18px;margin:14px 0;font-size:13.5px;line-height:2.05;}'
  '.warn b{color:#b25a00;}'
  '.note{background:#fff;border:1px solid #e3e6ec;border-radius:10px;padding:12px 16px;margin:10px 0;font-size:13px;line-height:1.95;color:#555;}'
  'table{border-collapse:collapse;width:100%;background:#fff;font-size:12.5px;margin:8px 0;}'
  'th,td{border:1px solid #e3e6ec;padding:6px 8px;text-align:center;}'
  'th{background:#eef1f6;position:sticky;top:0;}'
  'td.lft,th.lft{text-align:left;} tr.hl{background:#fdf3e3;} tr.g0{background:#f2f4f8;}'
  'details{background:#fff;border:1px solid #e3e6ec;border-radius:10px;padding:10px 16px;margin:12px 0;}'
  'summary{cursor:pointer;font-weight:600;font-size:14px;}'
  '.dim{color:#999;} .up{color:#b23a3a;} .dn{color:#2a7a4b;}'
  '.scroll{max-height:520px;overflow:auto;border:1px solid #e3e6ec;border-radius:8px;}'
  'footer{margin:34px 0 10px;color:#999;font-size:11.5px;line-height:1.9;}'
  '</style></head><body>')

a('<h1>产品栈条件下的拓扑条件增量检验</h1>')
a('<div class="meta">第十七版预登记 · 一句话：用产品级标准（三中二触发器＋纯静默冷却十日消音＋判定机票箱与账本引擎）'
  '重做日级老问题——警报响了之后，拓扑还分不分得出真假警报、还值不值得进产品。'
  '两层：判别层（条件面积与增量面积，45 事件样本内）＋账本层（三臂反事实记账）。'
  '全部样本内描述性 · 双跑字节一致 · 老标准参照列与第九版冻结件逐特征对账通过</div>')

# ---------------- 大数字 ----------------
a('<div class="tiles">')
a(f'<div class="tile"><div class="nm">判别层判决</div><div class="vl good" style="font-size:19px">拓扑有产品侧增量</div>'
  f'<div class="sm">条件判别成立 {manifest["layer1_cond_discrimination_count"]} 项 · 票箱之上增量成立 {manifest["layer1_delta_count"]} 项</div></div>')
a(f'<div class="tile"><div class="nm">老标准判读</div><div class="vl mid" style="font-size:19px">老标准低估</div>'
  f'<div class="sm">裸分离均值 {fnd(manifest["old_standard_bare_mean_auc_star"])} → 条件分离均值 {fnd(manifest["old_standard_cond_mean_auc_star"])}（装进警报态后反而更清楚）</div></div>')
a(f'<div class="tile"><div class="nm">实验臂甲净账（票箱扩容）</div><div class="vl good">+{fnum(c1["net_reference"])}</div>'
  f'<div class="sm">控制臂 +{fnum(c0["net_reference"])} · 过闸且更优＝增强件候选（钱的归属见下方丑话）</div></div>')
a(f'<div class="tile"><div class="nm">实验臂乙净账（平静撤销）</div><div class="vl bad">+{fnum(c2["net_reference"])}</div>'
  f'<div class="sm">提早解除反复再开，误报段反而更贵：无净增量</div></div>')
a(f'<div class="tile"><div class="nm">识别硬闸</div><div class="vl ok">45 / 45</div>'
  f'<div class="sm">三臂全部守住（识别窗含损伤窗，漏＝0）</div></div>')
a('</div>')

# ---------------- 一、问题 ----------------
a('<h2>一、这版要回答什么</h2>')
a('<div class="note">第九版当年是「光着测」的：把拓扑指标直接跟「危机临近的日子」比「平常日子」，得出 11 项里 7 项看得出危机。'
  '但产品栈里有两个悬而未决的问题：<br>'
  '① 触发器三元件（五日跌四、波动抬升、回撤警报）全是价量的，一个拓扑件都没有——'
  '警报已经响了之后，拓扑还能不能帮你分出「真警报」和「假警报」？<br>'
  '② 判定机票箱里的 7 件恰好是当年有区分度的 7 个拓扑特征，剩下 3 个弱件没进箱——'
  '把 11 件全放上去，在票箱之上还有没有增量？<br>'
  '结论会直接裁决拓扑的定位：<b>以增强件进产品</b>，还是<b>留在科研发现层</b>。</div>')

a('<div class="note"><b>样本一句话</b>：警报态日子共 6483 个交易日里的 23.4%；其中'
  f'「真警报早期日」{manifest["sample"]["p_early_alarm_days"]} 个（危机起点前 20 日到后 5 日的警报日，覆盖 {manifest["sample"]["p_events_with_early_days"]} / 45 个事件）、'
  f'「假警报日」{manifest["sample"]["n_false_alarm_days"]} 个（{manifest["sample"]["n_false_segments"]} 个与任何事件归属窗不相交的警报段）、'
  f'常态日 {manifest["sample"]["normal_days"]} 个、老标准邻近日 {manifest["sample"]["prox_unique_days"]} 个。'
  f'另有 {manifest["sample"]["deep_alarm_days_descriptive"]} 个「危机深处」警报日不进主对比（危机都展开了才响的日子，比赢了也不算本事），只留描述。</div>')

# ---------------- 二、层一主表 ----------------
a('<h2>二、判别层主表：真警报 对 假警报（警报态条件下）</h2>')
a('<div class="note">读法：<b>分离强度面积</b>＝该特征单独把真假警报日分开的能力（0.5＝瞎猜，1＝完美）；'
  '<b>增量面积</b>＝把它和票箱分等权合并后，比光用票箱分多出来的分离能力（正＝有增量）；'
  '「校正标注」是多重比较校正后的门槛值，越小越硬。带底纹的行＝过了对应判定。</div>')

a('<div class="scroll"><table id="t-main"><tr>'
  '<th class="lft">特征</th><th>冻结方向</th><th>正类日</th><th>负类日</th>'
  '<th>分离强度面积</th><th>95% 区间</th><th>票箱分面积</th><th>合并后面积</th>'
  '<th>增量面积</th><th>增量 95% 区间</th><th>校正标注</th>'
  '<th>条件判定</th><th>增量判定</th></tr>')

for _, r in main.iterrows():
    cls = ""
    if r["feature"] == "__vote_box_score__":
        cls = ' class="g0"'
    elif r["verdict_cond"] == "条件判别成立":
        cls = ' class="hl"'
    ci = f'{fnd(r["ci_low"])} ~ {fnd(r["ci_high"])}' if r["ci_low"] == r["ci_low"] else "—"
    dci = f'{fnd(r["delta_ci_low"])} ~ {fnd(r["delta_ci_high"])}' if r["delta_ci_low"] == r["delta_ci_low"] else "—"
    qd = fnd(r["q_delta"]) if r["q_delta"] == r["q_delta"] else "—"
    a(f'<tr{cls}><td class="lft" title="{h.escape(str(r["feature"]))}">{h.escape(str(r["feature_cn"]))}</td>'
      f'<td>{h.escape(str(r["frozen_direction"]))}</td>'
      f'<td>{int(r["n_pos"])}</td><td>{int(r["n_neg"])}</td>'
      f'<td><b>{fnd(r["auc_star"])}</b></td><td>{ci}</td>'
      f'<td>{fnd(r["auc_box"])}</td><td>{fnd(r["auc_combined"])}</td>'
      f'<td><b>{fnd(r["delta_auc"])}</b></td><td>{dci}</td><td>{qd}</td>'
      f'<td>{h.escape(str(r["verdict_cond"]))}</td>'
      f'<td>{h.escape(str(r["verdict_delta"]))}</td></tr>')
a('</table></div>')

cond_ok = [str(x) for x in main[main["verdict_cond"] == "条件判别成立"]["feature_cn"] if x != "票箱分（危机确认分）"]
inc_ok = [str(x) for x in main[main["verdict_delta"] == "票箱之上有增量"]["feature_cn"]]
a(f'<div class="note"><b>主对比小结</b>：条件判别成立 {len(cond_ok)} 项（{"、".join(cond_ok)}）；'
  f'票箱之上增量成立 {len(inc_ok)} 项（{"、".join(inc_ok)}）。'
  '方向与老标准全部一致——危机真来的时候相关网络「变简单」、状态尺度升，'
  '假警报日反而是「半紧张」状态：拓扑分得出「要出事」和「虚惊一场」。</div>')

# ---------------- 三、三组并排 ----------------
a('<h2>三、老标准与条件口径并排：谁高估谁低估</h2>')
a('<div class="note">同一个 11 件特征、三个问法并排：<b>老标准</b>（危机邻近日对常态日，第九版原样重算）、'
  '<b>主对比</b>（真警报对假警报）、<b>次对比</b>（真警报对常态日，桥接用）。'
  '数值越右越说明「装进警报态后信息更清楚」。</div>')

a('<table id="t-cmp"><tr><th class="lft">特征</th><th>老标准·分离强度</th><th>老标准判定</th>'
  '<th>主对比·分离强度</th><th>主对比·增量</th><th>次对比·分离强度</th><th>次对比·增量</th></tr>')
for _, r in bare.iterrows():
    key = r["feature"]
    mrow = main[main["feature"] == key].iloc[0]
    srow = sec[sec["feature"] == key].iloc[0]
    a(f'<tr><td class="lft" title="{h.escape(str(key))}">{h.escape(str(r["feature_cn"]))}</td>'
      f'<td>{fnd(r["auc_star"])}</td><td>{h.escape(str(r["verdict_cond"]))}</td>'
      f'<td><b>{fnd(mrow["auc_star"])}</b></td><td>{fnd(mrow["delta_auc"])}</td>'
      f'<td>{fnd(srow["auc_star"])}</td><td>{fnd(srow["delta_auc"])}</td></tr>')
a('</table>')

a(f'<div class="warn"><b>老标准低估了拓扑。</b>11 件的分离强度均值从裸测的 '
  f'{fnd(manifest["old_standard_bare_mean_auc_star"])} 升到警报态条件下的 '
  f'{fnd(manifest["old_standard_cond_mean_auc_star"])}，'
  f'方向判读＝{h.escape(str(manifest["old_standard_read"]))}。'
  '道理很直白：老标准拿「危机邻近」对「大后方的平常日」，平常日太好分，把指标的真本事看扁了；'
  '换成「真警报对假警报」这种难得多的题，拓扑反而考得更高——'
  '尤其是当年判「无区分度」的窗口均方根（0.68）和相邻日持续图距离（0.60），在警报态里都过了线。'
  '第九版「拓扑只是弱触发器」的印象要修正为：<b>当它站在警报态里时，比站在全历史里更有用。</b></div>')

# ---------------- 四、层二 ----------------
a('<h2>四、账本层：把拓扑装进产品栈两处入口，钱变不变</h2>')
a('<div class="note">三臂同表、机制不同各自独立与控制臂比：'
  '<b>控制臂</b>＝第十六版选定组合逐字（对账通过，与冻结汇总行逐字段一致）；'
  '<b>实验臂甲</b>＝票箱扩容（7 件扩 10 件，加进 3 个弱件，分数阈值 4/7 不变）；'
  '<b>实验臂乙</b>＝拓扑平静撤销（静默满 3 日且当日拓扑极端计数为 0 提前解除，其余不变）。'
  '硬闸＝45 全识别。</div>')

a('<table id="t-arms"><tr><th class="lft">臂</th><th>识别</th><th>提前</th><th>窗内</th><th>损伤窗</th>'
  '<th>切换数</th><th>已切换中位差</th><th>事件侧合计</th><th>误报段合计</th><th>净账合计</th>'
  '<th>误报日/年</th><th>警戒占比</th><th>判决</th></tr>')
for _, r in arms.iterrows():
    cls = ' class="hl"' if r["verdict"] == "可作产品增强件候选" else (
        ' class="g0"' if r["arm"] == "C0" else "")
    nm = {"C0": "控制臂（冻结合体）", "C1": "实验臂甲（票箱扩容）",
          "C2": "实验臂乙（拓扑平静撤销）"}[r["arm"]]
    a(f'<tr{cls}><td class="lft">{nm}</td>'
      f'<td>{int(r["identified"])}/45</td><td>{int(r["n_pre"])}</td><td>{int(r["n_in_window"])}</td>'
      f'<td>{int(r["n_damage"])}</td><td>{int(r["switched_n"])}</td>'
      f'<td>{fnum(r["diff_p4_p3_median_switched"])}</td>'
      f'<td>+{fnum(r["e2e_p4_p3_total"])}</td><td>{fnum(r["false_cost_total"])}</td>'
      f'<td><b>+{fnum(r["net_reference"])}</b></td>'
      f'<td>{fnum(r["false_days_per_year"])}</td>'
      f'<td>{fnum(r["alarm_day_share"] * 100, 1)}%</td>'
      f'<td>{h.escape(str(r["verdict"]))}</td></tr>')
a('</table>')

a('<div class="warn"><b>丑话三句，把钱的归属说清楚。</b><br>'
  '① 实验臂甲的 +26 不能全记在「拓扑特征有信息」头上。'
  '预登记就披露过：阈值 4/7 在 10 件下整数门槛从 4/7 升到 6/10，确认纪律变严了——'
  '切换数 19→17、已切换中位 +1.16→+3.22、误报段亏损 −68.6→−48.3。'
  '层一又显示信息增量集中在 5 件上（其中 4 件本来就在票箱里）。'
  '所以正确读法是：<b>拓扑信息有增量（层一）＋确认更谨慎（层二）两件事叠加</b>，'
  '都支持「增强件」定位，但别把钱全记在特征头上。<br>'
  '② 实验臂乙的教训很干净：用拓扑平静提早解除警报，等于更频繁地再开警报，'
  '误报段被反复激活反而亏更多（−68.6→−114.1）。消音层不是拓扑的入口。<br>'
  '③ 全表都是样本内上限：账本以「危机何时结束」这个后视镜答案为已知输入（回补起点、止损终点、'
  '认沽到期、切换资格四处都锚着它），实盘里你不知道危机哪天结束。这个第十六版立状的已知不足'
  '本版原样继承、不修补。+105 和 +79 一样是成绩单上限，不是实盘预期。</div>')

# ---------------- 五、判决 ----------------
a('<h2>五、判决与定位</h2>')
a(f'<div class="note"><b>判别层判决：{h.escape(str(manifest["layer1_verdict"]))}。</b><br>'
  '按预登记的三段映射走：条件判别成立 ≥1 且增量成立 ≥1 → 拓扑有产品侧增量，走增强件候选。'
  '本版 9 项条件判别成立、5 项增量成立，落入第一档。<br><br>'
  '<b>产品定位建议</b>：拓扑从「科研发现层」升格为「增强件候选」，具体形态优先走<b>判定机票箱扩容</b>这条路'
  '（实验臂甲过闸且净账更优），装在消音层（实验臂乙）已证伪。'
  '但注意：票箱扩容本身带来更严确认门槛的副作用，正式进产品前应再拆一版「同门槛扩容」与「同件数加严」的对照，'
  '把钱的两部分分开（另行预登记，本版不追）。<br><br>'
  '<b>对第九版的修正</b>：老标准（裸测）低估了拓扑；「日级 7/11 有区分度」的正确读法是'
  '「在警报态条件下 9/11 有区分度、5/11 在票箱之上还有增量」。'
  '当年「拓扑只是弱触发器」的定调作废，改为「拓扑是警报态里的真信息」。</div>')

# ---------------- 六、边界 ----------------
a('<h2>六、边界与已知不足（照抄继承，一句不改）</h2>')
a('<div class="warn">① 全部为样本内描述性对账，不外推、不做实盘宣称；2025 最终测试集封存未读。'
  '② 不重判十四条推测与第五版冻结判定；不动第一道闸门与第二道闸门。'
  '③ 账本以「事件结束日」（后视镜）为已知输入——回补起点、止损终点、认沽到期、切换资格四处锚定它，'
  '零解除误差成本。第十六版已正式立状、本版原样继承：<b>净账数字是上限，不是实盘预期</b>；'
  '将来修「解除规则」须另行预登记。'
  '④ 全样本中位数被未触发／无法判定记 0 拉平，读表请看已切换中位与合计。'
  '⑤ 误报两口径（账本口径与识别窗口径）不可混用。'
  '⑥ 11 件特征的方向冻结于第九版记录（前版冻结发现，非本轮反选）。'
  '⑦ 主对比正类只覆盖 27 / 45 个事件的早期警报日（其余 18 个事件的警报来得晚），'
  '结论对「警报来得早的危机」更有把握。</div>')

a('<details><summary>预登记修订区（实现勘误两则，规则零改动）</summary>'
  '<div class="note">① 合并分标准化按「双类合并样本内均值标准差」实现（首版误按类各自标准化，'
  '把类间差异抹掉，增量面积全负失真；已纠正并重跑双验收）。'
  '② 自助重抽内合并分的特征取向与点估计一致（按冻结方向取向；首版自助漏取向，'
  '降方向特征的增量区间失真；已纠正并重跑双验收）。'
  '另：本版运行环境无外部秩计算库，平均秩以纯数组实现（与第九版语义一致），'
  '老标准参照列点估计与第九版冻结件逐特征对账通过即为证。</div></details>')

a('<footer>预登记：第十七版配置（文件名见悬停）· '
  '<span title="config/regime_topology_increment_v0.17.toml">登记于 2026 年 11 月 14 日 21 时 52 分（先登记后计算）</span> · '
  '<span title="regime_v017_conditional_auc.csv / regime_v017_account_arms.csv / regime_v017_account_event_matrix.csv / regime_v017_manifest.json">数据产物四件（文件名见悬停）</span> · '
  '双跑字节一致 · 控制臂与第十六版冻结汇总行逐字段对账通过 · '
  '可见文本零拉丁（工程字段名只在悬停提示里）</footer>')

a('</body></html>')

open(f"{OUT}/crisis_topology_increment_v017_report.html", "w", encoding="utf-8").write("".join(out))
print("报告已生成：outputs/crisis_topology_increment_v017_report.html")
