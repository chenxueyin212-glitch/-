# -*- coding: utf-8 -*-
"""v0.25 条件化抱团拓扑：共享数据与指标实现。

只读既有行业数据库与事件表；不写任何冻结产物。所有新指标由本文件计算。
"""
from __future__ import annotations

import math
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist
from sklearn.cluster import DBSCAN
from sklearn.decomposition import PCA

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tda_project"))
from src.xy_replication.fetch_sw2014_corrected import CODES as SW2014  # noqa: E402

DB = ROOT / "a_share_pit" / "tdx_central.db"
CURRENT_DB = ROOT / "tda_project" / "outputs" / "xy_replication_data.db"
OLD_DB = ROOT / "tda_project" / "outputs" / "xy_sw2014_corrected_data.db"
EVENTS = ROOT / "tda_project" / "outputs" / "regime_v05_crisis_events.csv"
STYLE = ROOT / "paper_drafts" / "quintile_reversal.csv"
SWITCH = "2021-12-13"


def _series_from(db: Path, table: str, code_col: str = "code") -> dict[str, dict[str, float]]:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    out: dict[str, dict[str, float]] = {}
    for code, date, close in con.execute(f"SELECT {code_col},date,close FROM {table}"):
        if close is not None and float(close) > 0:
            out.setdefault(str(code), {})[str(date)] = float(close)
    con.close()
    return out


class IndustryData:
    def __init__(self) -> None:
        cur = sqlite3.connect(f"file:{CURRENT_DB.as_posix()}?mode=ro", uri=True)
        self.bench = {
            r[0]: float(r[1])
            for r in cur.execute("SELECT date,close FROM benchmark_daily WHERE code='801003' ORDER BY date")
            if r[1] is not None and float(r[1]) > 0
        }
        self.dates = sorted(self.bench)
        self.current_closes = _series_from(CURRENT_DB, "sw2_daily")
        self.current_codes = sorted(
            r[0] for r in cur.execute(
                "SELECT code FROM sw2_meta WHERE parent IS NOT 'SW2014 legacy supplement'"
            )
        )
        cur.close()
        self.old_closes = _series_from(OLD_DB, "sw2014_daily")
        self.old_codes = sorted(SW2014)
        self._cache: dict[str, "Panel"] = {}

    def source(self, date: str):
        if date < SWITCH:
            return self.old_closes, self.old_codes
        return self.current_closes, self.current_codes

    def panel(self, date: str) -> "Panel":
        if date in self._cache:
            return self._cache[date]
        closes, codes_all = self.source(date)
        i = self.dates.index(date) if date in self.bench else -1
        if i < 31:
            raise KeyError(f"日期 {date} 的前置窗不足")
        wd = self.dates[i - 30:i + 1]
        codes, cols = [], []
        for c in codes_all:
            s = closes.get(c, {})
            ps = [s.get(d) for d in wd]
            if any(p is None for p in ps):
                continue
            a = np.asarray(ps, float)
            r = a[1:] / a[:-1] - 1.0
            if np.std(r, ddof=1) <= 0 or not np.isfinite(r).all():
                continue
            codes.append(c)
            cols.append(r)
        if len(codes) < 8:
            raise RuntimeError(f"{date} 可计算行业仅 {len(codes)} 个")
        R = np.asarray(cols, float)          # industries x 30
        corr = np.corrcoef(R)
        corr = np.clip((corr + corr.T) / 2.0, -1.0, 1.0)
        np.fill_diagonal(corr, 1.0)
        D = np.sqrt(np.maximum(0.0, 2.0 * (1.0 - corr)))
        np.fill_diagonal(D, 0.0)
        # 每个行业30日收益的横截面标准化，供 Mapper 的 lens/cluster 使用
        X = R.T.copy()
        sd = X.std(axis=0, ddof=1)
        good = sd > 1e-12
        X[:, good] = (X[:, good] - X[:, good].mean(axis=0)) / sd[good]
        p = Panel(date=date, codes=codes, R=R, D=D, X=X)
        self._cache[date] = p
        return p

    def ret250(self, date: str, code: str) -> float | None:
        i = self.dates.index(date) if date in self.bench else -1
        if i < 250:
            return None
        closes, _ = self.source(date)
        s = closes.get(code, {})
        a, b = s.get(self.dates[i - 250]), s.get(date)
        if a is None or b is None or a <= 0 or b <= 0:
            return None
        return float(b / a - 1.0)


@dataclass
class Panel:
    date: str
    codes: list[str]
    R: np.ndarray          # industries x 30 daily returns
    D: np.ndarray          # correlation distance
    X: np.ndarray          # standardized rows for Mapper


