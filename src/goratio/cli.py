"""goratio 命令行入口。"""

import argparse
from datetime import date, datetime, timezone
import json
import sys
from typing import Optional, Sequence, TextIO

from .cache import (
    CacheError,
    DataLoader,
    DataUnavailableError,
    LoadedData,
    import_standard_csv,
    raw_data_hash,
)
from .dataset import DataQualityError, prepare_market_data
from .providers import ProviderError
from .reporting import build_result
from .research import compare_source_results, run_research


STATUS_TEXT = {
    "supported": "获得支持",
    "not_supported": "未获支持",
    "insufficient_data": "数据不足",
    "not_evaluated": "未执行研究检验",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goratio",
        description="金油比价历史统计与概率分析工具",
    )
    parser.add_argument("--version", action="version", version="goratio 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("now", "显示当前比值、滚动中枢和数据覆盖"),
        ("analyze", "执行冻结的预注册统计协议"),
    ):
        subparser = commands.add_parser(command, help=help_text)
        subparser.add_argument(
            "--period", choices=("3y", "5y", "10y"), default="5y"
        )
        subparser.add_argument(
            "--source",
            choices=("cn_public", "yahoo_futures"),
            default="cn_public",
        )
        subparser.add_argument("--json", action="store_true", dest="as_json")
        subparser.add_argument("--timeout", type=float, default=10.0)

    update = commands.add_parser("update", help="刷新在线缓存或导入自有 CSV")
    update.add_argument(
        "--source",
        choices=("cn_public", "yahoo_futures"),
        default="cn_public",
    )
    update.add_argument("--import-csv", type=str)
    update.add_argument("--json", action="store_true", dest="as_json")
    update.add_argument("--timeout", type=float, default=10.0)
    return parser


def _format_number(value, digits=4) -> str:
    return "数据不足" if value is None else f"{value:.{digits}f}"


def _render_text(result, command: str) -> str:
    source = result["source"]
    ratio = result["ratio"]
    quality = result["data_quality"]
    lines = [
        f"数据来源：{source['name']}（{source['id']} / {source['provenance']}）",
        f"价格口径：{result['price_basis']}",
        (
            "标的："
            f"{result['instruments']['gold']['contract']} / "
            f"{result['instruments']['oil']['contract']}"
        ),
        (
            f"实际共同样本：{result['actual_period'][0]} 至 "
            f"{result['actual_period'][1]}，{result['observation_count']} 条，"
            f"跨度 {result['span_days']} 天"
        ),
        f"质量状态：{quality['status']}；证据门槛：{'满足' if quality['evidence_eligible'] else '未满足'}",
        (
            f"最新收盘：黄金 {_format_number(ratio['gold_close'], 2)}，"
            f"原油 {_format_number(ratio['oil_close'], 2)}，"
            f"金油比 {_format_number(ratio['ratio'])}"
        ),
        (
            f"5 年滚动中枢：{_format_number(ratio['rolling_center'])}；"
            f"偏离度：{_format_number(ratio['deviation'])}；"
            f"历史分位：{_format_number(ratio['historical_percentile'])}"
        ),
    ]
    if command == "analyze":
        lines.append("预注册检验：")
        for hypothesis, status in result["evidence_status"].items():
            lines.append(f"  {hypothesis}: {STATUS_TEXT[status]}")
        lines.append(
            "结构稳定性："
            + result["stability_diagnostic"]["status"]
            + "（实验诊断，不作事件归因）"
        )
        for horizon, evidence in result["conditional_forward_returns"][
            "horizons"
        ].items():
            conditional = evidence["out_of_sample"]["conditional"]
            difference = evidence["out_of_sample"]["difference"]
            lines.append(
                f"  {horizon} 交易日：样本外低状态 {conditional['sample_count']} 条；"
                f"相对基线均值差 {_format_number(difference['mean'])}；"
                f"结论 {STATUS_TEXT[evidence['evidence_status']]}"
            )
    else:
        lines.append("证据状态：本命令未执行研究检验")
    if quality["warnings"]:
        lines.append("数据提示：" + "；".join(quality["warnings"]))
    lines.append("风险标记：" + "、".join(result["risk_flags"]))
    lines.append("方法局限：" + "；".join(result["method_limitations"]))
    lines.append("声明：" + result["disclaimer"])
    return "\n".join(lines)


def _attach_cached_replication(
    loader: DataLoader,
    source_id: str,
    period: str,
    completed_before: date,
    primary_research,
) -> None:
    other_source = (
        "yahoo_futures" if source_id == "cn_public" else "cn_public"
    )
    try:
        cached = loader.cache.load(other_source)
        secondary_data = prepare_market_data(
            cached.raw,
            period=period,
            completed_before=completed_before,
            provenance="cache",
            cache_stale=cached.stale,
        )
    except (CacheError, DataQualityError):
        return
    secondary_research = run_research(secondary_data)
    comparison = compare_source_results(
        primary_research,
        secondary_research,
        source_id,
        other_source,
    )
    primary_research["replication"]["cross_source_status"] = comparison[
        "status"
    ]
    primary_research["replication"]["cross_source_comparison"] = comparison
    hypothesis = "H4_cross_time_and_source_replication"
    primary_research["evidence_status"][hypothesis] = comparison["status"]
    primary_research["unpassed_hypotheses"] = [
        name
        for name, status in primary_research["evidence_status"].items()
        if status != "supported"
    ]
    flags = primary_research["risk_flags"]
    if "cross_source_replication_not_assessed" in flags:
        flags.remove("cross_source_replication_not_assessed")
    if comparison["status"] != "supported":
        flags.append("cross_source_replication_not_reproduced")
    if cached.stale:
        flags.append("secondary_source_cache_stale")


def _loaded_user_csv(raw) -> LoadedData:
    return LoadedData(
        raw=raw,
        provenance="user_csv",
        cache_origin=None,
        cache_age_hours=0.0,
        cache_stale=False,
        snapshot_sha256=raw_data_hash(raw),
        warnings=("数据来自用户自有 CSV，来源权利与口径由用户确认",),
    )


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    loader: Optional[DataLoader] = None,
    today=date.today,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(argv)
    loader = loader or DataLoader()
    completed_before = today()
    try:
        if args.command == "update" and args.import_csv:
            raw = import_standard_csv(
                args.import_csv,
                loader.provider_metadata(args.source),
                retrieved_at=datetime.now(timezone.utc),
            )
            loader.cache.write(raw, provenance="user_csv")
            loaded = _loaded_user_csv(raw)
        elif args.command == "update":
            loaded = loader.update(args.source, timeout=args.timeout)
        else:
            loaded = loader.load(args.source, timeout=args.timeout)

        period = getattr(args, "period", "10y")
        prepared = prepare_market_data(
            loaded.raw,
            period=period,
            completed_before=completed_before,
            provenance=loaded.provenance,
            cache_stale=loaded.cache_stale,
        )
        research = None
        if args.command == "analyze":
            research = run_research(prepared)
            _attach_cached_replication(
                loader,
                args.source,
                period,
                completed_before,
                research,
            )
        result = build_result(loaded, prepared, research=research)
        if args.command == "update":
            result["operation"] = "cache_updated"
        if args.as_json:
            stdout.write(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            )
        else:
            stdout.write(_render_text(result, args.command) + "\n")
        return 0
    except (
        CacheError,
        DataQualityError,
        DataUnavailableError,
        ProviderError,
        ValueError,
    ) as exc:
        stderr.write(f"错误：{exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
