"""Build the standalone offline Chinese report for v0.6 early curves."""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
PREFIX = "crisis_context_v06_early_"
REPORT = OUT / (PREFIX + "report.html")
D = json.loads((OUT / (PREFIX + "chart_data.json")).read_text(encoding="utf-8"))
M = json.loads((OUT / (PREFIX + "manifest.json")).read_text(encoding="utf-8"))
assert all(M["validation"].values())


class HtmlParts(list):
    """List of HTML fragments; allow append(fragment1, fragment2, ...)."""
    def append(self, *items):
        for item in items:
            super().append(item)


CN = {
    "a16_W_t": "十六行业·相邻持续图二阶威尔斯特拉斯距离之和",
    "a16_h0_death_mean": "十六行业·零维死亡值均值",
    "a16_h0_death_max": "十六行业·零维最大死亡值",
    "a16_h1_count": "十六行业·一维环数量",
    "a16_h1_birth_mean": "十六行业·一维环平均出生值",
    "a16_window_rms": "十六行业·窗口收益均方根",
    "a16_avg_pair_corr": "十六行业·平均成对相关",
    "a16_leading_eig_share": "十六行业·领先特征值占比",
    "b_n_nodes": "行业相关点云·合格行业节点数",
    "b_h2_count": "行业相关点云·二维空腔数量",
    "b_h1_count": "行业相关点云·一维环数量",
    "b_h2_landscape_l1": "行业相关点云·二维持续景观一阶范数",
    "b_industry_average_correlation": "行业相关点云·行业平均相关",
    "b_correlation_leading_eigenvalue_share": "行业相关点云·相关矩阵领先特征值占比",
    "b_xy_h0_death_mean": "行业相关点云·零维死亡值均值",
}
FIELD_CN = {
    "date": "日期", "phase": "阶段", "offset_from_onset": "相对事件起点交易日",
    "benchmark_close": "万得全A收盘点位", "benchmark_ret_pct": "万得全A相邻标签日收益（百分比）",
    "state_v0_primary": "牛熊状态", "crisis_in": "急性统计标签",
    "crisis_event_id": "工程原事件编号", "is_crisis_day": "是否危机段",
    "display_event_id": "统一事件编号", "event_id": "工程原事件编号",
    "onset": "事件起点", "end": "事件终点", "n_crisis_days": "危机段交易日数",
    "window_start": "窗口首日", "window_end": "窗口末日", "window_rows": "窗口总行数",
    "a16_window_summary_days": "十六行业有摘要天数",
    "b_window_summary_days": "行业相关点云有摘要天数",
    "a27_window_summary_days": "二十七行业有摘要天数",
    "b_nodes_min": "窗口内最少节点数", "b_nodes_max": "窗口内最多节点数",
    "coverage_note": "覆盖说明", **CN,
}
for k, v in {
    "pre20": "危机前二十日", "crisis": "危机段", "post20": "危机后二十日",
    "bull": "牛市", "bear": "熊市", "fuzzy": "模糊", "undefined_warmup": "预热未定义",
}.items():
    FIELD_CN[k] = v


def esc(x):
    return html.escape(str(x), quote=True)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fmt(x, digits=6):
    v = num(x)
    return "" if v is None else f"{v:.{digits}f}".rstrip("0").rstrip(".")


def decimal(x):
    v = num(x)
    if v is None or v == 0:
        return "0"
    return f"{v:.12f}".rstrip("0").rstrip(".")


