"""Episode 级事件研究的前置模块（协议 v2 地基）。

与 1A 的日频重叠事件不同，episode 把一段连续的低分位状态压缩为一个“可交易
信号/一笔记账单位”。本模块不改动冻结的 1A 协议，只提供可被后续协议 v2 使用
的构造与描述函数。
"""

from dataclasses import asdict, dataclass
from datetime import date
from statistics import median
from typing import Sequence, Tuple

from .data import AlignedPoint
from .research import ForwardEvent, build_forward_events


@dataclass(frozen=True)
class Episode:
    date: date
    outcome_date: date
    forward_return: float
    percentile: float
    history_count: int
    low_state_days: int


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else None


def collapse_low_state_episodes(
    events: Sequence[ForwardEvent],
) -> Tuple[Episode, ...]:
    """把连续的 low_state 日频事件压缩为一次 episode。

    一次 episode 从该段低分位状态的第一个可交易日开始；同一段连续低状态内不再
    重复建仓。这样得到的样本单位更接近真实交易中的“一次信号/一笔交易”。
    """
    ordered = tuple(sorted(events, key=lambda event: event.date))
    episodes = []
    run_start = None
    run_length = 0
    for event in ordered:
        if event.low_state:
            if run_start is None:
                run_start = event
                run_length = 1
            else:
                run_length += 1
            continue
        if run_start is not None:
            episodes.append(
                Episode(
                    date=run_start.date,
                    outcome_date=run_start.outcome_date,
                    forward_return=run_start.forward_return,
                    percentile=run_start.percentile,
                    history_count=run_start.history_count,
                    low_state_days=run_length,
                )
            )
            run_start = None
            run_length = 0
    if run_start is not None:
        episodes.append(
            Episode(
                date=run_start.date,
                outcome_date=run_start.outcome_date,
                forward_return=run_start.forward_return,
                percentile=run_start.percentile,
                history_count=run_start.history_count,
                low_state_days=run_length,
            )
        )
    return tuple(episodes)


def build_forward_episodes(
    history: Sequence[AlignedPoint],
    selected: Sequence[AlignedPoint],
    *,
    horizon: int,
) -> Tuple[Episode, ...]:
    """构造低分位状态 episode，而不是逐日事件。"""
    events = build_forward_events(history, selected, horizon=horizon)
    return collapse_low_state_episodes(events)


def summarize_episode_research(
    history: Sequence[AlignedPoint],
    selected: Sequence[AlignedPoint],
    *,
    horizon: int,
):
    """输出 episode 与旧日频事件之间的压缩程度和收益描述。"""
    daily_events = build_forward_events(history, selected, horizon=horizon)
    episodes = collapse_low_state_episodes(daily_events)
    low_returns = [
        event.forward_return for event in daily_events if event.low_state
    ]
    episode_returns = [episode.forward_return for episode in episodes]
    daily_count = len(low_returns)
    episode_count = len(episodes)
    return {
        "method": "episode_low_state_forward_return_research",
        "horizon_trading_days": horizon,
        "low_state_threshold": 0.2,
        "daily_low_state_event_count": daily_count,
        "episode_count": episode_count,
        "events_per_episode": (
            daily_count / episode_count if episode_count else None
        ),
        "daily_low_state_returns": {
            "mean": _mean(low_returns),
            "median": median(low_returns) if low_returns else None,
            "positive_rate": (
                sum(value > 0 for value in low_returns) / len(low_returns)
                if low_returns
                else None
            ),
        },
        "episode_returns": {
            "mean": _mean(episode_returns),
            "median": median(episode_returns) if episode_returns else None,
            "positive_rate": (
                sum(value > 0 for value in episode_returns)
                / len(episode_returns)
                if episode_returns
                else None
            ),
        },
        "episodes": [
            {
                **asdict(episode),
                "date": episode.date.isoformat(),
                "outcome_date": episode.outcome_date.isoformat(),
            }
            for episode in episodes
        ],
    }


def chronological_split_date(points: Sequence[AlignedPoint]) -> date:
    """与 1A 一致的 70/30 时间顺序切分，供 episode 诊断使用。"""
    if not points:
        raise ValueError("points 不能为空")
    if len(points) < 2:
        return points[0].date
    index = min(len(points) - 1, max(1, int(len(points) * 0.7)))
    return points[index].date


def split_episode_counts(
    episodes: Sequence[Episode],
    *,
    split_date: date,
    horizon: int,
) -> dict:
    """预注册协议 v2 的最小切分描述：样本内/边界清除/样本外 episode 数。"""
    in_sample = 0
    purged = 0
    out_of_sample = 0
    for episode in episodes:
        if episode.date >= split_date:
            out_of_sample += 1
        elif episode.outcome_date < split_date:
            in_sample += 1
        else:
            purged += 1
    return {
        "episode_count": len(episodes),
        "split_date": split_date.isoformat(),
        "in_sample_episodes": in_sample,
        "purged_boundary_episodes": purged,
        "out_of_sample_episodes": out_of_sample,
        "minimum_episode_count": 30,
        "note": "v2 仍需预注册完整证据门槛与推断方法",
    }
