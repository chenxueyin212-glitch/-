"""L0 计算内核的薄封装。算法不自己写，但**拟合口径由本项目控制**。

硬性规则：
- 任何 scaler / Landscape 网格 / 阈值只能在训练段 fit，禁止跨窗口或全样本 fit。
  这是 GUDHI 官方 notebook 的直接教训。
- 双参数第二轴首版采用 kNN 逆密度；full/core/edge 使用离散密度切片，
  不声称等价于完整双参数持续模。
"""
from __future__ import annotations

import importlib.util
import platform

HAS_GUDHI = importlib.util.find_spec("gudhi") is not None
HAS_RIPSER = importlib.util.find_spec("ripser") is not None
HAS_NUMPY = importlib.util.find_spec("numpy") is not None
# multipers 依赖 pykeops，Windows 无对应分发。实测 --no-deps 强装后
# `import multipers` 成功但 `import multipers.filtrations` 直接段错误（exit 139），
# 因此在 Windows 上一律判为不可用，避免调用时崩溃。WSL/Linux 下才启用。
MP_BLOCKED = platform.system() == "Windows"
HAS_MULTIPERS = (importlib.util.find_spec("multipers") is not None) and not MP_BLOCKED


def backend_status() -> dict:
    return {
        "gudhi": HAS_GUDHI, "ripser": HAS_RIPSER,
        "numpy": HAS_NUMPY, "multipers": HAS_MULTIPERS,
        "multipers_blocked_reason": (
            "Windows: pykeops 依赖缺失，filtrations 段错误；需 WSL/Linux"
            if MP_BLOCKED else None
        ),
    }


def vr_diagrams(cloud, maxdim: int = 1):
    """单个点云 -> 各维持续图（birth/death 数组列表）。优先 gudhi，回退 ripser。"""
    if not HAS_NUMPY:
        raise RuntimeError("numpy 未安装，无法调用拓扑后端")
    import numpy as np

    X = np.asarray(cloud, dtype=float)
    if X.ndim != 2:
        raise ValueError(f"点云应为 2D，实际 {X.shape}")
    if HAS_RIPSER:
        from ripser import ripser
        return ripser(X, maxdim=maxdim)["dgms"]
    if HAS_GUDHI:
        import gudhi
        rips = gudhi.RipsComplex(points=X.tolist())
        st = rips.create_simplex_tree(max_dimension=maxdim + 1)
        diag = st.persistence()
        out = []
        for d in range(maxdim + 1):
            out.append(np.array([(b, de) for dim, (b, de) in diag
                                 if dim == d and de != float("inf")]))
        return out
    raise RuntimeError("未安装 gudhi 或 ripser，无法计算持续同调")


def landscape_lp_norm(diagrams, p: int = 1, n_layers: int = 5,
                      n_bins: int = 100, grid_max: float | None = None):
    """固定网格的持续景观 Lp 范数。

    grid_max 必须由训练段估计后显式传入；禁止每窗口自动 fit 网格。
    H0 无限 bar 必须在调用前剔除。首版主特征使用 total_persistence，
    此函数仅留作固定网格稳健性检验。
    """
    import math

    if grid_max is None or not math.isfinite(grid_max) or grid_max <= 0:
        raise ValueError("grid_max 必须是由训练段确定的有限正数")
    if not HAS_GUDHI:
        raise RuntimeError("固定网格 Landscape 需要 gudhi")
    from gudhi.representations import Landscape
    import numpy as np

    dgm = finite_diagram(diagrams)
    if dgm.size == 0:
        return 0.0
    land = Landscape(num_landscapes=n_layers, resolution=n_bins,
                     sample_range=[0.0, float(grid_max)])
    layers = land.fit_transform([dgm])[0]
    dx = float(grid_max) / max(n_bins - 1, 1)
    return float((np.sum(np.abs(layers) ** p) * dx) ** (1.0 / p))


def persistence_entropy(diagrams, eps: float = 1e-12) -> float:
    import math
    life = [d - b for b, d in diagrams if d != float("inf") and d > b]
    if not life:
        return 0.0
    total = sum(life)
    return float(-sum((v / total) * math.log(v / total + eps) for v in life))


def finite_diagram(diagram):
    """转为 (n,2) 并剔除无限/非法 bar；H0 的无限类不进入有限特征。"""
    import numpy as np

    arr = np.asarray(diagram, dtype=float).reshape(-1, 2)
    if not len(arr):
        return np.empty((0, 2), dtype=float)
    keep = np.isfinite(arr).all(axis=1) & (arr[:, 1] >= arr[:, 0])
    return arr[keep]


