"""保证金/名义敞口的只读估算。

这里只做“研究性资金占用”估算，不构成仓位建议。实际保证金由交易所/期货公司
动态决定；本模块用于让交易员理解合约乘数与杠杆对名义敞口的影响。
"""

from typing import Optional

# 常见近似初始保证金率，仅供研究展示。
DEFAULT_MARGIN_RATES = {
    "GC": 0.05,
    "CL": 0.10,
}


def position_margin_estimate(
    gold_close: float,
    oil_close: float,
    *,
    gc_lots: int = 1,
    cl_lots: int = 0,
    margin_rate_gc: Optional[float] = None,
    margin_rate_cl: Optional[float] = None,
) -> dict:
    """估算多/空 GC 与 CL 组合的名义敞口和保证金占用。

    GC 合约乘数 100 盎司，CL 合约乘数 1000 桶。
    """
    if gold_close <= 0 or oil_close <= 0:
        raise ValueError("价格必须为正")
    if gc_lots < 0 or cl_lots < 0:
        raise ValueError("手数不能为负")
    rate_gc = margin_rate_gc or DEFAULT_MARGIN_RATES["GC"]
    rate_cl = margin_rate_cl or DEFAULT_MARGIN_RATES["CL"]
    gc_notional = gold_close * 100 * gc_lots
    cl_notional = oil_close * 1000 * cl_lots
    margin = gc_notional * rate_gc + cl_notional * rate_cl
    return {
        "gc_lots": gc_lots,
        "cl_lots": cl_lots,
        "gc_notional": gc_notional,
        "cl_notional": cl_notional,
        "total_notional": gc_notional + cl_notional,
        "margin_estimate": margin,
        "margin_rates": {"GC": rate_gc, "CL": rate_cl},
        "note": "仅为研究性资金占用估算，不构成仓位建议",
    }


def one_gc_one_cl_margin_report(gold_close: float, oil_close: float) -> dict:
    """输出 1 手 GC 与 0/1 手 CL 的保证金估算。"""
    return {
        "one_gc_only": position_margin_estimate(
            gold_close, oil_close, gc_lots=1, cl_lots=0
        ),
        "one_gc_one_cl": position_margin_estimate(
            gold_close, oil_close, gc_lots=1, cl_lots=1
        ),
    }


def position_pnl_estimate(
    records,
    *,
    instrument: str,
    entry_date,
    exit_date,
    direction: int = 1,
    lots: int = 1,
    margin_rate: Optional[float] = None,
) -> dict:
    """基于真实主力合约链估算单一持仓的保证金与换月收益 P&L。

    只用于研究性估算，不构成交易建议。direction 为 +1 多仓 / -1 空仓。
    """
    if direction not in (-1, 1):
        raise ValueError("direction 必须是 1 或 -1")
    if lots <= 0:
        raise ValueError("lots 必须为正整数")
    from datetime import date
    from .contracts import build_contract_series, roll_aware_contract_return

    report = build_contract_series(records)
    if instrument not in report["series"]:
        raise ValueError(f"合约链缺少 instrument={instrument}")
    calendar = report["series"][instrument]["calendar"]
    entry_price = None
    for point in calendar:
        if date.fromisoformat(point["date"]) == entry_date:
            entry_price = point["close"]
            break
    if entry_price is None:
        raise ValueError(f"entry_date 不在合约链中: {entry_date}")
    multiplier = 100 if instrument == "gold" else 1000
    notional = entry_price * multiplier * lots
    rate = margin_rate or DEFAULT_MARGIN_RATES.get(
        "GC" if instrument == "gold" else "CL", 0.1
    )
    margin = notional * rate
    roll_return = roll_aware_contract_return(
        records,
        instrument=instrument,
        entry_date=entry_date,
        exit_date=exit_date,
    )
    pnl = notional * roll_return * direction if roll_return is not None else None
    return {
        "instrument": instrument,
        "direction": direction,
        "lots": lots,
        "entry_price": entry_price,
        "roll_aware_return": roll_return,
        "notional": notional,
        "margin_estimate": margin,
        "pnl_estimate": pnl,
        "note": "研究性持仓估算，不构成交易建议",
    }


def run_position_simulation(
    records,
    episodes,
    *,
    instrument: str = "gold",
    direction: int = 1,
    lots: int = 1,
    margin_rate: Optional[float] = None,
) -> dict:
    """对一组 episode 批量运行真实主力链持仓估算。"""
    rows = []
    for episode in episodes:
        try:
            result = position_pnl_estimate(
                records,
                instrument=instrument,
                entry_date=episode.date,
                exit_date=episode.outcome_date,
                direction=direction,
                lots=lots,
                margin_rate=margin_rate,
            )
        except ValueError:
            continue
        rows.append(
            {
                "entry_date": episode.date.isoformat(),
                "outcome_date": episode.outcome_date.isoformat(),
                "roll_aware_return": result["roll_aware_return"],
                "pnl_estimate": result["pnl_estimate"],
                "margin_estimate": result["margin_estimate"],
            }
        )
    pnls = [
        row["pnl_estimate"]
        for row in rows
        if row["pnl_estimate"] is not None
    ]
    return {
        "instrument": instrument,
        "direction": direction,
        "lots": lots,
        "episode_count": len(rows),
        "valid_pnl_count": len(pnls),
        "mean_pnl_estimate": sum(pnls) / len(pnls) if pnls else None,
        "rows": rows,
    }


