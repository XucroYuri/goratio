"""可交易性诊断模块：合约规格、执行缺口代理、负价格与人民币披露。

本模块不改动 1A 统计协议，只把当前数据在“能否被真实交易者执行”上的已知
约束显式化。输出均为研究性事实，不构成交易指令或仓位建议。
"""

import math
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from .data import AlignedPoint
from .dataset import PreparedMarketData
from .providers import RawMarketData


GC_SPEC = {
    "symbol": "GC",
    "instrument": "COMEX Gold Futures",
    "contract_multiplier": 100,
    "quote_unit": "USD / troy ounce",
    "currency": "USD",
    "contract_size_description": "1 手 = 100 金衡盎司",
}
GOLD_GRAM_PER_TROY_OUNCE = 31.1034768

CL_SPEC = {
    "symbol": "CL",
    "instrument": "NYMEX WTI Crude Oil Futures",
    "contract_multiplier": 1000,
    "quote_unit": "USD / barrel",
    "currency": "USD",
    "contract_size_description": "1 手 = 1,000 桶",
}


@dataclass(frozen=True)
class NonPositiveEvent:
    date: str
    instrument: str
    symbol: str
    close: float
    source: str


def scan_non_positive_events(raw: RawMarketData) -> Tuple[NonPositiveEvent, ...]:
    """扫描原始记录中的非正价格，作为危机尾部审计入口。

    1A 的协议会把非正价格剔除；可交易性诊断必须把它们显式保留，否则 2020-04-20
    这类负油价压力日会从分析历史上消失。
    """
    events = []
    for instrument, symbol, records in (
        ("gold", "GC", raw.gold_records),
        ("oil", "CL", raw.oil_records),
    ):
        for record in records:
            raw_date = record.get("date")
            raw_close = record.get("close")
            try:
                parsed_date = date.fromisoformat(str(raw_date))
                close = float(raw_close)
            except (TypeError, ValueError):
                continue
            if close <= 0 and math.isfinite(close):
                events.append(
                    NonPositiveEvent(
                        date=parsed_date.isoformat(),
                        instrument=instrument,
                        symbol=symbol,
                        close=close,
                        source=raw.source.source_id,
                    )
                )
    return tuple(sorted(events, key=lambda event: (event.date, event.instrument)))


def _mean(values: Sequence[float]) -> float:
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


def next_close_gap_summary(
    points: Sequence[AlignedPoint],
    *,
    lookback: int = 252,
) -> dict:
    """使用日线收盘价近似统计“信号收盘到下一共同交易日收盘”的缺口。

    当前数据没有日内 OHLC，因此这不是真实开盘执行缺口，而是可交易性诊断所需的
    保守代理指标。等合约级 open/settle 数据接入后应升级为 T+1 open/settle 缺口。
    """
    if len(points) < 2:
        return {
            "method": "close_to_next_close_abs_log_return",
            "observation_count": 0,
            "mean": None,
            "median": None,
            "p95": None,
            "limitations": "只有收盘价时使用相邻收盘价近似；不等同于次日开盘缺口",
        }
    values = [
        abs(math.log(points[index + 1].gold_close / points[index].gold_close))
        for index in range(max(0, len(points) - lookback), len(points) - 1)
    ]
    return {
        "method": "close_to_next_close_abs_log_return",
        "observation_count": len(values),
        "mean": _mean(values),
        "median": median(values) if values else None,
        "p95": _quantile(values, 0.95),
        "limitations": "只有收盘价时使用相邻收盘价近似；不等同于次日开盘缺口",
    }


def ratio_trade_expression(gold_close: float, oil_close: float) -> dict:
    """根据合约乘数给出 1 GC 相对 CL 的名义表达参考。

    结果用于理解可交易性，不构成仓位建议。由于 ratio 不一定是整数比例，
    现实中的整数手组合会产生名义不平衡。
    """
    ratio = gold_close / oil_close
    cl_per_gc_notional = ratio * GC_SPEC["contract_multiplier"] / CL_SPEC[
        "contract_multiplier"
    ]
    nearest_lower = math.floor(cl_per_gc_notional)
    nearest_upper = math.ceil(cl_per_gc_notional)
    return {
        "ratio": ratio,
        "gold_contract_multiplier": GC_SPEC["contract_multiplier"],
        "oil_contract_multiplier": CL_SPEC["contract_multiplier"],
        "cl_contracts_per_one_gc_notional": cl_per_gc_notional,
        "integer_lot_reference": {
            "one_gc_plus_floor_cl": nearest_lower,
            "one_gc_plus_ceil_cl": nearest_upper,
            "note": "仅作名义表达参考；整数手会产生不平衡，不构成仓位建议",
        },
    }


def build_tradability_report(
    raw: RawMarketData,
    data: PreparedMarketData,
    *,
    usd_cny: Optional[float] = None,
) -> dict:
    """构造可交易性诊断报告；可选传入 USD/CNY 用于本地执行/展示换算。"""
    if usd_cny is not None and usd_cny <= 0:
        raise ValueError("usd_cny 必须是正数")
    current = data.selected.points[-1] if data.selected.points else None
    non_positive = scan_non_positive_events(raw)
    expression = (
        ratio_trade_expression(current.gold_close, current.oil_close)
        if current is not None
        else None
    )
    renminbi_disclosure = {
        "core_model_currency": "USD",
        "note": "中国大陆购金者实际承担人民币计价风险；核心双因子仍保持仅使用 GC/CL 两个国际价格序列，USD/CNY 只在执行/展示层披露，不进入因子",
        "usdcny_required_for_local_pnl": True,
        "usdcny_data_loaded": False,
    }
    if usd_cny is not None and current is not None:
        gold_cny_per_troy_oz = current.gold_close * usd_cny
        renminbi_disclosure.update(
            {
                "usdcny_data_loaded": True,
                "usd_cny": usd_cny,
                "gold_cny_per_troy_oz": gold_cny_per_troy_oz,
                "gold_cny_per_gram": (
                    gold_cny_per_troy_oz / GOLD_GRAM_PER_TROY_OUNCE
                ),
                "oil_cny_per_barrel": current.oil_close * usd_cny,
            }
        )
    return {
        "schema_version": "goratio-tradability-v1",
        "as_of": current.date.isoformat() if current else None,
        "source_id": raw.source.source_id,
        "source_name": raw.source.name,
        "contracts": {
            "gold": GC_SPEC,
            "oil": CL_SPEC,
        },
        "current_expression": expression,
        "execution_gap": next_close_gap_summary(data.selected.points),
        "negative_price_events": [event.__dict__ for event in non_positive],
        "negative_price_policy": {
            "protocol_1a": "非正价格被剔除并计数",
            "tradability_rule": "负油价/零价事件必须显式保留为压力测试输入；log ratio 模型需单独处理该区间",
        },
        "renminbi_disclosure": renminbi_disclosure,
        "data_limitations": [
            "当前来源为服务商连续期货日收盘价，不是交易所官方结算价",
            "没有合约月份、成交量、持仓量、开盘价或真实换月日历",
            "相邻收盘价缺口只是执行缺口代理，不等同于 T+1 open/settle 可执行价差",
        ],
        "risk_flags": [
            "provider_continuous_contract_rolls",
            "not_official_settlement",
            "no_volume_open_interest",
            "no_roll_calendar",
            "no_open_prices",
        ],
        "disclaimer": "仅供历史统计研究与方法复现，不构成投资建议或仓位建议",
    }
