"""双因子 v2 正式验收报告入口（预注册草案层）。

本模块不是“证明策略有效”，而是把协议、参数、各期限 evidence status 与
组合结论汇总为可审计的正式报告入口。
"""

from datetime import datetime, timezone

from .backtest import MIN_TRADE_COUNT
from .dataset import PreparedMarketData
from .episode_study import MIN_OUT_OF_SAMPLE_EPISODES
from .evidence_gates import (
    DEFAULT_COST_BPS,
    PROTOCOL_V2_ID,
    run_v2_evidence_bundle,
)


def generate_v2_formal_report(
    data: PreparedMarketData,
    *,
    cost_bps: float = DEFAULT_COST_BPS,
    roll_cost_bps: float = 0.0,
) -> dict:
    """生成协议 v2 正式验收前的可审计报告入口。"""
    bundle = run_v2_evidence_bundle(
        data,
        cost_bps=cost_bps,
        roll_cost_bps=roll_cost_bps,
    )
    statuses = {
        horizon: result["evidence_status"]
        for horizon, result in bundle["horizons"].items()
    }
    if all(status == "insufficient_data" for status in statuses.values()):
        overall = "insufficient_data"
    elif any(status == "supported" for status in statuses.values()) and not any(
        status == "not_supported" for status in statuses.values()
    ):
        overall = "supported"
    else:
        overall = "not_supported"

    return {
        "protocol": PROTOCOL_V2_ID,
        "report_type": "formal_preregistered_report_draft",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "parameters": {
            "cost_bps": cost_bps,
            "roll_cost_bps": roll_cost_bps,
            "minimum_out_of_sample_episodes": MIN_OUT_OF_SAMPLE_EPISODES,
            "minimum_trade_count": MIN_TRADE_COUNT,
            "familywise_confidence": 1 - 0.05 / 3,
        },
        "evidence": bundle,
        "horizon_status": statuses,
        "overall_status": overall,
        "freeze_checklist": freeze_checklist(),
        "note": "正式冻结验收仍需外部评审/日期戳；本模块是可复现报告入口",
    }


def generate_v2_overview(data: PreparedMarketData) -> dict:
    """生成 v2 研究总览：当前因子状态 + 三期限 formal 报告摘要。"""
    from .protocol_v2 import factor_snapshot
    formal = generate_v2_formal_report(data)
    factor = factor_snapshot(data)
    return {
        "protocol": PROTOCOL_V2_ID,
        "overview": {
            "factor_available": factor.get("available", False),
            "factor_state": factor.get("research_state"),
            "overall_status": formal["overall_status"],
            "horizon_status": formal["horizon_status"],
        },
        "formal": formal,
    }


def freeze_checklist() -> dict:
    """返回正式冻结验收所需清单的当前状态。"""
    return {
        "protocol_id": PROTOCOL_V2_ID,
        "pre_registered": True,
        "generated_at_supported": True,
        "formal_report_cli": True,
        "overview_cli": True,
        "external_review": False,
        "date_stamp_signed": False,
        "note": "代码/报告入口已具备；外部评审与签名日期戳需在项目治理流程中完成",
    }
