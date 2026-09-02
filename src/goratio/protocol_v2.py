"""双因子 v2 预注册协议草案。

本模块只完成“预注册定义 + 当前状态计算”，不把 v2 当作已通过证据。
所有阈值在读取新结果前固定；如需修改必须进入 v3 协议。
"""

from datetime import date
from typing import Optional, Sequence

from .data import AlignedPoint
from .dataset import PreparedMarketData
from .regime import structure_stability_factor


PROTOCOL_V2_ID = "goratio-2a-v1"

LOW_STATE_THRESHOLD = 0.2
HIGH_STATE_THRESHOLD = 0.8
TREND_LOOKBACK_TRADING_DAYS = 252
VALUATION_WINDOW_YEARS = 5

PROTOCOL_V2_SPEC = {
    "id": PROTOCOL_V2_ID,
    "status": "draft_preregistered",
    "version": "0.2.0",
    "research_question": "在只用 GC/CL 两条国际价格序列的前提下，双因子状态是否比单因子分位更有条件远期收益区分度？",
    "factors": [
        {
            "id": "F1_valuation",
            "name": "金油比滚动估值因子",
            "window": "trailing_5_calendar_years",
            "low_threshold": LOW_STATE_THRESHOLD,
            "high_threshold": HIGH_STATE_THRESHOLD,
        },
        {
            "id": "F2_trend_confirmation",
            "name": "黄金 252 共同交易日动量确认因子",
            "window_trading_days": TREND_LOOKBACK_TRADING_DAYS,
            "confirmation_rule": "低估值做多黄金研究触发需黄金动量>0；高估值相反",
        },
    ],
    "variants": [
        {
            "id": "A_value_plus_trend",
            "name": "价值 + 趋势确认",
            "implemented": True,
        },
        {
            "id": "B_opportunity_plus_structure",
            "name": "机会 + 结构稳定性",
            "implemented": True,
        },
    ],
    "pre_registration_rule": "任何新窗口、阈值或过滤器都必须作为 v3 重新预注册；不得用结果反推参数。",
    "not_investment_advice": True,
}


def _years_before(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def factor_snapshot(data: PreparedMarketData) -> dict:
    """计算当前快照的 F1 估值与 F2 趋势因子，并输出研究状态。"""
    current = data.selected.points[-1] if data.selected.points else None
    if current is None:
        return {"available": False, "reason": "no_selected_points"}
    if len(data.history.points) <= TREND_LOOKBACK_TRADING_DAYS:
        return {
            "available": False,
            "reason": "insufficient_history_for_252d_trend",
        }

    history = data.history.points
    rolling_start = _years_before(current.date, VALUATION_WINDOW_YEARS)
    valuation_points = [
        point.ratio for point in history
        if rolling_start <= point.date <= current.date
    ]
    if len(valuation_points) < TREND_LOOKBACK_TRADING_DAYS:
        return {
            "available": False,
            "reason": "insufficient_rolling_valuation_history",
        }

    valuation_percentile = (
        sum(value <= current.ratio for value in valuation_points)
        / len(valuation_points)
    )
    # history 与 selected 的末端一致：current 是 history 最后一个共同交易日。
    past = history[-1 - TREND_LOOKBACK_TRADING_DAYS]
    gold_momentum = current.gold_close / past.gold_close - 1
    ratio_momentum = current.ratio / past.ratio - 1

    valuation_zone = (
        "low" if valuation_percentile <= LOW_STATE_THRESHOLD
        else "high" if valuation_percentile >= HIGH_STATE_THRESHOLD
        else "middle"
    )
    if valuation_zone == "low" and gold_momentum > 0:
        research_state = "positive_research_trigger"
    elif valuation_zone == "high" and gold_momentum < 0:
        research_state = "negative_research_trigger"
    elif valuation_zone == "low":
        research_state = "valuation_low_trend_not_confirmed"
    elif valuation_zone == "high":
        research_state = "valuation_high_trend_not_confirmed"
    else:
        research_state = "neutral"

    return {
        "available": True,
        "protocol": PROTOCOL_V2_ID,
        "as_of": current.date.isoformat(),
        "factors": {
            "F1_valuation": {
                "percentile": valuation_percentile,
                "zone": valuation_zone,
                "thresholds": {
                    "low": LOW_STATE_THRESHOLD,
                    "high": HIGH_STATE_THRESHOLD,
                },
            },
            "F2_trend_confirmation": {
                "gold_252d_momentum": gold_momentum,
                "ratio_252d_momentum": ratio_momentum,
            },
        },
        "research_state": research_state,
        "risk_flags": [
            "diagnostic_not_preregistered_evidence",
            "cost_and_execution_not_yet_applied",
            "variant_b_not_implemented",
        ],
        "note": "这是预注册研究状态，不是买入/卖出建议",
    }


def factor_snapshot_variant_b(data: PreparedMarketData) -> dict:
    """变体 B：机会 + 结构稳定性。估值极端只有结构稳定时才进入研究触发。"""
    snapshot_a = factor_snapshot(data)
    stability = structure_stability_factor(data)
    if not snapshot_a["available"]:
        return {
            "available": False,
            "reason": snapshot_a.get("reason"),
            "stability": stability,
        }
    if not stability["available"]:
        return {
            "available": False,
            "reason": stability["reason"],
            "valuation": snapshot_a["factors"]["F1_valuation"],
        }

    zone = snapshot_a["factors"]["F1_valuation"]["zone"]
    stable = stability["state"] == "stable"
    if zone == "low" and stable:
        research_state = "positive_research_trigger"
    elif zone == "high" and stable:
        research_state = "negative_research_trigger"
    elif zone == "low":
        research_state = "valuation_low_structure_unstable"
    elif zone == "high":
        research_state = "valuation_high_structure_unstable"
    else:
        research_state = "neutral"

    return {
        "available": True,
        "protocol": PROTOCOL_V2_ID,
        "variant": "B_opportunity_plus_structure",
        "as_of": snapshot_a["as_of"],
        "valuation": snapshot_a["factors"]["F1_valuation"],
        "stability": stability,
        "research_state": research_state,
        "risk_flags": [
            "diagnostic_not_preregistered_evidence",
            "cost_and_execution_not_yet_applied",
        ],
        "note": "这是预注册研究状态，不是买入/卖出建议",
    }


def build_protocol_list() -> list:
    """供 MCP/CLI 展示当前协议清单。"""
    return [
        {"id": "goratio-1a-v1", "status": "frozen"},
        {
            "id": PROTOCOL_V2_ID,
            "status": "draft_preregistered",
            "implemented_variant": "A_value_plus_trend",
        },
    ]
