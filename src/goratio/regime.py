"""在线结构稳定性因子（双因子 v2 变体 B 前置模块）。

该模块使用“截至当前日的滚动中位数/MAD”描述短周期中位数相对长周期中枢的
漂移，不引入未来信息。阈值预先固定，不作为事后调参工具。
"""

from datetime import date
from statistics import median
from typing import Optional, Sequence

from .data import AlignedPoint
from .dataset import PreparedMarketData


VALUATION_WINDOW_YEARS = 5
RECENT_TRADING_DAYS = 252
STRUCTURE_SHIFT_Z_THRESHOLD = 0.5
MAD_SCALE = 1.4826


def _years_before(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return median(values)


def _mad(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    center = _median(values)
    if center is None:
        return None
    return MAD_SCALE * median(abs(value - center) for value in values)


def structure_stability_factor(data: PreparedMarketData) -> dict:
    """计算当前时点的无前视结构稳定性因子。"""
    current = data.selected.points[-1] if data.selected.points else None
    if current is None:
        return {"available": False, "reason": "no_selected_points"}

    history = data.history.points
    rolling_start = _years_before(current.date, VALUATION_WINDOW_YEARS)
    trailing = [
        point.ratio for point in history
        if rolling_start <= point.date <= current.date
    ]
    if len(trailing) < 504:
        return {
            "available": False,
            "reason": "insufficient_trailing_history",
        }

    recent = trailing[-RECENT_TRADING_DAYS:]
    full_median = _median(trailing)
    recent_median = _median(recent)
    full_mad = _mad(trailing)
    if full_median is None or recent_median is None or full_mad is None or full_mad == 0:
        return {
            "available": False,
            "reason": "non_zero_dispersion_required",
        }

    shift_z = (recent_median - full_median) / full_mad
    state = "stable" if abs(shift_z) <= STRUCTURE_SHIFT_Z_THRESHOLD else "unstable"

    return {
        "available": True,
        "as_of": current.date.isoformat(),
        "method": "rolling_median_shift_z",
        "full_window_years": VALUATION_WINDOW_YEARS,
        "recent_trading_days": RECENT_TRADING_DAYS,
        "shift_z_threshold": STRUCTURE_SHIFT_Z_THRESHOLD,
        "full_window_median": full_median,
        "recent_window_median": recent_median,
        "mad": full_mad,
        "median_shift_z": shift_z,
        "state": state,
        "note": "无前视结构稳定性代理，不等同于完整断点检验",
    }
