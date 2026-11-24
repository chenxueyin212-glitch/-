#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.18 封存验证期开箱检验（先登记后计算，见 config/regime_sealed_validation_v0.18.toml，
含 2026-11-16 修订 a1-a3）。只读冻结产物，不调参不换窗不重训。输出：
  outputs/regime_v018_episode_attribution.csv
  outputs/regime_v018_false_alarm_sealed.csv
  outputs/regime_v018_benchmark_episode_facts.csv
  outputs/regime_v018_summary.json
"""
from __future__ import annotations

import csv
import json
import hashlib
import os
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(BASE, "outputs")

VALIDATION_START = "2025-01-01"
DATA_END = "2026-11-03"
HIT_PAD = 20  # 交易日，认定窗两侧

NARRATIVE = [
    ("N1", "叙事一 三月地缘冲击", "2026-03-18", "2026-03-23", "浅快"),
    ("N2", "叙事二 七月科技踩踏", "2026-07-09", "2026-07-31", "浅快（板块深、宽基浅）"),
    ("N3", "叙事三 十月AI泡沫破裂", "2026-10-20", "2026-11-03", "深慢"),
]
LABEL = [
    ("L1", "标签段一", "2026-02-25", "2026-03-02"),
    ("L2", "标签段二", "2026-06-18", "2026-07-10"),
    ("L3", "标签段三", "2026-09-09", "2026-09-28"),
]

# 冻结事件认定窗（纯度注记用，v0.13 同构 [起点-20, 结束+20]）
FROZEN_EVENTS_NEAR = [
    ("16", "2024-12-12", "2024-12-12"),
    ("17", "2025-03-07", "2025-03-28"),
]

LAYERS = [
    ("S3 触发层（选定）", "regime_v015_lightpatch_false_alarm.csv", "policy", "S3", 9.9),
    ("REF8 实用候选（对照）", "regime_v015_lightpatch_false_alarm.csv", "policy", "REF8", 61.6),
    ("B10 消音链（选定）", "regime_v016_governed_pnl_false_alarm.csv", "variant", "B10", 29.9),
    ("G0 无治理（对照）", "regime_v016_governed_pnl_false_alarm.csv", "variant", "G0", 28.2),
]


def read_csv(name):
    with open(os.path.join(OUT, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_calendar():
    rows = read_csv("regime_v05_benchmark_daily.csv")
    return [r["date"] for r in rows], [float(r["benchmark_close"]) for r in rows]


def td_offset(dates, a, b):
    idx = {d: i for i, d in enumerate(dates)}
    return idx[b] - idx[a]


def shift_td(dates, d, k):
    idx = {d0: i for i, d0 in enumerate(dates)}
    i = idx[d]
    return dates[min(max(i + k, 0), len(dates) - 1)]


def episode_facts(dates, closes, start, end):
    idx = {d: i for i, d in enumerate(dates)}
    i0, i1 = idx[start], idx[end]
    seg = closes[i0: i1 + 1]
    peak, peak_d, mx, trough = seg[0], start, 0.0, start
    for j, d in enumerate(dates[i0: i1 + 1]):
        if seg[j] > peak:
            peak, peak_d = seg[j], d
        dd = seg[j] / peak - 1
        if dd < mx:
            mx, trough = dd, d
    return {
        "window": f"{start}..{end}",
        "ret": round(seg[-1] / seg[0] - 1, 4),
        "max_dd": round(mx, 4),
        "peak_date": peak_d,
        "trough_date": trough,
    }


def load_episodes(layer_file, filter_col, filter_val):
    rows = read_csv(layer_file)
    out = []
    for r in rows:
        if r[filter_col] != filter_val or r["episode_start"] < VALIDATION_START:
            continue
        out.append({
            "start": r["episode_start"], "end": r["episode_end"], "len": int(r["episode_len"]),
            "judged_type": r.get("judged_type", ""), "plan": r.get("final_plan_type", ""),
            "status": r.get("status", ""),
        })
    out.sort(key=lambda e: e["start"])
    return out


def build_events(dates):
    books = {"叙事": [], "标签": []}
    for eid, name, s, e, exp in NARRATIVE:
        books["叙事"].append({
            "def": "叙事", "id": eid, "name": name, "start": s, "end": e,
            "expected_type": exp, "win_start": shift_td(dates, s, -HIT_PAD),
            "win_end": shift_td(dates, e, HIT_PAD)})
    for eid, name, s, e in LABEL:
        books["标签"].append({
            "def": "标签", "id": eid, "name": name, "start": s, "end": e,
            "expected_type": "（标签无定性）", "win_start": shift_td(dates, s, -HIT_PAD),
            "win_end": shift_td(dates, e, HIT_PAD)})
    return books


def main():
    dates, closes = load_calendar()
    books = build_events(dates)
    fz_wins = [(eid, shift_td(dates, s, -HIT_PAD), shift_td(dates, e, HIT_PAD))
               for eid, s, e in FROZEN_EVENTS_NEAR]

    attribution_rows = []
    false_rows = []
    summary_layers = {}
    total_days = sum(1 for d in dates if VALIDATION_START <= d <= DATA_END)
    years = total_days / 243.0

    for layer_name, fname, fcol, fval, train_fa in LAYERS:
        eps = load_episodes(fname, fcol, fval)
        # 分账归因（修订 a1）：每本账独立匹配；同一警报段可各记一次
        attributed_ids = set()
        layer_hits = {}
        for book_name, events in books.items():
            used = set()
            for ev in events:
                hit = None
                for i, ep in enumerate(eps):
                    if i in used:
                        continue
                    if ep["end"] < ev["win_start"] or ep["start"] > ev["win_end"]:
                        continue
                    hit = (i, ep)
                    break
                if hit is None:
                    attribution_rows.append({
                        "layer": layer_name, "event_def": ev["def"], "event_id": ev["id"],
                        "event_name": ev["name"], "event_start": ev["start"], "event_end": ev["end"],
                        "hit": "漏", "first_alarm": "", "first_offset_td": "",
                        "offset_clamped": "", "timing_bin": "漏", "overlap_days": 0,
                        "judged_type": "", "plan": "", "engine_status": "",
                        "expected_type": ev["expected_type"],
                    })
                    continue
                i, ep = hit
                used.add(i)
                attributed_ids.add(i)
                first_raw = ep["start"]
                off_raw = td_offset(dates, ev["start"], first_raw)
                off_clamped = max(off_raw, -HIT_PAD)
                if first_raw < ev["start"]:
                    tbin = "提前"
                elif first_raw <= ev["end"]:
                    tbin = "窗内"
                else:
                    tbin = "损伤窗"
                ov_s = max(ep["start"], ev["win_start"])
                ov_e = min(ep["end"], ev["win_end"])
                ov = td_offset(dates, ov_s, ov_e) + 1 if ov_s <= ov_e else 0
                attribution_rows.append({
                    "layer": layer_name, "event_def": ev["def"], "event_id": ev["id"],
                    "event_name": ev["name"], "event_start": ev["start"], "event_end": ev["end"],
                    "hit": "命中", "first_alarm": first_raw, "first_offset_td": off_raw,
                    "offset_clamped": off_clamped, "timing_bin": tbin, "overlap_days": ov,
                    "judged_type": ep["judged_type"], "plan": ep["plan"],
                    "engine_status": ep["status"], "expected_type": ev["expected_type"],
                })
            layer_hits[book_name] = len(used)

        # 误报判定（修订 a4）：与两本账任一认定窗无交集才是误报；
        # 有交集但非指定首响段 = 关联命中段（不算误报）。
        fa_days = 0
        fa_out_days = 0
        assoc_days = 0
        n_assoc = 0
        win_days = set()
        for evs in books.values():
            for ev in evs:
                for d in dates:
                    if ev["win_start"] <= d <= ev["win_end"]:
                        win_days.add(d)
        for i, ep in enumerate(eps):
            intersects = any(
                not (ep["end"] < ev["win_start"] or ep["start"] > ev["win_end"])
                for evs in books.values() for ev in evs)
            if intersects and i in attributed_ids:
                continue
            if intersects and i not in attributed_ids:
                n_assoc += 1
                assoc_days += ep["len"]
                continue
            fz = []
            for eid, ws, we in fz_wins:
                if not (ep["end"] < ws or ep["start"] > we):
                    fz.append(f"事件{eid}")
            false_rows.append({
                "layer": layer_name, "episode_start": ep["start"], "episode_end": ep["end"],
                "episode_len": ep["len"], "judged_type": ep["judged_type"],
                "plan": ep["plan"], "engine_status": ep["status"],
                "frozen_event_overlap": "|".join(fz) if fz else "无",
            })
            fa_days += ep["len"]
            for d in dates:
                if ep["start"] <= d <= ep["end"] and d not in win_days:
                    fa_out_days += 1
        summary_layers[layer_name] = {
            "n_episodes_sealed": len(eps),
            "hit_narrative": layer_hits.get("叙事", 0),
            "hit_label": layer_hits.get("标签", 0),
            "n_false_episodes": len(eps) - len(attributed_ids) - n_assoc,
            "false_days_episodes": fa_days,
            "false_days_outside_event_windows": fa_out_days,
            "false_days_per_year_outside": round(fa_out_days / years, 1),
            "n_assoc_episodes": n_assoc,
            "assoc_days": assoc_days,
            "train_false_days_per_year": train_fa,
            "alarm_days_total": sum(e["len"] for e in eps),
            "sealed_days": total_days,
        }

    facts = []
    for eid, name, s, e, _ in NARRATIVE:
        f = episode_facts(dates, closes, s, e)
        f.update({"id": eid, "def": "叙事", "fwd20_min": ""})
        facts.append(f)
    for eid, name, s, e in LABEL:
        idx = {d: i for i, d in enumerate(dates)}
        i0, i1 = idx[s], idx[e]
        fwd_min = min(min(closes[i + 1: i + 21]) / closes[i] - 1 for i in range(i0, i1 + 1))
        f = episode_facts(dates, closes, s, e)
        f.update({"id": eid, "def": "标签", "fwd20_min": round(fwd_min, 4)})
        facts.append(f)

    for rows, name in ((attribution_rows, "regime_v018_episode_attribution.csv"),
                       (false_rows, "regime_v018_false_alarm_sealed.csv")):
        with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    with open(os.path.join(OUT, "regime_v018_benchmark_episode_facts.csv"), "w", newline="", encoding="utf-8-sig") as f:
        keys = sorted({k for r in facts for k in r})
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(facts)

    def sha(path):
        return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]

    summary = {
        "protocol": "regime-sealed-validation-v0.18-2026-11-16",
        "amendments": ["a1 分账归因", "a2 首响钳位双列", "a3 冻结事件波及注记", "a4 误报=两本账均无交集"],
        "generated_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "validation_span": f"{VALIDATION_START}..{DATA_END}",
        "product": {"trigger": "S3 三中二（回撤换年线）", "governance": "B10 纯静默·冷却十日",
                    "engine": "v0.12 判定机逐字同规则", "tuned": False},
        "layers": summary_layers,
        "attribution_sha": sha(os.path.join(OUT, "regime_v018_episode_attribution.csv")),
        "false_alarm_sha": sha(os.path.join(OUT, "regime_v018_false_alarm_sealed.csv")),
        "caveats": [
            "N3 仍在演化且被数据末日 2026-11-03 截断",
            "2025-01-01..2025-04-07 波及冻结事件 16/17，非纯样本外",
            "叙事背景为用户提供、未核验；评估锚只用万得全A与冻结产物",
            "标签段先于本预登记算出（规则固定），已披露",
        ],
    }
    with open(os.path.join(OUT, "regime_v018_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("v0.18 done:", summary["attribution_sha"], summary["false_alarm_sha"])


if __name__ == "__main__":
    main()
