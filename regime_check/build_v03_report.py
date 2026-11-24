"""Build the v0.3 line-split re-adjudication report + conclusion ledger.

Reads ONLY the already-frozen outputs (verdicts.json / grid.csv / spec).
No new statistics are computed here except descriptive counts for display.
"""
from __future__ import annotations

import csv
import html
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
J = json.loads((OUT / "regime_v03_verdicts.json").read_text(encoding="utf-8"))
G = list(csv.DictReader((OUT / "regime_v03_grid.csv")
                        .open(encoding="utf-8-sig", newline="")))
W = html.escape


def fmt(x, nd=4):
    if x is None or x == "":
        return "—"
    try:
        v = float(x)
        if v != v:
            return "—"
        return f"{v:.{nd}f}"
    except (TypeError, ValueError):
        return W(str(x))


def badge(v):
    cls = ("ok" if v == "支持" else
           "bad" if v == "矛盾" else "na")
    return f'<span class="b {cls}">{W(str(v))}</span>'


sig_rows = [g for g in G if g["p_bonferroni_pass"] == "True"
            and g["ci_crosses_zero"] == "False"]
sig_by_state = Counter(g["state"] for g in sig_rows)
sig_by_line = Counter(g["line"] for g in sig_rows)
sig_by_class = Counter(g["class"] for g in sig_rows)
main_state_sig = sum(1 for g in sig_rows
                     if g["state"] in ("crisis_in", "pre10"))

# ---------------------------------------------------------------- ledger ----
ledger = []
for c in J["conjectures"]:
    ledger.append({
        "protocol": "regime_split_check_v0.3", "id": c["id"],
        "lines": "|".join(c["lines"]),
        "v0_1_verdict": c["v0_1_verdict"],
        "v0_3_verdict": c["v0_3_verdict"],
        "claim_short": c["note"][:110],
        "evidence_json": "outputs/regime_v03_verdicts.json",
        "boundary": "样本内描述性；w=10；14 事件；不可外推为危机预警绩效",
    })
for line in ("A", "B"):
    v = J["primary"][line]
    ledger.append({
        "protocol": "regime_split_check_v0.3", "id": f"PRIMARY_{line}",
        "lines": line, "v0_1_verdict": "（v0.1 未设分线主判据）",
        "v0_3_verdict": v["verdict"],
        "claim_short": v["rule"],
        "evidence_json": "outputs/regime_v03_verdicts.json",
        "boundary": "两线独立；不合并；不读 2025 封存测试集",
    })
for q in ("J1", "J2", "J3", "J4"):
    ledger.append({
        "protocol": "regime_split_check_v0.3", "id": q,
        "lines": "A+B", "v0_1_verdict": "—",
        "v0_3_verdict": ("见报告" if q in ("J1", "J3", "J4")
                         else "无法判定（含数据不足）"),
        "claim_short": {"J1": "事后响应", "J2": "事前提前",
                        "J3": "结构可测性", "J4": "噪声代价"}[q],
        "evidence_json": "outputs/regime_v03_verdicts.json",
        "boundary": "分线披露，禁止跨线合并",
    })
lp = OUT / "regime_v03_conclusion_ledger.csv"
with lp.open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(ledger[0]))
    w.writeheader()
    w.writerows(ledger)

