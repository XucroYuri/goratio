"""Episode 级样本外事件研究（协议 v2 前置证据层）。

相对 1A 的日频重叠事件研究，本模块以“episode = 一次低分位信号”为样本，
对 63/126/252 日远期收益做时间顺序切分与边界清除，并对比 episode 与全样本
基线的平均收益。当前使用 trade-level iid bootstrap 给出差值的 95% 与 98.33%
区间；后续仍需在真实合约数据上补充换月、成本与更复杂的依赖结构。
"""

import math
import random
from typing import Optional, Sequence

from .data import AlignedPoint
from .dataset import PreparedMarketData
from .episodes import Episode, build_forward_episodes, chronological_split_date
from .research import build_forward_events

MIN_OUT_OF_SAMPLE_EPISODES = 30


def _mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _bootstrap_difference_ci(
    episode_returns: Sequence[float],
    baseline_returns: Sequence[float],
    *,
    confidence: float,
    repetitions: int = 999,
    seed: int = 20260902,
) -> Optional[list]:
    if not episode_returns or not baseline_returns:
        return None
    generator = random.Random(seed)
    differences = []
    for _ in range(repetitions):
        episode_sample = generator.choices(
            episode_returns, k=len(episode_returns)
        )
        baseline_sample = generator.choices(
            baseline_returns, k=len(baseline_returns)
        )
        differences.append(_mean(episode_sample) - _mean(baseline_sample))
    alpha = 1 - confidence
    return [
        _quantile(differences, alpha / 2),
        _quantile(differences, 1 - alpha / 2),
    ]


def _summarize_returns(returns: Sequence[float]) -> dict:
    if not returns:
        return {
            "sample_count": 0,
            "mean": None,
            "positive_rate": None,
        }
    return {
        "sample_count": len(returns),
        "mean": _mean(returns),
        "positive_rate": sum(value > 0 for value in returns) / len(returns),
    }


def _segment_study(
    episodes: Sequence[Episode],
    baseline: Sequence,
    *,
    seed: int,
    repetitions: int = 999,
) -> dict:
    episode_returns = [episode.forward_return for episode in episodes]
    baseline_returns = [event.forward_return for event in baseline]
    conditional = _summarize_returns(episode_returns)
    unconditional = _summarize_returns(baseline_returns)
    difference = (
        conditional["mean"] - unconditional["mean"]
        if conditional["mean"] is not None and unconditional["mean"] is not None
        else None
    )
    return {
        "conditional_episodes": conditional,
        "unconditional_daily_baseline": unconditional,
        "difference_mean": difference,
        "difference_ci_95": _bootstrap_difference_ci(
            episode_returns,
            baseline_returns,
            confidence=0.95,
            repetitions=repetitions,
            seed=seed,
        ),
        "difference_ci_98_33": _bootstrap_difference_ci(
            episode_returns,
            baseline_returns,
            confidence=1 - 0.05 / 3,
            repetitions=repetitions,
            seed=seed + 1,
        ),
    }


def run_episode_evidence_study(
    data: PreparedMarketData,
    *,
    horizon: int,
    bootstrap_repetitions: int = 999,
) -> dict:
    """对单个 horizon 运行 episode 级 OOS 证据诊断。"""
    history = data.history.points
    selected = data.selected.points
    daily_events = build_forward_events(history, selected, horizon=horizon)
    episodes = build_forward_episodes(history, selected, horizon=horizon)
    split_date = chronological_split_date(selected)

    in_sample_episodes = []
    purged_episodes = []
    out_of_sample_episodes = []
    for episode in episodes:
        if episode.date < split_date:
            if episode.outcome_date < split_date:
                in_sample_episodes.append(episode)
            else:
                purged_episodes.append(episode)
        else:
            out_of_sample_episodes.append(episode)

    in_sample_baseline = [
        event
        for event in daily_events
        if event.date < split_date and event.outcome_date < split_date
    ]
    out_of_sample_baseline = [
        event for event in daily_events if event.date >= split_date
    ]

    seed = 20260902 + horizon
    all_sample = _segment_study(
        episodes, daily_events, seed=seed
    )
    in_sample = _segment_study(
        in_sample_episodes,
        in_sample_baseline,
        seed=seed + 1000,
    )
    out_of_sample = _segment_study(
        out_of_sample_episodes,
        out_of_sample_baseline,
        seed=seed + 2000,
    )

    oos_count = out_of_sample["conditional_episodes"]["sample_count"]
    familywise_interval = out_of_sample["difference_ci_98_33"]
    if not data.evidence_eligible or oos_count < MIN_OUT_OF_SAMPLE_EPISODES:
        evidence_status = "insufficient_data"
    elif familywise_interval and familywise_interval[0] > 0:
        evidence_status = "supported"
    else:
        evidence_status = "not_supported"

    return {
        "method": "episode_oos_bootstrap_diagnostic_v2",
        "horizon_trading_days": horizon,
        "minimum_out_of_sample_episodes": MIN_OUT_OF_SAMPLE_EPISODES,
        "bootstrap": {
            "method": "iid_trade_level_resample",
            "repetitions": bootstrap_repetitions,
            "block_length": 1,
            "seed_base": seed,
            "limitation": "episode 已压缩为独立交易近似；仍未建模真实换月/成本/重叠组合",
        },
        "split_date": split_date.isoformat(),
        "episode_count": len(episodes),
        "split": {
            "in_sample_episodes": len(in_sample_episodes),
            "purged_boundary_episodes": len(purged_episodes),
            "out_of_sample_episodes": len(out_of_sample_episodes),
        },
        "all_sample": all_sample,
        "in_sample": in_sample,
        "out_of_sample": out_of_sample,
        "evidence_status": evidence_status,
        "limitations": [
            "episode 为低分位首次触发，忽略同一状态内的重复入场",
            "bootstrap 使用 trade-level iid 近似，尚未处理复杂时间依赖",
            "仍使用相邻收盘价代理执行，未包含真实换月和 T+1 open/settle",
        ],
    }


def run_episode_evidence_bundle(
    data: PreparedMarketData,
    *,
    bootstrap_repetitions: int = 999,
) -> dict:
    """对 63/126/252 三个期限运行 episode 级证据诊断。"""
    horizons = {}
    for horizon in (63, 126, 252):
        horizons[str(horizon)] = run_episode_evidence_study(
            data,
            horizon=horizon,
            bootstrap_repetitions=bootstrap_repetitions,
        )
    return {
        "method": "episode_oos_bootstrap_diagnostic_bundle_v2",
        "horizons": horizons,
    }
