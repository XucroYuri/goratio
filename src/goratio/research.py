"""预注册统计研究。"""

from dataclasses import dataclass
from datetime import date
import math
import random
from statistics import median
from typing import Sequence

from .data import AlignedPoint
from .dataset import PreparedMarketData


PROTOCOL_VERSION = "goratio-1a-v1"


@dataclass(frozen=True)
class ForwardEvent:
    date: date
    forward_return: float
    low_state: bool
    percentile: float
    history_count: int
    outcome_date: date


def _invert_matrix(matrix):
    size = len(matrix)
    augmented = [
        [float(value) for value in row]
        + [1.0 if row_index == column else 0.0 for column in range(size)]
        for row_index, row in enumerate(matrix)
    ]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            raise ValueError("回归矩阵不可逆")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                current - factor * pivot_value
                for current, pivot_value in zip(augmented[row], augmented[column])
            ]
    return [row[size:] for row in augmented]


def _multiply_matrix_vector(matrix, vector):
    return [sum(value * item for value, item in zip(row, vector)) for row in matrix]


def adf_mean_reversion(points: Sequence[AlignedPoint]):
    """执行预注册的带截距 ADF(1) 回归。"""

    critical_value = -2.86
    if len(points) < 30:
        return {
            "method": "ADF(1)_with_intercept",
            "lag": 1,
            "observation_count": len(points),
            "t_statistic": None,
            "critical_value_5pct": critical_value,
            "status": "insufficient_data",
            "limitation": "固定近似大样本临界值，不报告伪精确 p 值",
        }
    levels = [math.log(item.ratio) for item in points]
    rows = []
    outcomes = []
    for index in range(2, len(levels)):
        rows.append(
            [
                1.0,
                levels[index - 1],
                levels[index - 1] - levels[index - 2],
            ]
        )
        outcomes.append(levels[index] - levels[index - 1])
    xtx = [
        [sum(row[i] * row[j] for row in rows) for j in range(3)]
        for i in range(3)
    ]
    xty = [sum(row[i] * outcome for row, outcome in zip(rows, outcomes)) for i in range(3)]
    try:
        inverse = _invert_matrix(xtx)
    except ValueError:
        return {
            "method": "ADF(1)_with_intercept",
            "lag": 1,
            "observation_count": len(points),
            "t_statistic": None,
            "critical_value_5pct": critical_value,
            "status": "insufficient_data",
            "limitation": "序列缺少可估计的变化",
        }
    coefficients = _multiply_matrix_vector(inverse, xty)
    residuals = [
        outcome - sum(coefficient * value for coefficient, value in zip(coefficients, row))
        for row, outcome in zip(rows, outcomes)
    ]
    degrees_of_freedom = len(rows) - 3
    variance = sum(value * value for value in residuals) / degrees_of_freedom
    standard_error = math.sqrt(max(0.0, variance * inverse[1][1]))
    if standard_error == 0:
        t_statistic = None
        status = "insufficient_data"
    else:
        t_statistic = coefficients[1] / standard_error
        status = "supported" if t_statistic <= critical_value else "not_supported"
    return {
        "method": "ADF(1)_with_intercept",
        "lag": 1,
        "observation_count": len(points),
        "level_coefficient": coefficients[1],
        "t_statistic": t_statistic,
        "critical_value_5pct": critical_value,
        "status": status,
        "limitation": "固定近似大样本临界值，不报告伪精确 p 值",
    }


def _sup_f(values, minimum_segment):
    count = len(values)
    prefix = [0.0]
    prefix_squares = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
        prefix_squares.append(prefix_squares[-1] + value * value)

    def segment_sse(start, end):
        size = end - start
        total = prefix[end] - prefix[start]
        total_squares = prefix_squares[end] - prefix_squares[start]
        return max(0.0, total_squares - total * total / size)

    no_break_sse = segment_sse(0, count)
    best_statistic = -1.0
    best_split = minimum_segment
    for split in range(minimum_segment, count - minimum_segment + 1):
        broken_sse = segment_sse(0, split) + segment_sse(split, count)
        if broken_sse <= 1e-14:
            statistic = 1e15 if no_break_sse > 1e-14 else 0.0
        else:
            statistic = max(
                0.0,
                (no_break_sse - broken_sse) / (broken_sse / (count - 2)),
            )
        if statistic > best_statistic:
            best_statistic = statistic
            best_split = split
    return best_statistic, best_split