def total_persistence(diagram, p: float = 1.0) -> float:
    """有限 bar 的 p-total persistence：无网格、无拟合、跨窗口口径一致。"""
    if p <= 0:
        raise ValueError("p 必须为正数")
    import numpy as np

    dgm = finite_diagram(diagram)
    if not len(dgm):
        return 0.0
    life = dgm[:, 1] - dgm[:, 0]
    return float(np.sum(life ** p) ** (1.0 / p))


def inverse_density(cloud, k: int = 5):
    """kNN 逆密度 g_k：第 k 近邻半径，越小越常见，越大越边缘。

    仅使用当前窗口内的点；不对全样本拟合 scaler 或密度模型。
    """
    import numpy as np

    X = np.asarray(cloud, dtype=float)
    if X.ndim != 2 or not np.isfinite(X).all():
        raise ValueError("cloud 必须是有限的二维数组")
    n = len(X)
    if not 1 <= k < n:
        raise ValueError(f"k 必须满足 1 <= k < 点数，当前 k={k}, n={n}")
    delta = X[:, None, :] - X[None, :, :]
    dist = np.sqrt(np.einsum("ijk,ijk->ij", delta, delta))
    np.fill_diagonal(dist, np.inf)
    return np.partition(dist, k - 1, axis=1)[:, k - 1]


def diagram_wasserstein(diagram_a, diagram_b, p: int = 1) -> float:
    """有限持续图的 Wasserstein 距离，直接调用 persim。"""
    if p != 1:
        raise NotImplementedError("首版仅冻结 W1；其他阶数留作后续敏感性")
    from persim import wasserstein

    return float(wasserstein(finite_diagram(diagram_a),
                             finite_diagram(diagram_b)))


TOPOLOGY_FEATURE_COLUMNS = tuple(
    f"{kind}_{region}_h{dim}"
    for kind in ("A", "D")
    for region in ("full", "core", "edge")
    for dim in (0, 1)
)


SINGLE_PARAMETER_FEATURE_COLUMNS = (
    "A_full_h0", "A_full_h1", "D_full_h0", "D_full_h1",
)


def extract_single_parameter_features(clouds) -> list[dict]:
    """Gate 1专用：仅完整点云H0/H1的A与相邻图W1，不计算密度切片。"""
    import numpy as np

    rows = []
    previous = None
    for date, cloud in clouds:
        X = np.asarray(cloud, dtype=float)
        if X.ndim != 2 or not np.isfinite(X).all():
            raise ValueError(f"{date}点云无效")
        diagrams = vr_diagrams(X, maxdim=1)
        row = {"date": date}
        for dim in (0, 1):
            row[f"A_full_h{dim}"] = total_persistence(diagrams[dim])
            row[f"D_full_h{dim}"] = (
                None if previous is None else diagram_wasserstein(previous[dim], diagrams[dim])
            )
        rows.append(row)
        previous = diagrams
    return rows