def table(headers, rows):
    out = ["<div class='scroll'><table><thead><tr>"]
    for key, label in headers:
        out.append(f"<th title='{esc(key)}'>{esc(label)}</th>")
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for key, _ in headers:
            value = row.get(key, "")
            if key in CN:
                value = fmt(value)
            out.append(f"<td title='{esc(key)}'>{esc(value)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


CSS = """
:root{--ink:#172033;--muted:#5f6b7a;--line:#dce2ea;--blue:#2458b8;--red:#c9362b;--soft:#f5f7fb}
*{box-sizing:border-box}body{margin:0;background:#eef2f7;color:var(--ink);font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;line-height:1.7}
.wrap{max-width:1420px;margin:auto;padding:24px}header,.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px;margin-bottom:18px;box-shadow:0 3px 14px rgba(30,50,80,.04)}
h1{font-size:28px;margin:0 0 10px}h2{font-size:21px;margin:0 0 14px}h3{font-size:17px;margin:20px 0 8px}.sub,.small{color:var(--muted);font-size:13px}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:16px}.kpi{background:var(--soft);border-radius:10px;padding:14px}.kpi b{display:block;font-size:25px;color:var(--blue)}
.note,.warn,.ok,.empty-state{padding:12px 14px;border-radius:9px;margin:10px 0}.note{background:#f2f6fd;border-left:4px solid var(--blue)}.warn{background:#fff7e6;border-left:4px solid #c77c02}.ok{background:#eef8f1;border-left:4px solid #24824b}.empty-state{background:#fff7e6;text-align:center;min-height:120px;display:flex;align-items:center;justify-content:center;flex-direction:column}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}.method{border:1px solid var(--line);border-radius:10px;padding:15px;background:#fbfcfe}.ctrl{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:10px 0}select{font:inherit;padding:8px 10px;max-width:100%;border:1px solid #b9c4d3;border-radius:7px;background:#fff;color:var(--ink)}
.scroll{overflow:auto;max-height:620px;border:1px solid var(--line);border-radius:9px}table{border-collapse:collapse;width:100%;font-size:12px;background:#fff}th{position:sticky;top:0;background:#eaf0f8;color:#23334a;z-index:1}th,td{padding:7px 9px;border-bottom:1px solid #e8ecf2;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}tr:hover td{background:#f7f9fc}.chartbox{border:1px solid var(--line);border-radius:9px;padding:10px;margin:12px 0;min-height:120px}svg{display:block;width:100%;height:auto}.legend{font-size:12px;color:var(--muted)}.links a{display:inline-block;margin:5px 10px 5px 0;color:var(--blue);text-decoration:none;border-bottom:1px solid #9db5df}footer{color:var(--muted);font-size:12px;text-align:center;padding:15px}
@media(max-width:700px){.wrap{padding:10px}header,.card{padding:15px}h1{font-size:23px}.grid{grid-template-columns:1fr}}
"""

JS = r"""
const D=JSON.parse(document.getElementById('payload').textContent);
const CN=__CN__;
const FIELD_CN=__FIELD_CN__;
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const isNum=v=>v!==null&&v!==''&&Number.isFinite(Number(v));
const fmt=v=>{if(!isNum(v))return '—';const x=Number(v);if(Number.isInteger(x)&&Math.abs(x)<1e8)return String(x);return x.toFixed(6).replace(/0+$/,'').replace(/\.$/,'');};
function lineChart(e,k){
  const rows=e.rows,valid=rows.filter(r=>isNum(r[k]));
  if(!valid.length)return '<div class="empty-state"><b>当前事件与指标没有可绘制的实测值。</b><br>请查看下方覆盖原因，空白不被当作零。</div>';
  const W=960,H=340,L=72,R=24,T=24,B=48,pw=W-L-R,ph=H-T-B;
  const xs=rows.map(r=>Number(r.offset_from_onset)),ys=valid.map(r=>Number(r[k]));
  let xmin=Math.min.apply(null,xs),xmax=Math.max.apply(null,xs),ymin=Math.min.apply(null,ys),ymax=Math.max.apply(null,ys);
  if(xmin===xmax){xmin-=1;xmax+=1;} if(ymin===ymax){const d=Math.abs(ymin)||1;ymin-=d*.1;ymax+=d*.1;}
  const pad=(ymax-ymin)*.08;ymin-=pad;ymax+=pad;
  const X=x=>L+(x-xmin)/(xmax-xmin)*pw,Y=y=>T+(ymax-y)/(ymax-ymin)*ph;
  const crisis=rows.filter(r=>r.phase==='crisis').map(r=>Number(r.offset_from_onset));
  let s='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(CN[k]||k)+'">';
  if(crisis.length){const a=Math.min.apply(null,crisis),b=Math.max.apply(null,crisis);s+='<rect x="'+X(a)+'" y="'+T+'" width="'+Math.max(1,X(b)-X(a))+'" height="'+ph+'" fill="#fff0ed"/>';}
  for(let i=0;i<=5;i++){const y=ymin+(ymax-ymin)*i/5,yy=Y(y);s+='<line x1="'+L+'" y1="'+yy+'" x2="'+(W-R)+'" y2="'+yy+'" stroke="#e3e8ef"/><text x="'+(L-8)+'" y="'+(yy+4)+'" text-anchor="end" font-size="11" fill="#596779">'+fmt(y)+'</text>';}
  if(ymin<0&&ymax>0)s+='<line x1="'+L+'" y1="'+Y(0)+'" x2="'+(W-R)+'" y2="'+Y(0)+'" stroke="#8c98a8" stroke-dasharray="4 3"/>';
  let path='',open=false;
  rows.forEach(r=>{if(isNum(r[k])){const x=Number(r.offset_from_onset),y=Number(r[k]);path+=(open?' L':' M')+X(x).toFixed(2)+' '+Y(y).toFixed(2);open=true;}else open=false;});
  s+='<path d="'+path+'" fill="none" stroke="#2458b8" stroke-width="2.2"/>';
  rows.forEach(r=>{if(isNum(r[k])){const x=Number(r.offset_from_onset),y=Number(r[k]);s+='<circle cx="'+X(x)+'" cy="'+Y(y)+'" r="2.8" fill="#2458b8"><title>'+esc(r.date+'；'+CN[k]+'：'+fmt(y)+'；节点数：'+r.b_n_nodes)+'</title></circle>';}});
  const ticks=Array.from(new Set([xmin,0,xmax].filter(x=>x>=xmin&&x<=xmax)));
  ticks.forEach(x=>{s+='<line x1="'+X(x)+'" y1="'+T+'" x2="'+X(x)+'" y2="'+(H-B)+'" stroke="#bac4d1" stroke-dasharray="3 3"/><text x="'+X(x)+'" y="'+(H-B+22)+'" text-anchor="middle" font-size="12" fill="#46546a">'+x+'</text>';});
  s+='<text x="'+(L+pw/2)+'" y="'+(H-8)+'" text-anchor="middle" font-size="12" fill="#46546a">相对急性统计标签起点的交易日</text></svg>';
  return s;
}
function audit(e,k){
  const meta=D.metric_coverage[k],valid=e.rows.filter(r=>isNum(r[k]));
  let structural=0,uncovered=0,gaps=0;
  e.rows.forEach(r=>{if(isNum(r[k]))return;
    if(k==='a16_h1_birth_mean'&&String(r.a16_h1_count)==='0'){structural++;return;}
    if(r.date<meta.first||r.date>meta.last)uncovered++;else gaps++;});
  return {valid:valid.length,structural:structural,uncovered:uncovered,gaps:gaps};
}
(function(){
  const sel=$('evSelect'),met=$('evMetric');
  D.events.forEach(e=>sel.add(new Option('统一事件 '+e.display_event_id+'｜工程原编号 '+e.event_id+'｜'+e.onset+' 至 '+e.end,e.event_id)));
  D.metrics.forEach(k=>met.add(new Option(CN[k]||k,k)));
  met.value='a16_W_t';
  function cur(){return D.events.find(e=>e.event_id===sel.value)||D.events[0];}
  function detail(e,k){
    const cols=['date','phase','offset_from_onset','benchmark_close','benchmark_ret_pct','b_n_nodes',k];
    let s='<div class="scroll"><table><thead><tr>'+cols.map(c=>'<th title="'+esc(c)+'">'+esc(FIELD_CN[c]||CN[c]||c)+'</th>').join('')+'</tr></thead><tbody>';
    e.rows.forEach(r=>{s+='<tr>'+cols.map(c=>{let v=r[c];if(c==='phase')v=FIELD_CN[v]||v;else if(c===k||c==='benchmark_close'||c==='benchmark_ret_pct')v=fmt(v);return '<td title="'+esc(c)+'">'+esc(v)+'</td>';}).join('')+'</tr>';});
    return s+'</tbody></table></div>';
  }
  function draw(){
    const e=cur(),k=met.value,a=audit(e,k);
    $('evChart').innerHTML=lineChart(e,k);
    const parts=['当前指标有效 '+a.valid+' 行'];if(a.structural)parts.push('结构性无定义 '+a.structural+' 行');if(a.uncovered)parts.push('未覆盖 '+a.uncovered+' 行');if(a.gaps)parts.push('覆盖期内待核空值 '+a.gaps+' 行');
    $('evInfo').innerHTML='<b>统一事件 '+esc(e.display_event_id)+'（工程原编号 '+esc(e.event_id)+'）</b>：'+esc(e.onset)+' 至 '+esc(e.end)+'；危机段 '+esc(e.n_crisis_days)+' 日，整窗 '+esc(e.window_rows)+' 行。十六行业有摘要 '+esc(e.a16_window_summary_days)+' 行；行业相关点云有摘要 '+esc(e.b_window_summary_days)+' 行；节点数 '+esc(e.b_nodes_min)+'—'+esc(e.b_nodes_max)+'。'+esc(parts.join('；'))+'。';
    $('evDetail').innerHTML=detail(e,k);
  }
  sel.onchange=draw;met.onchange=draw;draw();
})();
"""


def build():
    sample = D["sample"]
    acceptance = D["acceptance"]
    a16 = acceptance["a16_overlap"]
    b = acceptance["b_overlap"]
    det = acceptance["b_determinism"]
    bmeta = acceptance["b"]
    payload = json.dumps(D, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    js = JS.replace("__CN__", json.dumps(CN, ensure_ascii=False))
    js = js.replace("__FIELD_CN__", json.dumps(FIELD_CN, ensure_ascii=False))
    parts = HtmlParts(["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             "<title>第六版早期危机上下文补算报告</title><style>", CSS, "</style></head><body><div class='wrap'>"])
    parts.append("<header><h1>第六版早期危机上下文补算报告</h1>",
                 "<div class='sub'>独立预登记、独立补算、独立产物｜早期二十八个急性统计事件｜只做样本内描述，不更新十四条推测判定</div>",
                 "<div class='kpis'>",
                 f"<div class='kpi'><b>{sample['events']}</b>早期统计事件</div>",
                 f"<div class='kpi'><b>{sample['window_rows']}</b>事件窗逐日记录</div>",
                 f"<div class='kpi'><b>{sample['a16_full_window_events']}／28</b>十六行业整窗覆盖事件</div>",
                 f"<div class='kpi'><b>{sample['b_full_window_events']}／28</b>行业相关点云整窗覆盖事件</div>",
                 f"<div class='kpi'><b>{bmeta['n_nodes_min']}—{bmeta['n_nodes_max']}</b>早期逐日合格行业节点范围</div>",
                 "</div><div class='ok'><b>这次是真正的持续同调补算，不是展示替代。</b>",
                 "十六行业状态点云由独立完整双跑确认；行业相关点云完成全部早期合格日计算，并通过重叠期逐值验收与固定二十四日独立重算。",
                 "第五版数据、报告及五条支持／两条矛盾／七条无法判定的历史判定均未改写。</div></header>")

    parts.append("<section class='card'><h2>一、预登记范围与不可越过边界</h2>",
                 "<div class='grid'><div class='method'><h3>十六行业状态点云</h3>",
                 "<p>点是最对齐交易日；最近十个日对数收益形成十个点，每个点的坐标是固定十六个申万一级行业收益。",
                 "使用欧氏距离与最高一维持续复形；相邻窗口的零维、一维持续图分别计算二阶威尔斯特拉斯距离后求和。",
                 "新算段从 1999 年末开始，2005 年初起沿用同一面板、同一算法的冻结段，不跨入二十七行业面板。</p></div>",
                 "<div class='method'><h3>行业相关点云</h3>",
                 "<p>点是逐日合格的申万 2014 版二级行业；十一期正收盘价生成十期简单收益，坐标就是这十期收益。",
                 "距离为相关距离，计算零维、一维、二维摘要。节点名单同时满足三十一日基础资格和四种窗口交集规则，逐日保存，不补零、不回填。</p></div></div>",
                 "<div class='warn'><b>分类与解释边界：</b>早期二级行业使用事后固定的申万 2014 版名单，只用于样本内历史描述，不冒充当时实时名单。",
                 "完整二十七行业早期新增行业数据不足，本版没有伪造二十七行业曲线。行业相关点云与状态点云构造不同，不互相替代。</div>",
                 "<p class='small'>数据来源与时点：本地冻结行业行情库，早期一级行业计算截至 2005-03-31；二级行业计算截至 2013-03-29；报告事件与标签只读第五版前段，止于 2012-12-28。",
                 "本次没有读取或评分 2025 年最终测试集。</p></section>")

    parts.append("<section class='card'><h2>二、二十八个早期事件覆盖总表</h2>",
                 "<p>窗口定义为事件起点前二十个标签交易日、完整危机段、事件终点后二十个标签交易日。",
                 "“有摘要天数”按该组至少一项所选实测摘要有值计数；完整逐日字段在下载表中保留。</p>")
    ov_headers = [(k, FIELD_CN[k]) for k in [
        "display_event_id", "event_id", "onset", "end", "n_crisis_days", "window_rows",
        "a16_window_summary_days", "b_window_summary_days", "a27_window_summary_days",
        "b_nodes_min", "b_nodes_max"]]
    parts.append(table(ov_headers, D["events"]))
    parts.append("<div class='note'>统一编号只用于展示；工程原编号一百零一至一百二十八完整保留。",
                 "二十七行业覆盖天数仍为零，不表示十六行业或行业相关点云没有补算。</div></section>")

    parts.append("<section class='card'><h2>三、早期事件逐日曲线</h2>",
                 "<div class='ctrl'><label>选择事件</label><select id='evSelect'></select>",
                 "<label>曲线指标</label><select id='evMetric'></select></div>",
                 "<p class='small' id='evInfo'></p><div class='chartbox' id='evChart'></div>",
                 "<div class='legend'>浅红底为危机段；竖向虚线标出事件起点；鼠标悬停数据点可看日期、数值和当日行业节点数。</div>",
                 "<div class='note'>零个环或零个空腔是已经算出的真实零值。一维环数量为零时，平均出生值没有数学定义，单独列为结构性无定义；不以零代替。",
                 "图形只用于描述性核对，不提供危机命中率、提前量或有效／无效判断。</div>",
                 "<h3>当前事件逐日明细</h3><div id='evDetail'></div></section>")

    parts.append("<section class='card'><h2>四、工程验收与旧元数据勘误</h2>")
    acc_rows = [
        {"项目": "十六行业完整双跑", "结果": "通过", "读数": "两轮输出逐字节一致"},
        {"项目": "十六行业重叠期", "结果": "通过" if a16["passed"] else "未通过",
         "读数": f"形状比较 {a16['compared_shape_dates']} 日，距离比较 {a16['compared_W_dates']} 日，最大绝对差 {decimal(a16['max_abs_diff'])}"},
        {"项目": "行业相关点云重叠期", "结果": "通过" if b["passed"] else "未通过",
         "读数": f"一维／二维 {b['xy_dates']} 日，零维 {b['h0_dates']} 日，最大绝对差 {decimal(max(b['xy_max_abs_diff'], b['h0_max_abs_diff']))}；节点名单差异 {len(b['node_list_mismatch_dates'])} 日"},
        {"项目": "固定二十四日独立重算", "结果": "通过" if det["passed"] else "未通过",
         "读数": f"一维／二维最大绝对差 {decimal(det['xy_max_abs_diff'])}；零维最大绝对差 {decimal(det['h0_max_abs_diff'])}"},
        {"项目": "最小生成树与持续同调交叉核对", "结果": "通过",
         "读数": f"最大绝对差 {decimal(det['mst_vs_ripser_max_abs_diff'])}，低于跨实现容差 0.000001"},
        {"项目": "早期合格日", "结果": "已全覆盖" if bmeta["ineligible_days"] == 0 else "存在未覆盖",
         "读数": f"{bmeta['eligible_days']} 个合格日；资格不足 {bmeta['ineligible_days']} 日"},
    ]
    parts.append(table([("项目", "验收项目"), ("结果", "结论"), ("读数", "实际读数")], acc_rows))
    parts.append("<div class='warn'><b>接缝预热与首次失败如实保留：</b>首次验收发现旧十六行业文件的九个形状预热日及一个距离预热日为空。",
                 "追加修订只允许跳过这些由旧计算起点造成的空白；自旧首个有效日起，数值和空值掩码仍严格一致。",
                 "正式报告是在该修订后重新计算并通过验收生成的，不宣称首次运行即通过。</div>",
                 "<div class='note'><b>旧元数据勘误：</b>旧清单曾把十期窗口误写为九个收益。实际数组形状已逐日断言为十行、每列一个行业，即十一期收盘价生成十期简单收益。",
                 f"相应相关估计的费雪变换标准误说明为 {bmeta['fisher_z_standard_error']:.6f}；此勘误不改变任何既有拓扑数值。</div></section>")

    parts.append("<section class='card'><h2>五、独立产物下载</h2><div class='links'>")
    links = [
        ("regime_v06_early_phti_p16_w10.csv", "十六行业早期完整日级摘要"),
        ("regime_v06_early_xy_10.csv", "行业相关点云一维与二维日级摘要"),
        ("regime_v06_early_xy_h0_w10.csv", "行业相关点云零维日级摘要"),
        ("regime_v06_early_xy_eligibility.csv", "行业相关点云逐日节点资格审计"),
        ("regime_v06_early_xy_eligible.json", "行业相关点云逐日最终节点名单"),
        ("regime_v06_early_descriptive_daily.csv", "早期三千一百四十四日分线描述性宽表"),
        (PREFIX + "event_windows.csv", "二十八个事件逐日窗口明细"),
        (PREFIX + "event_overview.csv", "二十八个事件覆盖总表"),
        ("regime_v06_early_manifest.json", "补算运行清单与冻结边界"),
        (PREFIX + "manifest.json", "报告数据校验清单"),
    ]
    for href, label in links:
        parts.append(f"<a href='{esc(href)}' title='{esc(href)}'>{esc(label)}</a>")
    parts.append("</div><p class='small'>文件名和工程字段名只放在链接属性或表头悬停中；报告可见文本使用中文全称。</p></section>")

    parts.append("<section class='card'><h2>六、研究边界</h2><ul>")
    for x in D["boundaries"]:
        parts.append("<li>" + esc(x) + "</li>")
    _t = M["generated_at"]
    _zh_time = f"{_t[0:4]} 年 {int(_t[5:7])} 月 {int(_t[8:10])} 日 {_t[11:19]}"
    parts.extend([
        "<li>第六版没有重新运行区块自助法、显著性检验或十四条推测判定；第五版结论只作为冻结历史结果保留。</li>",
        "<li>本版不计算绩效、信息系数、夏普比率、命中率、提前量、召回率、误报、仓位或阈值。</li>",
        "<li>早期曲线补齐只消除产物覆盖缺口，不自动增强或削弱任何拓扑推测，不得外推为持续同调对 A 股危机预警有效或无效。</li>",
        "</ul></section><footer>第六版早期描述性扩展｜单文件离线报告｜生成时间：" + esc(_zh_time) + "</footer>",
        "</div><script id='payload' type='application/json'>", payload, "</script><script>", js, "</script></body></html>"])
    REPORT.write_text("".join(parts), encoding="utf-8")
    print(json.dumps({"report": str(REPORT), "bytes": REPORT.stat().st_size,
                      "events": len(D["events"]), "windows": sample["window_rows"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
