"""双因子 v2 正式预注册证据门槛（成本后 episode 级）。

该模块把已有组件组合成协议 v2 的证据判断：
1. episode 作为独立样本；
2. OOS episode 数量不少于 30；
3. OOS episode 相对全样本基线的 98.33% 家族区间下界 > 0；
4. 对 episode 平均收益扣除预注册 round_trip_cost_bps 后仍为正；
5. 输出最小回撤门控供参考。

当前版本仍是协议 v2 诊断，不对外宣称已通过冻结验收。
"""

from typing import Optional

from .backtest import run_episode_cost_backtest
from .dataset import PreparedMarketData
from .episode_study import run_episode_evidence_study

PROTOCOL_V2_ID = "goratio-2a-v1"
DEFAULT_COST_BPS = 20.0
MIN_OUT_OF_SAMPLE_EPISODES = 30


def _mean(values) -> Optional[float]:
    return sum(values) / len(values) if values else None


def run_v2_horizon_gate(
    data: PreparedMarketData,
    *,
    horizon: int,
    cost_bps: float = DEFAULT_COST_BPS,
    roll_cost_bps: float = 0.0,
) -> dict:
    """对单个 horizon 运行 v2 组合门槛。"""
    study = run_episode_evidence_study(data, horizon=horizon)
    backtest = run_episode_cost_backtest(
        data,
        horizon=horizon,
        round_trip_cost_bps=cost_bps,
        trend_confirmation=True,
        t1_close_execution=True,
        roll_cost_bps=roll_cost_bps,
    )
    oos_count = study["out_of_sample"]["conditional_episodes"]["sample_count"]
    oos_mean = study["out_of_sample"]["conditional_episodes"]["mean"]
    cost_adjusted_oos_mean = (
        oos_mean - cost_bps / 10000.0 if oos_mean is not None else None
    )
    familywise_interval = study["out_of_sample"]["difference_ci_98_33"]
    max_drawdown = backtest["metrics"]["max_trade_equity_drawdown"]

    if not data.evidence_eligible or oos_count < MIN_OUT_OF_SAMPLE_EPISODES:
        evidence_status = "insufficient_data"
    elif not (
        familywise_interval
        and familywise_interval[0] > 0
        and cost_adjusted_oos_mean is not None
        and cost_adjusted_oos_mean > 0
    ):
        evidence_status = "not_supported"
    else:
        evidence_status = "supported"

    return {
        "protocol": PROTOCOL_V2_ID,
        "horizon_trading_days": horizon,
        "evidence_status": evidence_status,
        "gates": {
            "minimum_out_of_sample_episodes": MIN_OUT_OF_SAMPLE_EPISODES,
            "out_of_sample_episode_count": oos_count,
            "episode_count_passed": oos_count >= MIN_OUT_OF_SAMPLE_EPISODES,
            "familywise_98_33_lower": (
                familywise_interval[0] if familywise_interval else None
            ),
            "familywise_98_33_passed": bool(
                familywise_interval and familywise_interval[0] > 0
            ),
            "cost_bps": cost_bps,
            "roll_cost_bps": roll_cost_bps,
            "out_of_sample_mean_net_return": cost_adjusted_oos_mean,
            "cost_adjusted_positive_passed": bool(
                cost_adjusted_oos_mean is not None and cost_adjusted_oos_mean > 0
            ),
            "max_trade_level_drawdown": max_drawdown,
            "drawdown_passed": max_drawdown is None or max_drawdown < 0.2,
        },
        "study": study,
        "backtest": backtest,
        "note": "组合门槛为 v2 预注册草案，不等同于正式冻结验收",
    }


def run_v2_evidence_bundle(
    data: PreparedMarketData,
    *,
    cost_bps: float = DEFAULT_COST_BPS,
    roll_cost_bps: float = 0.0,
) -> dict:
    """对 63/126/252 三个期限运行 v2 组合门槛。"""
    return {
        "protocol": PROTOCOL_V2_ID,
        "horizons": {
            str(horizon): run_v2_horizon_gate(
                data,
                horizon=horizon,
                cost_bps=cost_bps,
                roll_cost_bps=roll_cost_bps,
            )
            for horizon in (63, 126, 252)
        },
    }