# ---------------------------------------------------------------------------
# H0 / graph helpers
# ---------------------------------------------------------------------------
def mst_weights(D: np.ndarray) -> np.ndarray:
    """Prim: VR 的有限 H0 死亡尺度，等于 MST 边权。"""
    n = len(D)
    if n <= 1:
        return np.empty(0)
    in_tree = np.zeros(n, dtype=bool)
    in_tree[0] = True
    best = D[0].copy()
    out = []
    for _ in range(n - 1):
        cand = np.where(in_tree, np.inf, best)
        j = int(np.argmin(cand))
        if not np.isfinite(cand[j]):
            break
        out.append(float(cand[j]))
        in_tree[j] = True
        np.minimum(best, D[j], out=best)
    return np.asarray(out, float)


def tp0(D: np.ndarray) -> float:
    return float(np.sum(mst_weights(D)))


def component_labels(D: np.ndarray, eps: float) -> np.ndarray:
    n = len(D)
    parent = np.arange(n)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if D[i, j] <= eps:
                a, b = find(i), find(j)
                if a != b:
                    parent[a] = b
    roots = np.array([find(i) for i in range(n)])
    _, lab = np.unique(roots, return_inverse=True)
    return lab


def components_by_eps(D: np.ndarray, grid: np.ndarray) -> list[np.ndarray]:
    """按递增阈值增量并查，返回每个 eps 的组件标签。"""
    n = len(D)
    grid = np.asarray(grid, float)
    out: list[np.ndarray | None] = [None] * len(grid)
    parent = np.arange(n)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = [(float(D[i, j]), i, j) for i in range(n) for j in range(i + 1, n)]
    edges.sort(key=lambda z: z[0])
    k = 0
    for gi, eps in enumerate(grid):
        while k < len(edges) and edges[k][0] <= eps + 1e-15:
            _, i, j = edges[k]
            a, b = find(i), find(j)
            if a != b:
                parent[a] = b
            k += 1
        roots = [find(i) for i in range(n)]
        _, lab = np.unique(roots, return_inverse=True)
        out[gi] = lab
    return out  # type: ignore[return-value]


def m2_area(D: np.ndarray, G: np.ndarray, grid: np.ndarray,
            full_labels: list[np.ndarray] | None = None,
            group_labels: list[np.ndarray] | None = None) -> float:
    Dg = D[np.ix_(G, G)]
    if full_labels is None:
        full_labels = components_by_eps(D, grid)
    if group_labels is None:
        group_labels = components_by_eps(Dg, grid)
    vals = []
    for lab_full, lab_g in zip(full_labels, group_labels):
        cg = len(np.unique(lab_g))
        img = len(np.unique(lab_full[G]))
        vals.append(img / max(cg, 1))
    return float(np.mean(vals))


def survival_days(panels: list[Panel], G: np.ndarray, eps: float,
                  start_panel_idx: int) -> tuple[int, int]:
    """固定 eps 的 G 主导连通分支前向寿命，返回 (存活日数, 死亡相对起点偏移)。"""
    comps = []
    for p in panels:
        Dg = p.D[np.ix_(G, G)]
        comps.append(component_labels(Dg, eps))
    base = comps[start_panel_idx]
    target = set(np.where(base == np.bincount(base).argmax())[0].tolist())
    last = start_panel_idx
    death = len(panels)
    for t in range(start_panel_idx + 1, len(comps)):
        lab = comps[t]
        sizes = {}
        for v in target:
            z = int(lab[v])
            sizes[z] = sizes.get(z, 0) + 1
        if not sizes:
            death = t
            break
        z, ov = max(sizes.items(), key=lambda kv: kv[1])
        if ov / max(len(target), 1) < 0.5:
            death = t
            break
        target = set(np.where(lab == z)[0].tolist())
        last = t
    return last - start_panel_idx, death - start_panel_idx


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------
def _cover_1d(v: np.ndarray, n: int = 5, overlap: float = 0.4):
    lo, hi = float(v.min()), float(v.max())
    if hi <= lo:
        hi = lo + 1e-9
    width = (hi - lo) / (1.0 + (n - 1) * (1.0 - overlap))
    centers = np.linspace(lo + width / 2, hi - width / 2, n)
    return [(c - width / 2, c + width / 2) for c in centers]


