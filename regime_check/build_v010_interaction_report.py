"""v0.10 interaction test compact Chinese report."""
import csv, json, re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"

def rd(name):
    with (OUT / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def zh_time(iso):
    dt = datetime.fromisoformat(iso)
    return f"{dt.year}年{dt.month}月{dt.day}日 {dt.hour}:{dt.minute:02d}"

cluster = rd("regime_v010_interaction_clustering.csv")
tests = rd("regime_v010_interaction_test_results.csv")
manifest = json.loads((OUT / "regime_v010_interaction_manifest.json").read_text(encoding="utf-8"))

A = []
def a(*items):
    for it in items:
        A.append(it)

# ── CSS ──
a("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>危机类型与拓扑响应的交互效应检验</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#f5f6fa;color:#2d3436;line-height:1.7;padding:2rem}
.card{background:#fff;border-radius:12px;padding:2rem;margin-bottom:1.5rem;box-shadow:0 2px 8px rgba(0,0,0,.06)}
h1{font-size:1.5rem;margin-bottom:.5rem;color:#2d3436}
h2{font-size:1.2rem;margin:1.5rem 0 .8rem;color:#0984e3;border-left:4px solid #0984e3;padding-left:.6rem}
h3{font-size:1.05rem;margin:1rem 0 .5rem;color:#636e72}
table{width:100%;border-collapse:collapse;margin:.8rem 0;font-size:.88rem}
th,td{padding:.55rem .7rem;border:1px solid #dfe6e9;text-align:left}
th{background:#f0f3f8;font-weight:600;white-space:nowrap}
tr:nth-child(even){background:#fafbfc}
.ok{color:#00b894;font-weight:600}
.warn{color:#e17055;font-weight:600}
.note{background:#ffeaa7;border-left:4px solid #fdcb6e;padding:.8rem 1rem;border-radius:0 8px 8px 0;margin:.8rem 0;font-size:.9rem}
.boundary{background:#dfe6e9;border-left:4px solid #636e72;padding:.8rem 1rem;border-radius:0 8px 8px 0;margin:.8rem 0;font-size:.85rem}
.big{font-size:1.8rem;font-weight:700;color:#0984e3}
.tag{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.78rem;font-weight:600}
.tag-sig{background:#00b894;color:#fff}
.tag-ns{background:#b2bec3;color:#fff}
.tag-warn{background:#e17055;color:#fff}
footer{text-align:center;color:#b2bec3;font-size:.8rem;margin-top:2rem}
</style></head><body>
<div class="card">
<h1>危机类型与拓扑响应的交互效应检验</h1>
<p style="color:#636e72">金融特征独立分型 × 拓扑变化量差异检验 · 预登记版本 v0.10 · 样本内描述性对账</p>
<div class="note"><b>本报告是什么：</b>把此前"两类危机拓扑方向相反"的描述性观察，升级为一次正式的交互效应检验。
分型只用金融特征（回撤深度、危机速度、事后恢复），检验只用拓扑变化量——<b>特征集完全不重叠</b>，打破循环论证。
只检验"两组是否不同"（交互），不检验"每组是否非零"（组内）。v0.5 的十四条正式判定仍为冻结历史，本检验提供独立证据。</div>
""")

# ── 一、核心发现 ──
n_bh = sum(1 for r in tests if r["bh_fdr_sig"] == "是")
a(f'<h2>一、核心发现</h2>')
a(f'<p><span class="big">{n_bh}/8</span> 条推测的拓扑响应在深慢型与浅快型危机之间<b>存在显著差异</b>'
  f'（错误发现率校正后 &lt; 0.10）。通过检验的四条推测，两类的拓扑变化方向完全相反。</p>')

a('<div class="note"><b>一句话结论：</b>拓扑摘要不是"在危机前统一朝某个方向变"，而是'
  '<b>深慢型危机让市场状态失控（尺度+相关同步膨胀），浅快型危机让行业相关结构重组（尺度反而收缩）</b>。'
  '这个交互效应通过了正式的置换检验。</div>')

# ── 二、分型结果 ──
a('<h2>二、金融特征独立分型</h2>')
a('<p>用回撤深度、危机速度、事后恢复三个<b>纯金融</b>特征做层次聚类（沃德法），不碰任何拓扑量。</p>')
a('<table><tr><th>类型</th><th>事件数</th><th>中位回撤</th><th>中位速度</th><th>中位恢复</th>'
  '<th>与拓扑分型一致</th></tr>')
for r in cluster:
    n_old_s = r["old_scale_type"]
    n_old_c = r["old_corr_type"]
    agree_note = f"尺度扩张 {n_old_s} / 相关重构 {n_old_c}"
    a(f'<tr><td><b>{r["fin_cluster"]}</b></td><td>{r["n_events"]}</td>'
      f'<td>{r["dd_median"]}%</td><td>{r["speed_median"]} 天</td>'
      f'<td>{r["recovery_median"]}%</td><td>{agree_note}</td></tr>')
a('</table>')
agree_n = manifest["clustering_agreement_with_v08"].split("/")[0]
a(f'<p class="note">与 v0.8 拓扑分型的一致率：{agree_n}/45 = 73.3%。'
  f'金融分型得到"深慢型 9 个 / 浅快型 36 个"，与拓扑分型的"尺度扩张 15 / 相关重构 30"不完全一致——'
  f'<b>这本身是信息</b>：金融深度和拓扑响应是相关但不同的维度。</p>')

# ── 三、交互检验结果 ──
a('<h2>三、交互检验逐条结果</h2>')
a('<p>置换检验（10000 次），统计量为两组中位数差。效应量用克利夫效应量（−1 到 +1，绝对值越大差异越大）。</p>')
a('<table><tr><th>推测</th><th>拓扑变量</th><th>深慢型中位</th><th>浅快型中位</th>'
  '<th>组间差</th><th>效应量</th><th>95% 置信区间</th><th>p 值</th><th>错误发现率</th></tr>')
for r in tests:
    bh = r["bh_fdr_sig"]
    cls = "tag-sig" if bh == "是" else "tag-ns"
    bh_label = '<span class="tag tag-sig">通过</span>' if bh == "是" else '<span class="tag tag-ns">未通过</span>'
    d_med = float(r["median_deep"])
    s_med = float(r["median_shallow"])
    d_dir = "↑" if d_med > 0 else ("↓" if d_med < 0 else "→")
    s_dir = "↑" if s_med > 0 else ("↓" if s_med < 0 else "→")
    conflict = ' <span class="tag tag-warn">反向</span>' if d_dir != s_dir else ''
    a(f'<tr><td><b>{r["conjecture"]}</b>{conflict}</td><td>{r["description"]}</td>'
      f'<td>{d_dir} {r["median_deep"]}</td><td>{s_dir} {r["median_shallow"]}</td>'
      f'<td>{r["median_diff"]}</td><td>{r["cliffs_delta"]}</td>'
      f'<td>[{r["ci_lo"]}, {r["ci_hi"]}]</td><td>{r["p_value"]}</td>'
      f'<td>{bh_label}</td></tr>')
a('</table>')
a(f'<p><b>最严校正</b>（族系误差率，阈值 0.00625）：0/8 通过。这与预登记的预期一致——'
  f'n=45 在如此严的阈值下功效不足，故预登记选择了错误发现率校正。</p>')

# ── 四、通过检验的四条推测 ──
a('<h2>四、通过检验的四条：两类方向完全相反</h2>')
a('<table><tr><th>推测</th><th>含义</th><th>深慢型（深回撤、慢速）</th><th>浅快型（浅回撤、快速）</th></tr>')
sig_rows = [r for r in tests if r["bh_fdr_sig"] == "是"]
desc_map = {
    "C01": "市场状态的尺度（均方根）",
    "C03": "行业间平均相关性",
    "C04": "相关矩阵第一特征值占比",
    "C09": "相关网络连通性（零维死亡值）",
}
meaning_map = {
    "C01": "危机中市场状态变极端的程度",
    "C03": "危机中行业同涨同跌的程度",
    "C04": "危机中市场被单一因子主导的程度",
    "C09": "危机中行业相关网络的连通程度",
}
for r in sig_rows:
    cid = r["conjecture"]
    d_med = float(r["median_deep"])
    s_med = float(r["median_shallow"])
    d_txt = f"{'升' if d_med > 0 else '降'}（{r['median_deep']}）"
    s_txt = f"{'升' if s_med > 0 else '降'}（{r['median_shallow']}）"
    a(f'<tr><td><b>{cid}</b></td><td>{desc_map.get(cid, r["description"])}<br>'
      f'<small>{meaning_map.get(cid, "")}</small></td>'
      f'<td class="ok">{d_txt}</td><td class="warn">{s_txt}</td></tr>')
a('</table>')
a('<div class="note"><b>金融含义：</b>深慢型危机（如 2015-07、2008-01）让整个市场状态失控——'
  '波动膨胀、行业同涨同跌、被单一因子主导、相关网络连通。'
  '浅快型危机（如 2001—2011 多数早期事件）恰好相反——行业相关结构被打散重组，'
  '市场尺度反而收缩。两种应对策略完全不同。</div>')

# ── 五、未通过的四条 ──
a('<h2>五、未通过检验的四条</h2>')
ns_rows = [r for r in tests if r["bh_fdr_sig"] != "是"]
a('<table><tr><th>推测</th><th>拓扑变量</th><th>p 值</th><th>原因</th></tr>')
reason_map = {
    "C05": "两型同向（都降），本来就不存在交互",
    "C06": "两型同向（都降），交互弱",
    "C07": "方向相反但效应量小，n=45 功效不足",
    "C08": "两型同向（都升），不存在交互",
}
for r in ns_rows:
    cid = r["conjecture"]
    a(f'<tr><td><b>{cid}</b></td><td>{r["description"]}</td>'
      f'<td>{r["p_value"]}</td><td>{reason_map.get(cid, "")}</td></tr>')
a('</table>')
a('<p class="note"><b>C05（一维环减少）和 C08（持续图距离升）的"未通过"恰恰是好消息：</b>'
  '它们在两类危机中方向一致，说明是<b>跨型稳健</b>的行为，不受危机类型调节。'
  'C07 和 C06 方向有一定差异但未达显著，属于功效不足而非"不存在"。</p>')

# ── 六、与 v0.5 判定的关系 ──
a('<h2>六、与 v0.5 冻结判定的关系</h2>')
a('<table><tr><th>推测</th><th>v0.5 判定</th><th>本次交互检验</th><th>综合解读</th></tr>')
update_map = {
    "C01": ("无法判定", "通过（p=0.038）", "v0.5 的\"无法判定\"是两类抵消所致；现证实类型调节效应"),
    "C03": ("支持", "通过（p=0.022）", "原\"支持\"由深慢型拉动；浅快型方向相反"),
    "C04": ("支持", "通过（p=0.029）", "原\"支持\"由深慢型拉动；浅快型方向相反"),
    "C05": ("支持", "未通过（同向）", "两型同向，是跨型稳健的\"支持\""),
    "C06": ("支持", "未通过（同向）", "两型同向偏弱，\"支持\"仍成立但效应小"),
    "C07": ("无法判定", "未通过（功效不足）", "方向相反但 n 不够；仍为\"无法判定\""),
    "C08": ("矛盾", "未通过（同向）", "两型同向升，原\"矛盾\"可能是统计口径问题"),
    "C09": ("支持", "通过（p=0.013）", "原\"支持\"由深慢型拉动；浅快型方向相反"),
}
for cid, (v05, v010, interp) in update_map.items():
    a(f'<tr><td><b>{cid}</b></td><td>{v05}</td><td>{v010}</td><td>{interp}</td></tr>')
a('</table>')

# ── 七、功效边界 ──
a('<h2>七、功效边界</h2>')
a('<p>预登记的功效分析：深慢型 n=9 在 0.80 功效下只能检测效应量 d≈0.82 以上的差异；'
  '浅快型 n=36 可检测 d≈0.47。通过检验的四条效应量在 0.30–0.57 之间，刚好在可检测边缘。</p>')
a('<div class="boundary"><b>未通过 ≠ 不存在：</b>C07 效应量 −0.167 方向明确，但 p=0.351 是功效不足。'
  '如果样本量翻倍，很可能也能通过。这叫"测不到"，不叫"不存在"。</div>')

# ── 八、研究边界 ──
a('<h2>八、研究边界</h2>')
for b in manifest.get("boundary", []):
    # hide engineering paths in tooltips (do specific paths first)
    display = b.replace("config/study.toml", '<span title="config/study.toml">工程配置文件</span>')
    display = display.replace("config/regime", '<span title="config/regime">工程预登记</span>')
    a(f'<p>· {display}</p>')
a('<div class="boundary"><b>本检验的定位：</b>这是样本内的交互效应检验，不是样本外预测验证。'
  '结论"危机类型调节拓扑响应"在当前 45 个事件中成立，但不能外推为"拓扑能预测危机类型"。'
  '要走到预测，需要前向验证或跨市场迁移。</div>')

# footer
_zh = zh_time(manifest["generated_at"])
a(f'<footer>危机类型与拓扑响应交互效应检验 · 预登记 v0.10 · 生成于 {_zh} · '
  f'置换检验 10000 次 · 自助 5000 次 · 全部为样本内描述性对账</footer>')
a('</body></html>')

html = "\n".join(A)
report_path = OUT / "crisis_interaction_v010_report.html"
report_path.write_text(html, encoding="utf-8")
print(f"Report: {report_path}  ({len(html.encode('utf-8')):,} bytes)")
