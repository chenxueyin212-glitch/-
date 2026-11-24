#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v0.9 日级检测与实时分类——离线单文件中文报告生成器。

只读消费 build_v09_daylevel_detection.py 的产物；不重算任何统计量。
可见文本零英文缩写；工程字段名只放悬停。
"""
import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"

FEATURE_CN = {
    "a16_W_t": "状态点云相邻日持续图距离",
    "a16_h0_death_mean": "状态点云零维死亡值均值",
    "a16_h1_count": "状态点云一维环数量",
    "a16_window_rms": "状态点云窗口均方根",
    "a16_avg_pair_corr": "状态点云平均两两相关",
    "a16_leading_eig_share": "状态点云第一特征值占比",
    "b_h2_count": "相关网络二维空腔数量",
    "b_h1_count": "相关网络一维环数量",
    "b_h2_landscape_l1": "相关网络二维景观范数",
    "b_industry_average_correlation": "相关网络平均相关",
    "b_xy_h0_death_mean": "相关网络零维死亡值均值",
}
FEAT_ORDER = list(FEATURE_CN)


def rd(name):
    with (OUT / name).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def hover(field, cn):
    return f'<span class="hv" title="{esc(field)}">{esc(cn)}</span>'


def zh_time(iso):
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y年%m月%d日 %H时%M分")
    except Exception:
        return iso


def main():
    q1 = rd("regime_v09_q1_trigger.csv")
    lag = rd("regime_v09_q2_lag_curve.csv")
    conf = rd("regime_v09_q2_confusion_k5.csv")
    power = rd("regime_v09_q3_power.csv")
    man = json.loads((OUT / "regime_v09_manifest.json").read_text(encoding="utf-8"))
    sample = man["sample"]

    lag_by = {(r["feature"], int(r["k"])): r for r in lag}
    conf_by = {r["feature"]: r for r in conf}

    P = []
    A = P.append

    A('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    A('<meta name="viewport" content="width=device-width, initial-scale=1">')
    A('<title>危机拓扑状态的日级检测与实时分类 · 第九版</title>')
    A('''<style>
:root{--bg:#f7f5f0;--card:#fff;--ink:#2b2620;--sub:#6b6259;--line:#e4ddd2;
--accent:#8c6d3f;--ok:#2e7d4f;--warn:#b3651e;--bad:#a33;--soft:#faf6ef}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.75 "Noto Serif SC","Source Han Serif SC",serif;padding:32px 16px 80px}
.wrap{max-width:980px;margin:0 auto}
header h1{font-size:26px;margin:0 0 6px}header .meta{color:var(--sub);font-size:13px}
section.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:22px 26px;margin:18px 0}
h2{font-size:19px;margin:0 0 12px;color:var(--accent)}
h3{font-size:16px;margin:18px 0 8px}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:10px 0}
th,td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}
th{background:var(--soft);font-weight:600}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.note{background:var(--soft);border-left:3px solid var(--accent);padding:12px 16px;
border-radius:0 8px 8px 0;margin:12px 0;font-size:14px}
.ok{background:#eef6f0;border-left-color:var(--ok)}
.warn{background:#fbf1e7;border-left-color:var(--warn)}
.bad{background:#f9ecec;border-left-color:var(--bad)}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;
border:1px solid var(--line);margin-right:6px}
.tag.ok{background:#eef6f0;color:var(--ok);border-color:#bcdcc7}
.tag.no{background:#f3f1ec;color:var(--sub)}
.hv{border-bottom:1px dotted var(--sub);cursor:help}
footer{color:var(--sub);font-size:12px;text-align:center;margin-top:28px}
code{background:var(--soft);padding:1px 5px;border-radius:4px;font-size:12.5px}
ul{margin:8px 0 8px 22px;padding:0}li{margin:4px 0}
.bar{display:inline-block;height:10px;border-radius:5px;background:var(--accent);vertical-align:middle}
.barwrap{background:#eee7db;border-radius:5px;height:10px;width:120px;display:inline-block;vertical-align:middle}
</style></head><body><div class="wrap">''')

    A('<header><h1>危机拓扑状态的日级检测与实时分类</h1>')
    A(f'<div class="meta">第九版 · 生成于 {zh_time(man["generated_at"])} · '
      '预登记后计算 · 全部为样本内描述性对账，不构成策略绩效或预警能力证明</div></header>')

    # 〇 总览
    A('<section class="card"><h2>〇、三个问题的一页结论</h2>')
    A('<div class="note"><b>本版做什么：</b>把危机拓扑研究从「事件级事后画像」降到「日级实时可算」，'
      '回答产品二（危机类型条件化预案）的三个前置问题：危机来临前拓扑能不能当触发器？'
      '危机进行到第几天能认出是哪一类？样本量到底够检测多大的效应？'
      '本版<b>不是</b>策略回测、不做绩效、不重判十四条推测。</div>')
    n_q1 = sum(1 for r in q1 if r["verdict"] == "有区分度")
    n_q2 = sum(1 for r in conf if r["verdict"] == "有实时分类价值")
    A(f'<p><b>问题一（触发器）：</b>11 项拓扑特征中 <b>{n_q1} 项</b>能把危机来临前 10 个交易日与常态日区分开。'
      '其中状态点云平均两两相关、第一特征值占比在危机前<b>升高</b>，'
      '相关网络的空腔、环、景观范数、零维死亡值在危机前<b>下降</b>——危机前相关网络先「变简单」，不是「变复杂」。</p>')
    A(f'<p><b>问题二（实时分类）：</b>按预登记严格判据（起点后第 5 个交易日、时间切分 2015 年、'
      f'曲线下面积不低于 0.70 且期望代价低于常数基线），<b>{n_q2} 项</b>通过：'
      '状态点云窗口均方根、相关网络平均相关。判别能力在起点当日（第 0 日）就已接近峰值——'
      '两类危机的拓扑差异<b>不需要等 9 天</b>，第一天就能看出大半。</p>')
    A('<p><b>问题三（功效边界）：</b>事件级样本（15 对 30）只能可靠检测曲线下面积约 0.80 以上的巨大效应；'
      '日级样本功效高得多，但危机邻近日的有效样本量受自相关折损（最少的一项只剩约 14 个有效观测）。'
      '此前「0/44 通过邦费罗尼」应读作<b>功效不足</b>，不是「证明无关联」。</p>')
    A('</section>')

    # 一 口径
    A('<section class="card"><h2>一、预登记口径与样本</h2>')
    A('<table><tr><th>项目</th><th>口径</th></tr>')
    A('<tr><td>日历</td><td>6483 个标签交易日（1999-12-30 至 2026-11-03），沿用第七版整合宽表</td></tr>')
    A(f'<tr><td>事件</td><td>45 个统计事件（状态扩张型 {sample["state_expansion"]} 个 / '
      f'相关重构型 {sample["correlation_reconstruction"]} 个），分组沿用第八版冻结标签</td></tr>')
    A(f'<tr><td>危机邻近日</td><td>每个事件起点前第 10 至第 1 个交易日，共 {sample["proximate_days_unique"]} 个不重复日</td></tr>')
    A(f'<tr><td>常态日</td><td>非危机日且不在任何事件起点前后 20 至 30 个交易日范围内，共 {sample["normal_days"]} 日</td></tr>')
    A(f'<tr><td>实时变化量</td><td>第 k 日变化量 = 起点至起点+k 的均值 − 起点前 10 日均值；只用起点+k 当日及以前数据</td></tr>')
    A(f'<tr><td>时间切分</td><td>训练 {sample["train_events"]} 个事件（起点早于 2015 年）、'
      f'测试 {sample["test_events"]} 个事件；阈值只在训练段选，测试段只评一次</td></tr>')
    A('<tr><td>不确定性</td><td>自助 2000 次；危机邻近日按事件整簇重抽、常态日按 20 交易日块重抽；随机种子固定</td></tr>')
    A('<tr><td>缺失处理</td><td>缺失记空值、逐特征成对剔除；不补零、不回填；二十七行业线整体排除（前段为空）</td></tr>')
    A('</table>')
    A('<div class="note"><b>一处如实披露：</b>两类危机的分组标签来自全样本聚类（第八版），'
      '所以问题二的时间切分只约束了分类器参数的选取，<b>不是完全样本外验证</b>。'
      '把它读作「参数内检验」，不要读作「样本外预测」。</div>')
    A('</section>')

    # 二 问题一
    A('<section class="card"><h2>二、问题一：拓扑能不能当危机触发器</h2>')
    A('<p>下表比较危机来临前 10 个交易日与常态日的分布。区分度记为曲线下面积* = '
      '「随机取一个危机前日、随机取一个常态日，前者数值更高的概率」的双侧版本（升或降都算区分）；'
      '括号内为事件簇自助 95% 区间。判定线：曲线下面积* 不低于 0.60 且区间不覆盖 0.50。</p>')
    A('<table><tr><th>拓扑特征</th><th>方向</th><th class="num">曲线下面积*</th>'
      '<th class="num">95% 区间</th><th class="num">中位数差</th><th>判定</th></tr>')
    for r in sorted(q1, key=lambda x: -float(x["auc_star"])):
        ok = r["verdict"] == "有区分度"
        tag = '<span class="tag ok">有区分度</span>' if ok else '<span class="tag no">无区分度</span>'
        A(f'<tr><td>{hover(r["feature"], r["feature_cn"])}</td>'
          f'<td>{r["direction"]}</td>'
          f'<td class="num">{float(r["auc_star"]):.3f}</td>'
          f'<td class="num">[{float(r["auc_ci_low"]):.3f}, {float(r["auc_ci_high"]):.3f}]</td>'
          f'<td class="num">{float(r["median_diff"]):+.5f}</td>'
          f'<td>{tag}</td></tr>')
    A('</table>')
    A('<div class="note ok"><b>读法：</b>7 项通过，说明<b>危机前市场确实留下拓扑痕迹</b>，触发器这一层成立。'
      '值得注意的是方向：状态点云的均方根、平均相关、第一特征值占比在危机前<b>升</b>（市场变极端、变同质），'
      '而相关网络的空腔数量、环数量、景观范数、零维死亡值在危机前<b>降</b>——'
      '危机前行业相关结构先塌缩成「简单而同质」，持续同调的洞先消失，然后才是危机本身。'
      '这与「危机中相关性上升、分散化失效」的金融直觉一致。</div>')
    A('<div class="note warn"><b>但别高估：</b>曲线下面积* 在 0.61–0.65 之间，'
      '是「弱到中等」的区分度，单独用会有一批误报。它的正确角色是风控仪表盘的一个输入，'
      '和你已有的 250 日均线、区间检测<b>叠加</b>使用，不是替代。</div>')
    A('</section>')

    # 三 问题二
    A('<section class="card"><h2>三、问题二：危机第几天能认出是哪一类</h2>')
    A('<h3>判别滞后曲线（起点后第 0 至 15 个交易日）</h3>')
    A('<p>纵轴是「状态扩张型对相关重构型」的曲线下面积（0.5 = 完全分不开，1.0 = 完全分开）。'
      '下表列出每项特征在各滞后日的判别能力与峰值位置。</p>')
    A('<table><tr><th>拓扑特征</th>' + ''.join(f'<th class="num">{k}</th>' for k in range(16))
      + '<th class="num">峰值</th></tr>')
    for f in FEAT_ORDER:
        tds = []
        vals = []
        for k in range(16):
            r = lag_by[(f, k)]
            a = float(r["auc"])
            astar = max(a, 1 - a)
            vals.append((astar, k, a))
            shade = f'opacity:{0.25 + 0.75 * min(1, max(0, (astar - 0.5) / 0.45)):.2f}'
            tds.append(f'<td class="num" style="{shade}">{a:.2f}</td>')
        best = max(vals)
        A(f'<tr><td>{hover(f, FEATURE_CN[f])}</td>' + ''.join(tds)
          + f'<td class="num">第 {best[1]} 日 · {best[0]:.3f}</td></tr>')
    A('</table>')
    A('<div class="note ok"><b>核心发现：分类信息在起点当日就已接近峰值。</b>'
      '状态点云窗口均方根、状态点云平均两两相关、相关网络平均相关、相关网络零维死亡值的峰值都在第 0–1 日，'
      '曲线下面积* 达 0.75–0.83。也就是说，两类危机（「市场状态失控型」对「相关结构重组型」）的分野'
      '<b>在危机爆发当天就能从拓扑上看出来</b>，不用等一周。这直接支持产品二在危机早期切换预案的可行性。</div>')

    A('<h3>第 5 个交易日的正式判定（预登记主检验）</h3>')
    A('<p>时间切分：2015 年前 28 个事件训练、2015 年后 17 个事件测试。'
      '代价单位是百分点收益：漏判深危机（状态扩张型误判为相关重构型、没降仓）代价 7.57，'
      '误判浅危机（过度降仓踏空修复）代价 6.16；基线 = 全判同一类的最优常数策略。</p>')
    A('<table><tr><th>拓扑特征</th><th class="num">曲线下面积</th><th class="num">测试误判代价</th>'
      '<th class="num">常数基线</th><th class="num">漏判</th><th class="num">误报</th><th>判定</th></tr>')
    for r in sorted(conf, key=lambda x: float(x["expected_cost"])):
        ok = r["verdict"] == "有实时分类价值"
        tag = '<span class="tag ok">有分类价值</span>' if ok else '<span class="tag no">无</span>'
        A(f'<tr><td>{hover(r["feature"], r["feature_cn"])}</td>'
          f'<td class="num">{float(r["auc_k5"]):.3f}</td>'
          f'<td class="num">{float(r["expected_cost"]):.3f}</td>'
          f'<td class="num">{float(r["baseline_cost"]):.3f}</td>'
          f'<td class="num">{r["fn"]}</td><td class="num">{r["fp"]}</td><td>{tag}</td></tr>')
    A('</table>')
    A('<div class="note warn"><b>严格判据下 2/11 通过</b>（状态点云窗口均方根、相关网络平均相关）；'
      '另有状态点云平均两两相关代价很低（1.78 对基线 3.12）但曲线下面积 0.691 差 0.009 没过线——'
      '按预登记不改判据，如实列为「未通过但接近」。</div>')
    A('<div class="note"><b>探索性补充（非预登记，仅供参考）：</b>'
      '四个相关网络特征的判别方向与命名极性相反（低值更像状态扩张型）；'
      '若按训练段极性翻转阈值方向，通过数升至 6/11，其中相关网络二维景观范数、零维死亡值的误判代价降至 2.06–2.23。'
      '此外持续图距离在测试段曲线下面积高达 0.90，但训练段阈值迁移后代价反而变差（4.93），'
      '提示<b>阈值不稳定、小样本下别依赖单一阈值</b>。这些只作参考，不升级为主结论。</div>')
    A('</section>')

    # 四 问题三
    A('<section class="card"><h2>四、问题三：功效边界——「测不到」还是「真没有」</h2>')
    A('<p>最小可检测效应（按双侧显著性水平 0.05/11、功效 80%）：效应小于该值则「测不出来是正常的」。'
      '下表为事件级（两类危机对比）与日级（危机邻近日对常态日）的对照。</p>')
    A('<table><tr><th>拓扑特征</th><th class="num">事件级有效样本</th><th class="num">事件级最小效应</th>'
      '<th class="num">日级有效样本</th><th class="num">日级最小效应</th></tr>')
    ev_rows = {r["feature"]: r for r in power if r["level"].startswith("状态扩张")}
    dy_rows = {r["feature"]: r for r in power if r["level"].startswith("危机邻近")}
    for f in FEAT_ORDER:
        e, d = ev_rows[f], dy_rows[f]
        A(f'<tr><td>{hover(f, FEATURE_CN[f])}</td>'
          f'<td class="num">{float(e["n1_eff"]):.0f} / {float(e["n2_eff"]):.0f}</td>'
          f'<td class="num">d={float(e["mde_cohen_d"]):.2f}（曲线下面积≈{float(e["mde_auc_equiv"]):.2f}）</td>'
          f'<td class="num">{float(d["n1_eff"]):.0f} / {float(d["n2_eff"]):.0f}</td>'
          f'<td class="num">d={float(d["mde_cohen_d"]):.2f}（曲线下面积≈{float(d["mde_auc_equiv"]):.2f}）</td></tr>')
    A('</table>')
    A('<div class="note"><b>结论：</b>事件级只能可靠检测曲线下面积约 0.80 以上的巨大效应——'
      '这就是为什么第八版 44 对关联没有一对通过邦费罗尼校正：<b>不是没有信号，是样本量证明不了</b>。'
      '日级功效高一个量级（最小可检测曲线下面积低至 0.57–0.78），'
      '这正是本版把颗粒度降到日级的价值所在：今后的检验应尽量在日级做，事件级只做汇总展示。'
      '但注意危机邻近日的自相关折损严重（零维死亡值有效样本只剩约 14 个），'
      '任何日级结论都必须按有效样本量而不是原始天数来解读。</div>')
    A('</section>')

    # 五 对产品二的含义
    A('<section class="card"><h2>五、对产品二（危机类型条件化预案）的直接含义</h2>')
    A('<ul>')
    A('<li><b>触发器层成立</b>：7/11 拓扑特征能把危机邻近日与常态日分开（区分度 0.61–0.65），'
      '可与 250 日均线、区间检测叠加做风控状态输入；单独使用会误报，不要单飞。</li>')
    A('<li><b>分类器可以早动</b>：两类危机的拓扑分野在起点当日最强（曲线下面积* 最高 0.83），'
      '第 5 个交易日仍有 0.73–0.74。预案切换放在起点后 1–5 个交易日内是有数据依据的。</li>')
    A('<li><b>首选特征</b>：状态点云窗口均方根 + 相关网络平均相关（预登记双通过）；'
      '状态点云平均两两相关（代价最优但差线 0.009）列为候选第二梯队。</li>')
    A('<li><b>代价不对称是划算的</b>：即使只有 2 项通过，测试误判代价 2.14–1.78 相比全判同一类的 3.12 仍降低了约三成——'
      '说明「深危机降仓、浅危机不乱砍」的条件化应对有正价值，值得继续往预案回测走。</li>')
    A('<li><b>下一步是产品二的反事实损益</b>：套对预案、套错预案、无预案三条路径的逐事件损益差，'
      '并给出误判代价表。日级检测层的参数（特征、极性、主判定日）按本版冻结。</li>')
    A('</ul>')
    A('</section>')

    # 六 边界
    A('<section class="card"><h2>六、研究边界与红线（不变）</h2>')
    A('<ul>')
    for b in man["boundary"]:
        A(f'<li>{esc(b)}</li>')
    A('<li>判别滞后曲线中测试段个别特征曲线下面积很高（如持续图距离 0.90）但阈值迁移代价变差，'
      '小样本下单点阈值不稳定，不得据此宣称「已可用」。</li>')
    A('<li>探索性极性感知结果只作参考，未升级为主结论；主结论以预登记判据为准。</li>')
    A('<li>本版不构成策略收益、预警绩效或样本外预测能力的任何证明。</li>')
    A('</ul>')
    A('</section>')

    A(f'<footer>第九版危机拓扑状态日级检测报告 · {zh_time(man["generated_at"])} · '
      '全部数字来自预登记后的一次计算，报告本身不重算任何统计量。</footer>')
    A('</div></body></html>')

    path = OUT / "crisis_daylevel_v09_report.html"
    path.write_text("\n".join(P), encoding="utf-8")
    print(f"report bytes = {path.stat().st_size}")
    print("Done.")


if __name__ == "__main__":
    main()