def _moving_block_sample(values, block_length, generator):
    sample = []
    count = len(values)
    while len(sample) < count:
        start = generator.randrange(count)
        sample.extend(
            values[(start + offset) % count] for offset in range(block_length)
        )
    return sample[:count]


def structural_break_diagnostic(
    points: Sequence[AlignedPoint],
    *,
    bootstrap_repetitions: int = 500,
    block_length: int = 20,
    seed: int = 20260902,
):
    """执行预注册的单均值断点 Sup-F 稳定性诊断。"""

    count = len(points)
    minimum_segment = max(252, math.ceil(count * 0.2))
    common = {
        "method": "single_mean_shift_sup_f",
        "minimum_segment_rule": "max(252, 20% of observations)",
        "minimum_segment_observations": minimum_segment,
        "bootstrap_repetitions": bootstrap_repetitions,
        "block_length": block_length,
        "seed": seed,
        "limitation": "Bai–Perron 思路的简化单均值断点诊断，不作事件归因",
    }
    if count < minimum_segment * 2:
        return {
            **common,
            "observation_count": count,
            "break_date": None,
            "sup_f": None,
            "bootstrap_p_value": None,
            "status": "insufficient_data",
        }
    values = [math.log(item.ratio) for item in points]
    observed, split = _sup_f(values, minimum_segment)
    centered = [value - sum(values) / count for value in values]
    generator = random.Random(seed)
    exceedances = 0
    for _ in range(bootstrap_repetitions):
        resampled = _moving_block_sample(centered, block_length, generator)
        simulated, _ = _sup_f(resampled, minimum_segment)
        exceedances += simulated >= observed
    p_value = (exceedances + 1) / (bootstrap_repetitions + 1)
    return {
        **common,
        "observation_count": count,
        "break_date": points[split].date.isoformat(),
        "sup_f": observed,
        "bootstrap_p_value": p_value,
        "status": "unstable" if p_value < 0.05 else "stable",
    }


