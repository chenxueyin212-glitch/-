"""从 tdx_central.db 构造严格 point-in-time 的行业面板与点云。

设计约束（针对已审出的公开代码缺陷）：
1. 对数收益 = log(P_t / P_{t-1})，只用过去价；绝不使用 np.roll(-1) 那种未来对齐。
2. 窗口 X_t 严格取 [t-w+1, t]，不含 t+1。
3. 申万 2014/2021 分类断点：按段固定坐标，跨段不静默拼接。
4. 中证行业指数 2005-2011 为基日回填，默认排除（真实发布 2011-08-02）。

零第三方依赖，返回纯 Python 结构；拓扑层自行转 numpy。
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class PanelSegment:
    start: str
    end: str
    codes: tuple[str, ...]
    names: dict
    dates: tuple[str, ...]
    closes: dict                      # code -> tuple[float, ...]，与 dates 等长
    returns: dict                     # code -> tuple[float|None, ...]，首日为 None
    note: str


def connect_ro(db_path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"主库不存在: {db_path}")
    return sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)


def load_trade_calendar(conn, start: str, end: str) -> list[str]:
    rows = conn.execute(
        "SELECT date FROM trade_calendar WHERE date BETWEEN ? AND ? ORDER BY date",
        (start, end),
    ).fetchall()
    return [r[0] for r in rows]


def _sw_meta(conn) -> dict:
    return {
        r[0]: {"name": r[1], "first": r[3], "last": r[4], "rows": r[2]}
        for r in conn.execute(
            "SELECT code,name,rows,first_date,last_date FROM sw_index_meta"
        )
    }


def build_pit_segments(cfg, conn=None) -> list[PanelSegment]:
    """按分类断点把时间轴分段，每段只使用全段均有数据的行业代码。"""
    own = conn is None
    conn = conn or connect_ro(cfg.db_path)
    try:
        meta = _sw_meta(conn)
        breaks = [cfg.start, *[b for b in cfg.classification_breaks if cfg.start < b < cfg.end], cfg.end]
        segments = []
        for k, (seg_start, seg_end) in enumerate(zip(breaks[:-1], breaks[1:])):
            is_last = k == len(breaks) - 2
            # 半开区间 [seg_start, seg_end)，断点日只归后一段；最后一段含 end 当日
            op = "<=" if is_last else "<"
            # 段内必须全程存在：发布日不晚于段首、终止日不早于段末
            usable = {
                c: m for c, m in meta.items()
                if m["first"] <= seg_start and m["last"] >= seg_end
            }
            codes = tuple(sorted(usable))
            if len(codes) < 3:
                continue
            placeholders = ",".join("?" * len(codes))
            rows = conn.execute(
                f"SELECT code,date,close FROM sw_industry_daily_clean "
                f"WHERE code IN ({placeholders}) AND date >= ? AND date {op} ? ORDER BY date,code",
                (*codes, seg_start, seg_end),
            ).fetchall()
            by_code: dict = {c: {} for c in codes}
            for code, date, close in rows:
                by_code[code][date] = float(close)
            # 申万指数自身比全市场日历少若干交易日（实测每段缺 8~10 天）。
            # 以「所有代码共同可得日」为时间轴，绝不向前填充、绝不假设缺失日收益为 0。
            common = set(by_code[codes[0]])
            for c in codes[1:]:
                common &= set(by_code[c])
            dates = sorted(common)
            if len(dates) < 30:
                continue
            closes = {c: tuple(by_code[c][d] for d in dates) for c in codes}
            returns = {
                c: tuple(
                    None if i == 0 or closes[c][i - 1] <= 0 or closes[c][i] <= 0
                    else math.log(closes[c][i] / closes[c][i - 1])
                    for i in range(len(dates))
                )
                for c in codes
            }
            cal = load_trade_calendar(conn, seg_start, seg_end)
            coverage = len(dates) / len(cal) if cal else 0.0
            segments.append(PanelSegment(
                start=seg_start, end=seg_end, codes=codes,
                names={c: usable[c]["name"] for c in codes},
                dates=tuple(dates), closes=closes, returns=returns,
                note=(f"段内坐标固定，段间不拼接；共同可得交易日 {len(dates)}/{len(cal)}"
                      f"（覆盖率 {coverage:.3f}）；跨缺口收益按相邻观测计算"),
            ))
        return segments
    finally:
        if own:
            conn.close()


def build_fixed_panel(cfg, panel_key: str, conn=None) -> PanelSegment:
    """读取Gate 0冻结的固定一级行业面板；默认配置拒绝读取2025年起数据。"""
    if panel_key not in cfg.raw["panels"]:
        raise KeyError(f"未知面板: {panel_key}")
    spec = cfg.raw["panels"][panel_key]
    codes = tuple(spec["codes"])
    expected = int(panel_key[1:])
    if len(codes) != expected or len(set(codes)) != expected:
        raise ValueError(f"{panel_key} 代码数量或唯一性错误: {len(codes)}")
    if cfg.end >= cfg.test_start:
        raise ValueError("开发配置end必须早于test_start，禁止触碰最终测试期")
    start, end = spec["start"], cfg.end
    own = conn is None
    conn = conn or connect_ro(cfg.db_path)
    try:
        meta = _sw_meta(conn)
        missing = [c for c in codes if c not in meta]
        if missing:
            raise ValueError(f"行业元数据缺失: {missing}")
        bad_identity = [c for c in codes if "待核实" in meta[c]["name"] or "市场表征" in meta[c]["name"]]
        if bad_identity:
            raise ValueError(f"面板混入非一级行业或待核代码: {bad_identity}")
        placeholders = ",".join("?" * len(codes))
        rows = conn.execute(
            f"SELECT code,date,close FROM sw_industry_daily_clean "
            f"WHERE code IN ({placeholders}) AND date>=? AND date<=? ORDER BY date,code",
            (*codes, start, end),
        ).fetchall()
        by_code: dict = {c: {} for c in codes}
        for code, date, close in rows:
            by_code[code][date] = float(close)
        empty = [c for c in codes if not by_code[c]]
        if empty:
            raise ValueError(f"面板代码在开发期无数据: {empty}")
        common = set(by_code[codes[0]])
        for c in codes[1:]:
            common &= set(by_code[c])
        dates = sorted(common)
        if len(dates) < 300:
            raise ValueError(f"{panel_key} 共同交易日不足: {len(dates)}")
        closes = {c: tuple(by_code[c][d] for d in dates) for c in codes}
        returns = {
            c: tuple(
                None if i == 0 or closes[c][i - 1] <= 0 or closes[c][i] <= 0
                else math.log(closes[c][i] / closes[c][i - 1])
                for i in range(len(dates))
            )
            for c in codes
        }
        cal = load_trade_calendar(conn, start, end)
        return PanelSegment(
            start=start, end=end, codes=codes,
            names={c: meta[c]["name"] for c in codes},
            dates=tuple(dates), closes=closes, returns=returns,
            note=(f"Gate 0固定{expected}个一级行业；共同可得交易日{len(dates)}/{len(cal)}"
                  f"（覆盖率{len(dates) / len(cal):.3f}）；不填充缺失日；开发数据止于{end}"),
        )
    finally:
        if own:
            conn.close()


def build_point_clouds(segment: PanelSegment, window: int) -> list[tuple[str, list[list[float]]]]:
    """X_t = {x_{t-w+1}, ..., x_t}，每个 x_s 是该日各行业对数收益向量。

    首 w 个交易日无完整窗口；任何含 None 的窗口直接丢弃（停牌/缺失不填充）。
    """
    if window < 2:
        raise ValueError("window 必须 >= 2")
    n = len(segment.dates)
    out = []
    for t in range(window - 1, n):
        cloud = []
        ok = True
        for s in range(t - window + 1, t + 1):
            row = [segment.returns[c][s] for c in segment.codes]
            if any(v is None for v in row):
                ok = False
                break
            cloud.append(row)
        if ok:
            out.append((segment.dates[t], cloud))
    return out


def load_benchmark(cfg, conn=None) -> tuple[tuple[str, ...], tuple[float, ...]]:
    """双指数日收益等权并链式合成；只取共同交易日，绝不直接平均点位。"""
    if cfg.benchmark != "daily_equal_weight_000001_399001":
        raise ValueError(f"Gate 0仅允许已冻结合成基准，当前: {cfg.benchmark}")
    own = conn is None
    conn = conn or connect_ro(cfg.db_path)
    try:
        rows = conn.execute(
            "SELECT code,date,close FROM index_daily_raw "
            "WHERE code IN ('000001','399001') AND date BETWEEN ? AND ? "
            "ORDER BY date,code",
            (cfg.start, cfg.end),
        ).fetchall()
        closes = {"000001": {}, "399001": {}}
        for code, date, close in rows:
            closes[code][date] = float(close)
        dates = sorted(set(closes["000001"]) & set(closes["399001"]))
        if len(dates) < 2:
            raise ValueError("合成基准共同交易日不足")
        level = [100.0]
        for i in range(1, len(dates)):
            r_sh = closes["000001"][dates[i]] / closes["000001"][dates[i - 1]] - 1.0
            r_sz = closes["399001"][dates[i]] / closes["399001"][dates[i - 1]] - 1.0
            level.append(level[-1] * (1.0 + 0.5 * (r_sh + r_sz)))
        return tuple(dates), tuple(level)
    finally:
        if own:
            conn.close()
