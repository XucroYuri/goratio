"""将来源记录转换为可研究的共同交易日数据集。"""

from dataclasses import dataclass
from datetime import date
from typing import Tuple

from .data import (
    AlignedPoint,
    AlignedSeries,
    ValidatedSeries,
    align_series,
    select_period,
    validate_series,
)
from .providers import RawMarketData, SourceMetadata


MIN_EVIDENCE_SPAN_DAYS = 1825
MIN_EVIDENCE_OBSERVATIONS = 1000


class DataQualityError(RuntimeError):
    """校验后没有可比较的共同价格。"""


@dataclass(frozen=True)
class PreparedMarketData:
    source: SourceMetadata
    requested_period: str
    actual_period: Tuple[str, str]
    total_period: Tuple[str, str]
    observation_count: int
    span_days: int
    evidence_eligible: bool
    quality_status: str
    provenance: str
    cache_stale: bool
    gold: ValidatedSeries
    oil: ValidatedSeries
    selected: AlignedSeries
    history: AlignedSeries

    @property
    def points(self) -> Tuple[AlignedPoint, ...]:
        return self.selected.points


def _has_quality_findings(series: ValidatedSeries) -> bool:
    audit = series.audit
    return any(
        (
            audit.invalid_date,
            audit.future_or_incomplete,
            audit.missing_close,
            audit.non_finite,
            audit.non_positive,
            audit.duplicate_identical,
            audit.duplicate_conflict,
            audit.outlier_candidates,
        )
    )


def prepare_market_data(
    raw: RawMarketData,
    *,
    period: str,
    completed_before: date,
    provenance: str,
    cache_stale: bool,
) -> PreparedMarketData:
    gold = validate_series(
        "gold", raw.gold_records, completed_before=completed_before
    )
    oil = validate_series("oil", raw.oil_records, completed_before=completed_before)
    history = align_series(gold, oil)
    if not history.points:
        raise DataQualityError("校验和同日对齐后没有共同有效价格")
    selected = select_period(history, period)
    if not selected.points:
        raise DataQualityError("请求周期内没有共同有效价格")

    first = selected.points[0].date
    last = selected.points[-1].date
    span_days = (last - first).days
    observation_count = len(selected.points)
    evidence_eligible = (
        span_days >= MIN_EVIDENCE_SPAN_DAYS
        and observation_count >= MIN_EVIDENCE_OBSERVATIONS
    )
    quality_findings = (
        _has_quality_findings(gold)
        or _has_quality_findings(oil)
        or history.gold_unmatched > 0
        or history.oil_unmatched > 0
    )
    if not evidence_eligible:
        quality_status = "insufficient_history"
    elif cache_stale:
        quality_status = "stale_cache"
    elif quality_findings:
        quality_status = "degraded"
    else:
        quality_status = "good"

    return PreparedMarketData(
        source=raw.source,
        requested_period=period,
        actual_period=(first.isoformat(), last.isoformat()),
        total_period=(
            history.points[0].date.isoformat(),
            history.points[-1].date.isoformat(),
        ),
        observation_count=observation_count,
        span_days=span_days,
        evidence_eligible=evidence_eligible,
        quality_status=quality_status,
        provenance=provenance,
        cache_stale=cache_stale,
        gold=gold,
        oil=oil,
        selected=selected,
        history=history,
    )
