"""只读插件白名单与静态插件清单。

MVP 阶段不提供任意动态加载。插件只能作为已冻结边界内的可扩展点出现：
数据源、预注册协议、报告器、Agent 工具和 SKILL。任何能改变研究结论的
插件（新因子、新窗口、新阈值）必须先进入新协议版本，不允许在运行时注入。
"""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

PLUGIN_API_VERSION = "goratio-plugin-v1"

KINDS = ("data_source", "protocol", "reporter", "agent_tool", "skill")


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    kind: str
    name: str
    version: str
    read_only: bool
    description: str
    entry: str

    def to_dict(self):
        return {
            "plugin_id": self.plugin_id,
            "kind": self.kind,
            "name": self.name,
            "version": self.version,
            "read_only": self.read_only,
            "description": self.description,
            "entry": self.entry,
        }


# 当前可被项目承认的插件清单。不在白名单中的名称即使出现在环境中也忽略。
PLUGIN_WHITELIST = (
    PluginManifest(
        plugin_id="cn_public_data_source",
        kind="data_source",
        name="新浪财经 GC/CL 连续期货日线",
        version="0.1.0",
        read_only=False,
        description="内置默认中国大陆可直连来源；只获取数据并写入本地缓存。",
        entry="goratio.providers:SinaProvider",
    ),
    PluginManifest(
        plugin_id="yahoo_futures_data_source",
        kind="data_source",
        name="Yahoo Finance GC=F/CL=F 日线",
        version="0.1.0",
        read_only=False,
        description="用户显式选择后才访问的海外来源。",
        entry="goratio.providers:YahooProvider",
    ),
    PluginManifest(
        plugin_id="evidence_baseline_1a",
        kind="protocol",
        name="第一阶段 1A 证据基线协议",
        version="goratio-1a-v1",
        read_only=True,
        description="已冻结统计协议：均值回归、结构变化、条件远期收益与跨来源复现。",
        entry="goratio.research:run_research",
    ),
    PluginManifest(
        plugin_id="dual_factor_v2_protocol",
        kind="protocol",
        name="双因子 v2 预注册协议草案",
        version="goratio-2a-v1",
        read_only=True,
        description="F1 滚动 5 年估值分位 + F2 黄金 252 日动量确认；状态为 draft_preregistered。",
        entry="goratio.protocol_v2:factor_snapshot",
    ),
    PluginManifest(
        plugin_id="episode_study_diagnostic",
        kind="reporter",
        name="Episode 级样本外事件研究诊断器",
        version="goratio-episode-study-v1",
        read_only=True,
        description="输出 63/126/252 期限的 episode OOS 门槛诊断；未包含完整自助与多重检验。",
        entry="goratio.episode_study:run_episode_evidence_bundle",
    ),
    PluginManifest(
        plugin_id="episode_cost_backtest_diagnostic",
        kind="reporter",
        name="成本后 Episode 回测与风控门控诊断器",
        version="goratio-backtest-v1",
        read_only=True,
        description="输出 episode 交易级净收益、回撤和最小风控门控；不作为冻结协议证据。",
        entry="goratio.backtest:run_episode_cost_backtest",
    ),
    PluginManifest(
        plugin_id="strict_json_reporter",
        kind="reporter",
        name="严格 JSON/中文文本报告器",
        version="goratio-result-v1",
        read_only=True,
        description="输出无 NaN/Infinity、含来源与协议版本的机器可读报告。",
        entry="goratio.reporting:build_result",
    ),
    PluginManifest(
        plugin_id="read_only_mcp_tools",
        kind="agent_tool",
        name="只读 MCP 工具集",
        version="goratio-mcp-v1",
        read_only=True,
        description="通过 MCP 暴露缓存数据的只读查询与协议结果；不访问在线接口，不写缓存。",
        entry="goratio.agent:TOOLS",
    ),
    PluginManifest(
        plugin_id="zh_cn_agent_skill",
        kind="skill",
        name="中国大陆用户中文研究代理 SKILL",
        version="goratio-skill-v1",
        read_only=True,
        description="约束 Agent 先查数据质量与协议版本，只陈述事实并保留风险与不确定性。",
        entry="goratio.agent:render_skill",
    ),
)


def whitelisted_plugins(kind: Optional[str] = None) -> Tuple[PluginManifest, ...]:
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind 必须是 {', '.join(KINDS)}")
    if kind is None:
        return PLUGIN_WHITELIST
    return tuple(plugin for plugin in PLUGIN_WHITELIST if plugin.kind == kind)


def list_plugins(
    kind: Optional[str] = None,
) -> Sequence[dict]:
    """返回可 JSON 序列化的白名单插件列表。"""
    return [plugin.to_dict() for plugin in whitelisted_plugins(kind)]


def get_plugin(plugin_id: str) -> PluginManifest:
    for plugin in PLUGIN_WHITELIST:
        if plugin.plugin_id == plugin_id:
            return plugin
    raise KeyError(f"plugin_id 不在白名单中: {plugin_id}")


def is_whitelisted(plugin_id: str) -> bool:
    try:
        get_plugin(plugin_id)
        return True
    except KeyError:
        return False
