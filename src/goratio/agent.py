"""只读 Agent 边界：MCP 兼容服务器与 SKILL 渲染。

设计约束：
- MCP 工具只读取本地缓存与协议结果，不会发起在线请求，也不会写缓存。
- SKILL 是给 Agent 的约束手册，不是交易策略。
- 任何输出都必须保留协议版本、数据质量、风险标记和免责声明。
"""

import json
import sys
from datetime import date
from typing import Any, Mapping, Optional, TextIO

from .cache import CacheError, DataLoader, LoadedData
from .dataset import prepare_market_data
from .plugins import PLUGIN_API_VERSION
from .protocol_v2 import build_protocol_list
from .reporting import DISCLAIMER, build_result
from .research import run_research


MCP_API_VERSION = "goratio-mcp-v1"
SOURCES = ("cn_public", "yahoo_futures")
PERIODS = ("3y", "5y", "10y")

TOOL_SCHEMA_SOURCE = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "enum": list(SOURCES),
            "default": "cn_public",
            "description": "只读取本地缓存中的来源，不触发在线获取。",
        },
        "period": {
            "type": "string",
            "enum": list(PERIODS),
            "default": "5y",
            "description": "展示/研究周期。",
        },
    },
}

TOOLS = (
    {
        "name": "get_data_quality",
        "description": "读取本地缓存中的来源与数据质量审计。不会访问在线接口。",
        "inputSchema": TOOL_SCHEMA_SOURCE,
    },
    {
        "name": "get_ratio_snapshot",
        "description": "读取当前金油比、滚动中枢、偏离度与历史分位。不会访问在线接口。",
        "inputSchema": TOOL_SCHEMA_SOURCE,
    },
    {
        "name": "run_research_protocol",
        "description": "对本地缓存运行冻结协议并返回证据状态。不会访问在线接口，不会写缓存。",
        "inputSchema": TOOL_SCHEMA_SOURCE,
    },
    {
        "name": "get_risk_flags",
        "description": "返回当前研究中的风险标记与数据质量提示。",
        "inputSchema": TOOL_SCHEMA_SOURCE,
    },
    {
        "name": "list_protocols",
        "description": "列出当前已冻结的研究协议版本。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
)


def render_skill(fmt: str = "markdown") -> str:
    if fmt != "markdown":
        raise ValueError("format 暂只支持 markdown")
    return _SKILL_MARKDOWN


_SKILL_MARKDOWN = """# goratio 研究代理 SKILL（中国大陆用户版）

你是一个只读研究代理，帮助用户理解 `goratio` 的金油比历史统计结果。

## 行为准则

1. 先执行 `list_protocols` 与 `get_data_quality`，确认协议版本、数据来源、缓存新鲜度和质量状态。
2. 只能引用已冻结协议中的结论；不得自行发明新窗口、新阈值或“更准”的统计规则。
3. 不提供买入、卖出、仓位或收益承诺。你可以描述“研究触发状态”“统计支持”“数据不足”，但不能把统计结果转述成操作指令。
4. 输出必须包含：数据来源、实际样本期、协议版本、数据质量、风险标记和免责声明。
5. 如果证据状态是 `insufficient_data` 或 `not_supported`，必须原样保留，不得用叙事补全为机会。
6. 如果数据来自本地缓存，要说明没有发起新的在线请求；若缓存陈旧，应提示用户通过 CLI `goratio update` 刷新。
7. 默认用简体中文回答。面向中国大陆用户时，不假设用户可稳定访问海外数据源。
8. 不要替用户做最终决策；可以列出“支持这种判断的证据”与“反对这种判断的证据”。

## 工具使用顺序建议

1. `list_protocols`
2. `get_data_quality(source="cn_public")`
3. `get_ratio_snapshot(source="cn_public")`
4. 需要完整证据时调用 `run_research_protocol(source="cn_public", period="10y")`
5. 最后总结 `get_risk_flags`

## 免责声明

{disclaimer}
""".format(disclaimer=DISCLAIMER)


def _cached_build(
    loader: DataLoader,
    source: str = "cn_public",
    period: str = "5y",
    *,
    include_research: bool = False,
    completed_before: Optional[date] = None,
):
    """只从本地缓存构建可序列化结果；不访问在线接口。"""
    if source not in SOURCES:
        raise ValueError(f"source 必须是 {', '.join(SOURCES)}")
    if period not in PERIODS:
        raise ValueError(f"period 必须是 {', '.join(PERIODS)}")
    cached = loader.cache.load(source)
    loaded = LoadedData(
        raw=cached.raw,
        provenance="cache",
        cache_origin=cached.provenance,
        cache_age_hours=cached.age_hours,
        cache_stale=cached.stale,
        snapshot_sha256=cached.snapshot_sha256,
        warnings=(
            (
                f"只读 Agent 未发起在线请求；缓存由 {cached.provenance} 写入"
                if cached.provenance != "online"
                else "只读 Agent 未发起在线请求；缓存来自最近一次在线更新"
            ),
        ),
    )
    prepared = prepare_market_data(
        cached.raw,
        period=period,
        completed_before=completed_before or date.today(),
        provenance="cache",
        cache_stale=cached.stale,
    )
    research = run_research(prepared) if include_research else None
    return build_result(loaded, prepared, research=research)


def _content_text(payload: Mapping[str, Any]) -> dict:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                ),
            }
        ]
    }


