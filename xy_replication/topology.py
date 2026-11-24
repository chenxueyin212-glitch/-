"""相关网络的VR持续同调；公式与兴业原报告图12核对。"""
from __future__ import annotations

import numpy as np
from ripser import ripser


def correlation_distance(returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """输入形状为(30个交易日, 行业数)，输出相关矩阵与报告距离矩阵。"""
    x = np.asarray(returns, dtype=float)
    if x.ndim != 2 or x.shape[0] != 30 or x.shape[1] < 4:
        raise ValueError("相关网络输入必须为30日×至少4个行业")
    if not np.isfinite(x).all():
        raise ValueError("相关网络输入含NaN/Inf")
    if np.any(np.std(x, axis=0, ddof=1) <= 0):
        raise ValueError("存在零波动行业，无法定义相关系数")
    corr = np.corrcoef(x, rowvar=False)
    corr = np.clip((corr + corr.T) / 2.0, -1.0, 1.0)
    np.fill_diagonal(corr, 1.0)
    distance = np.sqrt(np.maximum(0.0, 2.0 * (1.0 - corr)))
    np.fill_diagonal(distance, 0.0)
    return corr, distance


def exact_landscape_l1(diagram: np.ndarray) -> float:
    """持久景观L1范数的精确积分：各三角形面积之和。"""
    if diagram is None:
        return 0.0
    dgm = np.asarray(diagram, dtype=float)
    if dgm.size == 0:
        return 0.0
    finite = dgm[np.isfinite(dgm).all(axis=1)]
    persistence = np.maximum(0.0, finite[:, 1] - finite[:, 0])
    return float(np.sum(persistence ** 2) / 4.0)


def betti_at(diagram: np.ndarray, epsilon: float) -> int:
    if diagram is None:
        return 0
    dgm = np.asarray(diagram, dtype=float)
    if dgm.size == 0:
        return 0
    return int(np.sum((dgm[:, 0] <= epsilon) & (dgm[:, 1] > epsilon)))


def network_features(returns: np.ndarray, epsilons=(0.4, 0.6, 0.8)) -> dict:
    corr, distance = correlation_distance(returns)
    result = ripser(distance, distance_matrix=True, maxdim=2, thresh=2.0,
                    coeff=2, do_cocycles=False)
    diagrams = result["dgms"]
    if len(diagrams) != 3:
        raise RuntimeError("ripser未返回H0/H1/H2三组持续图")
    h2 = np.asarray(diagrams[2], dtype=float)
    h2_finite = h2[np.isfinite(h2).all(axis=1)] if h2.size else h2
    if h2_finite.size and np.any(h2_finite[:, 1] < h2_finite[:, 0]):
        raise RuntimeError("H2持续图出现death<birth")
    eigenvalues = np.linalg.eigvalsh(corr)
    upper = corr[np.triu_indices(corr.shape[0], k=1)]
    out = {
        "n_nodes": int(corr.shape[0]),
        "h2_count": int(len(h2_finite)),
        "h1_count": int(len(diagrams[1])),
        "h2_landscape_l1": exact_landscape_l1(h2),
        "h1_landscape_l1": exact_landscape_l1(diagrams[1]),
        "industry_average_correlation": float(np.mean(upper)),
        "correlation_leading_eigenvalue_share": float(eigenvalues[-1] / corr.shape[0]),
        "max_h2_persistence": float(np.max(h2_finite[:, 1] - h2_finite[:, 0])) if len(h2_finite) else 0.0,
    }
    for epsilon in epsilons:
        key = str(epsilon).replace(".", "p")
        out[f"h2_betti_{key}"] = betti_at(h2, float(epsilon))
    if not all(np.isfinite(v) for v in out.values()):
        raise RuntimeError("拓扑或相关特征含NaN/Inf")
    return out
