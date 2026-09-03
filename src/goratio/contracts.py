"""合约级数据模型与换月日历构造（可交易性数据层地基）。

当前在线来源只提供连续期货收盘价，缺少合约月份、成交量与持仓量。本模块定义
标准合约记录、按 OI/成交量选择主力、检测换月事件。未来接入官方结算价或合规
数据源后，可用同一套逻辑生成真实可执行合约链。
"""

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from statistics import median
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from .providers import RawMarketData, SourceMetadata


@dataclass(frozen=True)
class ContractRecord:
    date: date
    instrument: str  # gold | oil
    symbol: str  # GC | CL
    contract_month: str  # YYYY-MM
    close: float
    volume: Optional[float] = None
    open_interest: Optional[float] = None
    open: Optional[float] = None
    settle: Optional[float] = None


@dataclass(frozen=True)
class RollEvent:
    date: date
    instrument: str
    symbol: str
    old_contract: str
    new_contract: str
    old_close: Optional[float]
    new_close: Optional[float]
    roll_gap_bps: Optional[float]


def _parse_record(record: Mapping[str, object]) -> ContractRecord:
    try:
        parsed_date = date.fromisoformat(str(record["date"]))
        volume = record.get("volume")
        open_interest = record.get("open_interest")
        open_price = record.get("open")
        settle = record.get("settle")
        return ContractRecord(
            date=parsed_date,
            instrument=str(record["instrument"]),
            symbol=str(record["symbol"]),
            contract_month=str(record["contract_month"]),
            close=float(record["close"]),
            volume=float(volume) if volume not in (None, "") else None,
            open_interest=(
                float(open_interest)
                if open_interest not in (None, "")
                else None
            ),
            open=float(open_price) if open_price not in (None, "") else None,
            settle=float(settle) if settle not in (None, "") else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"无效合约记录: {record}") from exc


def parse_contract_records(
    rows: Iterable[Mapping[str, object]],
) -> Tuple[ContractRecord, ...]:
    """从 dict 行构造标准合约记录。"""
    return tuple(_parse_record(row) for row in rows)


def read_contract_csv(path) -> Tuple[ContractRecord, ...]:
    """从标准合约 CSV 读取记录。"""
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {
                "date",
                "instrument",
                "symbol",
                "contract_month",
                "close",
            }
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(
                    "contract CSV 必须包含 date,instrument,symbol,contract_month,close；"
                    "可含 volume,open_interest"
                )
            rows = tuple(reader)
    except OSError as exc:
        raise ValueError(f"无法读取合约 CSV：{exc}") from exc
    if not rows:
        raise ValueError("合约 CSV 不包含数据行")
    return parse_contract_records(rows)


CONTRACT_CSV_METADATA = SourceMetadata(
    source_id="contract_csv",
    name="用户自有合约级 CSV",
    price_basis="用户合约级主力收盘/结算数据（非内置连续期货指数）",
    instruments={
        "gold": {
            "symbol": "GC",
            "contract": "COMEX 黄金期货主力合约",
            "currency": "USD",
            "unit": "troy_ounce",
        },
        "oil": {
            "symbol": "CL",
            "contract": "NYMEX WTI 原油期货主力合约",
            "currency": "USD",
            "unit": "barrel",
        },
    },
)


def contract_csv_to_raw_market_data(
    path,
    *,
    roll_adjusted: bool = False,
    retrieved_at=None,
) -> RawMarketData:
    """从标准合约 CSV 构造可被 prepare_market_data 消费的 RawMarketData。

    roll_adjusted=True 时使用换月无跳空调整序列。注意：调整后的绝对价格不
    适合真实金油比水平；如用于回测收益率可接受，但需在输出中保持警告。
    """
    records = read_contract_csv(path)
    if roll_adjusted:
        report = build_roll_adjusted_series(records)
        metadata = SourceMetadata(
            source_id="contract_csv_roll_adjusted",
            name="用户自有合约级 CSV（换月无跳空调整）",
            price_basis="主力合约换月无跳空连续序列；绝对价格非真实市场水平",
            instruments=CONTRACT_CSV_METADATA.instruments,
        )
    else:
        report = build_contract_series(records)
        metadata = CONTRACT_CSV_METADATA
    series_by_instrument = report["series"]
    missing = {"gold", "oil"} - set(series_by_instrument)
    if missing:
        raise ValueError(
            f"合约 CSV 必须同时包含 gold 与 oil 系列；缺少 {sorted(missing)}"
        )
    return RawMarketData(
        source=metadata,
        gold_records=tuple(
            {"date": point["date"], "close": point["close"]}
            for point in series_by_instrument["gold"]["calendar"]
        ),
        oil_records=tuple(
            {"date": point["date"], "close": point["close"]}
            for point in series_by_instrument["oil"]["calendar"]
        ),
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
    )


