"""路径与研究参数加载。零第三方依赖（Python 3.11+ 内置 tomllib）。"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "study.toml"


@dataclass(frozen=True)
class StudyConfig:
    raw: dict
    db_path: Path
    start: str
    end: str
    test_start: str
    exclude_backfill: bool
    csi_release_date: str
    classification_breaks: tuple[str, ...]
    window: int
    second_axis: str
    horizon: int
    drawdown: float
    benchmark: str
    initial_train_days: int
    val_days: int
    purge_days: int
    embargo_days: int
    alpha: float
    beta: float
    s: int
    t: int
    lead_days: int
    lag_days: int
    trading_days_per_year: int


def load_config(path: str | Path | None = None) -> StudyConfig:
    p = Path(path) if path else DEFAULT_CONFIG
    with p.open("rb") as f:
        raw = tomllib.load(f)
    d, pc, lb, sp, det, ev = (
        raw["data"], raw["pointcloud"], raw["label"], raw["split"],
        raw["detector"], raw["evaluation"],
    )
    db = Path(d["db"])
    if not db.is_absolute():
        db = (p.parent.parent / db).resolve()
    return StudyConfig(
        raw=raw,
        db_path=db,
        start=d["start"], end=d["end"], test_start=d["test_start"],
        exclude_backfill=bool(d["exclude_backfill"]),
        csi_release_date=d["csi_release_date"],
        classification_breaks=tuple(d["classification_breaks"]),
        window=int(pc["window"]), second_axis=pc["second_axis"],
        horizon=int(lb["horizon"]), drawdown=float(lb["drawdown"]),
        benchmark=lb["benchmark"],
        initial_train_days=int(sp["initial_train_days"]),
        val_days=int(sp["val_days"]),
        purge_days=int(sp["purge_days"]),
        embargo_days=int(sp["embargo_days"]),
        alpha=float(det["alpha"]), beta=float(det["beta"]),
        s=int(det["s"]), t=int(det["t"]),
        lead_days=int(det["lead_days"]), lag_days=int(det["lag_days"]),
        trading_days_per_year=int(ev["trading_days_per_year"]),
    )
