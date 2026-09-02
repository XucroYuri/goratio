"""负油价/零价等危机尾部事件对回测与协议 v2 的接入状态诊断。

当前 1A 协议会把非正价格剔除；真实交易者不能忽略负油价压力日。本模块只做
“事件是否在样本窗口内、是否被协议排除、需要在 v2 如何处理”的透明诊断。
"""

from typing import Sequence

from .data import AlignedPoint
from .dataset import PreparedMarketData
from .providers import RawMarketData
from .tradability import scan_non_positive_events


def tail_stress_report(raw: RawMarketData, data: PreparedMarketData) -> dict:
    """输出原始非正价格事件相对当前研究窗口的接入状态。"""
    events = scan_non_positive_events(raw)
    if data.selected.points:
        first = data.selected.points[0].date.isoformat()
        last = data.selected.points[-1].date.isoformat()
    else:
        first = last = None
    in_window = []
    for event in events:
        inside = first is not None and first <= event.date <= last
        in_window.append(
            {
                "date": event.date,
                "instrument": event.instrument,
                "symbol": event.symbol,
                "close": event.close,
                "in_analysis_window": inside,
                "protocol_1a_excluded": True,
                "log_ratio_defined": False,
                "v2_handling": "需要在合约级/原始价格层保留事件，并对相关日期禁用 log ratio 状态或单列压力场景",
            }
        )
    return {
        "schema_version": "goratio-stress-v1",
        "analysis_window": {"first": first, "last": last},
        "non_positive_event_count": len(in_window),
        "events": in_window,
        "note": "负油价/零价事件不会被 log ratio 正常处理；必须显式保留并在 v2/真实回测中作为压力输入",
    }
