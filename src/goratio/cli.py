"""goratio 命令行入口。"""

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Optional, Sequence, TextIO

from . import __version__
from .agent import render_skill, serve as mcp_serve
from .backtest import run_episode_cost_backtest
from .cache import (
    CacheError,
    DataLoader,
    DataUnavailableError,
    LoadedData,
    import_standard_csv,
    raw_data_hash,
)
from .contracts import (
    build_contract_series,
    contract_csv_to_raw_market_data,
    read_contract_csv,
    run_contract_episode_net_backtest,
    summarize_roll_costs,
)
from .margin import summarize_batch_portfolio
from .dataset import DataQualityError, prepare_market_data
from .episode_study import run_episode_evidence_bundle
from .formal_v2 import generate_v2_formal_report, generate_v2_overview
from .evidence_gates import run_v2_evidence_bundle
from .episodes import (
    build_forward_episodes,
    chronological_split_date,
    split_episode_counts,
    summarize_episode_research,
)
from .plugins import KINDS, list_plugins
from .protocol_v2 import (
    PROTOCOL_V2_SPEC,
    factor_snapshot,
    factor_snapshot_variant_b,
)
from .providers import ProviderError
from .reporting import build_result
from .stress import tail_stress_report
from .web import render_dashboard_html, serve_dashboard
from .research import compare_source_results, run_research, summarize_current
from .tradability import build_tradability_report


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
    parser.add_argument(
        "--version", action="version", version=f"goratio {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("now", "显示当前比值、滚动中枢和数据覆盖"),
        ("analyze", "执行冻结的预注册统计协议"),
        ("episode", "显示低分位 episode 与日频事件的压缩诊断"),
        ("tradability", "显示可交易性诊断：合约规格、执行缺口、负油价与人民币披露"),
        ("episode-study", "运行 episode 级 63/126/252 样本外事件研究诊断"),
        ("stress", "检查负油价/零价危机事件相对研究窗口的接入状态"),
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
        if command == "episode":
            subparser.add_argument(
                "--horizon",
                type=int,
                choices=(63, 126, 252),
                default=126,
                help="远期收益的共同交易日期限",
            )
        if command == "tradability":
            subparser.add_argument(
                "--usdcny",
                type=float,
                default=None,
                help="可选 USD/CNY 汇率，用于人民币计价披露（不进入核心因子）",
            )

    update = commands.add_parser("update", help="刷新在线缓存或导入自有 CSV")
    update.add_argument(
        "--source",
        choices=("cn_public", "yahoo_futures"),
        default="cn_public",
    )
    update.add_argument("--import-csv", type=str)
    update.add_argument("--json", action="store_true", dest="as_json")
    update.add_argument("--timeout", type=float, default=10.0)

    contracts = commands.add_parser("contracts", help="读取合约级 CSV 并检查换月日历")
    contracts_subcommands = contracts.add_subparsers(dest="contracts_command", required=True)
    contracts_inspect = contracts_subcommands.add_parser("inspect", help="解析合约 CSV 并输出主力链/换月事件")
    contracts_inspect.add_argument("--csv", type=str, required=True, help="标准合约 CSV 路径")
    contracts_inspect.add_argument("--json", action="store_true", dest="as_json")

    contracts_backtest = contracts_subcommands.add_parser("backtest", help="用合约级 CSV 运行 episode 成本回测")
    contracts_backtest.add_argument("--csv", type=str, required=True, help="标准合约 CSV 路径")
    contracts_backtest.add_argument("--roll-adjusted", action="store_true", help="使用换月无跳空调整序列")
    contracts_backtest.add_argument("--horizon", type=int, choices=(63,126,252), default=126)
    contracts_backtest.add_argument("--cost-bps", type=float, default=20.0)
    contracts_backtest.add_argument("--roll-cost-bps", type=float, default=0.0)
    contracts_backtest.add_argument("--json", action="store_true", dest="as_json")

    contracts_portfolio = contracts_subcommands.add_parser("portfolio", help="用合约 CSV 运行批量持仓高层汇总")
    contracts_portfolio.add_argument("--csv", type=str, required=True)
    contracts_portfolio.add_argument("--horizon", type=int, choices=(63,126,252), default=126)
    contracts_portfolio.add_argument("--direction", type=int, default=1)
    contracts_portfolio.add_argument("--lots", type=int, default=1)
    contracts_portfolio.add_argument("--initial-capital", type=float, default=100000.0)
    contracts_portfolio.add_argument("--json", action="store_true", dest="as_json")

    contracts_net = contracts_subcommands.add_parser("net-backtest", help="用合约 CSV 运行 T+1 open/settle 净收益 episode 回测")
    contracts_net.add_argument("--csv", type=str, required=True)
    contracts_net.add_argument("--horizon", type=int, choices=(63,126,252), default=126)
    contracts_net.add_argument("--cost-bps", type=float, default=20.0)
    contracts_net.add_argument("--execution", choices=("open","settle"), default="open")
    contracts_net.add_argument("--json", action="store_true", dest="as_json")

    contracts_rollcost = contracts_subcommands.add_parser("roll-cost", help="输出合约 CSV 的换月 gap 成本统计")
    contracts_rollcost.add_argument("--csv", type=str, required=True)
    contracts_rollcost.add_argument("--json", action="store_true", dest="as_json")

    plugin = commands.add_parser("plugin", help="查看静态插件白名单")
    plugin_subcommands = plugin.add_subparsers(dest="plugin_command", required=True)
    plugin_list = plugin_subcommands.add_parser("list", help="列出白名单插件")
    plugin_list.add_argument("--kind", choices=KINDS)
    plugin_list.add_argument("--json", action="store_true", dest="as_json")

    mcp = commands.add_parser("mcp", help="只读 MCP Agent 接口")
    mcp_subcommands = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_serve = mcp_subcommands.add_parser("serve", help="运行只读 stdio MCP 服务")

    skill = commands.add_parser("skill", help="渲染 Agent SKILL 约束手册")
    skill_subcommands = skill.add_subparsers(dest="skill_command", required=True)
    skill_render = skill_subcommands.add_parser("render", help="以 Markdown 输出 SKILL")
    skill_render.add_argument("--format", default="markdown")

    backtest = commands.add_parser("backtest", help="运行成本后 episode 回测与风控门控诊断")
    backtest.add_argument("--period", choices=("3y", "5y", "10y"), default="5y")
    backtest.add_argument(
        "--source",
        choices=("cn_public", "yahoo_futures"),
        default="cn_public",
    )
    backtest.add_argument("--json", action="store_true", dest="as_json")
    backtest.add_argument("--timeout", type=float, default=10.0)
    backtest.add_argument(
        "--horizon", type=int, choices=(63, 126, 252), default=126
    )
    backtest.add_argument(
        "--cost-bps", type=float, default=20.0, help="单次往返交易成本（基点）"
    )
    backtest.add_argument(
        "--t1-close",
        action="store_true",
        dest="t1_close",
        help="使用信号后一个共同交易日收盘价作为执行价（T+1 close 近似）",
    )
    backtest.add_argument(
        "--roll-cost-bps",
        type=float,
        default=0.0,
        help="每笔 episode 附加的换月价差成本（基点）",
    )

    overview = commands.add_parser("overview", help="输出 v2 研究总览")
    overview.add_argument("--period", choices=("3y", "5y", "10y"), default="10y")
    overview.add_argument("--source", choices=("cn_public", "yahoo_futures"), default="cn_public")
    overview.add_argument("--json", action="store_true", dest="as_json")
    overview.add_argument("--timeout", type=float, default=10.0)

    formal = commands.add_parser("formal", help="输出双因子 v2 正式验收前报告")
    formal.add_argument("--period", choices=("3y", "5y", "10y"), default="10y")
    formal.add_argument(
        "--source",
        choices=("cn_public", "yahoo_futures"),
        default="cn_public",
    )
    formal.add_argument("--json", action="store_true", dest="as_json")
    formal.add_argument("--timeout", type=float, default=10.0)
    formal.add_argument("--cost-bps", type=float, default=20.0)
    formal.add_argument("--roll-cost-bps", type=float, default=0.0)

    evidence = commands.add_parser("evidence", help="运行双因子 v2 成本后 episode 组合证据门槛")
    evidence.add_argument("--period", choices=("3y", "5y", "10y"), default="10y")
    evidence.add_argument(
        "--source",
        choices=("cn_public", "yahoo_futures"),
        default="cn_public",
    )
    evidence.add_argument("--json", action="store_true", dest="as_json")
    evidence.add_argument("--timeout", type=float, default=10.0)
    evidence.add_argument("--cost-bps", type=float, default=20.0)
    evidence.add_argument("--roll-cost-bps", type=float, default=0.0)

    web = commands.add_parser("web", help="只读 Web 工作台（本地 HTML 导出）")
    web_subcommands = web.add_subparsers(dest="web_command", required=True)
    web_export = web_subcommands.add_parser("export", help="导出自包含 HTML 快照")
    web_export.add_argument("--period", choices=("3y", "5y", "10y"), default="10y")
    web_export.add_argument(
        "--source",
        choices=("cn_public", "yahoo_futures"),
        default="cn_public",
    )
    web_export.add_argument("--timeout", type=float, default=10.0)
    web_export.add_argument("--output", type=str, help="输出 HTML 文件路径；缺省输出到 stdout")
    web_export.add_argument("--json", action="store_true", dest="as_json", help="同时输出 JSON 数据载荷")
    web_serve = web_subcommands.add_parser("serve", help="启动只读本地 HTTP 工作台")
    web_serve.add_argument("--period", choices=("3y", "5y", "10y"), default="10y")
    web_serve.add_argument(
        "--source",
        choices=("cn_public", "yahoo_futures"),
        default="cn_public",
    )
    web_serve.add_argument("--timeout", type=float, default=10.0)
    web_serve.add_argument("--host", default="127.0.0.1")
    web_serve.add_argument("--port", type=int, default=8765)

    factor = commands.add_parser("factor", help="查看预注册双因子 v2 当前研究状态")
    factor_subcommands = factor.add_subparsers(dest="factor_command", required=True)
    factor_status = factor_subcommands.add_parser("status", help="显示当前因子快照")
    factor_status.add_argument("--period", choices=("3y", "5y", "10y"), default="5y")
    factor_status.add_argument(
        "--source",
        choices=("cn_public", "yahoo_futures"),
        default="cn_public",
    )
    factor_status.add_argument("--json", action="store_true", dest="as_json")
    factor_status.add_argument("--timeout", type=float, default=10.0)
    factor_status.add_argument(
        "--variant", choices=("a", "b"), default="a",
        help="a=价值+趋势确认；b=机会+结构稳定性",
    )
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
    stdin: TextIO = sys.stdin,
) -> int:
    args = build_parser().parse_args(argv)
    loader = loader or DataLoader()
    completed_before = today()
    try:
        if args.command == "contracts" and args.contracts_command == "backtest":
            raw = contract_csv_to_raw_market_data(
                args.csv,
                roll_adjusted=bool(args.roll_adjusted),
            )
            prepared = prepare_market_data(
                raw,
                period="10y",
                completed_before=completed_before,
                provenance="user_contract_csv",
                cache_stale=False,
            )
            report = run_episode_cost_backtest(
                prepared,
                horizon=args.horizon,
                round_trip_cost_bps=args.cost_bps,
                t1_close_execution=True,
                roll_cost_bps=args.roll_cost_bps,
            )
            report["source_id"] = raw.source.source_id
            report["price_basis"] = raw.source.price_basis
            if args.as_json:
                stdout.write(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                stdout.write(
                    f"合约 CSV 回测：{report['source_id']}；"
                    f"换月无跳空调整={bool(args.roll_adjusted)}\n"
                    f"交易数：{report['trade_count']}；平均净收益："
                    f"{_format_number(report['metrics']['mean_net_return'])}\n"
                )
            return 0
        if args.command == "contracts" and args.contracts_command == "portfolio":
            records = read_contract_csv(args.csv)
            raw = contract_csv_to_raw_market_data(args.csv)
            prepared = prepare_market_data(
                raw,
                period="10y",
                completed_before=completed_before,
                provenance="user_contract_csv",
                cache_stale=False,
            )
            episodes = build_forward_episodes(
                prepared.history.points,
                prepared.selected.points,
                horizon=args.horizon,
            )
            report = summarize_batch_portfolio(
                records,
                episodes,
                direction=args.direction,
                lots=args.lots,
                initial_capital=args.initial_capital,
            )
            if args.as_json:
                stdout.write(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                stdout.write(
                    f"合约 CSV 批量组合：episode {report['simulation']['episode_count']}；"
                    f"最终权益 {_format_number(report['equity']['final_equity'], 2)}\n"
                )
            return 0
        if args.command == "contracts" and args.contracts_command == "net-backtest":
            records = read_contract_csv(args.csv)
            raw = contract_csv_to_raw_market_data(args.csv)
            prepared = prepare_market_data(
                raw,
                period="10y",
                completed_before=completed_before,
                provenance="user_contract_csv",
                cache_stale=False,
            )
            episodes = build_forward_episodes(
                prepared.history.points,
                prepared.selected.points,
                horizon=args.horizon,
            )
            report = run_contract_episode_net_backtest(
                records,
                episodes,
                cost_bps=args.cost_bps,
                execution=args.execution,
            )
            if args.as_json:
                stdout.write(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                stdout.write(
                    f"合约 CSV T+1 {args.execution} 净收益回测：episode {report['episode_count']}；"
                    f"成本后均值 {_format_number(report['mean_net_after_cost_return'])}\n"
                )
            return 0
        if args.command == "contracts" and args.contracts_command == "roll-cost":
            records = read_contract_csv(args.csv)
            report = summarize_roll_costs(records)
            if args.as_json:
                stdout.write(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                stdout.write(
                    f"换月事件数：{report['roll_event_count']}；可量化 gap 数："
                    f"{report['measurable_roll_gap_count']}\n"
                )
            return 0
        if args.command == "contracts":
            records = read_contract_csv(args.csv)
            report = build_contract_series(records)
            payload = {
                "schema_version": "goratio-contracts-v1",
                "record_count": len(records),
                "instruments": sorted(report["series"].keys()),
                "roll_event_count": len(report["roll_events"]),
                "series": report["series"],
                "roll_events": report["roll_events"],
            }
            if args.as_json:
                stdout.write(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                stdout.write(
                    f"记录数：{len(records)}\n"
                    f"合约系列：{', '.join(payload['instruments']) or '无'}\n"
                    f"换月事件数：{len(report['roll_events'])}\n"
                )
                for event in report["roll_events"]:
                    stdout.write(
                        f"  {event['date']} {event['symbol']} "
                        f"{event['old_contract']} -> {event['new_contract']}\n"
                    )
            return 0
        if args.command == "plugin":
            plugins = list_plugins(
                getattr(args, "kind", None)
            )
            if args.as_json:
                stdout.write(
                    json.dumps(
                        {
                            "api_version": "goratio-plugin-v1",
                            "count": len(plugins),
                            "plugins": plugins,
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                )
            else:
                if not plugins:
                    stdout.write("（无白名单插件）\n")
                else:
                    for plugin in plugins:
                        stdout.write(
                            f"{plugin['plugin_id']}  [{plugin['kind']}] "
                            f"{plugin['name']} v{plugin['version']} "
                            f"{'只读' if plugin['read_only'] else '读写'}\n"
                        )
            return 0
        if args.command == "skill":
            stdout.write(render_skill(getattr(args, "format", "markdown")))
            stdout.write("\n")
            return 0
        if args.command == "mcp":
            mcp_serve(loader, stdin=stdin, stdout=stdout)
            return 0
        if args.command == "web":
            def make_web_payload():
                loaded = loader.load(args.source, timeout=args.timeout)
                prepared = prepare_market_data(
                    loaded.raw,
                    period=args.period,
                    completed_before=today(),
                    provenance=loaded.provenance,
                    cache_stale=loaded.cache_stale,
                )
                current = summarize_current(
                    prepared.history.points,
                    prepared.selected.points,
                )
                return {
                    "schema_version": "goratio-web-v1",
                    "source_id": prepared.source.source_id,
                    "as_of": current["as_of"],
                    "ratio": current,
                    "series": [
                        {
                            "date": point.date.isoformat(),
                            "ratio": point.ratio,
                        }
                        for point in prepared.selected.points[-252:]
                    ],
                    "factor": factor_snapshot(prepared),
                    "evidence": run_v2_evidence_bundle(prepared),
                    "risk_flags": (
                        ["insufficient_history"] if not prepared.evidence_eligible else []
                    ),
                }

            if args.web_command == "serve":
                serve_dashboard(
                    payload_factory=make_web_payload,
                    host=args.host,
                    port=args.port,
                )
                return 0
            payload = make_web_payload()
            html = render_dashboard_html(payload)
            if args.output:
                Path(args.output).write_text(html, encoding="utf-8")
            else:
                stdout.write(html)
                stdout.write("\n")
            if args.as_json:
                json_payload = payload
                json_payload["html_path"] = args.output
                stdout.write(json.dumps(json_payload, ensure_ascii=False, allow_nan=False) + "\n")
            return 0
        if args.command == "factor":
            loaded = loader.load(args.source, timeout=args.timeout)
            prepared = prepare_market_data(
                loaded.raw,
                period=args.period,
                completed_before=completed_before,
                provenance=loaded.provenance,
                cache_stale=loaded.cache_stale,
            )
            snapshot = (
                factor_snapshot(prepared)
                if getattr(args, "variant", "a") == "a"
                else factor_snapshot_variant_b(prepared)
            )
            payload = {
                "schema_version": "goratio-factor-v1",
                "protocol": PROTOCOL_V2_SPEC,
                "snapshot": snapshot,
            }
            if args.as_json:
                stdout.write(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                if snapshot["available"]:
                    valuation = snapshot.get("factors", {}).get(
                        "F1_valuation", snapshot.get("valuation")
                    )
                    stdout.write(
                        f"协议：{snapshot['protocol']}（draft_preregistered）\n"
                        f"变体：{snapshot.get('variant', 'A_value_plus_trend')}\n"
                        f"数据截至：{snapshot['as_of']}\n"
                        f"F1 估值分位：{_format_number(valuation['percentile'])}"
                        f"（{valuation['zone']}）\n"
                    )
                    if "F2_trend_confirmation" in snapshot.get("factors", {}):
                        trend = snapshot["factors"]["F2_trend_confirmation"]
                        stdout.write(
                            f"F2 黄金 252 日动量：{_format_number(trend['gold_252d_momentum'])}；"
                            f"比值 252 日动量：{_format_number(trend['ratio_252d_momentum'])}\n"
                        )
                    if "stability" in snapshot:
                        stability = snapshot["stability"]
                        stdout.write(
                            f"结构稳定性：{stability['state']}"
                            f"（median_shift_z={_format_number(stability['median_shift_z'])}）\n"
                        )
                    stdout.write(
                        f"研究状态：{snapshot['research_state']}\n"
                        f"注意：这是预注册研究状态，不是买入/卖出建议\n"
                    )
                else:
                    stdout.write(
                        f"协议：{PROTOCOL_V2_SPEC['id']}；当前状态不可用：{snapshot['reason']}\n"
                    )
            return 0
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
        if args.command == "tradability":
            report = build_tradability_report(
                loaded.raw,
                prepared,
                usd_cny=getattr(args, "usdcny", None),
            )
            if args.as_json:
                stdout.write(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                current = report.get("current_expression")
                expression = current["cl_contracts_per_one_gc_notional"] if current else None
                stdout.write(
                    f"数据来源：{report['source_name']}（{report['source_id']}）\n"
                    f"合约规格：黄金 1 手 {report['contracts']['gold']['contract_multiplier']} 盎司；"
                    f"原油 1 手 {report['contracts']['oil']['contract_multiplier']} 桶\n"
                    f"当前比值名义对应：1 手 GC ≈ {_format_number(expression)} 手 CL（含小数，非真实整数手）\n"
                    f"负油价事件数：{len(report['negative_price_events'])} 个；"
                    f"USD/CNY 数据已加载：{report['renminbi_disclosure']['usdcny_data_loaded']}\n"
                    f"局限：未提供真实换月日历/持仓量/开盘价，详见 JSON\n"
                )
            return 0
        if args.command == "backtest":
            report = run_episode_cost_backtest(
                prepared,
                horizon=args.horizon,
                round_trip_cost_bps=args.cost_bps,
                t1_close_execution=getattr(args, "t1_close", False),
                roll_cost_bps=getattr(args, "roll_cost_bps", 0.0),
            )
            if args.as_json:
                stdout.write(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                stdout.write(
                    f"数据来源：{prepared.source.name}（{prepared.source.source_id}）\n"
                    f"期限：{args.horizon} 共同交易日；往返成本：{args.cost_bps} bps\n"
                    f"交易数：{report['trade_count']}；平均净收益："
                    f"{_format_number(report['metrics']['mean_net_return'])}\n"
                    f"风险门控：最小交易数通过={report['risk_gates']['minimum_trade_count_passed']}，"
                    f"成本后正收益通过={report['risk_gates']['cost_adjusted_positive_passed']}\n"
                    f"风险标记：{', '.join(report['risk_flags']) or '无'}\n"
                    f"说明：诊断回测，非冻结协议证据；不构成投资建议\n"
                )
            return 0
        if args.command == "episode-study":
            study = run_episode_evidence_bundle(prepared)
            if args.as_json:
                stdout.write(
                    json.dumps(
                        study,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                stdout.write(
                    f"数据来源：{prepared.source.name}（{prepared.source.source_id}）\n"
                    f"episode 级样本外事件研究诊断（协议 v2 前置）\n"
                )
                for horizon, report in study["horizons"].items():
                    out = report["out_of_sample"]["conditional_episodes"]
                    stdout.write(
                        f"  {horizon} 交易日：样本外 episode {out['sample_count']} 个；"
                        f"均值 {_format_number(out['mean'])}；"
                        f"结论 {report['evidence_status']}\n"
                    )
            return 0
        if args.command == "stress":
            report = tail_stress_report(loaded.raw, prepared)
            if args.as_json:
                stdout.write(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                stdout.write(
                    f"分析窗口：{report['analysis_window']['first']} 至 "
                    f"{report['analysis_window']['last']}\n"
                    f"非正价格事件数：{report['non_positive_event_count']}\n"
                )
                for event in report["events"]:
                    stdout.write(
                        f"  {event['date']} {event['symbol']} close={event['close']} "
                        f"in_window={event['in_analysis_window']}\n"
                    )
            return 0
        if args.command == "overview":
            report = generate_v2_overview(prepared)
            if args.as_json:
                stdout.write(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                ov = report["overview"]
                stdout.write(
                    f"协议：{report['protocol']}；总体状态：{ov['overall_status']}\n"
                )
            return 0
        if args.command == "formal":
            report = generate_v2_formal_report(
                prepared,
                cost_bps=args.cost_bps,
                roll_cost_bps=args.roll_cost_bps,
            )
            if args.as_json:
                stdout.write(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                stdout.write(
                    f"协议：{report['protocol']}；总体状态：{report['overall_status']}\n"
                )
                for horizon, status in report["horizon_status"].items():
                    stdout.write(f"  {horizon} 交易日：{status}\n")
            return 0
        if args.command == "evidence":
            report = run_v2_evidence_bundle(
                prepared,
                cost_bps=args.cost_bps,
                roll_cost_bps=getattr(args, "roll_cost_bps", 0.0),
            )
            if args.as_json:
                stdout.write(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                stdout.write(
                    f"协议：{report['protocol']}；成本后 episode 组合门槛\n"
                )
                for horizon, result in report["horizons"].items():
                    stdout.write(
                        f"  {horizon} 交易日：{result['evidence_status']}；"
                        f"OOS {result['gates']['out_of_sample_episode_count']} 个\n"
                    )
            return 0
        if args.command == "episode":
            episodes = build_forward_episodes(
                prepared.history.points,
                prepared.selected.points,
                horizon=args.horizon,
            )
            summary = summarize_episode_research(
                prepared.history.points,
                prepared.selected.points,
                horizon=args.horizon,
            )
            split_date = chronological_split_date(prepared.selected.points)
            split = split_episode_counts(
                episodes,
                split_date=split_date,
                horizon=args.horizon,
            )
            payload = {
                "schema_version": "goratio-episode-v1",
                "protocol_version": "diagnostic-not-preregistered",
                "as_of": prepared.selected.points[-1].date.isoformat(),
                "source_id": prepared.source.source_id,
                "period": prepared.requested_period,
                "observation_count": prepared.observation_count,
                "split": split,
                "episode_study": summary,
            }
            if args.as_json:
                stdout.write(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            else:
                daily = summary["daily_low_state_event_count"]
                episode_count = summary["episode_count"]
                mean_episode = summary["episode_returns"]["mean"]
                stdout.write(
                    f"数据来源：{prepared.source.name}（{prepared.source.source_id}）\n"
                    f"实际共同样本：{prepared.actual_period[0]} 至 {prepared.actual_period[1]}；"
                    f"{prepared.observation_count} 条\n"
                    f"期限 {args.horizon} 共同交易日：日频低状态事件 {daily} 个；"
                    f"压缩为 episode {episode_count} 个\n"
                    f"episode 平均远期收益：{_format_number(mean_episode)}；"
                    f"样本外 episode {split['out_of_sample_episodes']} 个\n"
                    f"说明：episode 诊断尚未预注册为正式证据协议\n"
                )
            return 0
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
