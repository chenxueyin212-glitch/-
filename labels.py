"""市场级危机标签与事件清单。

provenance：
- 主标签 Y_t 完全由程序化规则定义（未来 horizon 个交易日内基准指数最大回撤）。
- `DRAFT_CRISIS_EVENTS` 是**整理者设定的草案**，仅用于 leave-one-crisis-out 分组与结果展示，
  不是权威危机年表；正式使用前必须用 index_daily_raw 按同一回撤规则校准起点并登记来源。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrisisEvent:
    name: str
    start: str
    end: str
    kind: str
    source: str = "整理者草案，待指数校准"


DRAFT_CRISIS_EVENTS: tuple[CrisisEvent, ...] = (
    CrisisEvent("2008 全球金融危机", "2008-01-15", "2008-11-04", "长期深熊"),
    CrisisEvent("2015 杠杆股灾", "2015-06-12", "2015-08-26", "急性崩盘"),
    CrisisEvent("2016 熔断与汇率冲击", "2016-01-04", "2016-01-28", "外生冲击"),
    CrisisEvent("2018 去杠杆慢熊", "2018-01-29", "2019-01-04", "长期深熊"),
    CrisisEvent("2020 疫情冲击", "2020-01-20", "2020-03-23", "外生冲击"),
    CrisisEvent("2022 紧缩与地缘冲击", "2022-01-04", "2022-04-26", "长期深熊"),
    CrisisEvent("2024 小微盘流动性危机", "2024-01-02", "2024-02-05", "结构性危机"),
)


def market_drawdown_label(dates, prices, horizon: int, drawdown: float) -> list[bool | None]:
    """Y_t = 1{ min_{1<=k<=horizon}(P_{t+k}/P_t - 1) <= drawdown }。

    末尾 horizon 个交易日无法判定，返回 None（必须从评估中剔除，不能填 0）。
    """
    n = len(prices)
    if n != len(dates):
        raise ValueError("dates 与 prices 长度不一致")
    out: list[bool | None] = []
    for t in range(n):
        if t + horizon >= n or prices[t] <= 0:
            out.append(None)
            continue
        p0 = prices[t]
        worst = min(prices[t + k] / p0 - 1.0 for k in range(1, horizon + 1))
        out.append(worst <= drawdown)
    return out


def threshold_crossing_events(dates, prices, horizon: int, drawdown: float,
                              merge_gap: int = 20) -> list[dict]:
    """由同一标签规则机械生成危机事件，不使用事后人工峰谷。

    若存在1<=u-t<=horizon使P_u/P_t-1<=drawdown，则u为阈值穿越日。
    相邻穿越日的交易日索引距离<=merge_gap时合并为一轮事件，首个穿越日为onset。
    """
    if len(dates) != len(prices) or len(dates) < 2:
        raise ValueError("dates与prices须等长且至少含两日")
    crossing: set[int] = set()
    for t in range(len(prices) - 1):
        if prices[t] <= 0:
            continue
        for k in range(1, horizon + 1):
            u = t + k
            if u >= len(prices):
                break
            if prices[u] / prices[t] - 1.0 <= drawdown:
                crossing.add(u)
    ordered = sorted(crossing)
    if not ordered:
        return []
    clusters: list[list[int]] = [[ordered[0]]]
    for u in ordered[1:]:
        if u - clusters[-1][-1] <= merge_gap:
            clusters[-1].append(u)
        else:
            clusters.append([u])
    return [
        {
            "onset_index": cluster[0], "onset_date": dates[cluster[0]],
            "last_crossing_index": cluster[-1], "last_crossing_date": dates[cluster[-1]],
            "n_crossing_days": len(cluster),
        }
        for cluster in clusters
    ]


def event_to_index(dates, event_date: str) -> int:
    """取不晚于事件日的最近交易日索引。"""
    lo, hi = 0, len(dates) - 1
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if dates[mid] <= event_date:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    if dates[best] > event_date:
        raise ValueError(f"{event_date} 早于数据起点")
    return best


def leave_one_crisis_out(events=DRAFT_CRISIS_EVENTS):
    """每次留一轮危机作最终检验，其余用于调参。"""
    for i, held in enumerate(events):
        train = tuple(e for j, e in enumerate(events) if j != i)
        yield held, train
