"""统一文本与 JSON 输出所需的结构化结果。"""

from dataclasses import asdict
from typing import Mapping, Optional

from .cache import LoadedData
from .dataset import PreparedMarketData
from .research import PROTOCOL_VERSION, summarize_current


RESULT_SCHEMA_VERSION = "goratio-result-v1"

METHOD_LIMITATIONS = [
    "连续期货由数据服务商拼接，换月规则和历史修订可能造成跳跃",
    "使用同一交易日收盘价内连接，不填补缺失交易日，可能改变样本构成",
    "历史相关与条件分布不能证明因果关系，也不能保证未来复现",
    "结构断点为简化单均值 Sup-F 实验诊断，不等价于完整多断点检验",
    "两个在线来源都不是交易所官方结算数据，服务可用性不受本项目控制",
]

DISCLAIMER = (
    "仅供历史统计研究与方法复现，不构成投资建议；数据可能延迟、修订或含误差，"
    "使用者应独立核验来源、口径和适用性。"
)


def _removed_count(audit: Mapping[str, object]) -> int:
    return sum(
        int(audit[name])
        for name in (
            "invalid_date",
            "future_or_incomplete",
            "missing_close",
            "non_finite",
            "non_positive",
            "duplicate_identical",
            "duplicate_conflict",
        )
    )


def build_result(
    loaded: LoadedData,
    data: PreparedMarketData,
    *,
    research: Optional[Mapping[str, object]] = None,
):
    """构造 now 与 analyze 共用的严格 JSON 契约。"""

    current = (
        research["current"]
        if research is not None
        else summarize_current(data.history.points, data.selected.points)
    )
    gold_audit = asdict(data.gold.audit)
    oil_audit = asdict(data.oil.audit)
    quality = {
        "status": data.quality_status,
        "evidence_eligible": data.evidence_eligible,
        "minimum_evidence_span_days": 1825,
        "minimum_evidence_observations": 1000,
        "gold_audit": gold_audit,
        "oil_audit": oil_audit,
        "removed_record_count": _removed_count(gold_audit)
        + _removed_count(oil_audit),
        "alignment": {
            "method": "same_completed_trading_day_inner_join",
            "forward_fill": False,
            "gold_unmatched": data.history.gold_unmatched,
            "oil_unmatched": data.history.oil_unmatched,
        },
        "cache": {
            "used": loaded.provenance == "cache",
            "origin": loaded.cache_origin,
            "age_hours": loaded.cache_age_hours,
            "stale_after_hours": 72,
            "stale": loaded.cache_stale,
            "retrieved_at": loaded.raw.retrieved_at.isoformat().replace(
                "+00:00", "Z"
            ),
        },
        "warnings": list(loaded.warnings),
    }
    risk_flags = []
    if not data.evidence_eligible:
        risk_flags.append("insufficient_history")
    if loaded.cache_stale:
        risk_flags.append("stale_cache")
    if data.quality_status == "degraded":
        risk_flags.append("data_quality_findings")
    risk_flags.append("provider_continuous_contract_rolls")

    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "as_of": current["as_of"],
        "source": {
            "id": data.source.source_id,
            "name": data.source.name,
            "provenance": data.provenance,
        },
        "price_basis": data.source.price_basis,
        "instruments": data.source.instruments,
        "requested_period": data.requested_period,
        "actual_period": list(data.actual_period),
        "total_available_period": list(data.total_period),
        "observation_count": data.observation_count,
        "span_days": data.span_days,
        "snapshot_sha256": loaded.snapshot_sha256,
        "data_quality": quality,
        "ratio": current,
        "evidence_status": {"overall": "not_evaluated"},
        "risk_flags": risk_flags,
        "method_limitations": METHOD_LIMITATIONS,
        "disclaimer": DISCLAIMER,
    }
    if research is not None:
        result.update(
            {
                "parameters": research["parameters"],
                "trial_count": research["trial_count"],
                "evidence_status": research["evidence_status"],
                "mean_reversion": research["mean_reversion"],
                "conditional_forward_returns": research["event_study"],
                "stability_diagnostic": research["stability_diagnostic"],
                "replication": research["replication"],
                "unpassed_hypotheses": research["unpassed_hypotheses"],
                "risk_flags": research["risk_flags"],
            }
        )
    return result