def batch_equity_summary(sim: dict, *, initial_capital: float = 100000.0) -> dict:
    """基于批量持仓模拟结果生成简单资金曲线摘要。

    该摘要按行顺序累加 P&L，适用于非重叠 episode 的初步资金曲线研究。
    """
    if initial_capital <= 0:
        raise ValueError("initial_capital 必须为正")
    equity = initial_capital
    peak = initial_capital
    max_drawdown = 0.0
    row_count = 0
    for row in sim.get("rows", []):
        pnl = row.get("pnl_estimate")
        if pnl is None:
            continue
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        row_count += 1
    return {
        "initial_capital": initial_capital,
        "final_equity": equity,
        "total_pnl": equity - initial_capital,
        "max_drawdown": max_drawdown,
        "valid_pnl_count": row_count,
        "note": "简单逐笔资金曲线摘要，不包含重叠持仓、融资与提现",
    }


def margin_utilization_summary(sim: dict, *, initial_capital: float = 100000.0) -> dict:
    """从批量持仓模拟中统计保证金占用率（逐笔近似）。"""
    if initial_capital <= 0:
        raise ValueError("initial_capital 必须为正")
    utilizations = []
    for row in sim.get("rows", []):
        margin = row.get("margin_estimate")
        if margin is None:
            continue
        utilizations.append(margin / initial_capital)
    return {
        "initial_capital": initial_capital,
        "valid_margin_count": len(utilizations),
        "mean_margin_utilization": (
            sum(utilizations) / len(utilizations) if utilizations else None
        ),
        "max_margin_utilization": max(utilizations) if utilizations else None,
        "note": "逐笔近似保证金占用，不包含重叠持仓的逐日合并监控",
    }


def run_daily_position_mark(
    records,
    *,
    instrument: str,
    entry_date,
    exit_date,
    direction: int = 1,
    lots: int = 1,
    margin_rate: Optional[float] = None,
) -> dict:
    """运行单笔持仓的逐日盯市（mark-to-market）与保证金占用估算。

    换月时先按旧合约价格实现盈亏，再按新合约价格重开仓。返回每日行与摘要。
    """
    if direction not in (-1, 1):
        raise ValueError("direction 必须是 1 或 -1")
    if lots <= 0:
        raise ValueError("lots 必须为正整数")
    from datetime import date
    from .contracts import build_contract_series

    report = build_contract_series(records)
    if instrument not in report["series"]:
        raise ValueError(f"合约链缺少 instrument={instrument}")
    calendar = report["series"][instrument]["calendar"]
    daily = [
        point
        for point in calendar
        if entry_date <= date.fromisoformat(point["date"]) <= exit_date
    ]
    if not daily:
        return {"rows": [], "final_pnl": None}
    multiplier = 100 if instrument == "gold" else 1000
    rate = margin_rate or DEFAULT_MARGIN_RATES.get(
        "GC" if instrument == "gold" else "CL", 0.1
    )
    roll_map = {
        event["date"]: event
        for event in report["roll_events"]
        if event["instrument"] == instrument
    }
    active_contract = daily[0]["contract_month"]
    entry_price = daily[0]["close"]
    realized = 0.0
    rows = []
    for point in daily:
        current_date = point["date"]
        close = point["close"]
        if point["contract_month"] != active_contract:
            roll = roll_map.get(current_date)
            old_close = roll["old_close"] if roll else None
            if old_close is None:
                prev_index = len(rows) - 1
                old_close = rows[prev_index]["close"] if rows else entry_price
            realized += (old_close - entry_price) * multiplier * lots * direction
            active_contract = point["contract_month"]
            entry_price = close
        unrealized = (close - entry_price) * multiplier * lots * direction
        cumulative_pnl = realized + unrealized
        rows.append(
            {
                "date": current_date,
                "contract_month": point["contract_month"],
                "close": close,
                "realized_pnl": realized,
                "unrealized_pnl": unrealized,
                "cumulative_pnl": cumulative_pnl,
                "margin_estimate": close * multiplier * lots * rate,
            }
        )
    final_pnl = rows[-1]["cumulative_pnl"] if rows else None
    return {
        "instrument": instrument,
        "direction": direction,
        "lots": lots,
        "entry_date": entry_date.isoformat(),
        "exit_date": exit_date.isoformat(),
        "row_count": len(rows),
        "final_pnl": final_pnl,
        "max_abs_pnl": max((abs(row["cumulative_pnl"]) for row in rows), default=None),
        "rows": rows,
        "note": "逐日盯市研究模拟，不构成交易建议",
    }