def _years_before(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def build_forward_events(
    history: Sequence[AlignedPoint],
    selected: Sequence[AlignedPoint],
    *,
    horizon: int,
) -> Sequence[ForwardEvent]:
    """只用当时可见的滚动历史构造远期收益事件。"""

    if horizon <= 0:
        raise ValueError("horizon 必须为正整数")
    if not history or not selected:
        return ()
    selected_start = selected[0].date
    selected_end = selected[-1].date
    events = []
    window_start_index = 0
    for index, current in enumerate(history):
        if current.date < selected_start:
            continue
        if current.date > selected_end or index + horizon >= len(history):
            break
        future = history[index + horizon]
        if future.date > selected_end:
            continue
        rolling_start = _years_before(current.date, 5)
        while (
            window_start_index < index
            and history[window_start_index].date < rolling_start
        ):
            window_start_index += 1
        trailing = history[window_start_index : index + 1]
        if len(trailing) < 252:
            continue
        percentile = (
            sum(item.ratio <= current.ratio for item in trailing) / len(trailing)
        )
        events.append(
            ForwardEvent(
                date=current.date,
                forward_return=future.gold_close / current.gold_close - 1,
                low_state=percentile <= 0.2,
                percentile=percentile,
                history_count=len(trailing),
                outcome_date=future.date,
            )
        )
    return tuple(events)


def _quantile(values, probability):
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


def _bootstrap_mean_interval(
    values, *, confidence, repetitions, block_length, seed
):
    if not values:
        return None
    generator = random.Random(seed)
    estimates = []
    effective_block = min(block_length, len(values))
    for _ in range(repetitions):
        sample = _moving_block_sample(values, effective_block, generator)
        estimates.append(sum(sample) / len(sample))
    alpha = 1 - confidence
    return [
        _quantile(estimates, alpha / 2),
        _quantile(estimates, 1 - alpha / 2),
    ]


def _describe_returns(events, *, repetitions, block_length, seed):
    values = [event.forward_return for event in events]
    if not values:
        return {
            "sample_count": 0,
            "positive_rate": None,
            "mean": None,
            "median": None,
            "distribution_interval_5_95": None,
            "mean_ci_95": None,
        }
    return {
        "sample_count": len(values),
        "positive_rate": sum(value > 0 for value in values) / len(values),
        "mean": sum(values) / len(values),
        "median": median(values),
        "distribution_interval_5_95": [
            _quantile(values, 0.05),
            _quantile(values, 0.95),
        ],
        "mean_ci_95": _bootstrap_mean_interval(
            values,
            confidence=0.95,
            repetitions=repetitions,
            block_length=block_length,
            seed=seed,
        ),
    }


def _bootstrap_difference_interval(
    events, *, confidence, repetitions, block_length, seed
):
    if not events or not any(event.low_state for event in events):
        return None
    generator = random.Random(seed)
    estimates = []
    effective_block = min(block_length, len(events))
    for _ in range(repetitions):
        sample = _moving_block_sample(events, effective_block, generator)
        conditional = [event.forward_return for event in sample if event.low_state]
        if not conditional:
            continue
        unconditional = [event.forward_return for event in sample]
        estimates.append(
            sum(conditional) / len(conditional)
            - sum(unconditional) / len(unconditional)
        )
    if not estimates:
        return None
    alpha = 1 - confidence
    return [
        _quantile(estimates, alpha / 2),
        _quantile(estimates, 1 - alpha / 2),
    ]


def _summarize_event_segment(
    events, *, repetitions, block_length, seed
):
    conditional_events = [event for event in events if event.low_state]
    conditional = _describe_returns(
        conditional_events,
        repetitions=repetitions,
        block_length=block_length,
        seed=seed,
    )
    unconditional = _describe_returns(
        events,
        repetitions=repetitions,
        block_length=block_length,
        seed=seed + 1,
    )
    difference = (
        conditional["mean"] - unconditional["mean"]
        if conditional["mean"] is not None and unconditional["mean"] is not None
        else None
    )
    return {
        "period": (
            [events[0].date.isoformat(), events[-1].date.isoformat()]
            if events
            else None
        ),
        "conditional": conditional,
        "unconditional": unconditional,
        "difference": {
            "mean": difference,
            "ci_95": _bootstrap_difference_interval(
                events,
                confidence=0.95,
                repetitions=repetitions,
                block_length=block_length,
                seed=seed + 2,
            ),
            "familywise_ci_98_33": _bootstrap_difference_interval(
                events,
                confidence=1 - 0.05 / 3,
                repetitions=repetitions,
                block_length=block_length,
                seed=seed + 3,
            ),
        },
    }


def summarize_event_records(
    events: Sequence[ForwardEvent],
    *,
    split_date: date,
    horizon: int,
    evidence_eligible: bool,
    bootstrap_repetitions: int = 1000,
    block_length: int = 20,
):
    """按固定顺序切分汇总一个期限的事件记录。"""

    ordered = tuple(sorted(events, key=lambda event: event.date))
    in_sample = tuple(
        event
        for event in ordered
        if event.date < split_date and event.outcome_date < split_date
    )
    purged = tuple(
        event
        for event in ordered
        if event.date < split_date and event.outcome_date >= split_date
    )
    out_of_sample = tuple(event for event in ordered if event.date >= split_date)
    seed = 20260902 + horizon
    all_summary = _summarize_event_segment(
        ordered,
        repetitions=bootstrap_repetitions,
        block_length=block_length,
        seed=seed,
    )
    in_summary = _summarize_event_segment(
        in_sample,
        repetitions=bootstrap_repetitions,
        block_length=block_length,
        seed=seed + 1000,
    )
    out_summary = _summarize_event_segment(
        out_of_sample,
        repetitions=bootstrap_repetitions,
        block_length=block_length,
        seed=seed + 2000,
    )
    conditional_count = out_summary["conditional"]["sample_count"]
    familywise_interval = out_summary["difference"]["familywise_ci_98_33"]
    if not evidence_eligible or conditional_count < 30:
        evidence_status = "insufficient_data"
    elif familywise_interval and familywise_interval[0] > 0:
        evidence_status = "supported"
    else:
        evidence_status = "not_supported"
    return {
        "horizon_trading_days": horizon,
        "approximate_months": {63: 3, 126: 6, 252: 12}.get(horizon),
        "low_state_threshold": 0.2,
        "minimum_conditional_events": 30,
        "bootstrap": {
            "method": "circular_moving_block",
            "repetitions": bootstrap_repetitions,
            "block_length": block_length,
            "seed": seed,
        },
        "split": {
            "rule": "chronological_70_30",
            "split_date": split_date.isoformat(),
            "in_sample_event_observations": len(in_sample),
            "purged_boundary_events": len(purged),
            "out_of_sample_event_observations": len(out_of_sample),
        },
        "all_sample": all_summary,
        "in_sample": in_summary,
        "out_of_sample": out_summary,
        "evidence_status": evidence_status,
    }


def run_event_study(
    data: PreparedMarketData,
    *,
    bootstrap_repetitions: int = 1000,
):
    selected = data.selected.points
    if len(selected) < 2:
        split_date = selected[0].date
    else:
        split_index = min(len(selected) - 1, max(1, int(len(selected) * 0.7)))
        split_date = selected[split_index].date
    results = {}
    for horizon in (63, 126, 252):
        events = build_forward_events(
            data.history.points,
            selected,
            horizon=horizon,
        )
        results[str(horizon)] = summarize_event_records(
            events,
            split_date=split_date,
            horizon=horizon,
            evidence_eligible=data.evidence_eligible,
            bootstrap_repetitions=bootstrap_repetitions,
        )
    return {
        "method": "trailing_quantile_forward_gold_return_event_study",
        "quantile_window": "trailing_5_calendar_years",
        "low_state_threshold": 0.2,
        "horizons": results,
    }


def _time_replication_status(event_study):
    comparisons = []
    for result in event_study["horizons"].values():
        in_difference = result["in_sample"]["difference"]["mean"]
        out_difference = result["out_of_sample"]["difference"]["mean"]
        if in_difference is None or out_difference is None:
            return "insufficient_data"
        comparisons.append(
            (in_difference == 0 and out_difference == 0)
            or (in_difference > 0 and out_difference > 0)
            or (in_difference < 0 and out_difference < 0)
        )
    return "supported" if all(comparisons) else "not_supported"


def run_research(
    data: PreparedMarketData,
    *,
    event_bootstrap_repetitions: int = 1000,
    structural_bootstrap_repetitions: int = 500,
):
    """执行冻结的六项假设并返回可序列化研究结果。"""

    current = summarize_current(data.history.points, data.selected.points)
    mean_reversion = adf_mean_reversion(data.selected.points)
    stability = structural_break_diagnostic(
        data.selected.points,
        bootstrap_repetitions=structural_bootstrap_repetitions,
    )
    if not data.evidence_eligible:
        mean_reversion["status"] = "insufficient_data"
        mean_reversion["eligibility_gate"] = "not_met"
        stability["status"] = "insufficient_data"
        stability["eligibility_gate"] = "not_met"
    event_study = run_event_study(
        data,
        bootstrap_repetitions=event_bootstrap_repetitions,
    )
    structural_hypothesis = {
        "unstable": "supported",
        "stable": "not_supported",
        "insufficient_data": "insufficient_data",
    }[stability["status"]]
    horizons = event_study["horizons"]
    evidence_status = {
        "H1_mean_reversion": mean_reversion["status"],
        "H2_structural_change": structural_hypothesis,
        "H3a_low_quantile_3m": horizons["63"]["evidence_status"],
        "H3b_low_quantile_6m": horizons["126"]["evidence_status"],
        "H3c_low_quantile_12m": horizons["252"]["evidence_status"],
        "H4_cross_time_and_source_replication": "insufficient_data",
    }
    risk_flags = ["provider_continuous_contract_rolls"]
    if not data.evidence_eligible:
        risk_flags.append("insufficient_history")
    if data.cache_stale:
        risk_flags.append("stale_cache")
    if data.quality_status == "degraded":
        risk_flags.append("data_quality_findings")
    if stability["status"] == "unstable":
        risk_flags.append("structural_instability")
    risk_flags.append("cross_source_replication_not_assessed")
    unpassed = [
        hypothesis
        for hypothesis, status in evidence_status.items()
        if status != "supported"
    ]
    return {
        "protocol_version": PROTOCOL_VERSION,
        "trial_count": 6,
        "parameters": {
            "rolling_center": "median",
            "rolling_window": "5y",
            "low_quantile_threshold": 0.2,
            "horizons_trading_days": [63, 126, 252],
            "chronological_split": [0.7, 0.3],
            "event_bootstrap_repetitions": event_bootstrap_repetitions,
            "structural_bootstrap_repetitions": structural_bootstrap_repetitions,
            "block_length": 20,
            "seed_base": 20260902,
        },
        "current": current,
        "mean_reversion": mean_reversion,
        "stability_diagnostic": stability,
        "event_study": event_study,
        "replication": {
            "cross_time_status": _time_replication_status(event_study),
            "cross_source_status": "insufficient_data",
            "note": "需用另一同口径来源运行相同协议后比较",
        },
        "evidence_status": evidence_status,
        "unpassed_hypotheses": unpassed,
        "risk_flags": risk_flags,
    }


def _direction(value):
    if value is None:
        return None
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def compare_source_results(first, second, first_source: str, second_source: str):
    """按冻结协议比较两个来源的状态、显著性与样本外方向。"""

    checks = {}
    statuses = [
        first["mean_reversion"]["status"],
        second["mean_reversion"]["status"],
        first["stability_diagnostic"]["status"],
        second["stability_diagnostic"]["status"],
        first["replication"]["cross_time_status"],
        second["replication"]["cross_time_status"],
    ]
    checks["mean_reversion_status_match"] = statuses[0] == statuses[1]
    checks["stability_status_match"] = statuses[2] == statuses[3]
    checks["cross_time_supported_both"] = statuses[4:] == ["supported", "supported"]
    incomplete = "insufficient_data" in statuses
    for horizon in (63, 126, 252):
        key = str(horizon)
        first_horizon = first["event_study"]["horizons"][key]
        second_horizon = second["event_study"]["horizons"][key]
        first_status = first_horizon["evidence_status"]
        second_status = second_horizon["evidence_status"]
        first_direction = _direction(
            first_horizon["out_of_sample"]["difference"]["mean"]
        )
        second_direction = _direction(
            second_horizon["out_of_sample"]["difference"]["mean"]
        )
        checks[f"{horizon}_status_match"] = first_status == second_status
        checks[f"{horizon}_direction_match"] = first_direction == second_direction
        incomplete = incomplete or "insufficient_data" in {
            first_status,
            second_status,
        }
        incomplete = incomplete or first_direction is None or second_direction is None
    if incomplete:
        status = "insufficient_data"
    else:
        status = "supported" if all(checks.values()) else "not_supported"
    return {
        "method": "fixed_protocol_cross_source_comparison",
        "sources": [first_source, second_source],
        "status": status,
        "checks": checks,
    }


def summarize_current(
    history: Sequence[AlignedPoint], selected: Sequence[AlignedPoint]
):
    if not history or not selected:
        raise ValueError("至少需要一个共同交易日")
    current = selected[-1]
    try:
        rolling_start = current.date.replace(year=current.date.year - 5)
    except ValueError:
        rolling_start = current.date.replace(year=current.date.year - 5, day=28)
    rolling = [
        item.ratio
        for item in history
        if rolling_start <= item.date <= current.date
    ]
    full = [item.ratio for item in selected]
    rolling_ready = len(rolling) >= 252
    rolling_center = median(rolling) if rolling_ready else None
    rolling_percentile = (
        sum(value <= current.ratio for value in rolling) / len(rolling)
        if rolling_ready
        else None
    )
    return {
        "as_of": current.date.isoformat(),
        "gold_close": current.gold_close,
        "oil_close": current.oil_close,
        "ratio": current.ratio,
        "ratio_unit": "barrels_of_oil_per_troy_ounce_of_gold",
        "rolling_window": "5y",
        "rolling_observation_count": len(rolling),
        "rolling_center": rolling_center,
        "deviation": (
            current.ratio / rolling_center - 1 if rolling_center else None
        ),
        "historical_percentile": rolling_percentile,
        "full_period_reference": {
            "center": median(full),
            "percentile": sum(value <= current.ratio for value in full) / len(full),
            "observation_count": len(full),
        },
    }
