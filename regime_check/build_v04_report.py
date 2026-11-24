"""Build the v0.4 OPTION A extension report + conclusion ledger.

Reads ONLY the already-frozen outputs (v0.3 and v0.4 verdicts/grid/side-by-side/
compare-summary/acceptance). No statistic is recomputed here; only descriptive
display counts. Written and executed AFTER the user confirmed the spec on
2026-11-09, in the same turn as the judgement run.
"""
from __future__ import annotations

import csv
import html
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"

J3 = json.loads((OUT / "regime_v03_verdicts.json").read_text(encoding="utf-8"))
J4 = json.loads((OUT / "regime_v04_verdicts.json").read_text(encoding="utf-8"))
S = json.loads((OUT / "regime_v04_compare_summary.json").read_text(
    encoding="utf-8"))
A = json.loads((OUT / "regime_v04_label_acceptance.json").read_text(
    encoding="utf-8"))
DA = json.loads((OUT / "xy_wind_all_a_daily_v04_audit.json").read_text(
    encoding="utf-8"))


def rows(p):
    return list(csv.DictReader((OUT / p).open(encoding="utf-8-sig",
                                             newline="")))


G3, G4, SB = (rows("regime_v03_grid.csv"), rows("regime_v04_grid.csv"),
              rows("regime_v04_vs_v03_side_by_side.csv"))
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
    cls = "ok" if v == "支持" else "bad" if v == "矛盾" else "na"
    return f'<span class="b {cls}">{W(str(v))}</span>'


def T(x):
    return x in ("True", "true", "1")


def F(x):
    return x in ("False", "false", "0")


def sig(g):
    return [r for r in g if T(r["p_bonferroni_pass"])
            and F(r["ci_crosses_zero"])]


MAIN = {"crisis_in", "pre5", "pre10", "pre20", "bear_in_crisis"}
s3, s4 = sig(G3), sig(G4)
sb = S["side_by_side"]
eq = S["equivalence_selfcheck"]
k3, k4 = S["keypack_v0_3"], S["keypack_v0_4"]
m3, m4 = J3["method"], J4["method"]
p3, p4 = J3["primary"], J4["primary"]

# ---------------------------------------------------------------- ledger ----
ledger = []
for c3, c4 in zip(J3["conjectures"], J4["conjectures"]):
    v3 = c3["v0_3_verdict"]
    v4 = c4["v0_3_verdict"]      # frozen engine keeps the same field name
    ledger.append({
        "protocol": "regime_split_check_v0.4_OPTION_A",
        "id": c3["id"],
        "lines": "|".join(c3["lines"]),
        "v0_1_verdict": c3["v0_1_verdict"],
        "v0_3_verdict": v3,
        "v0_4_verdict": v4,
        "changed": "否" if v3 == v4 else "是",
        "claim_short": c3["note"][:110],
        "evidence_json": "outputs/regime_v03_verdicts.json + "
                         "outputs/regime_v04_verdicts.json",
        "boundary": "样本内描述性；w=10；14 事件；补足 345 天定义后并列；"
                    "不可外推为危机预警绩效",
    })
for line in ("A", "B"):
    v = p4[line]
    ledger.append({
        "protocol": "regime_split_check_v0.4_OPTION_A",
        "id": f"PRIMARY_{line}", "lines": line,
        "v0_1_verdict": "（v0.1 未设分线主判据）",
        "v0_3_verdict": p3[line]["verdict"],
        "v0_4_verdict": v["verdict"],
        "changed": "否" if p3[line]["verdict"] == v["verdict"] else "是",
        "claim_short": v["rule"][:110],
        "evidence_json": "outputs/regime_v04_verdicts.json",
        "boundary": "两线独立；不合并；不读 Gate 1 封存 2025 评分数据集",
    })
