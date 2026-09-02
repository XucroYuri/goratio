"""价格数据模型和质量处理。"""

from dataclasses import dataclass
from datetime import date
import math
from statistics import median
from typing import Iterable, Mapping, Tuple


@dataclass(frozen=True)
class PricePoint:
    date: date
    close: float


@dataclass(frozen=True)
class QualityAudit:
    input_records: int = 0
    invalid_date: int = 0
    future_or_incomplete: int = 0
    missing_close: int = 0
    non_finite: int = 0
    non_positive: int = 0
    duplicate_identical: int = 0
    duplicate_conflict: int = 0
    outlier_candidates: int = 0


@dataclass(frozen=True)
class ValidatedSeries:
    instrument: str
    points: Tuple[PricePoint, ...]
    audit: QualityAudit


@dataclass(frozen=True)
class AlignedPoint:
    date: date
    gold_close: float
    oil_close: float
    ratio: float


@dataclass(frozen=True)
class AlignedSeries:
    points: Tuple[AlignedPoint, ...]
    gold_unmatched: int
    oil_unmatched: int


def select_period(series: AlignedSeries, period: str) -> AlignedSeries:
    """按最后一个共同交易日截取日历年周期。"""

    years_by_period = {"3y": 3, "5y": 5, "10y": 10}
    try:
        years = years_by_period[period]
    except KeyError as exc:
        raise ValueError("period 必须是 3y、5y 或 10y") from exc
    if not series.points:
        return series
    latest = series.points[-1].date
    try:
        start = latest.replace(year=latest.year - years)
    except ValueError:
        start = latest.replace(year=latest.year - years, day=28)
    return AlignedSeries(
        points=tuple(point for point in series.points if point.date >= start),
        gold_unmatched=series.gold_unmatched,
        oil_unmatched=series.oil_unmatched,
    )


def align_series(gold: ValidatedSeries, oil: ValidatedSeries) -> AlignedSeries:
    """按双方共同完成的交易日对齐价格。"""

    gold_by_date = {point.date: point.close for point in gold.points}
    oil_by_date = {point.date: point.close for point in oil.points}
    common_dates = sorted(gold_by_date.keys() & oil_by_date.keys())
    points = tuple(
        AlignedPoint(
            date=trading_date,
            gold_close=gold_by_date[trading_date],
            oil_close=oil_by_date[trading_date],
            ratio=gold_by_date[trading_date] / oil_by_date[trading_date],
        )
        for trading_date in common_dates
    )
    return AlignedSeries(
        points=points,
        gold_unmatched=len(gold_by_date) - len(common_dates),
        oil_unmatched=len(oil_by_date) - len(common_dates),
    )


def validate_series(
    instrument: str,
    records: Iterable[Mapping[str, object]],
    *,
    completed_before: date,
) -> ValidatedSeries:
    """校验单个标的的日收盘记录。"""

    counters = {
        "input_records": 0,
        "invalid_date": 0,
        "future_or_incomplete": 0,
        "missing_close": 0,
        "non_finite": 0,
        "non_positive": 0,
        "duplicate_identical": 0,
        "duplicate_conflict": 0,
        "outlier_candidates": 0,
    }
    candidates = {}

    for record in records:
        counters["input_records"] += 1
        raw_date = record.get("date")
        try:
            parsed_date = (
                raw_date
                if isinstance(raw_date, date)
                else date.fromisoformat(str(raw_date))
            )
        except (TypeError, ValueError):
            counters["invalid_date"] += 1
            continue
        if parsed_date >= completed_before:
            counters["future_or_incomplete"] += 1
            continue

        raw_close = record.get("close")
        if raw_close is None or str(raw_close).strip() == "":
            counters["missing_close"] += 1
            continue
        try:
            close = float(raw_close)
        except (TypeError, ValueError):
            counters["non_finite"] += 1
            continue
        if not math.isfinite(close):
            counters["non_finite"] += 1
            continue
        if close <= 0:
            counters["non_positive"] += 1
            continue
        candidates.setdefault(parsed_date, []).append(close)

    points = []
    for parsed_date, closes in candidates.items():
        if any(close != closes[0] for close in closes[1:]):
            counters["duplicate_conflict"] += len(closes)
            continue
        counters["duplicate_identical"] += len(closes) - 1
        points.append(PricePoint(parsed_date, closes[0]))

    points.sort(key=lambda point: point.date)
    if len(points) >= 4:
        log_returns = [
            math.log(current.close / previous.close)
            for previous, current in zip(points, points[1:])
        ]
        center = median(log_returns)
        mad = median(abs(value - center) for value in log_returns)
        if mad > 0:
            counters["outlier_candidates"] = sum(
                0.6745 * abs(value - center) / mad > 8
                for value in log_returns
            )
    return ValidatedSeries(
        instrument=instrument,
        points=tuple(points),
        audit=QualityAudit(**counters),
    )
