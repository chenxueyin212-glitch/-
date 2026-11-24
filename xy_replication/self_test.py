"""兴业复现的数学内核合成样例与跨库核验。"""
from __future__ import annotations

import sys
from pathlib import Path

import gudhi
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.xy_replication.topology import (
    betti_at, correlation_distance, exact_landscape_l1, network_features,
)
from src.xy_replication.backtest import signal_source


def main() -> None:
    rng = np.random.default_rng(20261107)
    x = rng.normal(size=(30, 8)) * 0.01
    corr, distance = correlation_distance(x)
    assert np.allclose(np.diag(distance), 0)
    assert np.allclose(distance, distance.T)
    assert distance.min() >= 0 and distance.max() <= 2 + 1e-12
    anti = np.column_stack([x[:, 0], -x[:, 0], x[:, 1], x[:, 2]])
    _, anti_distance = correlation_distance(anti)
    assert np.isclose(anti_distance[0, 1], 2.0)
    assert np.isclose(exact_landscape_l1(np.array([[1.0, 3.0]])), 1.0)
    assert exact_landscape_l1(np.empty((0, 2))) == 0.0
    assert betti_at(np.array([[0.2, 0.7], [0.5, 0.9]]), 0.6) == 2
    # t=10信号：收盘口径作用于start=10..13；开盘口径作用于start=11..14。
    assert [10 in signal_source(s, 4, "report_close") for s in range(10, 15)] == [True] * 4 + [False]
    assert [10 in signal_source(s, 4, "causal_open") for s in range(10, 16)] == [False] + [True] * 4 + [False]
    assert max(signal_source(11, 4, "causal_open")) < 11

    # 球面点云应出现显著H2；同时用GUDHI独立重算持续图。
    n = 24
    k = np.arange(n, dtype=float)
    z = 1.0 - 2.0 * (k + 0.5) / n
    theta = np.pi * (1.0 + np.sqrt(5.0)) * k
    radius = np.sqrt(1.0 - z * z)
    sphere = np.column_stack([radius * np.cos(theta), radius * np.sin(theta), z])
    d = np.sqrt(np.sum((sphere[:, None, :] - sphere[None, :, :]) ** 2, axis=2))
    result = __import__("ripser").ripser(d, distance_matrix=True, maxdim=2, thresh=2.0)
    h2 = result["dgms"][2]
    assert len(h2) >= 1 and np.max(h2[:, 1] - h2[:, 0]) > 0.1
    complex_ = gudhi.RipsComplex(distance_matrix=d.tolist(), max_edge_length=2.0)
    tree = complex_.create_simplex_tree(max_dimension=3)
    tree.persistence(homology_coeff_field=2, min_persistence=0)
    gudhi_h2 = np.asarray(tree.persistence_intervals_in_dimension(2), dtype=float)
    ripser_h2 = np.asarray(sorted(map(tuple, h2.tolist())), dtype=float)
    gudhi_h2 = np.asarray(sorted(map(tuple, gudhi_h2.tolist())), dtype=float)
    assert ripser_h2.shape == gudhi_h2.shape
    assert np.allclose(ripser_h2, gudhi_h2, atol=1e-8)

    # 人为构造高相关与异质相关窗口，检查普通变量方向而非预设H2结论。
    common = rng.normal(size=(30, 1))
    high_corr = common * rng.normal(size=(1, 10)) + rng.normal(size=(30, 10)) * 0.001
    high = network_features(high_corr)
    heterogeneous = network_features(rng.normal(size=(30, 10)))
    assert high["industry_average_correlation"] > heterogeneous["industry_average_correlation"]
    print({"status": "ok", "sphere_h2": len(h2), "gudhi_crosscheck": True,
           "high_corr_h2": high["h2_count"], "heterogeneous_h2": heterogeneous["h2_count"]})


if __name__ == "__main__":
    main()