for q, desc in (("J1", "事后响应"), ("J2", "事前提前 pre10"),
                ("J3", "结构可测性"), ("J4", "噪声代价")):
    # Keep the v0.3 ledger wording verbatim, so no artificial verdict change
    # is introduced by the display layer.
    v = ("见报告" if q in ("J1", "J3", "J4")
         else "无法判定（含数据不足）")
    ledger.append({
        "protocol": "regime_split_check_v0.4_OPTION_A",
        "id": q, "lines": "A+B", "v0_1_verdict": "—",
        "v0_3_verdict": v,
        "v0_4_verdict": v,
        "changed": "否",
        "claim_short": desc,
        "evidence_json": "outputs/regime_v04_verdicts.json",
        "boundary": "分线披露，禁止跨线合并；J3/J4 为结构性说明",
    })
lp = OUT / "regime_v04_conclusion_ledger.csv"
with lp.open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(ledger[0]))
    w.writeheader()
    w.writerows(ledger)

# ----------------------------------------------------------------- HTML ----
P = []
a = P.append
a("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>v0.4 · 基准延拓（真万得全A日线）新旧并列报告</title>
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
.hero{border-left:5px solid var(--accent);background:#f3f8fe}
.hero .big{font-size:19px;font-weight:600;color:var(--accent);margin:2px 0 8px}
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
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:820px){.grid2{grid-template-columns:1fr}}
code{background:#f0f3f7;padding:1px 5px;border-radius:3px;font-size:12.5px}
.foot{margin-top:42px;padding-top:16px;border-top:1px solid var(--line);
font-size:12.5px;color:var(--mut)}
.same{color:var(--ok);font-weight:600}.chg{color:var(--warn);font-weight:600}
</style></head><body><div class="wrap">""")

a("<h1>v0.4 · 基准延拓（真万得全A日线）新旧并列报告</h1>")
a('<div class="sub">2026-11-09 · 规格 <code>config/regime_split_check_v0.4.toml</code>'
  '（含 OPTION A amendment 与 confirmation 段）· 全部样本内描述性对账 · '
  'v0.3 冻结产物原封保留作并列对照</div>')

# 0 hero
a('<div class="card hero"><div class="big">结论：补齐 345 天真实行情，未改变 v0.3 的结论</div>'
  '<div>唯一实质变化是常态基线 <b>normal '
  + str(m3["normal_n"]) + ' → ' + str(m4["normal_n"]) +
  '</b>（+345 天）。A / B 两条点云的主判据仍均为「无法判定（含数据不足）」，'
  'J2 事前提前 pre10 两线显著格仍为 0 / 0，14 条推测逐条判定'
  '<b>零变化</b>（5 支持 / 0 矛盾 / 9 无法判定），停止门槛仍为'
  '「两线主判据均未检出」。危机中 / 危机前主状态组的双闸门显著格'
  '<b>v0.3 = 0，v0.4 = 0</b>。</div></div>')
a('<div class="card note"><b>本报告不评估预警绩效</b>：不计算 PR-AUC / IC / 夏普 / 仓位 / '
  '误报率，不读取 Gate 1 封存的 2025 模型评分数据集，不做阈值反选。'
  '按冻结措辞规则，两版判定一致时只能写「补齐 345 天真实行情未改变结论」；'
  '<b>不得写成「验证了 TDA 无效」或任何全称外推</b>。</div>')

# 1 why
a("<h2>1. 为什么有 v0.4：一个数据/实现缺陷，不是新实验</h2>")
a('<div class="card"><table><tr><th>环节</th><th>事实</th></tr>'
  '<tr><td>最初错话</td><td>v0.1 规格写「万得全A 日线止于 2025-05-30」，'
  '标签脚本 <code>build_regime_labels.py</code> 把之后 345 天无条件标为 '
  '<code>undefined_after_2025_05_30</code>，5 个版本全部覆盖，'
  '<code>bull_bear_defined</code> 整段置 0</td></tr>'
  '<tr><td>用户质疑</td><td>「万得全A日线是查不到还是什么别的原因，后面的没有？」</td></tr>'
  '<tr><td>查证结果</td><td>不是取不到，是 2026-11-07 那次 '
  '<code>get_index_kline</code> 显式传了 '
  '<code>end_date="2025-05-30"</code>（对齐兴业研报 2015/07—2025/05 报告期）；'
  '该接口 end_date 必填。数据库个股与 15 个指数均覆盖到 2026-11-04</td></tr>'
  '<tr><td>方案选择</td><td>用户先选「2：升 v0.4 独立版本」，'
  '在查明连接器可取真数据后改选「A：用真 881001.WI 重做」；'
  'Gate0 收益率续接方案整体作废，产物另存 <code>*_gate0_superseded.*</code> 留痕</td></tr>'
  '<tr><td>变更性质</td><td>由数据可用性缺陷触发，在看到任何 v0.4 判定之前冻结；'
  '<b>不新建信号/特征/点云、不改窗口/模型/阈值、不做绩效</b></td></tr></table></div>')

# 2 engineering acceptance
a("<h2>2. 真数据落盘与标签工程验收</h2>")
a('<div class="card"><div class="kv">'
  '<div>数据源</div><div>Wind <code>get_index_kline(881001.WI, '
  '2025-05-30..2026-11-04)</code>，同一连接器、同一指数</div>'
  '<div>原始快照</div><div class="mono">third_party/wind/'
  '881001WI_day_20250530_20261104.json</div>'
  '<div>提取方式</div><div>从会话 JSONL 逐字提取工具原始返回，无手工转录</div>'
  '<div>拼接点</div><div>2025-05-30 OHLC 与冻结前段逐值差 0；'
  '全程单一序列，无锚定、无收益率换算、无点位跳变</div>'
  '<div>后段覆盖</div><div>347 行真日线（2025-06-03 收 5100.58 → '
  '2026-11-04 收 5641.11）；345 个标签日 100% 有真实价格</div>'
  '<div>前段</div><div>2994 天 × 55 列与 v0.1 逐位一致（差异格 0），不重取、不改写</div>'
  '<div>后段危机</div><div><code>crisis_in=0 / pre20=0</code> → '
  '危机组与危机前组完全不变</div>'
  '<div>常态基线</div><div>' + str(m3["normal_n"]) + ' → ' +
  str(m4["normal_n"]) + '（+345），这是 8340 格每一格共用的对照组</div>'
  '</div></div>')
a('<div class="card"><h3>12 项验收与确定性</h3><ul>'
  '<li>标签验收 <code>regime_v04_label_acceptance.json</code>：<b>'
  + str(A["all_passed"]) + '</b>，失败项 '
  + str([k for k, v in A["checks"].items() if not v]) + '</li>'
  '<li>两次标签重建 CSV sha256 逐位一致；判定脚本两次重跑 '
  '<b>stdout / grid / verdicts / side_by_side / compare_summary 全部逐位一致</b></li>'
  '<li>判定脚本带 <code>V04_CONFIRMED</code> 硬开关与 '
  '<code>benchmark_source</code> 防护，确认前直接运行会拒绝执行</li>'
  '</ul></div>')

# 3 primary side by side
a("<h2>3. 新旧并列：主判据与关键标量</h2>")
a('<div class="card"><table><tr><th>项目</th><th>v0.3（冻结）</th>'
  '<th>v0.4（OPTION A）</th><th>是否改变</th></tr>')
a('<tr><td>标签日历</td><td>3339 日（后 345 天未定义）</td>'
  '<td>3339 日（全部有定义）</td><td class="chg">是 · 唯一变更</td></tr>')
a('<tr><td>常态基线 normal_n</td><td>' + str(m3["normal_n"]) +
  '</td><td>' + str(m4["normal_n"]) + '</td><td class="chg">+345</td></tr>')
a('<tr><td>危机中日级样本</td><td>' + str(m3["crisis_in_daily_n"]) +
  '</td><td>' + str(m4["crisis_in_daily_n"]) + '</td><td class="same">否</td></tr>')
a('<tr><td>纳入事件数</td><td>' + str(m3.get("included_events", 14)) +
  '</td><td>' + str(m4.get("included_events", 14)) +
  '</td><td class="same">否</td></tr>')
a('<tr><td>主判据 A</td><td>' + badge(p3["A"]["verdict"]) +
  '</td><td>' + badge(p4["A"]["verdict"]) + '</td><td class="same">否</td></tr>')
a('<tr><td>主判据 B</td><td>' + badge(p3["B"]["verdict"]) +
  '</td><td>' + badge(p4["B"]["verdict"]) + '</td><td class="same">否</td></tr>')
a('<tr><td>A 事件级显著格</td><td>' + str(p3["A"]["n_event_sig_cells"]) +
  '</td><td>' + str(p4["A"]["n_event_sig_cells"]) +
  '</td><td class="same">否</td></tr>')
a('<tr><td>B 事件级显著格</td><td>' + str(p3["B"]["n_event_sig_cells"]) +
  '</td><td>' + str(p4["B"]["n_event_sig_cells"]) +
  '</td><td class="same">否</td></tr>')
a('<tr><td>J2 事前提前 pre10 显著格</td><td>' +
  str(len(J3["J2_ex_ante"]["A"].get("pre10_sig_cells", []))) + ' / ' +
  str(len(J3["J2_ex_ante"]["B"].get("pre10_sig_cells", []))) +
  '</td><td>' +
  str(len(J4["J2_ex_ante"]["A"].get("pre10_sig_cells", []))) + ' / ' +
  str(len(J4["J2_ex_ante"]["B"].get("pre10_sig_cells", []))) +
  '</td><td class="same">否</td></tr>')
a('<tr><td>14 条推测计数</td><td>' +
  str(J3["conjecture_counts"]) + '</td><td>' +
  str(J4["conjecture_counts"]) + '</td><td class="same">否</td></tr>')
a('<tr><td>停止门槛</td><td>' + W(str(J3["stop_threshold"]["result"])) +
  '</td><td>' + W(str(J4["stop_threshold"]["result"])) +
  '</td><td class="same">否</td></tr>')
a('</table><div class="small">判定脚本 keypack 逐键对照：'
  '<b>唯一改变的键是 <code>normal_n</code></b>（'
  + str(S["keypack_changed_keys"]) + '）；其余主判据、J2、推测计数、'
  '停止门槛、grid_rows、crisis_in_daily_n 全部相同。</div></div>')

# 4 grid
a("<h2>4. 全网格逐格对照</h2>")
a('<div class="card"><table><tr><th>指标</th><th>v0.3</th><th>v0.4</th></tr>'
  '<tr><td>网格行数</td><td>' + str(len(G3)) + '</td><td>' +
  str(len(G4)) + '</td></tr>'
  '<tr><td>过 Bonferroni(12) 且 CI 不跨零</td><td>' + str(len(s3)) +
  '</td><td>' + str(len(s4)) + '</td></tr>'
  '<tr><td>其中按线</td><td>' +
  W(str(dict(Counter(r["line"] for r in s3)))) + '</td><td>' +
  W(str(dict(Counter(r["line"] for r in s4)))) + '</td></tr>'
  '<tr><td>按状态</td><td>' +
  W(str(dict(Counter(r["state"] for r in s3)))) + '</td><td>' +
  W(str(dict(Counter(r["state"] for r in s4)))) + '</td></tr>'
  '<tr><td><b>危机中 / 危机前主状态组显著格</b></td><td><b>' +
  str(sum(1 for r in s3 if r["state"] in MAIN)) + '</b></td><td><b>' +
  str(sum(1 for r in s4 if r["state"] in MAIN)) + '</b></td></tr>'
  '</table></div>')
a('<div class="card"><h3>8340 格逐格并列（<code>regime_v04_vs_v03_side_by_side.csv</code>）</h3>'
  '<div class="kv">'
  '<div>并列行数</div><div>' + str(sb["rows"]) + '（键集合完全一致，无缺失格）</div>'
  '<div>delta 改变</div><div>' + str(sb["delta_changed_cells"]) +
  ' 格 —— 常态基线换了，几乎所有共用该对照组的格子数值都会动</div>'
  '<div>显著判定翻转</div><div>' + str(sb["sig_changed_cells"]) +
  ' 格（新增 ' + str(sb["sig_gained"]) + ' / 消失 ' +
  str(sb["sig_lost"]) + '）</div>'
  '</div>')
chg = [r for r in SB if r["sig_changed"] == "1"]
gained = Counter(r["state"] for r in chg
                 if r["sig_v03"] == "0" and r["sig_v04"] == "1")
lost = Counter(r["state"] for r in chg
               if r["sig_v03"] == "1" and r["sig_v04"] == "0")
a('<table><tr><th>翻转方向</th><th>按状态分布</th><th>按线</th></tr>'
  '<tr><td>新增显著 ' + str(sum(gained.values())) +
  '</td><td>' + W(str(dict(gained))) + '</td><td rowspan="2">' +
  W(str(dict(Counter(r["line"] for r in chg)))) + '</td></tr>'
  '<tr><td>消失显著 ' + str(sum(lost.values())) + '</td><td>' +
  W(str(dict(lost))) + '</td></tr></table>'
  '<div class="small"><b>解释</b>：全部 90 个翻转集中在 '
  '<code>bear / pre_high_vol / bull / fuzzy / pre_low_vol</code>，'
  '即牛熊状态与放量缩量分型；这些组本身就是用 MA250、回撤、成交额等构造的，'
  '新增 345 天样本会机械地改变它们的中位数差与显著性。'
  '<b>没有一格落在 crisis_in / pre5 / pre10 / pre20 / bear_in_crisis</b>，'
  '因此不构成危机提前量的证据。</div></div>')

# 5 pseudo significance
a("<h2>5. 为什么不看 p 值单列：退化伪显著披露</h2>")
a('<div class="card"><table><tr><th>版本</th><th>p_raw &lt; 0.0041667</th>'
  '<th>双闸门（+CI 不跨零）</th><th>主状态 p 通过</th>'
  '<th>其中 delta=0 的退化格</th><th>主状态 CI 含 0</th></tr>')
for tag, g in (("v0.3", G3), ("v0.4", G4)):
    pp = [r for r in g if T(r["p_bonferroni_pass"])]
    mp = [r for r in g if r["state"] in MAIN and T(r["p_bonferroni_pass"])]
    a('<tr><td>' + tag + '</td><td>' + str(len(pp)) + '</td><td>' +
      str(len(sig(g))) + '</td><td>' + str(len(mp)) + '</td><td>' +
      str(sum(1 for r in mp if abs(float(r["delta"])) < 1e-15)) +
      '</td><td>' + str(sum(1 for r in mp if T(r["ci_crosses_zero"]))) +
      '</td></tr>')
a('</table><div class="small">常数 / 退化列（如 '
  '<code>components_at_delta</code>、部分状态全 0 的 <code>h1_count</code>）'
  '会算出 <code>delta=0, CI=[0,0], p=0</code> 的伪显著；'
  '「CI 不含 0」这第二道闸门把它们全部挡掉。'
  '<b>两版主状态双闸门后都是 0 格</b>，这才是「未检出」的底层来源。'
  'v0.4 的 ' + str(len(s4)) + ' 个显著格反过来全部 '
  '<code>delta≠0、CI 宽度≠0、degenerate=False</code>，'
  '中位 |标准化效应| ≈ ' +
  fmt(sorted(abs(float(r["std_effect"])) for r in s4)[len(s4) // 2], 3) +
  '，不是数值退化造成的。</div></div>')

# 6 equivalence
a("<h2>6. 等价性 / 确定性自检（第二遍判定）</h2>")
a('<div class="card"><div class="kv">'
  '<div>性质</div><div><b>不是敏感性分析</b>。全程单一 881001.WI 序列，'
  '没有跨两套收益来源的混合 MA250 窗口，'
  '<code>mixed_ma250_window</code> 恒 0</div>'
  '<div>清空天数</div><div>' + str(eq["days_cleared"]) + '（必须 = 0）</div>'
  '<div>两遍 grid</div><div>逐字节相同 = <b>' +
  str(eq["grid_bytes_identical"]) + '</b></div>'
  '<div>keypack 差异</div><div>' + str(eq["keypack_changed_vs_v0_4_main"]) +
  '</div>'
  '<div>显著格</div><div>' + str(eq["sig_cells"]) + '</div>'
  '<div>自检通过</div><div><b>' + str(eq["passed"]) + '</b></div>'
  '</div><div class="small">脚本带硬断言：若 <code>cleared≠0</code>、'
  '两遍 grid 不一致或 keypack 不一致，直接抛错、不产出判定产物。'
  '报告措辞不得写成「排除了混合窗口的敏感性结果」。</div></div>')

# 7 conjectures
a("<h2>7. 14 条推测逐条并列</h2>")
a('<div class="card"><table><tr><th>ID</th><th>线别</th><th>v0.1</th>'
  '<th>v0.3</th><th>v0.4</th><th>是否改变</th></tr>')
for c3, c4 in zip(J3["conjectures"], J4["conjectures"]):
    v3, v4 = c3["v0_3_verdict"], c4["v0_3_verdict"]
    a('<tr><td class="mono">' + W(c3["id"]) + '</td><td>' +
      W("|".join(c3["lines"])) + '</td><td>' + badge(c3["v0_1_verdict"]) +
      '</td><td>' + badge(v3) + '</td><td>' + badge(v4) + '</td><td>' +
      ('<span class="same">否</span>' if v3 == v4
       else '<span class="chg">是</span>') + '</td></tr>')
a('</table><div class="small">判定变化清单：' +
  W(str(S["conjecture_verdict_changes"])) +
  '。5 条「支持」为 C03 / C04 / C05 / C06 / C09，其中 C04 支持的是'
  '「危机前与常态无稳定差异」这一否定式命题；'
  '<b>没有任何一条支持危机可被提前识别</b>。</div></div>')

# 8 erratum
a("<h2>8. 归因更正（写进规格的勘误）</h2>")
a('<div class="card warn"><b>上一版有一句归因是错的：</b>'
  '曾把后段 <code>overheat=283/345</code> 说成「链式拼接的构造性偏差、'
  '不是市场真实过热」。换成真数据后仍为 <b>279/345</b>，'
  '两版只差 6 天，说明与拼接无关。主因是 '
  '<code>oh4 = pct750 &gt; 0.90</code>：2025-07～2026-05 是真实单边上行'
  '（+36.5%），收盘几乎天天落在自己过去 750 日的前 10%；'
  '2026-07 回撤后 overheat 下降、oversold 上升。'
  '<b>正确说法是「第三层附加标签在趋势市几乎恒触发、区分度低」</b>。'
  '原错误段落保留作归因错误的审计留痕，见规格 '
  '<code>ERRATUM_attribution</code>。'
  '<br><br>这两组<b>仍不进 8340 格网格</b>：v0.3 宽表 67 列本就不含 '
  '<code>overheat</code>/<code>oversold</code>，'
  '<code>build_masks</code> 用 zeros 兜底，两版各 695 格全为 '
  '<code>n_a=0 / degenerate</code>。这是 v0.3 的既有缺陷，'
  '本版不修、不补列、不借机改网格结构，只登记。</div>')

# 9 boundary
a("<h2>9. 边界与措辞规则</h2>")
a('<div class="card"><ul>'
  '<li>v0.1 / v0.2 / v0.3 的规格、脚本、判定、网格、报告、台账'
  '<b>一律未覆盖、未回改、未重新解释</b>；Gate0 续接版三个产物另存留痕</li>'
  '<li>Gate 1 封存的 2025 <b>模型评分数据集</b>未读取——本轮取回的 '
  '881001.WI 是公开指数行情，仅用于牛熊状态标签定义；Gate 2 未启动；'
  'PHTI 正式绩效回测未运行</li>'
  '<li>无绩效 / IC / 夏普 / PR-AUC / 仓位 / 误报率；'
  '未做阈值或窗口反选；未改 <code>config/study.toml</code></li>'
  '<li>判定口径一字不改：三层规则、5 个标签版本、D3 排除(3,16)、'
  '14 事件、20 日区块自助 B=1000、Bonferroni(12)=0.0041667、'
  '双闸门、事件级去重主读数、三档判定、停止门槛</li>'
  '<li><b>允许写的</b>：在 w=10、14 事件、当前行业价格数据、'
  '补足 345 天定义后，两线主判据仍未检出；补齐真实行情未改变 v0.3 结论</li>'
  '<li><b>不得写的</b>：「验证了 TDA 无效」「TDA 对 A 股做不到」'
  '「危机预警无效」等全称外推；也不得把 90 个牛熊/放量格翻转'
  '包装成危机可检出性的改善</li>'
  '<li>本轮是同一数据缺陷的第二次修正（Gate0 续接 → 真数据），'
  '判定一跑即冻结，<b>不再以「再补一段数据」为由第三次重算</b></li>'
  '</ul></div>')

# 10 deliverables
a("<h2>10. 交付物</h2>")
a('<div class="card"><ul>'
  '<li><code>outputs/regime_v04_extension_report.html</code>（本报告）</li>'
  '<li><code>outputs/regime_v04_conclusion_ledger.csv</code>（' +
  str(len(ledger)) + ' 行结论台账，含 v0_3 / v0_4 逐条并列与 changed 列）</li>'
  '<li><code>outputs/regime_v04_verdicts.json</code> / '
  '<code>regime_v04_grid.csv</code>（' + str(len(G4)) + ' 行全网格）</li>'
  '<li><code>outputs/regime_v04_vs_v03_side_by_side.csv</code>（' +
  str(sb["rows"]) + ' 行逐格并列）</li>'
  '<li><code>outputs/regime_v04_compare_summary.json</code>（新旧 keypack '
  '对照、翻转计数、等价性自检）</li>'
  '<li><code>outputs/regime_v04_grid_equivalence_check.csv</code> / '
  '<code>regime_v04_verdicts_equivalence_check.json</code>（第二遍自检产物）</li>'
  '<li><code>outputs/regime_daily_labels_v04.csv</code> / '
  '<code>regime_v04_label_acceptance.json</code> / '
  '<code>xy_wind_all_a_daily_v04_audit.json</code>（标签与真数据审计）</li>'
  '<li><code>config/regime_split_check_v0.4.toml</code>（冻结规格，'
  '含 OPTION A amendment、ERRATUM、confirmation、judgement_run）</li>'
  '<li>脚本 <code>import_wind_extension.py</code> / '
  '<code>build_v04_labels.py</code> / '
  '<code>verify_v04_extension.py</code> / '
  '<code>build_v04_report.py</code></li>'
  '</ul></div>')

a('<div class="foot">v0.4 OPTION A · 生成于 2026-11-09 · '
  '展示层只读已冻结产物，不重新计算任何统计量 · '
  '全部结果为样本内描述性对账，不可用于实盘或绩效宣称</div>')
a('</div></body></html>')

rp = OUT / "regime_v04_extension_report.html"
rp.write_text("\n".join(P), encoding="utf-8")
print(json.dumps({
    "report": str(rp), "ledger": str(lp),
    "report_bytes": rp.stat().st_size, "ledger_rows": len(ledger),
    "grid_rows": {"v0_3": len(G3), "v0_4": len(G4)},
    "sig_cells": {"v0_3": len(s3), "v0_4": len(s4)},
    "main_state_sig": {"v0_3": sum(1 for r in s3 if r["state"] in MAIN),
                       "v0_4": sum(1 for r in s4 if r["state"] in MAIN)},
    "keypack_changed_keys": S["keypack_changed_keys"],
    "equivalence_passed": eq["passed"],
    "conjecture_verdict_changes": S["conjecture_verdict_changes"],
}, ensure_ascii=False, indent=2))
