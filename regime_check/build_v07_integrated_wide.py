"""Integrate the accepted v0.5 calendar with v0.6 early descriptions.

No persistent homology, labels, masks, tests, verdicts or performance measures
are computed.  Only new v07 artefacts are written.  Running this script a
second time verifies byte-level determinism against the first output.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
V05 = OUT / "regime_v05_split_wide.csv"
V06 = OUT / "regime_v06_early_descriptive_daily.csv"
DEST = OUT / "regime_v07_split_wide.csv"
MANIFEST = OUT / "regime_v07_integration_manifest.json"
SPEC = ROOT / "config" / "regime_context_integration_v0.7.toml"

INPUTS = [
    "config/study.toml",
    "config/regime_split_check_v0.5.toml",
    "config/regime_early_extension_v0.6.toml",
    "outputs/regime_v05_split_wide.csv",
    "outputs/regime_v05_daily_labels.csv",
    "outputs/regime_v05_crisis_events.csv",
    "outputs/regime_v05_grid.csv",
    "outputs/regime_v05_verdicts.json",
    "outputs/regime_v05_conclusion_ledger.csv",
    "outputs/crisis_context_v05_report.html",
    "outputs/crisis_context_v05_chart_data.json",
    "outputs/regime_v06_early_descriptive_daily.csv",
    "outputs/regime_v06_early_manifest.json",
    "outputs/crisis_context_v06_early_manifest.json",
    "outputs/crisis_context_v06_early_report.html",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot() -> dict:
    ans = {}
    for rel in INPUTS:
        p = ROOT / rel
        st = p.stat()
        ans[rel] = {"sha256": sha256(p), "bytes": st.st_size, "mtime_ns": st.st_mtime_ns}
    return ans


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        return list(rd.fieldnames or []), list(rd)


def csv_bytes(fields: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO(newline="")
    wr = csv.DictWriter(buf, fieldnames=fields, extrasaction="raise", lineterminator="\r\n")
    wr.writeheader()
    wr.writerows(rows)
    raw = buf.getvalue()
    assert "NaN" not in raw and "Inf" not in raw
    return b"\xef\xbb\xbf" + raw.encode("utf-8")


def main():
    assert SPEC.exists(), "第七版预登记不存在"
    before = snapshot()
    v06_manifest = json.loads((OUT / "regime_v06_early_manifest.json").read_text(encoding="utf-8"))
    v06_context = json.loads((OUT / "crisis_context_v06_early_manifest.json").read_text(encoding="utf-8"))
    assert all(v06_manifest["validation"].values()), "第六版计算验收未全部通过"
    assert all(v06_context["validation"].values()), "第六版上下文验收未全部通过"

    fields, old = read_csv(V05)
    fields6, early = read_csv(V06)
    assert fields == fields6 and len(fields) == 67
    assert len(old) == 6483 and len(early) == 3144
    assert old[0]["date"] == early[0]["date"] == "1999-12-30"
    assert early[-1]["date"] == "2012-12-28"
    assert old[3144]["date"] == "2012-12-31"
    assert old[-1]["date"] == "2026-11-03"
    old_dates = [r["date"] for r in old]
    assert old_dates == sorted(set(old_dates))
    assert [r["date"] for r in early] == old_dates[:3144]

    summary = [c for c in fields if c.startswith(("a16_", "a27_", "b_"))]
    assert len(summary) == 50
    allowed_changes = set(summary) | {"line_a16_present"}
    for i in range(3144):
        for c in fields:
            if c not in allowed_changes:
                assert early[i][c] == old[i][c], f"前段不变量变化：{i} {c}"
    for r in early:
        assert r["line_a27_present"] == "0"
        assert all(r[c] == "" for c in fields if c.startswith("a27_"))

    merged = early + old[3144:]
    raw = csv_bytes(fields, merged)
    repeat_identical = DEST.exists() and DEST.read_bytes() == raw
    DEST.write_bytes(raw)

    # Reading the deliverable back proves that serialisation did not alter values.
    out_fields, check = read_csv(DEST)
    assert out_fields == fields and len(check) == 6483
    assert check[:3144] == early and check[3144:] == old[3144:]
    after = snapshot()
    assert before == after, "第五版、第六版或研究配置在整合过程中发生变化"
    validation = {
        "preregistered": True,
        "v06_acceptance_all_true": True,
        "calendar_6483_days_67_columns": True,
        "front_3144_rows_exactly_v06": check[:3144] == early,
        "back_3339_rows_exactly_v05": check[3144:] == old[3144:],
        "front_labels_states_events_unchanged": True,
        "front_a27_all_blank": all(all(r[c] == "" for c in fields if c.startswith("a27_")) for r in early),
        "no_nan_or_inf": True,
        "independent_second_run_byte_identical": repeat_identical,
        "all_inputs_untouched": before == after,
        "no_label_mask_or_verdict_recompute": True,
        "no_2025_final_test_read_or_scored": True,
    }
    manifest = {
        "version": "0.7",
        "purpose": "第五版完整危机上下文与第六版早期真实补算的只读整合宽表",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "spec": "config/regime_context_integration_v0.7.toml",
        "script": "src/regime_check/build_v07_integrated_wide.py",
        "calendar": {"first": old_dates[0], "last": old_dates[-1], "rows": 6483,
                     "front_rows": 3144, "back_rows": 3339, "columns": 67},
        "changed_fields_only": sorted(allowed_changes),
        "validation": validation,
        "inputs": before,
        "output": {"path": "outputs/regime_v07_split_wide.csv", "bytes": len(raw), "sha256": sha256(DEST)},
        "boundary": [
            "仅整合已验收描述性产物，不重算持续同调、标签、掩码、显著性或十四条推测",
            "第五版 5 支持／2 矛盾／7 无法判定只作冻结历史展示",
            "早期完整二十七行业仍不可得，前段二十七行业字段全部留空",
            "行业相关点云采用事后固定的申万2014版二级行业名单，不能冒充当时实时可知名单",
            "不得外推为持续同调对A股危机预警有效或无效",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(DEST), "rows": len(check), "columns": len(fields),
                      "validation": validation, "all_valid": all(validation.values())},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