def build_mapper(panel: Panel, eps_scale: float) -> dict:
    lens = PCA(n_components=2, random_state=0).fit_transform(panel.X)
    if lens.shape[1] < 2:
        lens = np.c_[lens[:, 0], np.zeros(len(lens))]
    covs = [_cover_1d(lens[:, k]) for k in range(2)]
    # 每个 cube 内 DBSCAN；只对 cube 内点算，不跨 cube
    node_sets: list[set[int]] = []
    for a in covs[0]:
        for b in covs[1]:
            m = (lens[:, 0] >= a[0]) & (lens[:, 0] <= a[1]) & \
                (lens[:, 1] >= b[0]) & (lens[:, 1] <= b[1])
            idx = np.where(m)[0]
            if len(idx) == 0:
                continue
            if len(idx) == 1:
                node_sets.append({int(idx[0])})
                continue
            db = DBSCAN(eps=eps_scale, min_samples=1).fit(panel.X[idx])
            for lab in sorted(set(db.labels_)):
                node_sets.append(set(int(idx[k]) for k in np.where(db.labels_ == lab)[0]))
    # 去重并建图
    uniq = []
    for s in node_sets:
        if s not in uniq:
            uniq.append(s)
    nodes = uniq
    adj = [set() for _ in nodes]
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if nodes[i] & nodes[j]:
                adj[i].add(j)
                adj[j].add(i)
    return {"nodes": nodes, "adj": adj, "lens": lens}


def mapper_metrics(mapper: dict, G: set[int]) -> dict:
    nodes, adj = mapper["nodes"], mapper["adj"]
    gnodes = [i for i, s in enumerate(nodes) if s & G]
    # G 节点诱导子图连通分量
    if not gnodes:
        return {"frag": 0, "centrality": float("nan"), "purity": float("nan"),
                "coverage": 0.0}
    seen, comps = set(), 0
    for u in gnodes:
        if u in seen:
            continue
        comps += 1
        stack = [u]
        seen.add(u)
        while stack:
            z = stack.pop()
            for v in adj[z]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
    # 全图 BFS 最短路；G 到所有节点的平均距离/直径
    all_dist = []
    for src in gnodes:
        dist = {src: 0}
        q = [src]
        for u in q:
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    q.append(v)
        all_dist.extend(dist.values())
    diameter = max(all_dist) if all_dist else 1
    centrality = float(np.mean(all_dist) / max(diameter, 1))
    purity = float(np.mean([len(nodes[i] & G) / len(nodes[i]) for i in gnodes]))
    coverage = len(gnodes) / max(len(nodes), 1)
    return {"frag": int(comps), "centrality": centrality, "purity": purity,
            "coverage": float(coverage)}


# ---------------------------------------------------------------------------
# 事件与轮次
# ---------------------------------------------------------------------------
ROUNDS = [
    ("2000-11 基金黑幕", [101]),
    ("2001-06→2005-07 国有股减持到998", list(range(102, 115))),
    ("2007-05 印花税", [115]),
    ("2007-10→2008-11 全球金融危机", [116, 117, 118, 119, 120]),
    ("2009-08→2012-12 四万亿退潮", list(range(121, 129))),
    ("2015-06→2016-01 股灾熔断", [1, 2, 3, 4]),
    ("2018 去杠杆与贸易战", [5, 6, 7, 8]),
    ("2020-01→2020-03 疫情", [9, 10]),
    ("2021-02→2022-10 抱团到封城", [11, 12, 13]),
    ("2023-12→2024-02 微盘雪球", [14]),
    ("2024-10→2025-04 政策脉冲回落", [15, 16, 17]),
]


def round_of(event_id: int) -> str | None:
    for name, ids in ROUNDS:
        if int(event_id) in ids:
            return name
    return None


def load_events() -> pd.DataFrame:
    ev = pd.read_csv(EVENTS, parse_dates=["onset", "end"])
    q = pd.read_csv(STYLE, encoding="utf-8-sig", parse_dates=["onset"])
    q = q[~q["label"].astype(str).str.startswith("2026")]
    q["spread"] = pd.to_numeric(q["spread"], errors="coerce")
    q["pre_q5"] = pd.to_numeric(q.get("pre_q5"), errors="coerce")
    q["kind"] = np.where(q["形态"].astype(str).str.contains("抱团"), "抱团瓦解",
                         np.where(q["形态"].astype(str).str.contains("弱势"), "弱势杀", "均匀"))
    out = ev.merge(q[["onset", "spread", "pre_q5", "kind"]], on="onset", how="inner")
    out["round"] = out.event_id.map(round_of)
    # b_线自2007-01起可用；此前事件虽在旧库有数据，也不混入本臂
    out = out[(out.onset >= pd.Timestamp("2007-01-04")) &
              (out.onset <= pd.Timestamp("2025-04-07"))].copy()
    out = out.sort_values("onset").reset_index(drop=True)
    return out
