"""v0.6 early-history descriptive TDA extension.

Pre-registered in config/regime_early_extension_v0.6.toml before any v0.6
persistent-homology result was computed.  This script reuses the frozen
implementations, reads industry prices only through 2013-03-29, and writes only
new v06 artefacts.  It does not run labels, statistics, verdicts, performance,
IC, Gate 1, or the sealed 2025 final test.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sqlite3
import sys
import time
import tomllib
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
from ripser import ripser

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "phti_replication"))
sys.path.insert(0, str(ROOT / "src" / "regime_check"))
warnings.filterwarnings("ignore", message=".*more columns than rows.*")

import build_window_grid_summaries as bg  # noqa: E402
import build_v03_summaries as bv03  # noqa: E402
from build_daily_ph_summaries import SHAPE_COLS, shape_of_window  # noqa: E402
from phti_pipeline import finite_diagram, load_industry_panel, wasserstein_p  # noqa: E402
from src.xy_replication.fetch_sw2014_corrected import CODES as SW2014  # noqa: E402

OUT = ROOT / "outputs"
CFG = ROOT / "config" / "regime_early_extension_v0.6.toml"
DB = (ROOT.parent / "a_share_pit" / "tdx_central.db").resolve()
OLD_DB = OUT / "xy_sw2014_corrected_data.db"
CAL_DB = OUT / "xy_replication_data.db"
W = 10
XY_WINDOWS = (10, 15, 20, 30)
RIPSER_FLOAT32_TOL = 1e-6
SAME_IMPLEMENTATION_TOL = 1e-8

A16_OUT = OUT / "regime_v06_early_phti_p16_w10.csv"
XY_OUT = OUT / "regime_v06_early_xy_10.csv"
H0_OUT = OUT / "regime_v06_early_xy_h0_w10.csv"
ELIGIBLE_OUT = OUT / "regime_v06_early_xy_eligible.json"
ELIGIBILITY_OUT = OUT / "regime_v06_early_xy_eligibility.csv"
DAILY_OUT = OUT / "regime_v06_early_descriptive_daily.csv"
AUDIT_OUT = OUT / "regime_v06_early_input_audit.json"
MANIFEST_OUT = OUT / "regime_v06_early_manifest.json"

FROZEN_FILES = [
    "config/study.toml",
    "config/regime_split_check_v0.5.toml",
    "outputs/regime_v05_split_wide.csv",
    "outputs/regime_v05_daily_labels.csv",
    "outputs/regime_v05_crisis_events.csv",
    "outputs/regime_v05_grid.csv",
    "outputs/regime_v05_verdicts.json",
    "outputs/crisis_context_v05_report.html",
    "outputs/regime_v03_phti_p16_w10.csv",
    "outputs/regime_v03_xy_h0_w10.csv",
    "outputs/regime_win_summaries_xy_10.csv",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def frozen_baseline() -> dict:
    return {
        name: {
            "sha256": sha256(ROOT / name),
            "bytes": (ROOT / name).stat().st_size,
            "mtime_ns": (ROOT / name).stat().st_mtime_ns,
        }
        for name in FROZEN_FILES
    }


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def csv_bytes(fields: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO(newline="")
    wr = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore", lineterminator="\r\n")
    wr.writeheader()
    wr.writerows(rows)
    raw = buf.getvalue()
    assert "NaN" not in raw and "Inf" not in raw
    return b"\xef\xbb\xbf" + raw.encode("utf-8")


def write_bytes(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, bool):
        return bool(obj)
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        return float(obj) if math.isfinite(obj) else None
    if obj is None or isinstance(obj, str):
        return obj
    return str(obj)


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(jsonable(obj), ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def fmt(value):
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)) and not math.isfinite(value):
        return ""
    return value


def input_precheck(codes: list[str]) -> dict:
    """Read-only early input assertions; no persistent homology is computed."""
    result = {}
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    placeholders = ",".join("?" * len(codes))
    for table in ("sw_industry_daily", "sw_industry_daily_clean"):
        by_date = {}
        sql = (f"SELECT date,code,close FROM {table} WHERE code IN ({placeholders}) "
               "AND date<='2004-12-31' AND close>0 ORDER BY date,code")
        for d, c, _ in con.execute(sql, codes):
            by_date.setdefault(d, set()).add(c)
        aligned = sorted(d for d, found in by_date.items() if len(found) == len(codes))
        early = [d for d in aligned if "2001-01-01" <= d <= "2004-12-31"]
        assert len(early) == 961, (table, len(early))
        result[table] = {"first_aligned": aligned[0], "aligned_through_2004": len(aligned),
                         "aligned_2001_2004": len(early)}
    con.close()
    return result


# ---------------------------------------------------------------------------
# A16: independent full double run with the frozen loader and feature functions.
# ---------------------------------------------------------------------------
def a16_once(spec: dict, phti_cfg: dict) -> tuple[bytes, dict]:
    scope = spec["scope"]
    panel = load_industry_panel(
        DB, list(spec["a16_state_cloud"]["codes"]),
        scope["a16_compute_start"], scope["a16_compute_end"], name="v06_early_p16")
    r, dates, n = panel.log_returns, list(panel.dates), len(panel.dates)
    order = int(phti_cfg["distance"]["order_p"])
    norm = phti_cfg["distance"]["internal_norm"]
    Wvals = np.full(n, np.nan)
    rows_by_date = {}
    prev = None
    for t in range(W - 1, n):
        cloud = r[t - W + 1:t + 1]
        dgms = ripser(cloud, maxdim=1, metric="euclidean", coeff=2)["dgms"]
        cur = (finite_diagram(dgms[0]), finite_diagram(dgms[1]))
        if prev is not None:
            Wvals[t] = (wasserstein_p(prev[0], cur[0], order, norm)
                        + wasserstein_p(prev[1], cur[1], order, norm))
        prev = cur
        shape = shape_of_window(cloud, dgms)
        shape["date"] = dates[t]
        rows_by_date[dates[t]] = shape
    rows = []
    for i, d in enumerate(dates):
        shape = rows_by_date.get(d)
        rows.append({"date": d, "W_t": fmt(Wvals[i]),
                     **{c: fmt(shape[c]) if shape else "" for c in SHAPE_COLS}})
    payload = csv_bytes(["date", "W_t"] + SHAPE_COLS, rows)
    meta = {
        "rows": len(rows), "first_date": dates[0], "last_date": dates[-1],
        "windows": len(rows_by_date), "W_finite": int(np.isfinite(Wvals).sum()),
        "first_shape_date": min(rows_by_date), "last_shape_date": max(rows_by_date),
        "first_W_date": dates[int(np.flatnonzero(np.isfinite(Wvals))[0])],
    }
    return payload, meta


# ---------------------------------------------------------------------------
# B: early-only loader.  No industry price later than b_compute_end is read.
# ---------------------------------------------------------------------------
def load_early_xy_prices(end: str):
    con = sqlite3.connect(f"file:{OLD_DB.as_posix()}?mode=ro", uri=True)
    closes = {c: {} for c in sorted(SW2014)}
    for c, d, p in con.execute(
            "SELECT code,date,close FROM sw2014_daily WHERE date<=? ORDER BY date,code",
            (end,)):
        if c in closes:
            closes[c][d] = p
    con.close()
    con = sqlite3.connect(f"file:{CAL_DB.as_posix()}?mode=ro", uri=True)
    dates = [r[0] for r in con.execute(
        "SELECT date FROM benchmark_daily WHERE code='801003' AND date<=? ORDER BY date",
        (end,))]
    con.close()
    assert dates[0] == "1999-12-30" and dates[-1] == end
    assert len(closes) == 104
    return closes, dates


def early_eligible(closes: dict, dates: list[str]):
    eligible, audit_rows = {}, []
    for i, d in enumerate(dates):
        if i < 30:
            continue
        base = {c for c in sorted(SW2014)
                if bg._valid_prices(closes[c], dates[i - 30:i + 1]) is not None}
        final = set(base)
        for w in XY_WINDOWS:
            wd = dates[i - w:i + 1]
            for c in list(final):
                if bg._valid_prices(closes[c], wd) is None:
                    final.discard(c)
        status = "eligible" if len(final) >= 4 else "insufficient_nodes"
        if status == "eligible":
            eligible[d] = sorted(final)
        audit_rows.append({
            "date": d, "n_base": len(base), "n_final": len(final),
            "n_dropped_from_base": len(base) - len(final), "status": status,
        })
    return eligible, audit_rows


def returns_for(d: str, codes: list[str], closes: dict, dates: list[str], pos: dict):
    i = pos[d]
    wd = dates[i - W:i + 1]
    cols = [bg._valid_prices(closes[c], wd) for c in codes]
    if any(c is None for c in cols) or len(cols) < 4:
        raise RuntimeError("eligible list contains an invalid ten-day return column: " + d)
    returns = np.asarray(cols, dtype=float).T
    assert returns.shape == (10, len(codes)), "B线必须是11期收盘价生成10期简单收益"
    return returns


def compare_numeric(got: dict, ref: dict, fields: list[str], count_fields: set[str]):
    diffs, blanks = [], 0
    for k in fields:
        a, b = got.get(k, ""), ref.get(k, "")
        if a in ("", None) or b in ("", None):
            if (a in ("", None)) != (b in ("", None)):
                raise AssertionError("blank mismatch in " + k)
            blanks += 1
            continue
        if k in count_fields:
            if int(float(a)) != int(float(b)):
                raise AssertionError(f"count mismatch {k}: {a} != {b}")
            diffs.append(0.0)
        else:
            diffs.append(abs(float(a) - float(b)))
    return {"max_abs_diff": max(diffs, default=0.0), "paired_blanks": blanks}


def main() -> None:
    started = time.time()
    spec = tomllib.loads(CFG.read_text(encoding="utf-8"))
    phti_cfg = tomllib.loads((ROOT / "config" / "phti_replication.toml").read_text(encoding="utf-8"))
    assert spec["meta"]["status"] == "PRE-REGISTERED_BEFORE_ANY_V06_TDA_RESULT"
    baseline = frozen_baseline()
    precheck = input_precheck(list(spec["a16_state_cloud"]["codes"]))
    input_hashes = {
        str(CFG.relative_to(ROOT)): sha256(CFG),
        "config/phti_replication.toml": sha256(ROOT / "config" / "phti_replication.toml"),
        "src/regime_check/build_v06_early_summaries.py": sha256(Path(__file__)),
        "src/regime_check/build_window_grid_summaries.py": sha256(ROOT / "src/regime_check/build_window_grid_summaries.py"),
        "src/regime_check/build_v03_summaries.py": sha256(ROOT / "src/regime_check/build_v03_summaries.py"),
        "src/regime_check/build_daily_ph_summaries.py": sha256(ROOT / "src/regime_check/build_daily_ph_summaries.py"),
        "src/phti_replication/phti_pipeline.py": sha256(ROOT / "src/phti_replication/phti_pipeline.py"),
        str(DB): sha256(DB),
        str(OLD_DB): sha256(OLD_DB),
        str(CAL_DB): sha256(CAL_DB),
    }
    print("[1/6] A16 independent full run 1", flush=True)
    a16_payload_1, a16_meta_1 = a16_once(spec, phti_cfg)
    print("[2/6] A16 independent full run 2", flush=True)
    a16_payload_2, a16_meta_2 = a16_once(spec, phti_cfg)
    a16_deterministic = a16_payload_1 == a16_payload_2 and a16_meta_1 == a16_meta_2
    if not a16_deterministic:
        raise RuntimeError("A16 full double run differs; refusing to publish v0.6")
    write_bytes(A16_OUT, a16_payload_1)
    a16_rows = read_csv(A16_OUT)
    print("   A16", a16_meta_1, flush=True)

    print("[3/6] B early eligibility and full XY/H0 pass", flush=True)
    closes, dates = load_early_xy_prices(spec["scope"]["b_compute_end"])
    pos = {d: i for i, d in enumerate(dates)}
    eligible, eligibility_rows = early_eligible(closes, dates)
    write_json(ELIGIBLE_OUT, eligible)
    write_bytes(ELIGIBILITY_OUT, csv_bytes(
        ["date", "n_base", "n_final", "n_dropped_from_base", "status"], eligibility_rows))
    xy_rows, h0_rows = [], []
    t_b = time.time()
    for k, d in enumerate(sorted(eligible)):
        codes = eligible[d]
        returns = returns_for(d, codes, closes, dates, pos)
        feat = bg.xy_features(returns)
        h0, _, _ = bv03.h0_features(returns)
        xy_rows.append({"date": d, **{c: feat[c] for c in bg.XY_FIELDS}})
        h0_rows.append({"date": d, **h0})
        if (k + 1) % 100 == 0:
            print(f"   B progress {k+1}/{len(eligible)} {time.time()-t_b:.1f}s", flush=True)
    write_bytes(XY_OUT, csv_bytes(["date"] + bg.XY_FIELDS, xy_rows))
    write_bytes(H0_OUT, csv_bytes(["date"] + bv03.H0_FIELDS, h0_rows))
    xy_by_date = {r["date"]: r for r in xy_rows}
    h0_by_date = {r["date"]: r for r in h0_rows}
    assert set(xy_by_date) == set(h0_by_date) == set(eligible)
    print("   B rows", len(xy_rows), "seconds", round(time.time() - t_b, 1), flush=True)

    print("[4/6] overlap equivalence and B deterministic/H0 checks", flush=True)
    # A16: every overlapping frozen date and every summary field.
    old_a16 = {r["date"]: r for r in read_csv(OUT / "regime_v03_phti_p16_w10.csv")
               if spec["scope"]["a16_overlap_start"] <= r["date"] <= spec["scope"]["a16_overlap_end"]}
    new_a16 = {r["date"]: r for r in a16_rows
               if spec["scope"]["a16_overlap_start"] <= r["date"] <= spec["scope"]["a16_overlap_end"]}
    assert set(old_a16) == set(new_a16) and old_a16
    # Registered boundary-warmup amendment: the old loader begins 2005-01-04,
    # so its shape/W warmup blanks are expected.  From each family'S first
    # valid old date onward, every value and every blank mask must match.
    old_shape_start = min(d for d in old_a16 if old_a16[d]["h0_death_mean"] != "")
    old_W_start = min(d for d in old_a16 if old_a16[d]["W_t"] != "")
    assert old_shape_start == "2005-01-17" and old_W_start == "2005-01-18"
    a16_diffs = []
    for d in sorted(old_a16):
        compare_fields = list(SHAPE_COLS) if d >= old_shape_start else []
        if d >= old_W_start:
            compare_fields.append("W_t")
        else:
            assert old_a16[d]["W_t"] == ""
        if d < old_shape_start:
            assert all(old_a16[d][k] == "" for k in SHAPE_COLS)
        if compare_fields:
            a16_diffs.append(compare_numeric(
                new_a16[d], old_a16[d], compare_fields,
                {"components_at_delta", "h1_count"}))
    a16_overlap = {
        "dates": len(old_a16), "first": min(old_a16), "last": max(old_a16),
        "old_shape_start": old_shape_start, "old_W_start": old_W_start,
        "registered_warmup_shape_days": sum(d < old_shape_start for d in old_a16),
        "registered_warmup_W_days": sum(d < old_W_start for d in old_a16),
        "compared_shape_dates": sum(d >= old_shape_start for d in old_a16),
        "compared_W_dates": sum(d >= old_W_start for d in old_a16),
        "max_abs_diff": max(x["max_abs_diff"] for x in a16_diffs),
        "passed": max(x["max_abs_diff"] for x in a16_diffs) < SAME_IMPLEMENTATION_TOL,
    }

    old_xy = {r["date"]: r for r in read_csv(OUT / "regime_win_summaries_xy_10.csv")
              if spec["scope"]["b_overlap_start"] <= r["date"] <= spec["scope"]["b_overlap_end"]}
    old_h0 = {r["date"]: r for r in read_csv(OUT / "regime_v03_xy_h0_w10.csv")
              if spec["scope"]["b_overlap_start"] <= r["date"] <= spec["scope"]["b_overlap_end"]}
    new_xy_overlap = {d: xy_by_date[d] for d in old_xy if d in xy_by_date}
    new_h0_overlap = {d: h0_by_date[d] for d in old_h0 if d in h0_by_date}
    assert set(old_xy) == set(new_xy_overlap) and old_xy
    assert set(old_h0) == set(new_h0_overlap) and old_h0
    xy_count_fields = {"n_nodes", "h2_count", "h1_count", "h2_betti_0p4", "h2_betti_0p6", "h2_betti_0p8"}
    h0_count_fields = {"n_nodes", "xy_h0_components_0p4", "xy_h0_components_0p6", "xy_h0_components_0p8"}
    xy_diffs = [compare_numeric(new_xy_overlap[d], old_xy[d], bg.XY_FIELDS, xy_count_fields)
                for d in sorted(old_xy)]
    h0_diffs = [compare_numeric(new_h0_overlap[d], old_h0[d], bv03.H0_FIELDS, h0_count_fields)
                for d in sorted(old_h0)]
    old_eligible = json.loads((OUT / "regime_win_xy_eligible.json").read_text(encoding="utf-8"))
    node_list_mismatch = [d for d in sorted(old_xy) if eligible[d] != old_eligible[d]]
    b_overlap = {
        "xy_dates": len(old_xy), "h0_dates": len(old_h0),
        "xy_max_abs_diff": max(x["max_abs_diff"] for x in xy_diffs),
        "h0_max_abs_diff": max(x["max_abs_diff"] for x in h0_diffs),
        "node_list_mismatch_dates": node_list_mismatch,
        "passed": (max(x["max_abs_diff"] for x in xy_diffs) < SAME_IMPLEMENTATION_TOL
                   and max(x["max_abs_diff"] for x in h0_diffs) < SAME_IMPLEMENTATION_TOL
                   and not node_list_mismatch),
    }

    sample_dates = sorted(eligible)[::max(1, len(eligible) // 24)][:24]
    assert len(sample_dates) == 24
    b_det_diffs, h0_det_diffs, mst_checks = [], [], []
    for d in sample_dates:
        returns = returns_for(d, eligible[d], closes, dates, pos)
        feat = bg.xy_features(returns)
        h0, dist, edges = bv03.h0_features(returns)
        b_det_diffs.append(compare_numeric(feat, xy_by_date[d], bg.XY_FIELDS, xy_count_fields))
        h0_det_diffs.append(compare_numeric(h0, h0_by_date[d], bv03.H0_FIELDS, h0_count_fields))
        dgms = ripser(dist, distance_matrix=True, maxdim=0, thresh=2.0, coeff=2)["dgms"]
        h0_dgm = np.asarray(dgms[0], dtype=float)
        finite = h0_dgm[np.isfinite(h0_dgm).all(axis=1)]
        deaths = np.sort(finite[:, 1])
        nz_edges, nz_deaths = edges[edges > 0], deaths[deaths > 0]
        assert len(nz_edges) == len(nz_deaths), "MST/ripser H0 count mismatch: " + d
        mst_checks.append(float(np.max(np.abs(nz_edges - nz_deaths))) if len(nz_edges) else 0.0)
    b_determinism = {
        "sample_dates": sample_dates,
        "xy_max_abs_diff": max(x["max_abs_diff"] for x in b_det_diffs),
        "h0_max_abs_diff": max(x["max_abs_diff"] for x in h0_det_diffs),
        "mst_vs_ripser_max_abs_diff": max(mst_checks),
        "passed": (max(x["max_abs_diff"] for x in b_det_diffs) < SAME_IMPLEMENTATION_TOL
                   and max(x["max_abs_diff"] for x in h0_det_diffs) < SAME_IMPLEMENTATION_TOL
                   and max(mst_checks) < RIPSER_FLOAT32_TOL),
    }
    if not (a16_overlap["passed"] and b_overlap["passed"] and b_determinism["passed"]):
        write_json(AUDIT_OUT, {"a16_overlap": a16_overlap, "b_overlap": b_overlap,
                               "b_determinism": b_determinism})
        raise RuntimeError("v0.6 equivalence/determinism acceptance failed; no report may be built")

    print("[5/6] merge early descriptive daily table; labels copied only", flush=True)
    v05_front = []
    with (OUT / "regime_v05_split_wide.csv").open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        for row in reader:
            if row["date"] > spec["scope"]["front_calendar_end"]:
                break
            v05_front.append(row)
    assert len(v05_front) == 3144 and len(fields) == 67
    a16_by_date = {r["date"]: r for r in a16_rows}
    old_a16_all = {r["date"]: r for r in read_csv(OUT / "regime_v03_phti_p16_w10.csv")
                   if r["date"] <= spec["scope"]["front_calendar_end"]}
    a16_cols = [c for c in fields if c.startswith("a16_")]
    b_cols = [c for c in fields if c.startswith("b_")]
    merged = []
    for row in v05_front:
        d = row["date"]
        out = dict(row)
        a16_source = a16_by_date.get(d) if d < "2005-01-04" else old_a16_all.get(d)
        for c in a16_cols:
            out[c] = (a16_source or {}).get(c[4:], "")
        out["line_a16_present"] = "1" if a16_source is not None else "0"
        out["line_a27_present"] = "0"
        for c in [c for c in fields if c.startswith("a27_")]:
            out[c] = ""
        for c in b_cols:
            key = c[2:]
            if key in xy_by_date.get(d, {}):
                out[c] = xy_by_date[d][key]
            elif key in h0_by_date.get(d, {}):
                out[c] = h0_by_date[d][key]
            else:
                out[c] = ""
        merged.append(out)
    daily_payload = csv_bytes(fields, merged)
    write_bytes(DAILY_OUT, daily_payload)
    # Merge/report-layer determinism is checked by an immediate second serialization.
    assert daily_payload == csv_bytes(fields, merged)

    input_audit = {
        "spec": str(CFG.relative_to(ROOT)),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "input_hashes": input_hashes,
        "input_precheck": precheck,
        "a16": a16_meta_1,
        "b": {
            "effective_return_observations": 10,
            "price_observations_per_coordinate": 11,
            "fisher_z_standard_error": 1 / math.sqrt(10 - 3),
            "metadata_correction": "旧regime_v03_stage1_manifest把W=10误写为9个收益；本版按实际数组形状(10,n_nodes)披露",
            "calendar_days": len(dates), "eligible_days": len(eligible),
            "ineligible_days": len(eligibility_rows) - len(eligible),
            "first_eligible": min(eligible), "last_eligible": max(eligible),
            "n_nodes_min": min(r["n_final"] for r in eligibility_rows),
            "n_nodes_max": max(r["n_final"] for r in eligibility_rows),
            "n_base_min": min(r["n_base"] for r in eligibility_rows),
            "n_base_max": max(r["n_base"] for r in eligibility_rows),
            "total_dropped_from_base": sum(r["n_dropped_from_base"] for r in eligibility_rows),
        },
        "a16_full_double_run": {"passed": a16_deterministic, "sha256": hashlib.sha256(a16_payload_1).hexdigest()},
        "a16_overlap": a16_overlap,
        "b_overlap": b_overlap,
        "b_determinism": b_determinism,
        "early_industry_price_cutoff": spec["scope"]["b_compute_end"],
        "post_cutoff_industry_prices_read": False,
        "labels_recomputed": False,
        "verdicts_recomputed": False,
    }
    write_json(AUDIT_OUT, input_audit)

    print("[6/6] final manifest and frozen-file verification", flush=True)
    after = frozen_baseline()
    frozen_untouched = baseline == after
    if not frozen_untouched:
        raise RuntimeError("a frozen input changed during v0.6; aborting")
    produced = [A16_OUT, XY_OUT, H0_OUT, ELIGIBLE_OUT, ELIGIBILITY_OUT, DAILY_OUT, AUDIT_OUT]
    validation = {
        "preregistered_before_v06_tda": True,
        "a16_full_double_run_identical": a16_deterministic,
        "a16_overlap_equivalent": a16_overlap["passed"],
        "b_overlap_equivalent": b_overlap["passed"],
        "b_sample_deterministic_and_h0_crosscheck": b_determinism["passed"],
        "front_daily_3144_rows_67_columns": len(merged) == 3144 and len(fields) == 67,
        "a27_not_fabricated": all(not r["line_a27_present"] or r["line_a27_present"] == "0" for r in merged),
        "frozen_products_untouched": frozen_untouched,
        "no_label_or_verdict_recompute": True,
        "no_2025_final_test_read_or_scored": True,
    }
    manifest = {
        "version": "0.6",
        "purpose": "早期十六行业状态点云与较少节点行业相关点云的样本内描述性补算",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "spec": str(CFG.relative_to(ROOT)),
        "validation": validation,
        "coverage": {
            "a16_days_with_shape": sum(r["a16_h0_death_mean"] != "" for r in merged),
            "a16_days_with_W": sum(r["a16_W_t"] != "" for r in merged),
            "b_days_with_xy": sum(r["b_h2_count"] != "" for r in merged),
            "b_days_with_h0": sum(r["b_xy_h0_death_mean"] != "" for r in merged),
            "front_rows": len(merged),
        },
        "boundary": [
            "仅样本内描述性补算，不重判十四条推测，不计算绩效或预警指标",
            "完整二十七行业早期未补算；a27列保持空白，绝不把a16写入a27",
            "二级行业使用事后固定的申万2014版名单，逐日披露合格节点",
            "Gate 1暂停；2025最终测试集封存未读未评分；Gate 2未启动",
            "不得外推为TDA对A股危机预警有效或无效",
        ],
        "frozen_baseline": baseline,
        "files": {str(p.relative_to(ROOT)): {"bytes": p.stat().st_size, "sha256": sha256(p)}
                  for p in produced},
        "elapsed_seconds": round(time.time() - started, 1),
    }
    write_json(MANIFEST_OUT, manifest)
    print(json.dumps({"validation": validation, "coverage": manifest["coverage"],
                      "elapsed_seconds": manifest["elapsed_seconds"]}, ensure_ascii=False, indent=2), flush=True)
    if not all(validation.values()):
        raise RuntimeError("v0.6 manifest validation is not all true")


if __name__ == "__main__":
    main()
