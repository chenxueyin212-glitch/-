"""严格因果的检测器与评估器（交易日口径）。

改写自 third_party/guritanu2025/utils_causal.py，并做三处项目化修正：
1. 时间单位由自然日 Timedelta 改为**交易日索引**（A股停牌/节假日会扭曲自然日提前期）。
2. 增加 FP/年、purge/embargo 切分、leave-one-crisis-out 接口。
3. 明确拒绝旧 utils.py 的"未来均值"条件与 700 天提前窗口。
"""
from __future__ import annotations

from itertools import product
from statistics import median


def past_average(x: list[float], w: int) -> list[float | None]:
    """j 处返回 x[j-w:j] 的均值（严格不含 x[j]）；不足 w 返回 None。"""
    out: list[float | None] = [None] * len(x)
    if w <= 0:
        return out
    cs = [0.0]
    for v in x:
        cs.append(cs[-1] + v)
    for j in range(w, len(x)):
        out[j] = (cs[j] - cs[j - w]) / w
    return out


def detect_ews(norms: list[float], alpha: float, beta: float, s: int, t: int) -> list[int]:
    """三条件全部只用 t 及之前的信息。

    (1) N_j/N_{j-1} >= alpha
    (2) N_j/Q_short_j >= beta
    (3) Q_short_j/Q_long_j >= beta   <- 旧 utils.py 此处用未来均值，已修正
    """
    eps = 1e-12
    # 注意：论文配置 s=57 > t=16，故 avg_s 是长窗口、avg_t 是短窗口，
    # 与其变量名 short/long 相反。此处按公式原样实现，不做语义猜测。
    avg_s = past_average(norms, s)
    avg_t = past_average(norms, t)
    hits = []
    for j in range(max(1, s, t), len(norms)):
        if avg_s[j] is None or avg_t[j] is None:
            continue
        if (norms[j] / max(norms[j - 1], eps) >= alpha
                and norms[j] / max(avg_s[j], eps) >= beta
                and avg_s[j] / max(avg_t[j], eps) >= beta):
            hits.append(j)
    return hits


def collapse_runs(idx) -> list[int]:
    idx = sorted(set(idx))
    if not idx:
        return []
    keep = [idx[0]]
    for k in idx[1:]:
        if k != keep[-1] + 1:
            keep.append(k)
    return keep


def evaluate_ews(
    crisis_idx, signal_idx, lead: int, lag: int,
    total_days: int, trading_days_per_year: int = 244,
) -> dict:
    """交易日口径评估。crisis_idx / signal_idx 均为同一坐标轴的整数索引。"""
    crises = sorted(set(crisis_idx))
    signals = sorted(set(signal_idx))
    used: set[int] = set()
    matched_early, matched_late = {}, {}

    for c in crises:
        early = [e for e in signals if c - lead <= e <= c and e not in used]
        if early:
            pick = max(early)
            matched_early[c] = pick
            used.add(pick)
            continue
        late = [e for e in signals if c < e <= c + lag and e not in used]
        if late:
            pick = min(late)
            matched_late[c] = pick
            used.add(pick)

    tp, late_ct = len(matched_early), len(matched_late)
    fn = sum(1 for c in crises if c not in matched_early and c not in matched_late)
    fp = sum(1 for e in signals if e not in used)
    precision = tp / (tp + late_ct + fp) if (tp + late_ct + fp) else None
    recall = tp / (tp + late_ct + fn) if (tp + late_ct + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else (0.0 if precision == 0 and recall == 0 else None)
    )
    years = total_days / trading_days_per_year if trading_days_per_year else 1.0
    leads = [c - matched_early[c] for c in matched_early]
    return {
        "TP": tp, "Late": late_ct, "FN": fn, "FP": fp,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "false_alarms_per_year": round(fp / years, 3) if years else None,
        "mean_lead_days": round(sum(leads) / len(leads), 2) if leads else None,
        "median_lead_days": round(float(median(leads)), 2) if leads else None,
        "evaluated_days": total_days,
    }


def walk_forward_splits(n: int, initial_train: int, val: int, purge: int, embargo: int):
    """扩展窗口切分：训练段尾部剔除 purge，验证段前留 embargo 间隔。"""
    if n < initial_train + purge + embargo + val:
        return
    train_end = initial_train
    while True:
        tr = (0, train_end - purge)
        va = (train_end + embargo, train_end + embargo + val)
        if va[1] > n:
            return
        yield tr, va
        train_end = va[1]
        if train_end + embargo + val > n:
            return


def walk_forward_date_splits(dates, label_end_dates, initial_train: int, val_days: int):
    """扩展训练的日期级切分；保留尾折，训练标签终点必须早于验证开始日。

    返回字典同时携带日期和整数索引，供审计表与模型管线共同使用。
    调用方须先剔除标签未定样本，并保证dates与label_end_dates一一对应。
    """
    dates = list(dates)
    label_end_dates = list(label_end_dates)
    if len(dates) != len(label_end_dates):
        raise ValueError("dates与label_end_dates长度不一致")
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError("dates必须严格递增且不得重复")
    if any(v is None for v in label_end_dates):
        raise ValueError("切分输入不得包含标签未定样本")
    if initial_train < 1 or val_days < 1:
        raise ValueError("initial_train与val_days必须为正整数")
    raw_end = initial_train
    fold = 0
    while raw_end < len(dates):
        val_idx = tuple(range(raw_end, min(raw_end + val_days, len(dates))))
        if not val_idx:
            break
        validation_start = dates[val_idx[0]]
        train_idx = tuple(
            i for i in range(raw_end) if label_end_dates[i] < validation_start
        )
        if not train_idx:
            raise RuntimeError(f"第{fold + 1}折purge后无训练样本")
        fold += 1
        yield {
            "fold": fold,
            "train_raw_start": dates[0],
            "train_raw_end": dates[raw_end - 1],
            "train_used_start": dates[train_idx[0]],
            "train_used_end": dates[train_idx[-1]],
            "max_train_label_end": max(label_end_dates[i] for i in train_idx),
            "validation_start": validation_start,
            "validation_end": dates[val_idx[-1]],
            "n_train_raw": raw_end,
            "n_train": len(train_idx),
            "n_purged": raw_end - len(train_idx),
            "n_validation": len(val_idx),
            "train_indices": train_idx,
            "validation_indices": val_idx,
        }
        raw_end = val_idx[-1] + 1


def threshold_grid(alphas, betas) -> list[tuple[float, float]]:
    return list(product(alphas, betas))
