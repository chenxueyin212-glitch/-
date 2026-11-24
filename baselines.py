"""Gate 1普通风险基线；所有统计量仅使用当前右对齐窗口。"""
from __future__ import annotations


def ordinary_risk_features(cloud, market_returns) -> dict:
    import numpy as np

    X = np.asarray(cloud, dtype=float)
    r = np.asarray(market_returns, dtype=float)
    if X.ndim != 2 or len(X) < 3 or len(r) != len(X):
        raise ValueError("点云与市场收益窗口长度不一致或样本不足")
    if not np.isfinite(X).all() or not np.isfinite(r).all():
        raise ValueError("普通风险基线输入含NaN/Inf")
    n_dim = X.shape[1]
    corr = np.corrcoef(X, rowvar=False, ddof=1)
    upper = corr[np.triu_indices(n_dim, k=1)]
    cov = np.cov(X, rowvar=False, ddof=1)
    eigenvalues = np.linalg.eigvalsh(cov)
    dispersion = np.std(X, axis=1, ddof=1)
    out = {
        "market_realized_volatility_50": float(np.std(r, ddof=1)),
        "market_downside_semideviation_50": float(np.sqrt(np.mean(np.minimum(r, 0.0) ** 2))),
        "industry_average_correlation_50": float(np.mean(upper)),
        "industry_covariance_leading_eigenvalue_50": float(eigenvalues[-1]),
        "industry_cross_sectional_dispersion_50": float(np.mean(dispersion)),
    }
    if not all(np.isfinite(v) for v in out.values()):
        raise ValueError("普通风险基线输出含NaN/Inf")
    return out
