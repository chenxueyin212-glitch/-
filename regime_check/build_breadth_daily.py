"""Stage B-0: daily cross-sectional breadth / amount / limit-move proxies.

Frozen spec: config/regime_conjecture_check.toml (v0.1).
Purpose: supply layer-2 item A (share of stocks above MA20), item C1 (all-A
turnover percentile), and layer-3 limit-up/down proxies for the conjecture
check. IN-SAMPLE DESCRIPTIVE ONLY: no equity index return, no strategy result.

Known caveats (disclosed, not silently repaired):
  * suspended stocks are MISSING rows (no volume=0 records) -> denominator
    shrinks on mass-suspension days (2015-07), breadth is biased upward.
  * universe size grows over time -> per-day denominator is written out.
  * limit-up/down has NO native field; approximated by close/prev_close
    thresholds (10% / 20% / 5% boards), NOT filtered for ex-rights days.
    It is an attached label only, never a main bull/bear criterion.
"""
from __future__ import annotations

import csv
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = (ROOT.parent / "a_share_pit" / "tdx_central.db").resolve()
OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

# One extra year of warm-up so MA20/250d percentile are complete from 2012-12-31.
WARMUP_START = "2011-01-01"

SQL = """
WITH base AS (
  SELECT e.code, e.date, e.close, e.volume, e.amount,
         AVG(e.close) OVER w20                        AS ma20,
         COUNT(e.close) OVER w20                     AS n20,
         LAG(e.close) OVER w1                        AS prev_close
  FROM equity_daily_raw e
  WHERE e.date >= ?
  WINDOW w20 AS (PARTITION BY e.code ORDER BY e.date
                 ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
         w1  AS (PARTITION BY e.code ORDER BY e.date)
)
SELECT date,
       COUNT(*)                                                   AS n_records,
       SUM(CASE WHEN volume > 0 THEN 1 ELSE 0 END)                 AS n_traded,
       SUM(CASE WHEN n20 = 20 AND volume > 0 THEN 1 ELSE 0 END)   AS n_valid20,
       SUM(CASE WHEN n20 = 20 AND volume > 0 AND close > ma20
                THEN 1 ELSE 0 END)                                 AS n_above20_strict,
       SUM(CASE WHEN volume > 0 AND close > ma20 THEN 1 ELSE 0 END) AS n_above20_all,
       SUM(CASE WHEN volume > 0 THEN amount ELSE 0 END)            AS total_amount,
       SUM(CASE WHEN prev_close > 0 AND volume > 0
                 AND close/prev_close - 1 >= 0.098 THEN 1 ELSE 0 END) AS n_up_10,
       SUM(CASE WHEN prev_close > 0 AND volume > 0
                 AND close/prev_close - 1 <= -0.098 THEN 1 ELSE 0 END) AS n_down_10,
       SUM(CASE WHEN prev_close > 0 AND volume > 0
                 AND close/prev_close - 1 >= 0.198 THEN 1 ELSE 0 END) AS n_up_20,
       SUM(CASE WHEN prev_close > 0 AND volume > 0
                 AND close/prev_close - 1 <= -0.198 THEN 1 ELSE 0 END) AS n_down_20,
       SUM(CASE WHEN prev_close > 0 AND volume > 0
                 AND close/prev_close - 1 >= 0.048 THEN 1 ELSE 0 END) AS n_up_5,
       SUM(CASE WHEN prev_close > 0 AND volume > 0
                 AND close/prev_close - 1 <= -0.048 THEN 1 ELSE 0 END) AS n_down_5
FROM base
GROUP BY date
ORDER BY date
"""

COLS = ["date", "n_records", "n_traded", "n_valid20", "n_above20_strict",
        "n_above20_all", "total_amount", "n_up_10", "n_down_10",
        "n_up_20", "n_down_20", "n_up_5", "n_down_5"]


def main() -> None:
    t0 = time.time()
    conn = sqlite3.connect(str(DB))
    rows = conn.execute(SQL, (WARMUP_START,)).fetchall()
    conn.close()
    elapsed = time.time() - t0

    path = OUT / "regime_breadth_daily.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for r in rows:
            w.writerow([r[0]] + ["" if v is None else v for v in r[1:]])

    print({
        "output": str(path),
        "rows": len(rows),
        "first": rows[0][0] if rows else None,
        "last": rows[-1][0] if rows else None,
        "elapsed_sec": round(elapsed, 1),
        "zero_stock_days": sum(1 for r in rows if r[1] == 0),
    })


if __name__ == "__main__":
    main()