def build_contract_series(
    records: Sequence[ContractRecord],
) -> dict:
    """按 instrument 构造主力合约链，并记录换月事件。"""
    if not records:
        return {"series": {}, "roll_events": []}

    by_instrument: dict[str, dict[date, list[ContractRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in records:
        by_instrument[record.instrument][record.date].append(record)

    series = {}
    roll_events = []
    for instrument in sorted(by_instrument):
        daily_records = by_instrument[instrument]
        selected = []
        previous = None
        for trading_date in sorted(daily_records):
            day_records = daily_records[trading_date]
            chosen = max(
                day_records,
                key=lambda rec: (
                    rec.open_interest if rec.open_interest is not None else -1.0,
                    rec.volume if rec.volume is not None else -1.0,
                ),
            )
            if previous is not None and chosen.contract_month != previous.contract_month:
                old_close = None
                new_close = chosen.close
                for rec in day_records:
                    if rec.contract_month == previous.contract_month:
                        old_close = rec.close
                        break
                roll_gap_bps = (
                    (new_close / old_close - 1) * 10000
                    if old_close not in (None, 0)
                    else None
                )
                roll_events.append(
                    RollEvent(
                        date=trading_date,
                        instrument=instrument,
                        symbol=chosen.symbol,
                        old_contract=previous.contract_month,
                        new_contract=chosen.contract_month,
                        old_close=old_close,
                        new_close=new_close,
                        roll_gap_bps=roll_gap_bps,
                    )
                )
            selected.append(chosen)
            previous = chosen
        series[instrument] = {
            "symbol": selected[0].symbol,
            "calendar": [
                {
                    "date": point.date.isoformat(),
                    "contract_month": point.contract_month,
                    "close": point.close,
                    "volume": point.volume,
                    "open_interest": point.open_interest,
                    "open": point.open,
                    "settle": point.settle,
                }
                for point in selected
            ],
        }
    return {
        "series": series,
        "roll_events": [
            {
                "date": event.date.isoformat(),
                "instrument": event.instrument,
                "symbol": event.symbol,
                "old_contract": event.old_contract,
                "new_contract": event.new_contract,
                "old_close": event.old_close,
                "new_close": event.new_close,
                "roll_gap_bps": event.roll_gap_bps,
            }
            for event in sorted(
                roll_events,
                key=lambda event: (event.date, event.instrument),
            )
        ],
    }


def build_roll_adjusted_series(
    records: Sequence[ContractRecord],
) -> dict:
    """构造换月后无跳空的连续调整序列。

    用途：当真实回测需要“持有同一市场方向但按主力换月”时，先用换月当天新旧
    合约价格比例调整后续新合约价格，使连续收益率不因合约切换产生虚假跳空。
    注意：调整后的绝对价格不再是真实市场价，不能用于计算真实金油比水平。
    """
    report = build_contract_series(records)
    roll_by_instrument: dict[str, dict[str, dict]] = {}
    for event in report["roll_events"]:
        roll_by_instrument.setdefault(event["instrument"], {})[event["date"]] = event

    adjusted_series = {}
    for instrument, chain in report["series"].items():
        factor = 1.0
        previous_contract = None
        calendar = []
        for point in chain["calendar"]:
            if previous_contract is not None and point["contract_month"] != previous_contract:
                roll = roll_by_instrument.get(instrument, {}).get(point["date"])
                if (
                    roll is not None
                    and roll["old_close"] not in (None, 0)
                    and roll["new_close"] not in (None, 0)
                ):
                    factor *= roll["old_close"] / roll["new_close"]
            adjusted_close = point["close"] * factor
            calendar.append(
                {
                    **point,
                    "close": adjusted_close,
                    "adjustment_factor": factor,
                }
            )
            previous_contract = point["contract_month"]
        adjusted_series[instrument] = {
            "symbol": chain["symbol"],
            "calendar": calendar,
        }

    return {
        "series": adjusted_series,
        "roll_events": report["roll_events"],
        "note": "roll-adjusted 绝对价格不可用于真实比值水平，仅用于跨换月的连续收益计算",
    }


def summarize_roll_costs(records: Sequence[ContractRecord]) -> dict:
    """汇总主力合约换月价差成本统计。

    只统计换月当天新旧合约同时存在时的可计算 gap；未提供同日双合约价格的换月
    事件无法量化，会单独计数。
    """
    report = build_contract_series(records)
    measurable_gaps = [
        event["roll_gap_bps"]
        for event in report["roll_events"]
        if event["roll_gap_bps"] is not None
    ]
    unknown_count = sum(
        1
        for event in report["roll_events"]
        if event["roll_gap_bps"] is None
    )
    return {
        "roll_event_count": len(report["roll_events"]),
        "measurable_roll_gap_count": len(measurable_gaps),
        "unknown_roll_gap_count": unknown_count,
        "mean_abs_roll_gap_bps": (
            sum(abs(value) for value in measurable_gaps) / len(measurable_gaps)
            if measurable_gaps
            else None
        ),
        "median_abs_roll_gap_bps": (
            median(abs(value) for value in measurable_gaps)
            if measurable_gaps
            else None
        ),
        "max_abs_roll_gap_bps": (
            max(abs(value) for value in measurable_gaps)
            if measurable_gaps
            else None
        ),
        "note": "换月 gap 是实际滚动时可能产生的价差成本之一，不等同于完整交易成本",
    }


def roll_aware_contract_return(
    records: Sequence[ContractRecord],
    *,
    instrument: str,
    entry_date: date,
    exit_date: date,
) -> Optional[float]:
    """计算真实主力合约链上的持有期收益（含换月）。

    与 roll-adjusted 连续序列不同，本函数显式模拟：换月时按旧合约价格结算，
    再按新合约价格重新开仓。返回值为无交易成本的合约链收益率。
    """
    report = build_contract_series(records)
    if instrument not in report["series"]:
        return None
    calendar = report["series"][instrument]["calendar"]
    events = [
        point
        for point in calendar
        if entry_date <= date.fromisoformat(point["date"]) <= exit_date
    ]
    if len(events) < 2:
        return None
    roll_events = {
        (event["date"], event["instrument"]): event
        for event in report["roll_events"]
    }
    active_contract = events[0]["contract_month"]
    entry_price = events[0]["close"]
    cumulative = 1.0
    for point in events[1:]:
        current_date = point["date"]
        if point["contract_month"] == active_contract:
            continue
        roll = roll_events.get((current_date, instrument))
        old_close = roll["old_close"] if roll is not None else None
        if old_close is None or old_close == 0:
            # 无法同日确认旧合约价格时，使用前一交易日收盘价作为近似。
            previous_index = calendar.index(point) - 1
            old_close = calendar[previous_index]["close"]
        cumulative *= old_close / entry_price
        active_contract = point["contract_month"]
        entry_price = point["close"]
    final_price = events[-1]["close"]
    cumulative *= final_price / entry_price
    return cumulative - 1.0


def contract_episode_return_summary(records, episodes) -> dict:
    """在真实合约链上验证一组 episode 的换月收益差异。

    episodes 可以是任何包含 date/outcome_date/forward_return 的序列；
    本函数对每个 episode 用 roll_aware_contract_return 计算 gold 的实际换月收益，
    并与连续序列 forward_return 对比。
    """
    rows = []
    for episode in episodes:
        roll_return = roll_aware_contract_return(
            records,
            instrument="gold",
            entry_date=episode.date,
            exit_date=episode.outcome_date,
        )
        t1_gap = t1_open_settle_gap(
            records,
            instrument="gold",
            signal_date=episode.date,
        )
        t1_open_gap = t1_gap.get("open_gap") if t1_gap is not None else None
        rows.append(
            {
                "entry_date": episode.date.isoformat(),
                "outcome_date": episode.outcome_date.isoformat(),
                "continuous_forward_return": episode.forward_return,
                "roll_aware_return": roll_return,
                "difference": (
                    None
                    if roll_return is None
                    else episode.forward_return - roll_return
                ),
                "t1_open_gap": t1_open_gap,
                "t1_settle_gap": (
                    t1_gap.get("settle_gap") if t1_gap is not None else None
                ),
                "long_net_roll_aware_return": (
                    roll_return - t1_open_gap
                    if roll_return is not None and t1_open_gap is not None
                    else None
                ),
                "settle_net_roll_aware_return": (
                    roll_return - t1_gap.get("settle_gap")
                    if roll_return is not None
                    and t1_gap is not None
                    and t1_gap.get("settle_gap") is not None
                    else None
                ),
            }
        )
    valid = [
        row["difference"]
        for row in rows
        if row["difference"] is not None
    ]
    valid_gaps = [
        abs(row["t1_open_gap"])
        for row in rows
        if row["t1_open_gap"] is not None
    ]
    valid_net = [
        row["long_net_roll_aware_return"]
        for row in rows
        if row["long_net_roll_aware_return"] is not None
    ]
    valid_settle_net = [
        row["settle_net_roll_aware_return"]
        for row in rows
        if row["settle_net_roll_aware_return"] is not None
    ]
    return {
        "episode_count": len(rows),
        "valid_roll_aware_count": len(valid),
        "mean_absolute_difference": (
            sum(abs(value) for value in valid) / len(valid) if valid else None
        ),
        "valid_t1_open_gap_count": len(valid_gaps),
        "mean_abs_t1_open_gap": (
            sum(valid_gaps) / len(valid_gaps) if valid_gaps else None
        ),
        "valid_long_net_roll_aware_count": len(valid_net),
        "mean_long_net_roll_aware_return": (
            sum(valid_net) / len(valid_net) if valid_net else None
        ),
        "valid_settle_net_roll_aware_count": len(valid_settle_net),
        "mean_settle_net_roll_aware_return": (
            sum(valid_settle_net) / len(valid_settle_net)
            if valid_settle_net
            else None
        ),
        "rows": rows,
    }


def t1_open_settle_gap(
    records: Sequence[ContractRecord],
    *,
    instrument: str,
    signal_date: date,
) -> Optional[dict]:
    """计算信号日收盘到下一交易日 open/settle 的执行缺口。

    需要合约记录包含 open/settle 字段；缺少时返回 None。
    """
    report = build_contract_series(records)
    if instrument not in report["series"]:
        return None
    calendar = report["series"][instrument]["calendar"]
    signal_point = None
    next_point = None
    for point in calendar:
        current_date = date.fromisoformat(point["date"])
        if current_date == signal_date:
            signal_point = point
        elif current_date > signal_date and signal_point is not None:
            next_point = point
            break
    if signal_point is None or next_point is None:
        return None
    if next_point.get("open") is None and next_point.get("settle") is None:
        return None
    signal_close = signal_point["close"]
    return {
        "signal_date": signal_date.isoformat(),
        "next_date": next_point["date"],
        "signal_close": signal_close,
        "next_open": next_point.get("open"),
        "next_settle": next_point.get("settle"),
        "open_gap": (
            next_point["open"] / signal_close - 1
            if next_point.get("open") is not None and signal_close != 0
            else None
        ),
        "settle_gap": (
            next_point["settle"] / signal_close - 1
            if next_point.get("settle") is not None and signal_close != 0
            else None
        ),
    }


def run_contract_episode_net_backtest(
    records,
    episodes,
    *,
    cost_bps: float = 20.0,
    execution: str = "open",
) -> dict:
    """基于合约 CSV 的 episode 净收益回测摘要（T+1 open/settle 默认成交模型）。

    execution="open" 使用扣减 T+1 open gap 后的真实换月净收益；
    execution="settle" 使用扣减 T+1 settle gap 后的真实换月净收益。
    """
    if execution not in ("open", "settle"):
        raise ValueError("execution 必须是 open 或 settle")
    summary = contract_episode_return_summary(records, episodes)
    key = (
        "long_net_roll_aware_return"
        if execution == "open"
        else "settle_net_roll_aware_return"
    )
    net_rows = []
    for row in summary["rows"]:
        net_return = row.get(key)
        if net_return is None:
            continue
        net_after_cost = net_return - cost_bps / 10000.0
        net_rows.append(
            {
                "entry_date": row["entry_date"],
                "outcome_date": row["outcome_date"],
                "execution_net_return": net_return,
                "net_after_cost_return": net_after_cost,
            }
        )
    returns = [row["net_after_cost_return"] for row in net_rows]
    return {
        "method": "contract_episode_net_backtest",
        "execution": execution,
        "cost_bps": cost_bps,
        "episode_count": len(net_rows),
        "mean_net_after_cost_return": (
            sum(returns) / len(returns) if returns else None
        ),
        "positive_rate": (
            sum(value > 0 for value in returns) / len(returns)
            if returns
            else None
        ),
        "rows": net_rows,
    }
