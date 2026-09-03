# 变更日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构，并使用 [语义化版本](https://semver.org/lang/zh-CN/)。候选版本的命令行和 JSON 契约仍可能在正式版前调整。

## [Unreleased]

### 新增

- 静态插件白名单与只读 Agent 薄接口；
- `plugin list`、`mcp serve`、`skill render` 子命令；
- 无第三方依赖的只读 MCP JSON-RPC 服务；
- Agent SKILL 约束手册，限制只引用冻结协议、保留风险和数据不足；
- Episode 级低分位事件压缩与 `episode` 诊断命令；
- 可交易性诊断模块与 `tradability` 命令：合约规格、执行缺口代理、负油价审计、人民币披露；
- 双因子 v2 预注册协议草案 `goratio-2a-v1` 与 `factor status` 命令；
- 成本后 episode 回测与风控门控诊断 `backtest` 命令；
- 双因子 v2 变体 B：无前视在线结构稳定性因子 `regime.py` 与 `factor status --variant b`；
- Episode 级样本外事件研究诊断模块与 `episode-study` 命令；
- Episode v2 前置证据加入 95%/98.33% 差值 bootstrap 区间与家族门槛；
- 合约级数据模型与换月日历模块 `contracts.py`；
- CLI 子命令 `contracts inspect`：读取标准合约 CSV 并输出主力链/换月事件；
- `contract_csv_to_raw_market_data`：将合约级 CSV 桥接到现有研究/回测管线；
- `tradability --usdcny`：人民币计价披露层支持传入 USD/CNY，不进入核心因子；
- `backtest --t1-close`：成本后 episode 回测支持 T+1 共同交易日收盘价执行近似；
- `build_roll_adjusted_series()`：合约级主力链换月无跳空连续收益序列；
- `contract_csv_to_raw_market_data(..., roll_adjusted=True)`：直接生成换月无跳空调整的 RawMarketData；
- `stress` 命令：负油价/零价危机尾部事件接入状态诊断；
- `evidence_gates`：协议 v2 成本后 episode 级组合证据门槛；
- `evidence` CLI 命令：直接运行双因子 v2 成本后组合门槛；
- `summarize_roll_costs()`：合约级换月 gap 成本统计；
- `web export`：只读本地 HTML 研究工作台导出；
- `web serve`：只读本地 HTTP 研究工作台；
- Web 工作台增加近期金油比 SVG 走势图；
- `web serve` 页面默认 60 秒自动刷新；
- `backtest`/`evidence` 支持 `--roll-cost-bps` 附加换月价差成本；
- `contracts backtest`：从合约级 CSV 直接运行 episode 成本回测；
- `roll_aware_contract_return()`：真实主力合约链含换月结算的持有期收益计算；
- `contract_episode_return_summary()`：episode 连续收益与真实换月收益对比验证；
- 合约 CSV/记录支持可选 `open` 与 `settle` 字段，为 T+1 open/settle 执行缺口打基础；
- `t1_open_settle_gap()`：计算信号日收盘到下一交易日 open/settle 的执行缺口；
- `contract_episode_return_summary()` 增加 T+1 open gap 统计；
- `contract_episode_return_summary()` 增加扣减 T+1 open gap 的多头真实换月净收益；
- `margin.py` 与 `tradability` 保证金/名义敞口估算；
- `position_pnl_estimate()`：真实主力链持仓保证金与换月 P&L 估算；
- `run_position_simulation()`：对一组 episode 批量运行真实主力链持仓估算；
- `batch_equity_summary()`：基于批量模拟生成简单资金曲线摘要；
- `formal_v2.generate_v2_formal_report()`：协议 v2 正式验收前的可审计报告入口；
- `margin_utilization_summary()`：批量持仓保证金占用率统计；
- `formal` CLI：输出双因子 v2 正式验收前报告；
- `run_daily_position_mark()`：单笔持仓逐日盯市与保证金占用估算；
- `portfolio_daily_margin()`：多笔持仓逐日合并盯市与保证金监控；
- `check_portfolio_constraints()`：组合级保证金占用与回撤风控门控；
- `financing_cost_estimate()`：保证金资金成本估算；
- `position_pnl_estimate()` 增加资金成本与净 P&L 估算；
- `summarize_batch_portfolio()`：批量 episode → 持仓模拟 → 资金/保证金高层汇总；
- `contracts portfolio` CLI：从合约 CSV 直接运行批量持仓高层汇总。

## [0.1.0-rc1] - 2026-09-02

### 新增

- 新浪财经 `GC` / `CL` 默认来源与显式启用的 Yahoo Finance 期货来源；
- 自有 CSV 导入、本地原子缓存、摘要校验与在线失败降级；
- 数据质量审计、共同交易日内连接、滚动 5 年中枢及全周期参考；
- 冻结的均值回归、结构稳定性、条件远期收益和跨来源复现协议；
- `now`、`analyze`、`update` 命令及严格 JSON 输出；
- Python 3.11–3.14、macOS、Windows、包构建和 CodeQL 自动门禁；
- 数据来源、贡献、安全、行为准则和引用文档。

### 已知限制

- 在线接口没有可用性承诺，且服务商条款与返回格式可能变化；
- 仓库不分发原始价格快照，因此未来下载不保证逐字节复现；
- 当前公开基线发现结构不稳定，样本外低分位事件不足，未形成方向性结论。

[0.1.0-rc1]: https://github.com/XucroYuri/goratio/releases/tag/v0.1.0-rc1