def _tool_result(payload: Mapping[str, Any]) -> dict:
    return {"content": _content_text(payload)["content"], "isError": False}


def _tool_error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def invoke_tool(
    loader: DataLoader,
    name: str,
    arguments: Optional[Mapping[str, Any]] = None,
    *,
    completed_before: Optional[date] = None,
):
    args = dict(arguments or {})
    source = args.get("source", "cn_public")
    period = args.get("period", "5y")
    try:
        if name == "list_protocols":
            payload = {
                "api_version": PLUGIN_API_VERSION,
                "protocols": build_protocol_list(),
            }
        elif name in {"get_data_quality", "get_ratio_snapshot", "run_research_protocol", "get_risk_flags"}:
            if name == "run_research_protocol":
                result = _cached_build(
                    loader,
                    source=source,
                    period=period,
                    include_research=True,
                    completed_before=completed_before,
                )
            else:
                result = _cached_build(
                    loader,
                    source=source,
                    period=period,
                    include_research=name == "get_risk_flags",
                    completed_before=completed_before,
                )
            if name == "get_data_quality":
                payload = {
                    "source_id": result["source"]["id"],
                    "as_of": result["as_of"],
                    "data_quality": result["data_quality"],
                    "method_limitations": result["method_limitations"],
                }
            elif name == "get_ratio_snapshot":
                payload = {
                    "source_id": result["source"]["id"],
                    "as_of": result["as_of"],
                    "ratio": result["ratio"],
                    "risk_flags": result["risk_flags"],
                }
            elif name == "get_risk_flags":
                payload = {
                    "source_id": result["source"]["id"],
                    "as_of": result["as_of"],
                    "risk_flags": result["risk_flags"],
                    "evidence_status": result["evidence_status"],
                    "method_limitations": result["method_limitations"],
                }
            else:
                payload = {
                    "source_id": result["source"]["id"],
                    "as_of": result["as_of"],
                    "protocol_version": result["protocol_version"],
                    "schema_version": result["schema_version"],
                    "evidence_status": result["evidence_status"],
                    "mean_reversion": result["mean_reversion"],
                    "stability_diagnostic": result["stability_diagnostic"],
                    "conditional_forward_returns": result["conditional_forward_returns"],
                    "replication": result["replication"],
                    "unpassed_hypotheses": result["unpassed_hypotheses"],
                    "risk_flags": result["risk_flags"],
                    "method_limitations": result["method_limitations"],
                    "disclaimer": result["disclaimer"],
                }
        else:
            raise ValueError(f"未知只读工具: {name}")
        return _tool_result(payload)
    except (CacheError, ValueError, Exception) as exc:  # noqa: BLE001 - MCP boundary returns JSON error
        return _tool_error(f"tool_error: {exc}; 如需在线数据请使用 goratio update 后再查询缓存。")


def _error_response(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def mcp_handle_message(
    message: Mapping[str, Any],
    loader: DataLoader,
    *,
    completed_before: Optional[date] = None,
):
    """处理单条 MCP/JSON-RPC 消息；通知类返回 None。"""
    if not isinstance(message, Mapping):
        return _error_response(None, -32600, "invalid request")
    request_id = message.get("id")
    method = message.get("method")
    if not isinstance(request_id, (str, int)) or request_id is True:
        # Notifications may omit id; notifications are not responded.
        if method is not None and method.startswith("notifications/"):
            return None
        return _error_response(None, -32600, "request id must be string or number")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {},
                },
                "serverInfo": {"name": "goratio-readonly", "version": MCP_API_VERSION},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": list(TOOLS)}}
    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": []}}
    if method == "tools/call":
        params = message.get("params") or {}
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if tool_name not in {tool["name"] for tool in TOOLS}:
            return _error_response(request_id, -32602, f"unknown tool: {tool_name}")
        result = invoke_tool(loader, tool_name, arguments, completed_before=completed_before)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    return _error_response(request_id, -32601, f"method not found: {method}")


def serve(
    loader: DataLoader,
    *,
    stdin: TextIO = None,
    stdout: TextIO = None,
) -> None:
    """运行只读 MCP stdio 服务器。

    MCP stdio transport 在本实现中按行读取 JSON-RPC 消息；不会发起在线数据请求。
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            stdout.write(
                json.dumps(_error_response(None, -32700, f"parse error: {exc}"), ensure_ascii=False)
                + "\n"
            )
            stdout.flush()
            continue
        response = mcp_handle_message(message, loader)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()