# ----------------------------------------------------------------- HTML ----
P = []
a = P.append
a("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>v0.3 分线重解 · 10 日短尺度推测核对报告</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1b2430;--mut:#5c6a7a;--line:#e2e7ee;
--accent:#2b5b8c;--warn:#b45309;--bad:#b91c1c;--ok:#166534;--soft:#eef3f9}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
line-height:1.72;font-size:15px}
.wrap{max-width:1120px;margin:0 auto;padding:36px 24px 80px}
h1{font-size:27px;margin:0 0 8px;letter-spacing:.3px}
h2{font-size:20px;margin:38px 0 12px;padding-left:11px;border-left:4px solid var(--accent)}
h3{font-size:16px;margin:24px 0 8px;color:var(--accent)}
.sub{color:var(--mut);font-size:13px;margin-bottom:22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:9px;
padding:18px 20px;margin:14px 0;box-shadow:0 1px 3px rgba(20,40,70,.04)}
.hero{border-left:5px solid var(--bad);background:#fff7f6}
.hero .big{font-size:19px;font-weight:600;color:var(--bad);margin:2px 0 8px}
.warn{border-left:4px solid var(--warn);background:#fffbf3}
.note{border-left:4px solid var(--accent);background:var(--soft)}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:10px 0}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#eef2f7;font-weight:600;white-space:nowrap}
tr:nth-child(even) td{background:#fbfcfe}
.b{display:inline-block;padding:1px 7px;border-radius:10px;font-size:12px;
font-weight:600;white-space:nowrap}
.b.ok{background:#dcf5e4;color:var(--ok)}.b.bad{background:#fde3e1;color:var(--bad)}
.b.na{background:#eceef2;color:#4b5563}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
.small{font-size:12.5px;color:var(--mut)}
ul{margin:6px 0 6px 20px;padding:0}li{margin:4px 0}
.kv{display:grid;grid-template-columns:150px 1fr;gap:4px 14px;font-size:13.5px}
.kv div:nth-child(odd){color:var(--mut)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:820px){.grid2{grid-template-columns:1fr}}
.tag{display:inline-block;background:#e6edf6;color:var(--accent);border-radius:4px;
padding:1px 6px;font-size:12px;margin-right:5px}
code{background:#f0f3f7;padding:1px 5px;border-radius:3px;font-size:12.5px}
.foot{margin-top:42px;padding-top:16px;border-top:1px solid var(--line);
font-size:12.5px;color:var(--mut)}
</style></head><body><div class="wrap">""")

a("<h1>v0.3 分线重解 · 10 日短尺度推测核对报告</h1>")
a('<div class="sub">2026-11-09 · 规格 <code>config/regime_split_check_v0.3.toml</code>'
  '（含 stage2 / 2b / 2c / 2d amendment）· 全部样本内描述性对账</div>')

# 0 hero
a('<div class="card hero"><div class="big">结论：A / B 两条点云的主判据在 w=10 尺度下均未检出</div>'
  '<div>J1 事后响应：A 线 6 格、B 线 10 格，'
  '<b>日级显著 0、事件级显著 0</b>；J2 事前提前（pre10）：两线均 0 显著格。'
  '全网格 8340 格中 151 格过 Bonferroni 且 CI 不跨零，但'
  '<b>危机中 / 危机前 10 日两个主状态组为 0 格</b>——显著格全部落在牛熊状态与放量/缩量分型，'
  '那是状态划分本身的伴随差异，不是危机可检出性。</div></div>')
a('<div class="card note"><b>本报告不评估预警绩效</b>：不计算 PR-AUC / IC / 夏普 / 仓位 / 误报每年，'
  '不读取 Gate 1 封存的 2025 最终测试集，不做阈值反选。两线均未检出只能读作'
  '<b>「在 w=10、14 个事件、当前行业价格数据、当前牛熊/危机标签下未检出」</b>，'
  '不得写成「TDA 对 A 股做不到」的全称外推。</div>')

# 1 concept correction
a("<h2>1. 先纠正一个概念错误：三种「长度」不是一回事</h2>")
a('<div class="card"><div class="small">用户 2026-11-09 指出：'
  '「你犯的错是：都把标签段长当成了行情长度」——这条纠正成立，'
  '且 v0.2 的 <code>prior_fill_counts</code> 与上一轮「6 段填不满 10 日窗口」的说法同属此错，已作废。</div>'
  '<table><tr><th>口径</th><th>定义</th><th>回答什么</th></tr>'
  '<tr><td class="mono">L1 label_run_days</td><td>连续满足 Y_t=1 的<b>起点日个数</b></td>'
  '<td>有多少个 t 往后看 20 日能凑够 −10%；与下跌持续多久无关</td></tr>'
  '<tr><td class="mono">L2 crisis_in 日数</td><td>该段被标为危机中的<b>日级样本数</b></td>'
  '<td>「危机中」分组有多少行可用于统计</td></tr>'
  '<tr><td class="mono">L3 span_to_worst</td><td>起点 → 20 日窗口内最低点的交易日距离</td>'
  '<td>跌到最深用了多久；<b>被 20 日标签窗口截断，不是事件总长度</b></td></tr></table>'
  '<div class="small"><b>关键</b>：逐日摘要的回看窗口 w 与事件持续长度是两个独立量。'
  '每天都有一张持续图，事件短只减少该状态组的样本行数，'
  '不会让 w=10 的摘要「算不出来」，也不需要左截断或可变窗口。</div></div>')

a('<div class="card"><h3>三列窗口可填满事件数（16 个可用事件，分线披露）</h3>'
  '<table><tr><th>w</th><th>按 L1</th><th>按 L2</th><th>按 L3</th></tr>')
fc = J["J3_structural"]["fill_counts"]
for wv in ("10", "15", "20", "30", "40", "60"):
    a(f'<tr><td class="mono">w={wv}</td><td>{fc["L1"][wv]}/16</td>'
      f'<td>{fc["L2"][wv]}/16</td><td>{fc["L3"][wv]}/16</td></tr>')
a('</table><div class="small">三列给出不同答案，禁止合并成一个数。'
  'A 线 w 是<b>点的个数</b>，B 线 w 是<b>坐标长度</b>，结构性代价见 J4；'
  '不得用 A 的 60 日尺子替 B 下结论。</div></div>')

# 2 D3
a("<h2>2. D3 用户决定与事件样本</h2>")
a('<div class="card"><div class="kv">'
  '<div>用户指定排除</div><div><b>2016-02-17（event 3）</b>、<b>2024-12-12（event 16）</b>'
  '——整段剔除，单列标「无法判定（用户指定排除）」</div>'
  '<div>照常算的 4 段</div><div>2016-04-15、2021-02-18、2022-09-06、2024-10-08'
  '（统一固定 w=10，不左截断、不用可变窗口）</div>'
  '<div>纳入主判据</div><div><b>14 个事件起点</b>；日级 crisis_in = '
  f'{J["method"]["crisis_in_daily_n"]} 日（原 221 − 排除两段 7 日）；'
  f'normal 基线 {J["method"]["normal_n"]} 日</div>'
  '<div>对照敏感性</div><div>预先另跑「含全部 16 个事件」版本，事件级显著格数 '
  f'={sum(1 for p in J["full_16_event_sensitivity"].values() for c in p.values() if c["event_sig"])}'
  '（与主判据并列披露，不是事后反选）</div></div>'
  '<div class="warn card" style="margin-top:14px"><b>这不是尺度决定。</b>'
  '被排除的两段 L3 分别是 8 日与 20 日，一短一长；而保留的 2024-10-08 只有 7 日。'
  '用户指令未给出排除理由，<b>助手不代拟、不把「标签段短」「真实跨度短」或任何尺度论证当作依据</b>。'
  '上一轮的传统金融定性（熊市二次探底 / 小微盘风格性去杠杆）只是整理者注解，不是判据。</div></div>')

a('<div class="card"><h3>被排除两段的描述性披露（不进任何显著性计数）</h3>'
  '<table><tr><th>event</th><th>起点</th><th>L1</th><th>L3</th><th>危机中日</th>'
  '<th>W_t 中位（事件/常态）</th><th>h2_count</th><th>xy_h0_death_cv</th></tr>')
for e in J["excluded_event_disclosure"]:
    a(f'<tr><td>{e["event_id"]}</td><td class="mono">{e["onset"]}</td>'
      f'<td>{e["label_run_days"]}</td><td>{e["span_to_worst"]}</td>'
      f'<td>{e["n_usable_days"]}</td>'
      f'<td>{fmt(e["W_t"]["event_median"])} / {fmt(e["W_t"]["normal_median"])}</td>'
      f'<td>{fmt(e["h2_count"]["event_median"],1)} / '
      f'{fmt(e["h2_count"]["normal_median"],1)}</td>'
      f'<td>{fmt(e["xy_h0_death_cv"]["event_median"])} / '
      f'{fmt(e["xy_h0_death_cv"]["normal_median"])}</td></tr>')
a('</table><div class="small">两段的 N（h2_count）一个低于常态（3.5 vs 11）、'
  '一个高于常态（35 vs 11），方向相反——也说明把它们剔除与「让结果更好看」无关。</div></div>')

# 3 line separation
a("<h2>3. 三类构造严格分线</h2>")
a('<div class="card"><table><tr><th>线</th><th>一个点</th><th>w 的角色</th>'
  '<th>距离</th><th>摘要</th></tr>'
  '<tr><td><b>A</b> PHTI 状态点云</td><td>交易日</td><td>点的个数</td>'
  '<td>欧氏，含量级</td><td>W₂、H0 death、H1 birth、RMS</td></tr>'
  '<tr><td><b>B</b> 兴业相关网络</td><td>行业</td><td>坐标长度</td>'
  '<td>√(2(1−ρ))，尺度无关</td><td>N=H₂、L¹ 景观、betti、<b>本版首次产出 H₀ 聚类</b></td></tr>'
  '<tr><td><b>C</b> 原文 3.3 节</td><td>交易日（2 行业、月末）</td><td>—</td>'
  '<td>欧氏</td><td>只作形态对照，<b>不作 A/B 判定证据</b></td></tr></table>'
  '<div class="small">同名量 <code>h1_count</code>、<code>avg_pair_corr</code>、'
  '<code>leading_eig_share</code> 在 A/B 同名异物；本版全部加线别前缀，'
  '禁止跨线合并计数、禁止把控制量当两次独立重复。</div></div>')

# 4 primary
a("<h2>4. 两线主判据（J1 事后响应）</h2>")
a('<div class="card note"><b>冻结判据</b>：以<b>事件级去重（14 个起点）</b>为主读数；'
  '「支持」需满足 ①至少 1 格事件级过 Bonferroni(12) 且 CI 不跨零 '
  '②两面板（A 线 p16/p27）事件方向一致 ③日级方向不矛盾。'
  '<b>日级单独显著不计支持</b>（重复计数嫌疑）。全不显著判「无法判定」，不判「矛盾」（方向未预设）。</div>')

a('<div class="grid2">')
for line in ("A", "B"):
    v = J["primary"][line]
    d = J["primary_detail"][line]
    panels = ("a16", "a27") if line == "A" else ("xy",)
    a(f'<div class="card"><h3>{line} 线 · {badge(v["verdict"])}</h3>'
      f'<div class="small">格数 {v["n_cells"]} · 日级显著 '
      f'{v["n_daily_sig_cells"]} · 事件级显著 {v["n_event_sig_cells"]} · '
      f'支持格 {len(v["supporting_cells"])}</div>'
      '<table><tr><th>摘要</th><th>日级方向</th><th>日级 p</th>'
      '<th>事件级方向</th></tr>')
    for c, info in d["cells"].items():
        ps = []
        for p in panels:
            r = d["daily"].get(f"{p}|{c}")
            ps.append(fmt(None if not r else r["p_raw"], 3))
        a(f'<tr><td class="mono">{W(c)}</td>'
          f'<td>{"/".join(info["daily_directions"])}</td>'
          f'<td class="mono">{"/".join(ps)}</td>'
          f'<td>{"/".join(info["event_directions"])}</td></tr>')
    a('</table>')
    if line == "A":
        a('<div class="small">两面板方向频繁互相矛盾（如 '
          '<code>h0_death_cv</code> 日级 down/up、事件级 down/up），'
          '连方向稳定性都不具备，更谈不上显著。</div>')
    else:
        a('<div class="small">H0 / H1 / H2 三维内部方向不一致（如 '
          '<code>h1_landscape_l1</code> 日级 up、事件级 down），'
          '且 10 格全部不显著。</div>')
    a('</div>')          # close .card
a('</div>')              # close .grid2

# 5 J1-J4
a("<h2>5. J1 / J2 / J3 / J4 分线结果</h2>")
a('<div class="card"><table><tr><th>判据</th><th>A 线</th><th>B 线</th><th>说明</th></tr>')
a('<tr><td><b>J1 事后响应</b></td><td>' + badge(J["J1_post_hoc"]["A"]["verdict"]) +
  '</td><td>' + badge(J["J1_post_hoc"]["B"]["verdict"]) +
  '</td><td>危机中 vs 常态是否可检出；两线各自出结论</td></tr>')
a('<tr><td><b>J2 事前提前</b></td><td>' + badge(J["J2_ex_ante"]["A"]["verdict"]) +
  '</td><td>' + badge(J["J2_ex_ante"]["B"]["verdict"]) +
  '</td><td>pre10 主窗口显著格数 A='
  + str(len(J["J2_ex_ante"]["A"]["pre10_sig_cells"])) + ' / B='
  + str(len(J["J2_ex_ante"]["B"]["pre10_sig_cells"]))
  + '；与 J1 分开报，不得用 J1 反推提前量</td></tr>')
a('<tr><td><b>J3 结构可测性</b></td><td colspan="2">按 L1/L2/L3 三列分线披露（见第 1 节表）</td>'
  '<td>v0.2 prior_fill_counts 已作废</td></tr>')
a('<tr><td><b>J4 噪声代价</b></td><td>10 点 &lt; 16/27 维，H0 仅 9 个有限 death，'
  'H1 受点数-维数比约束，W₂ 方差放大</td>'
  '<td>相关用 9 个日收益，Fisher z 标准误 '
  + fmt(J["J4_noise_cost"]["B"]["fisher_z_se"], 3) + '（w=30 为 '
  + fmt(J["J4_noise_cost"]["B"]["fisher_z_se_w30"], 3) + '）</td>'
  '<td>两线代价不同，禁止跨窗口比绝对量级</td></tr></table></div>')

a('<div class="card warn"><b>5 个标签版本的平凡性（本版新登记）</b>：'
  '5 个版本只改变 bull / bear / fuzzy 划分，crisis_in / pre / overheat / oversold '
  '在这 5 版下<b>完全相同</b>。因此「5 版本方向稳定」对危机类主判据是平凡成立，'
  '不构成 5 次独立重复。网格中这些格标记 <code>version_invariant=true</code>；'
  '危机类命题的稳健性改由 A 线两面板一致 + w=10/20/60 全窗口方向一致承担。</div>')

# 6 split
a("<h2>6. C04 / C07 / C10 拆分（不再混线计数）</h2>")
s = J["split_C04_C07_C10"]
a('<div class="card"><table><tr><th>推测</th><th>拆分后计数</th><th>判定</th></tr>')
a(f'<tr><td>C04 危机前形状摘要无差异</td><td>A 形状 '
  f'{s["C04"]["A_shape"]["n_sig"]}/{s["C04"]["A_shape"]["n_cells"]} 格显著；'
  f'B 形状 {s["C04"]["B_shape"]["n_sig"]}/{s["C04"]["B_shape"]["n_cells"]} 格显著'
  '<div class="small">v0.1 报的「24 格 0 显著」是 6 格 A ＋ 2 格 B 的混合数，本版作废</div></td>'
  f'<td>{badge("支持")}</td></tr>')
g = s["C07"]["groups"]
a('<tr><td>C07 危机中孔洞计数方向</td><td>'
  + "; ".join(f'{k}: 下降 {v["n_down"]}/{len(v["cells"])}、显著 {v["n_sig"]}'
              for k, v in g.items())
  + '<div class="small">A 的 H1、B 的 H1、B 的 H2 分维独立报，'
    '不再合并成「4 个孔洞 0/4 下降」</div></td>'
  + f'<td>{badge(s["C07"]["verdict"])}</td></tr>')
a(f'<tr><td>C10 窗口填满后 H1/H2 消失</td><td>A 窗口 [10,20,60] / B 窗口 [10,30]；'
  '各按 L1/L2/L3 三列分别披露；L3 被 20 日标签窗口截断</td>'
  f'<td>{badge(s["C10"]["verdict"])}</td></tr></table>'
  '<div class="small">B 线 w=30 长尺度对照<b>没有 H0 摘要</b>（阶段 1 只新算了 w=10 的 H0），'
  '因此 H0 维度跨窗口不可比，单列披露，不把 w=10 的 H0 结论外推到 w=30。</div></div>')

# 7 14 conjectures
a("<h2>7. 14 条推测分线重解（v0.1 → v0.3）</h2>")
a('<div class="card"><table><tr><th>ID</th><th>线别</th><th>v0.1 判定</th>'
  '<th>v0.3 判定</th><th>关键证据 / 边界</th></tr>')
for c in J["conjectures"]:
    ev = c["evidence"]
    brief = ""
    if c["id"] == "C01":
        brief = (f'A 线 6 尺度量上升 {ev["A_scale6_up"]}/6、显著 '
                 f'{ev["A_scale6_sig"]}/6；B 景观单列；C 构造 ρ 不作证据')
    elif c["id"] == "C04":
        brief = f'A {ev["A_sig"]}/{ev["A_shape"]}、B {ev["B_sig"]}/{ev["B_shape"]} 格显著'
    elif c["id"] == "C09":
        brief = 'A 线 10 格牛熊中位数差非零（机械结果）；B 线 H0 五版差首次可描述'
    elif c["id"] == "C03":
        brief = (f'p16 峰值滞后中位 {fmt(ev["a16"]["median"],1)} 日，'
                 f'CI [{fmt(ev["a16"]["boot"]["ci_lo"],1)}, '
                 f'{fmt(ev["a16"]["boot"]["ci_hi"],1)}]；含机械成分')
    else:
        brief = c["note"]
    a(f'<tr><td class="mono"><b>{c["id"]}</b></td>'
      f'<td>{"".join(f"<span class=tag>{W(x)}</span>" for x in c["lines"])}</td>'
      f'<td>{badge(c["v0_1_verdict"])}</td><td>{badge(c["v0_3_verdict"])}</td>'
      f'<td class="small">{W(brief)}</td></tr>')
a('</table><div class="kv" style="margin-top:10px">'
  '<div>v0.1 计数</div><div>5 支持 / 1 矛盾 / 8 无法判定</div>'
  f'<div>v0.3 计数</div><div>{J["conjecture_counts"]["支持"]} 支持 / '
  f'{J["conjecture_counts"]["矛盾"]} 矛盾 / '
  f'{J["conjecture_counts"]["无法判定（含数据不足）"]} 无法判定</div></div>'
  '<div class="small"><b>怎么读这 5 条「支持」</b>：C03 峰值滞后含 argmax 必落窗内的机械成分；'
  'C04 支持的是「危机前形状摘要与常态<b>无</b>差异」；C05/C06 只按方向判、显著性全单列；'
  'C09 只判「牛熊中位数有差异」这一层，且属机械结果。'
  '<b>没有一条支持「危机可被提前识别」</b>。v0.1 的 C01「矛盾」在 v0.3 收窄为「无法判定」，'
  '因为分线后该命题只约束 A 的逐日尺度量，且 6 格无显著。</div></div>')

# 8 full grid disclosure
a("<h2>8. 全网格披露（含全部否定与显著结果）</h2>")
a('<div class="card"><div class="kv">'
  f'<div>网格行数</div><div>{len(G)}（5 标签版本 × 8 个 variant × 12 状态组 × 摘要列）</div>'
  f'<div>过 Bonferroni 且 CI 不跨零</div><div><b>{len(sig_rows)} 格</b></div>'
  f'<div>其中主判据状态组</div><div><b>crisis_in / pre10 = {main_state_sig} 格</b></div>'
  f'<div>显著格按状态</div><div>{", ".join(f"{k}: {v}" for k, v in sig_by_state.most_common())}</div>'
  f'<div>显著格按线</div><div>A: {sig_by_line["A"]} / B: {sig_by_line["B"]}</div>'
  f'<div>显著格按类别</div><div>{", ".join(f"{k}: {v}" for k, v in sig_by_class.most_common())}</div>'
  '</div><div class="small" style="margin-top:10px">'
  '显著格集中在 <b>bear / fuzzy / bull</b> 与 <b>pre_low_vol / pre_high_vol</b>，'
  '且以 control / residual / shape 为主。牛熊标签本身就由 MA250、回撤、成交额等定义，'
  '与波动率尺度高度共线；放量/缩量分型也直接按危机前 60 日平均绝对收益划分。'
  '因此这些差异更像<b>状态划分的机械伴随</b>，不是拓扑对危机的增量信息。'
  '详见 <code>outputs/regime_v03_grid.csv</code>（全 8340 行可复核）。</div></div>')

bn = J["B_new_descriptive"]
a('<div class="card"><h3>B 线新增 H₀ 描述性命题（首次可算，全披露）</h3>'
  '<table><tr><th>命题</th><th>状态</th><th>显著格</th><th>说明</th></tr>')
for k, v in bn.items():
    a(f'<tr><td class="mono">{k}</td><td>{W(v["state"])}</td>'
      f'<td>{v["n_sig"]}/{len(v["cells"])}</td>'
      '<td class="small">描述性附加，不进主判据计数、不因结果升级</td></tr>')
a('</table><div class="small">BN3 的牛-熊 H₀ 差在 5 个标签版本下均非零（如 '
  + fmt(bn["BN3"]["five_version_diffs"]["v0_primary"][0], 4) + ' 等），'
  '但这只说明牛熊两组的行业聚类形状不同，与危机提前量无关。</div></div>')

# 9 engineering fixes
a("<h2>9. 工程缺陷修复与审计留痕（判据未改）</h2>")
a('<div class="card warn"><table><tr><th>项</th><th>内容</th><th>影响</th></tr>'
  '<tr><td>初版漏算</td><td>网格循环写了 <code>if sname not in m</code>，'
  '但 bull/bear/fuzzy 存于 <code>version_masks()</code>，导致这三组全部格被静默跳过</td>'
  '<td>修复前 C09 与 BN3 被误判「无法判定」；修复后 C09 恢复「支持」（机械结果）、'
  '主判据结论不变。修正前产物 <code>regime_v03_grid_pregridfix.csv</code> / '
  '<code>regime_v03_verdicts_pregridfix.json</code> 保留</td></tr>'
  '<tr><td>随机种子稳定化</td><td>初版单一共享 rng 流，增删行会让其余格抽样顺序抖动；'
  '最终版每格用 <code>sub_rng(SEED, 稳定标签)</code> 独立派生</td>'
  '<td>两次重跑 stdout / JSON / grid <b>逐位一致</b>；任一格数值与行序无关</td></tr>'
  '<tr><td>规格手写笔误</td><td>stage2 的「按 L2, w=30 → 1/16」应为 2/16</td>'
  '<td>按脚本实测更正并登记于 stage2c；不影响任何判定</td></tr>'
  '<tr><td>规则文本归档</td><td>14 条推测的 v0.3 判定规则写入 stage2d</td>'
  '<td>脚本运行时已冻结，此处只补文本、未改规则</td></tr></table>'
  '<div class="small"><b>这些都不是按结果反选</b>：修复只恢复本应在全网格出现的行、'
  '稳定随机数、更正手写计数；判据、命题、样本定义、阈值、标签版本全部未改。</div></div>')

# 10 boundary
a("<h2>10. 停止门槛与边界</h2>")
a('<div class="card hero"><div class="big">'
  + W(J["stop_threshold"]["result"]) + '</div><div>'
  '用户口径：「10 日尺度做完还不行，才认为确实做不到」。本次在概念分清'
  '（A / B / C 三类构造分线）、短尺度（w=10，两条线都取）、'
  '事件样本按用户指定（排除 2 段、纳入 14 段）三项全部落实之后，'
  'A / B 两线主判据仍均判「无法判定（含数据不足）」，J2 事前提前两线 0 显著格。'
  '按冻结规格，这构成<b>用户个人决定是否停止该路线的依据</b>。</div></div>')
a('<div class="card"><div class="kv">'
  '<div>允许的措辞</div><div>在 w=10、14 事件、当前行业价格数据、'
  '当前牛熊/危机标签下<b>未检出</b></div>'
  '<div>禁止的措辞</div><div>「TDA 对 A 股做不到」「TDA 对 A 股危机预警无效」等全称外推；'
  '把两线结论合并成一句「变好了 / 没变好」</div>'
  '<div>数据边界</div><div>全日期、逐日、样本内描述性对账；'
  '2025-05-30 后牛熊未定义仅保留摘要</div>'
  '<div>冻结协议</div><div>未读 Gate 1 封存的 2025 最终测试集；未算绩效 / IC / 夏普 / 仓位；'
  '未改 <code>config/study.toml</code>；未覆盖 v0.1 / v0.2 任何产物</div>'
  '<div>项目状态</div><div>Gate 1 仍暂停 · Gate 2 未启动 · PHTI 正式绩效未运行</div>'
  '</div></div>')

a('<div class="foot"><b>产物</b>：'
  '<code>outputs/regime_v03_grid.csv</code>（8340 行全网格）、'
  '<code>outputs/regime_v03_verdicts.json</code>（判定台账）、'
  '<code>outputs/regime_v03_conclusion_ledger.csv</code>（本页结论台账 ' +
  str(len(ledger)) + ' 行）、'
  '<code>config/regime_split_check_v0.3.toml</code>（stage2 / 2b / 2c / 2d）、'
  '<code>src/regime_check/verify_v03_split.py</code>。<br>'
  '<b>Provenance</b>：数值全部来自本项目已落盘产物；'
  '三种长度口径的分离、5 版平凡性、分线规则为用户 2026-11-09 纠正后由整理者登记；'
  '传统金融定性属市场解释而非因果证明。本报告不评估预警绩效。</div>')
a("</div></body></html>")

rp = OUT / "regime_v03_split_check_report.html"
rp.write_text("\n".join(P), encoding="utf-8")
print(json.dumps({
    "report": str(rp), "ledger": str(lp), "ledger_rows": len(ledger),
    "grid_rows": len(G), "sig_cells": len(sig_rows),
    "main_state_sig": main_state_sig,
    "verdict_counts": J["conjecture_counts"],
    "primary": {k: v["verdict"] for k, v in J["primary"].items()},
}, ensure_ascii=False, indent=2))
