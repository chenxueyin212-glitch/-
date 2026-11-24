"""导出2024-12-31相关网络持久图，与兴业原图作视觉核对。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from ripser import ripser

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
DATE = "2024-12-31"


def main() -> None:
    con = sqlite3.connect(f"file:{OUT / 'xy_replication_data.db'}?mode=ro", uri=True)
    codes = [r[0] for r in con.execute("SELECT code FROM sw2_meta WHERE last_date>='2025-05-31' ORDER BY code")]
    series = {c: dict(con.execute("SELECT date,close FROM sw2_daily WHERE code=?", (c,))) for c in codes}
    dates = [r[0] for r in con.execute("SELECT date FROM benchmark_daily WHERE code='801003' AND date<=? ORDER BY date", (DATE,))]
    con.close()
    window = dates[-31:]
    assert window[-1] == DATE and len(window) == 31
    eligible = [(c, [series[c].get(d) for d in window]) for c in codes]
    eligible = [(c, p) for c, p in eligible if all(x is not None and x > 0 for x in p)]
    prices = np.asarray([p for _, p in eligible], dtype=float).T
    returns = prices[1:] / prices[:-1] - 1.0
    corr = np.corrcoef(returns, rowvar=False)
    distance = np.sqrt(np.maximum(0.0, 2.0 * (1.0 - corr)))
    np.fill_diagonal(distance, 0.0)
    diagrams = ripser(distance, distance_matrix=True, maxdim=2, thresh=2.0)["dgms"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    colors = ["#c44e52", "#4c72b0", "#55a868"]
    for dim, ax in enumerate(axes):
        dgm = np.asarray(diagrams[dim])
        finite = dgm[np.isfinite(dgm).all(axis=1)] if dgm.size else dgm
        if len(finite):
            ax.scatter(finite[:, 0], finite[:, 1], s=24, alpha=0.75, color=colors[dim])
        ax.plot([0, 1], [0, 1], color="#999999", linewidth=0.8)
        ax.set_xlim(0, 0.9)
        ax.set_ylim(0, 0.9)
        ax.set_title(f"H{dim}: {len(finite)} finite intervals")
        ax.set_xlabel("Birth")
        if dim == 0:
            ax.set_ylabel("Death")
        ax.grid(alpha=0.15)
    fig.suptitle(f"SW second-level correlation network, {DATE}, n={len(eligible)}")
    fig.tight_layout()
    fig.savefig(OUT / "xy_persistence_20241231.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    serializable_diagrams = {
        f"H{i}": [
            [float(birth), float(death) if np.isfinite(death) else None]
            for birth, death in np.asarray(diagram)
        ]
        for i, diagram in enumerate(diagrams)
    }
    payload = {"date": DATE, "n_nodes": len(eligible),
               "infinite_death_encoding": "null",
               "diagrams": serializable_diagrams}
    (OUT / "xy_persistence_20241231.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print({"n_nodes": len(eligible), "h2_count": len(diagrams[2]),
           "figure": str(OUT / "xy_persistence_20241231.png")})


if __name__ == "__main__":
    main()
