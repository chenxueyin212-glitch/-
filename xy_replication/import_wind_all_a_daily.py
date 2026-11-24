"""Import the raw Wind Alice 881001.WI daily K-line snapshot.

The snapshot was returned in an earlier session by
get_index_kline(881001.WI, 2012-12-31..2025-05-30, period=10, count=0) and was
written verbatim to the tool-results directory. Nothing is retyped here: the
JSON is parsed, validated, cross-checked against the already-registered
monthly MATCH-close CSV, and exported as a daily CSV plus an audit file.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "third_party" / "wind" / "881001WI_day_20121231_20250530.json"
MONTHLY = ROOT / "outputs" / "xy_wind_all_a_monthly.csv"
DAILY_CSV = ROOT / "outputs" / "xy_wind_all_a_daily.csv"
AUDIT = ROOT / "outputs" / "xy_wind_all_a_daily_audit.json"
FEATURES = ROOT / "outputs" / "xy_corrected_sw193_ifind_peak_features.csv"
EXPECTED_COLUMNS = ["TIME", "OPEN", "MATCH", "HIGH", "LOW", "TURNOVER",
                    "VOLUME", "CHANGEHANDRATE", "AVPRICE"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    raw = SNAPSHOT.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    assert payload.get("error") is None, payload.get("error")
    columns = [c["name"] for c in payload["data"]["columns"]]
    assert columns == EXPECTED_COLUMNS, columns
    src_rows = payload["data"]["rows"]

    daily: list[dict] = []
    for row in src_rows:
        assert len(row) == len(columns)
        d = row[0][:10]
        date.fromisoformat(d)  # strict ISO date
        open_, close, high, low = (float(row[i]) for i in (1, 2, 3, 4))
        assert min(open_, close, high, low) > 0
        assert low <= min(open_, close) and high >= max(open_, close)
        daily.append({"date": d, "open": open_, "close": close,
                      "high": high, "low": low})

    dates = [r["date"] for r in daily]
    assert len(set(dates)) == len(dates), "duplicate trading dates"
    assert dates == sorted(dates), "dates not ascending"
    assert dates[0] == "2012-12-31" and dates[-1] == "2025-05-30"
    assert len(daily) == 3012, len(daily)

    # Cross-check every month-end MATCH close against the monthly CSV already
    # registered in THIRD_PARTY.md (150 anchors).
    month_last: dict[str, dict] = {}
    for r in daily:
        month_last[r["date"][:7]] = r
    monthly = list(csv.DictReader(MONTHLY.open(encoding="utf-8-sig")))
    assert len(monthly) == 150
    mismatches = []
    for m in monthly:
        d, value = m["date"], float(m["close"])
        last = month_last.get(d[:7])
        if last is None or last["date"] != d or abs(last["close"] - value) > 1e-9:
            mismatches.append({"monthly_date": d, "monthly_close": value,
                               "daily_last": last})
    assert not mismatches, mismatches[:3]

    # Calendar coverage of the corrected feature window (2012-12-31..2025-05-30).
    with FEATURES.open(encoding="utf-8-sig", newline="") as handle:
        feature_dates = [r["date"] for r in csv.DictReader(handle)
                         if "2012-12-31" <= r["date"] <= "2025-05-30"]
    wind_dates = set(dates)
    missing = [d for d in feature_dates if d not in wind_dates]
    assert not missing, f"feature dates missing from Wind daily: {missing[:5]}"
    # The corrected-feature calendar is a subset of the Wind trading calendar
    # (some days have no complete SW industry panel). Returns between adjacent
    # feature dates are still tradable price ratios, so extra Wind sessions are
    # recorded rather than silently dropped.
    extra = [d for d in dates if d not in set(feature_dates)]

    with DAILY_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "open", "close", "high", "low"])
        writer.writeheader()
        writer.writerows(daily)

    audit = {
        "generated_on": date.today().isoformat(),
        "source": "Wind Alice MCP get_index_kline(881001.WI, period=10, count=0)",
        "snapshot": "third_party/wind/881001WI_day_20121231_20250530.json",
        "snapshot_bytes": len(raw),
        "snapshot_sha256": sha256(raw),
        "output": "outputs/xy_wind_all_a_daily.csv",
        "rows": len(daily),
        "first_date": dates[0],
        "last_date": dates[-1],
        "price_field": "MATCH (close) and OPEN (open), as returned by the connector",
        "monthly_anchor_check": {"rows": len(monthly), "mismatches": 0,
                                 "reference": "outputs/xy_wind_all_a_monthly.csv",
                                 "correction_2026_11_07": "2014-10-31 in the monthly CSV had been filled with that day's HIGH 2947.91; verified against both the period=12 MATCH return and the daily MATCH close and corrected to 2946.80. The remaining 149 month-ends matched exactly."},
        "feature_calendar_check": {
            "wind_daily_days": len(dates),
            "feature_days_in_window": len(feature_dates),
            "missing_from_wind": 0,
            "extra_in_wind": len(extra),
            "extra_dates": extra,
            "handling": "Feature calendar is the analysis grid; all feature dates have Wind prices. Extra Wind sessions carry no complete SW industry panel and are omitted. Returns across adjacent feature dates remain tradable price ratios.",
        },
        "boundary": "Connector-returned整理数据, not an original Wind export; daily series now available for descriptive/event analysis and exploratory parameter grids. It does not resolve the missing Wind industry constituent list or the missing Wind level-4 industry panel.",
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"rows": len(daily), "first": dates[0], "last": dates[-1],
           "monthly_anchors": len(monthly), "feature_days": len(feature_dates),
           "snapshot_sha256": sha256(raw)[:16], "output": str(DAILY_CSV)})


if __name__ == "__main__":
    main()