def extract_sliced_features(clouds, k: int = 5, core_fraction: float = 0.7,
                            point_dates=None) -> list[dict]:
    """从逐日点云提取 full/core/edge × H0/H1 × 状态/变化特征。

    A = 有限 bar 的 total persistence（H0 无限 bar 剔除）。
    D_t = W1(PD_t, PD_{t-1})，首日无前值记 None。
    edge = full - core，仅为诊断差分，不是独立边缘同调模，也不保证非负。

    clouds: [(窗口末日, cloud), ...]；point_dates 若给出，须与 clouds 等长，
    每项是该窗口内各点的原始日期，用于保留边缘点溯源信息。
    """
    import numpy as np

    if not 0 < core_fraction <= 1:
        raise ValueError("core_fraction 必须位于 (0,1]")
    clouds = list(clouds)
    if point_dates is not None and len(point_dates) != len(clouds):
        raise ValueError("point_dates 必须与 clouds 等长")
    rows = []
    previous = {"full": None, "core": None}

    for i, (date, cloud) in enumerate(clouds):
        X = np.asarray(cloud, dtype=float)
        dates = None if point_dates is None else list(point_dates[i])
        if dates is not None and len(dates) != len(X):
            raise ValueError(f"第 {i} 个窗口的 point_dates 与点数不一致")
        g = inverse_density(X, k=k)
        threshold = float(np.quantile(g, 1.0 - core_fraction))
        core_mask = g <= threshold
        if core_mask.sum() < 2:
            raise RuntimeError("核心切片点数不足，无法计算持续图")
        diagrams = {
            "full": vr_diagrams(X, maxdim=1),
            "core": vr_diagrams(X[core_mask], maxdim=1),
        }
        edge_mask = ~core_mask
        row = {
            "date": date,
            "n_full": int(len(X)),
            "n_core": int(core_mask.sum()),
            "density_g_median": float(np.median(g)),
            "density_g_q90": float(np.quantile(g, 0.9)),
            "density_g_latest": float(g[-1]),
            "core_threshold": threshold,
            "edge_fraction": float(edge_mask.mean()),
            "latest_is_edge": bool(edge_mask[-1]),
            "edge_dates": (
                [d for d, is_edge in zip(dates, edge_mask) if is_edge]
                if dates is not None else None
            ),
        }
        for region in ("full", "core"):
            for dim in (0, 1):
                current = diagrams[region][dim]
                row[f"A_{region}_h{dim}"] = total_persistence(current)
                row[f"D_{region}_h{dim}"] = (
                    None if previous[region] is None
                    else diagram_wasserstein(previous[region][dim], current)
                )
        for dim in (0, 1):
            row[f"A_edge_h{dim}"] = (
                row[f"A_full_h{dim}"] - row[f"A_core_h{dim}"]
            )
            row[f"D_edge_h{dim}"] = (
                None if row[f"D_full_h{dim}"] is None
                else row[f"D_full_h{dim}"] - row[f"D_core_h{dim}"]
            )
        missing = [c for c in TOPOLOGY_FEATURE_COLUMNS if c not in row]
        if missing:
            raise AssertionError(f"特征列缺失: {missing}")
        rows.append(row)
        previous = diagrams
    return rows


def sliced_bifiltration(cloud, scores, quantiles=(0.2, 0.4, 0.6, 0.8, 1.0),
                        maxdim: int = 1):
    """投影条形码近似：沿第二滤过轴分层，每层跑一次单参数 VR，用 ripser/gudhi 即可。

    这是 Windows 下的**可用替代路径**，不依赖 multipers/pykeops。
    注意：它是对双参数模的离散切片近似（fibered barcode 思路），
    **不等价于**完整的双参数持续模；若声称完整双参数不变量或与其比较，
    仍须在 WSL/Linux 上用 multipers 复核。

    scores: 与 cloud 行数等长的第二轴取值，越大表示越"核心"。
    quantiles: 从核心到全体逐层纳入的比例（1.0 = 全部点）。
    """
    import numpy as np

    X = np.asarray(cloud, dtype=float)
    s = np.asarray(scores, dtype=float)
    if X.ndim != 2 or len(s) != len(X):
        raise ValueError("cloud 必须为 2D，scores 长度须与点数一致")
    out = []
    for q in quantiles:
        thr = float(np.quantile(s, 1.0 - q))
        sub = X[s >= thr]
        if len(sub) < maxdim + 2:
            out.append({"quantile": q, "n_points": len(sub),
                        "n_h1": 0, "h1_max_lifetime": 0.0, "h1_entropy": 0.0})
            continue
        dgms = vr_diagrams(sub.tolist(), maxdim=maxdim)
        h1 = dgms[1] if len(dgms) > 1 else np.empty((0, 2))
        life = (h1[:, 1] - h1[:, 0]) if len(h1) else np.array([])
        out.append({
            "quantile": q,
            "n_points": int(len(sub)),
            "n_h1": int(len(h1)),
            "h1_max_lifetime": float(life.max()) if len(life) else 0.0,
            "h1_entropy": persistence_entropy(h1.tolist() if len(h1) else []),
        })
    return out


def bifiltration_signed_measure(points, densities, **kwargs):
    """完整双参数（尺度 × 密度）入口 —— 当前平台阻塞。

    切片第二轴已采用 kNN 逆密度，但这不代表完整 signed measure 已实现。
    """
    if not HAS_MULTIPERS:
        raise NotImplementedError(
            "完整双参数需要 multipers + pykeops，Windows 原生环境不可用"
            "（实测 filtrations 段错误）。请用 WSL/Linux，或改用 sliced_bifiltration。"
        )
    raise NotImplementedError(
        "第二滤过轴的金融定义未定；先确定 density/correlation/liquidity 口径"
        "并用训练段校准，再接 multipers。"
    )
