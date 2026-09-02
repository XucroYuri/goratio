"""成本后 episode 回测与最小风控门控（协议 v2 前置诊断）。

当前版本采用 episode 作为一次交易样本，使用“次日收盘等价执行”的简化处理：
- 同一段低分位状态只做一次交易；
- 仅保留符合双因子 v2 变体 A 中“黄金 252 日动量 > 0”确认的交易；
- 每笔交易扣除 round_trip_cost_bps；
- 输出交易级净收益、累计净值最大回撤与最小风控门控。

该模块不把连续期货序列伪装成真实可执行合约；真实换月、保证金、滑点和
T+1 open/settle 执行缺口仍需后续接入。
"""

import math
from datetime import date
from statistics import median
from typing import Optional, Sequence

from .data import AlignedPoint
from .dataset import PreparedMarketData
from .episodes import Episode, build_forward_episodes


MIN_TRADE_COUNT = 30


def _mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _momentum_at(
    history: Sequence[AlignedPoint],
    entry_date: date,
    *,
    lookback: int = 252,
) -> Optional[float]:
    for index, point in enumerate(history):
        if point.date == entry_date:
            if index - lookback >= 0:
                past = history[index - lookback]
                return point.gold_close / past.gold_close - 1
            return None
    return None


def _history_index_by_date(
    history: Sequence[AlignedPoint],
    entry_date: date,
) -> Optional[int]:
    for index, point in enumerate(history):
        if point.date == entry_date:
            return index
    return None


def _t1_close_return(
    history: Sequence[AlignedPoint],
    entry_date: date,
    horizon: int,
) -> Optional[float]:
    index = _history_index_by_date(history, entry_date)
    if index is None:
        return None
    fill_index = index + 1
    exit_index = fill_index + horizon
    if exit_index >= len(history):
        return None
    return (
        history[exit_index].gold_close / history[fill_index].gold_close - 1
    )


def _max_drawdown_from_compounded(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in values:
        equity *= 1.0 + value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def run_episode_cost_backtest(
    data: PreparedMarketData,
    *,
    horizon: int = 126,
    round_trip_cost_bps: float = 20.0,
    trend_confirmation: bool = True,
    t1_close_execution: bool = False,
    roll_cost_bps: float = 0.0,
) -> dict:
    """对低分位 episode 做成本后交易级回测诊断。

    t1_close_execution=True 时，信号日之后一个共同交易日的收盘价作为成交价；
    该实现只使用现有收盘序列，不等同于 T+1 open/settle 真实执行。
    roll_cost_bps 用于把换月价差成本作为每笔 episode 的附加成本简单计入。
    """
    history = data.history.points
    episodes = build_forward_episodes(
        history,
        data.selected.points,
        horizon=horizon,
    )
    trades = []
    for episode in episodes:
        momentum = _momentum_at(history, episode.date)
        if trend_confirmation and (momentum is None or momentum <= 0):
            continue
        if t1_close_execution:
            gross_return = _t1_close_return(
                history, episode.date, horizon
            )
            if gross_return is None:
                continue
        else:
            gross_return = episode.forward_return
        net_return = gross_return - (
            round_trip_cost_bps + roll_cost_bps
        ) / 10000.0
        trades.append(
            {
                "entry_date": episode.date.isoformat(),
                "outcome_date": episode.outcome_date.isoformat(),
                "gross_return": gross_return,
                "net_return": net_return,
                "momentum_252d": momentum,
                "low_state_days": episode.low_state_days,
            }
        )

    gross_returns = [trade["gross_return"] for trade in trades]
    net_returns = [trade["net_return"] for trade in trades]
    mean_gross = _mean(gross_returns)
    mean_net = _mean(net_returns)
    max_drawdown = _max_drawdown_from_compounded(net_returns)

    risk_flags = []
    if len(trades) < MIN_TRADE_COUNT:
        risk_flags.append("insufficient_trade_count")
    if mean_net is not None and mean_net <= 0:
        risk_flags.append("negative_cost_adjusted_mean")
    if max_drawdown is not None and max_drawdown >= 0.2:
        risk_flags.append("trade_level_drawdown_exceeds_20pct")

    return {
        "method": "episode_cost_backtest_v2_diagnostic",
        "horizon_trading_days": horizon,
        "round_trip_cost_bps": round_trip_cost_bps,
        "trend_confirmation": trend_confirmation,
        "t1_close_execution": t1_close_execution,
        "roll_cost_bps": roll_cost_bps,
        "trade_count": len(trades),
        "risk_gates": {
            "minimum_trade_count": MIN_TRADE_COUNT,
            "minimum_trade_count_passed": len(trades) >= MIN_TRADE_COUNT,
            "cost_adjusted_positive_passed": bool(
                mean_net is not None and mean_net > 0
            ),
            "max_trade_level_drawdown_threshold": 0.2,
            "max_trade_level_drawdown_passed": bool(
                max_drawdown is not None and max_drawdown < 0.2
            ),
        },
        "metrics": {
            "mean_gross_return": mean_gross,
            "mean_net_return": mean_net,
            "median_gross_return": median(gross_returns) if gross_returns else None,
            "median_net_return": median(net_returns) if net_returns else None,
            "positive_net_rate": (
                sum(value > 0 for value in net_returns) / len(net_returns)
                if net_returns
                else None
            ),
            "total_net_return_compounded": (
                math.prod(1.0 + value for value in net_returns) - 1.0
                if net_returns
                else None
            ),
            "max_trade_equity_drawdown": max_drawdown,
            "largest_single_trade_loss": min(net_returns) if net_returns else None,
        },
        "trades": trades,
        "risk_flags": risk_flags,
        "limitations": [
            "episode 作为交易样本，忽略重叠持仓与真实换月",
            "成交价使用相邻共同交易日收盘价代理，不是 T+1 open/settle"
            if not t1_close_execution
            else "T+1 模式使用信号后一个共同交易日收盘价执行，仍非 open/settle",
            "未包含保证金、资金成本、市场冲击和人民币换算",
            "当前是诊断，不是已冻结协议 v2 的证据",
        ],
        "disclaimer": "仅供历史统计研究与方法复现，不构成投资建议或仓位建议",
    }
