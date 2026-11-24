"""v0.4 OPTION A: extend bull/bear labels past 2025-05-30 with REAL Wind data.

Pre-registered in config/regime_split_check_v0.4.toml
[amendment_2026_11_09_option_A_real_wind] BEFORE any v0.4 group /
significance / verdict was computed.

Background
----------
The frozen `outputs/xy_wind_all_a_daily.csv` ends at 2025-05-30 because the
2026-11-07 connector call explicitly passed `end_date="2025-05-30"` to align
with the Xingye report period, NOT because Wind stopped publishing.  The user
chose option A: use the real 881001.WI daily series instead of a Gate-0
composite-return splice.  The [benchmark_continuation] Gate-0 design in the
same spec is SUPERSEDED and kept only as an audit record.

Strategy: DO NOT re-implement the frozen label rules. Import the frozen module
build_regime_labels and call its main() unchanged, with only three things
redirected:

  1. a scratch OUT directory,
  2. BULL_BEAR_END / UNDEFINED_AFTER set to a far-future date so the
     `st[beyond] = undefined_after_2025_05_30` overwrite becomes a no-op,
  3. a wind CSV built from `xy_wind_all_a_daily_v04_full.csv` = the frozen
     front 3012 rows + the REAL 881001.WI extension (347 rows).

All 55 original columns for d <= 2025-05-30 are then bitwise-copied back from
the frozen v0.1 label file, so the front segment is guaranteed untouched even
where the frozen legacy logic looks 10 days ahead.

This script produces LABELS ONLY. No bootstrap, no group comparison, no
significance, no verdict, no TDA, no performance metric.
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import build_regime_labels as base  # noqa: E402  (frozen v0.1 module)

OUT = ROOT / "outputs"
CUTOFF = "2025-05-30"
ANCHOR = 5074.29
FIRST_EXTENSION_CLOSE = 5100.58
FAR_FUTURE = "2099-12-31"
TMP = OUT / "_v04_scratch"

V04_LABELS = OUT / "regime_daily_labels_v04.csv"
V04_META = OUT / "regime_labels_meta_v04.json"
ACCEPT = OUT / "regime_v04_label_acceptance.json"

FROZEN_LABELS = OUT / "regime_daily_labels.csv"
FROZEN_WA = OUT / "xy_wind_all_a_daily.csv"
REAL_WA_FULL = OUT / "xy_wind_all_a_daily_v04_full.csv"
REAL_WA_AUDIT = OUT / "xy_wind_all_a_daily_v04_audit.json"


def read_dict_csv(p: Path) -> list[dict]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_rows(p: Path) -> tuple[list[str], list[list[str]]]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        return next(r), list(r)


def main() -> None:
    # ---------- dates (identical to frozen v0.1 source) --------------------
    _, xy_rows = read_rows(OUT / "xy_corrected_features.csv")
    dates = [r[0] for r in xy_rows]
    n = len(dates)
    i_cut = dates.index(CUTOFF)
    assert i_cut >= 0, "cutoff date missing from xy_corrected_features.csv"
    after_dates = dates[i_cut + 1:]

    # ---------- REAL 881001.WI benchmark (front + extension) ---------------
    wa_hdr, wa_rows = read_rows(FROZEN_WA)
    frozen_wa = {r[0]: r for r in wa_rows}
    full_hdr, full_rows = read_rows(REAL_WA_FULL)
    assert full_hdr == wa_hdr, (full_hdr, wa_hdr)
    full_wa = {r[0]: r for r in full_rows}
    audit = json.loads(REAL_WA_AUDIT.read_text(encoding="utf-8"))
    assert audit["splice_point"]["max_abs_diff"] == 0.0
    assert audit["calendar_alignment"]["missing_price_days"] == 0

    # front segment must be bitwise identical to the frozen series
    front_close_diff = max(
        abs(base.to_float(frozen_wa[d][2]) - base.to_float(full_wa[d][2]))
        for d in dates if d <= CUTOFF)
    assert front_close_diff < 1e-9, front_close_diff
    # every label date must have a real price
    assert all(d in full_wa for d in dates), "label date without a real price"
    assert abs(base.to_float(full_wa[CUTOFF][2]) - ANCHOR) < 1e-9
    assert abs(base.to_float(full_wa[after_dates[0]][2]) -
               FIRST_EXTENSION_CLOSE) < 1e-9

    # ---------- scratch workspace: identical inputs, REAL benchmark --------
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    for name in ("xy_corrected_features.csv", "xy_crisis_events.csv",
                 "regime_breadth_daily.csv"):
        shutil.copy2(OUT / name, TMP / name)
    with (TMP / "xy_wind_all_a_daily.csv").open(
            "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(wa_hdr)
        for d in dates:
            w.writerow(full_wa[d])          # real date/open/close/high/low

    # ---------- run the FROZEN label engine unchanged ----------------------
    base.OUT = TMP
    base.BULL_BEAR_END = FAR_FUTURE
    base.UNDEFINED_AFTER = FAR_FUTURE
    base.main()
    scratch_labels = TMP / "regime_daily_labels.csv"
    scratch_meta = json.loads((TMP / "regime_labels_meta.json").read_text(
        encoding="utf-8"))

    # ---------- assemble v0.4: front segment bitwise copied from v0.1 ------
    v04_rows = read_dict_csv(scratch_labels)
    frozen_rows = read_dict_csv(FROZEN_LABELS)
    assert len(v04_rows) == len(frozen_rows) == n
    frozen_cols = list(frozen_rows[0].keys())          # 55 columns
    assert all(r["date"] == s["date"] for r, s in zip(v04_rows, frozen_rows))

    copied = 0
    for r, s in zip(v04_rows, frozen_rows):
        if r["date"] <= CUTOFF:
            for c in frozen_cols:
                r[c] = s[c]
            copied += 1

    # new descriptive columns. `mixed_ma250_window` is retained for the
    # judgement script's compatibility but is ALWAYS 0: the entire series is
    # one and the same 881001.WI index, so no MA250 window mixes two return
    # sources. The second engine pass is thus an equivalence self-check.
    for r in v04_rows:
        d = r["date"]
        ext = int(d > CUTOFF)
        r["benchmark_source"] = (
            "wind_all_a_881001WI_real_extension" if ext
            else "wind_all_a_proxy_frozen_v0_1")
        r["extension_day"] = str(ext)
        r["mixed_ma250_window"] = "0"
        r["real_wind_close"] = full_wa[d][2]

    out_cols = frozen_cols + ["benchmark_source", "extension_day",
                              "mixed_ma250_window", "real_wind_close"]
    with V04_LABELS.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=out_cols)
        w.writeheader()
        w.writerows(v04_rows)

    # ---------- acceptance --------------------------------------------------
    diffs = []
    for r, s in zip(v04_rows, frozen_rows):
        if r["date"] > CUTOFF:
            continue
        for c in frozen_cols:
            if r[c] != s[c]:
                diffs.append({"date": r["date"], "col": c,
                              "v0_4": r[c], "v0_1": s[c]})

    after = [r for r in v04_rows if r["date"] > CUTOFF]
    state_cols = [c for c in frozen_cols if c.startswith("state_")]
    undef_after = sum(
        1 for r in after for c in state_cols
        if r[c] == "undefined_after_2025_05_30")
    defined_after = sum(1 for r in after if r["bull_bear_defined"] == "1")
    close_filled_after = sum(1 for r in after if r["close_wind"].strip())
    crisis_after = sum(1 for r in after if r["crisis_in"] == "1")
    pre20_after = sum(1 for r in after if r["pre20"] == "1")
    overheat_after = sum(1 for r in after if r["overheat"] == "1")
    oversold_after = sum(1 for r in after if r["oversold"] == "1")
    mixed_after = sum(1 for r in after if r["mixed_ma250_window"] != "0")

    fmap = {r["date"]: r for r in frozen_rows}
    nonbench = ["close_sse", "ma250_sse", "dd250_sse", "frac_above_ma20",
                "n_traded", "B1_ratio_chg60", "B2_ret_diff60",
                "C1_amount_pct250", "C2_sse_vol_pct250", "crisis_in",
                "crisis_in_usable", "pre5", "pre10", "pre20"]
    nonbench_diff = {
        c: sum(1 for r in after if r[c] != fmap[r["date"]][c])
        for c in nonbench}

    # EXACT v0.3 normal baseline rule: defined & ~crisis_all & ~pre20_rebuilt
    # from the 14 included onsets (NOT the frozen 16-event pre20 column).
    sd = read_dict_csv(OUT / "regime_v03_state_daily.csv")
    included_pre20 = {r["date"]: r["pre20_judged"] for r in sd}
    normal_old = sum(1 for r in sd if r["normal_baseline"] == "1")
    normal_new = sum(
        1 for r in v04_rows
        if r["bull_bear_defined"] == "1" and r["crisis_in"] != "1"
        and included_pre20[r["date"]] != "1")

    coarse_after = {}
    for c in state_cols:
        coarse_after[c] = {
            k: sum(1 for r in after if r[c] == k)
            for k in sorted(set(r[c] for r in after))}

    checks = {
        "front_segment_bitwise_identical": len(diffs) == 0,
        "real_benchmark_front_identical": front_close_diff < 1e-9,
        "splice_point_no_level_jump": audit["splice_point"]["max_abs_diff"] == 0.0,
        "all_label_dates_have_real_price": all(d in full_wa for d in dates),
        "after_close_wind_all_filled": close_filled_after == len(after),
        "after_no_undefined_marker": undef_after == 0,
        "after_all_defined": defined_after == len(after),
        "after_crisis_days_zero": crisis_after == 0,
        "after_pre20_days_zero": pre20_after == 0,
        "no_mixed_ma250_window": mixed_after == 0,
        "after_nonbenchmark_all_identical": all(v == 0 for v in
                                                nonbench_diff.values()),
        "normal_baseline_2450_to_2795": (normal_old, normal_new) == (2450, 2795),
    }
    acceptance = {
        "protocol": "config/regime_split_check_v0.4.toml "
                    "[amendment_2026_11_09_option_A_real_wind]",
        "stage": "LABELS ONLY — no bootstrap / no significance / no verdict",
        "benchmark": "REAL 881001.WI daily OHLC, front 3012 rows frozen + "
                     "347 real extension rows; NO Gate-0 splice",
        "superseded": "the earlier Gate-0 continuation acceptance is void; "
                      "its outputs were overwritten by this run",
        "raw_snapshot_sha256": audit["raw_sha256"],
        "front_days_copied": copied,
        "after_days": len(after),
        "after_first": after[0]["date"], "after_last": after[-1]["date"],
        "front_diff_cells": len(diffs), "front_diff_examples": diffs[:5],
        "front_close_max_diff": front_close_diff,
        "splice_point": audit["splice_point"],
        "splice_first_extension_close": base.to_float(
            full_wa[after_dates[0]][2]),
        "calendar_alignment": audit["calendar_alignment"],
        "after_close_wind_filled": close_filled_after,
        "after_bull_bear_defined": defined_after,
        "after_undefined_marker_cells": undef_after,
        "after_crisis_in_days": crisis_after,
        "after_frozen_pre20_days": pre20_after,
        "after_nonbenchmark_column_diffs": nonbench_diff,
        "after_nonbenchmark_all_identical": all(v == 0 for v in
                                                nonbench_diff.values()),
        "after_overheat_days": overheat_after,
        "after_oversold_days": oversold_after,
        "gate0_version_overheat_oversold_for_contrast": [283, 54],
        "ERRATUM_prior_attribution_was_wrong":
            "The earlier Gate-0 acceptance called the 283/345 overheat days a "
            "'chained benchmark level-drift construction artefact, NOT real "
            "market overheating'. That attribution is WRONG or at best "
            "secondary. With the REAL 881001.WI series there is no chained "
            "splice, yet 279/345 days are still flagged (only 6 days differ "
            "between the two versions, and the two benchmarks track within "
            "~1% over this segment). The dominant driver is oh4 = pct750 > 0.90: "
            "the 750-day rolling midrank of the close. 2025-07..2026-05 is a "
            "genuine one-way advance (5074.29 -> ~6927 by 2026-05-29, +36.5%), "
            "so the close sits in the top decile of its own trailing 750-day "
            "window almost every day; after the 2026-07 drawdown the flag "
            "falls and oversold rises (2026-07: 11 overheat / 16 oversold; "
            "2026-10: 4 / 15). This is consistent with real market state, not "
            "a benchmark artefact. Disclosed as a LIMITATION: the third-layer "
            "attached label has almost no discriminating power in a trending "
            "market. It still does NOT enter the 8340-cell grid because the "
            "v0.3 wide table carries no such columns and v0.4 keeps the "
            "identical 67-column structure.",
        "third_layer_note":
            "overheat / oversold recomputed from the REAL series and disclosed "
            "above; see ERRATUM_prior_attribution_was_wrong for the corrected "
            "attribution. They do NOT enter the 8340-cell grid.",
        "mixed_ma250_window_days": 0,
        "mixed_ma250_note": "retained as an all-zero column for engine "
                            "compatibility; the second engine pass is now an "
                            "equivalence self-check, not a sensitivity run",
        "normal_baseline_v0_3": normal_old,
        "normal_baseline_v0_4": normal_new,
        "normal_delta": normal_new - normal_old,
        "coarse_state_counts_after_by_version": coarse_after,
        "checks": checks,
        "all_passed": all(checks.values()),
        "boundary": [
            "no bootstrap computed", "no group comparison computed",
            "no significance / verdict computed", "no TDA recomputed",
            "no persistence summary loaded",
            "Gate 1 sealed 2025 test set NOT read",
            "no v0.1 / v0.2 / v0.3 file overwritten",
            "frozen xy_wind_all_a_daily.csv NOT modified",
        ],
    }
    ACCEPT.write_text(json.dumps(acceptance, ensure_ascii=False, indent=2,
                                 allow_nan=False) + "\n", encoding="utf-8")

    meta = dict(scratch_meta)
    meta.update({
        "protocol": "config/regime_split_check_v0.4.toml "
                    "[amendment_2026_11_09_option_A_real_wind] (pre-registered)",
        "parent": "config/regime_conjecture_check.toml v0.1 + "
                  "config/regime_split_check_v0.3.toml",
        "benchmark_primary": "REAL 881001.WI daily close: frozen front "
                             "2012-12-31..2025-05-30 (3012 rows) + real Wind "
                             "extension 2025-06-03..2026-11-04 (347 rows). "
                             "One continuous index series, no proxy, no splice",
        "bull_bear_undefined_after": None,
        "n_days_undefined_after": 0,
        "n_days_extended": len(after),
        "front_segment": "all 55 original columns bitwise copied from v0.1",
        "mixed_ma250_window": "0 days: no benchmark splice, so no mixed window",
        "note": "scratch meta fields state_* come from the frozen engine run "
                "with the beyond-cutoff overwrite disabled; front segment was "
                "then restored bitwise from v0.1",
        "known_caveats": [c for c in scratch_meta.get("known_caveats", [])
                          if "2025-06+ has no bull/bear label" not in c] + [
            "345 days after 2025-05-30 are now labelled using REAL 881001.WI prices",
            "PE / margin financing still unavailable; turnover uses amount proxy",
            "connector-returned processed data, not an original Wind export",
        ],
    })
    V04_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2,
                                   allow_nan=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "labels": str(V04_LABELS), "meta": str(V04_META),
        "acceptance": str(ACCEPT), "rows": len(v04_rows),
        "front_copied": copied, "after_days": len(after),
        "front_diff_cells": len(diffs),
        "normal": [normal_old, normal_new],
        "after_overheat": overheat_after, "after_oversold": oversold_after,
        "checks": checks, "all_passed": all(checks.values()),
        "after_states_v0": coarse_after["state_v0_primary"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
