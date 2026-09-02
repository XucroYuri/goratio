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
