# goratio 后续迭代路线（Round 工作记录）

目标：

1. 守住极简与只读边界：CLI + MCP + SKILL 薄接口，插件白名单；
2. 解决可交易性：合约级数据、换月成本、T+1 执行、负油价与人民币换算披露；
3. 用 episode 而不是日频状态重做事件研究；
4. 预注册双因子 v2：价值 + 趋势确认，或机会 + 结构稳定性；
5. 跑通成本后回测和风控门控；
6. 最后再做 Web 工作台。

## 当前状态

### 已完成（持续开发中）

- [x] 静态插件白名单 `plugins.py`，不提供动态加载。
- [x] 只读 MCP JSON-RPC 薄服务 `agent.py`：仅读本地缓存，不访问在线接口。
- [x] CLI 子命令：`plugin list`、`mcp serve`、`skill render`。
- [x] SKILL 约束手册，限制 Agent 只引用冻结协议、保留风险与数据不足。
- [x] README / CHANGELOG 更新。
- [x] Episode 级低分位事件压缩与 `episode` 诊断命令。
- [x] 可交易性诊断 `tradability`：合约规格、执行缺口代理、负油价审计、人民币披露层框架。
- [x] 双因子 v2 预注册协议草案 `goratio-2a-v1` 与 `factor status` 命令（变体 A/B 均已实现）。
- [x] 成本后 episode 回测与风控门控诊断 `backtest` 命令。
- [x] 双因子 v2 变体 B：无前视在线结构稳定性因子 `regime.py` 与 `factor status --variant b`。
- [x] Episode 级样本外事件研究诊断 `episode-study` 命令（63/126/252）。

### 待下一轮

- [x] 合约级数据模型、按 OI/成交量选主力与换月事件检测（`contracts.py`）。
- [x] 合约级 CSV 可由 `contracts inspect` 读取并输出换月事件。
- [x] 合约级 CSV 可桥接为 `RawMarketData` 并进入 `prepare_market_data`。
- [x] 合约级主力链可生成换月无跳空的连续收益序列 `build_roll_adjusted_series()`。
- [x] 合约 CSV 可 `roll_adjusted=True` 桥接为 RawMarketData，供跨换月收益序列进入研究管线。
- [x] `contracts backtest` 可将合约级 CSV 桥接后直接运行 episode 成本回测。
- [x] `roll_aware_contract_return()` 已提供显式换月结算/重开仓的合约链收益验证入口。
- [x] `contract_episode_return_summary()` 可对 episode 批量对比连续收益与真实换月收益。
- [x] 保证金/名义敞口估算已加入 `margin.py` 与 `tradability` 报告。
- [x] `position_pnl_estimate()` 已提供真实主力链持仓保证金与 P&L 估算。
- [x] `run_position_simulation()` 已支持对一组 episode 批量运行持仓估算。
- [x] `batch_equity_summary()` 已提供简单资金曲线摘要。
- [x] `margin_utilization_summary()` 已提供批量持仓保证金占用率统计。
- [ ] 在完整组合持仓/资金引擎中接入逐日保证金监控。
- [x] T+1 close 执行近似已加入 `backtest --t1-close`（仍非 open/settle，真实缺口待合约数据接入）。
- [x] `summarize_roll_costs()` 已提供合约级可量化换月 gap 成本统计。
- [x] 真实换月 gap 成本可作为 `--roll-cost-bps` 附加到 `backtest`/`evidence`。
- [x] 合约级模型已支持可选 `open`/`settle` 字段。
- [x] `t1_open_settle_gap()` 已支持基于 open/settle 字段计算 T+1 执行缺口。
- [x] `contract_episode_return_summary()` 已输出每笔 episode 的 T+1 open gap。
- [x] episode 摘要已输出扣减 T+1 open gap 的多头真实换月净收益。
- [ ] 将 T+1 open/settle 执行缺口作为默认成交模型接入回测。
- [x] `stress` 命令可诊断负油价/零价事件是否落入研究窗口并标注 v2 处理要求。
- [ ] 负油价/危机尾部事件进一步接入真实回测压力场景与 protocol v2。
- [x] 人民币披露层支持可选 `--usdcny` 换算（未自动接入数据源，仍需调用方提供汇率）。
- [x] `evidence_gates`：协议 v2 组合门槛已落地（episode OOS、98.33% 家族区间、成本后正收益、回撤门控）。
- [x] `evidence` CLI 已接入 `evidence_gates`。
- [x] `formal_v2.generate_v2_formal_report()` 已作为正式验收报告入口。
- [ ] 完成外部评审/日期戳后的正式冻结验收流程。
- [ ] 输出双因子 v2 的 episode 级正式样本外成本后检验报告文档。
- [ ] 从诊断回测升级为真实合约级回测：换月、保证金、市场冲击、T+1 open/settle。
- [ ] 正式预注册成本后回测门槛与家族检验（已具备模块入口）。
- [x] 只读 Web 工作台开始落地：`web export` 本地自包含 HTML。
- [x] `web serve` 可启动只读本地 HTTP 服务；仍不提供交易指令。
- [x] Web 工作台已加入近期金油比 SVG 走势图。
- [x] `web serve` 页面已支持 60 秒自动刷新。
- [ ] 后续可增加更多研究工作台模块与事件流刷新。

## 验证

当前测试：`PYTHONPATH=src python3 -m unittest discover -s tests -v`

当前通过：100 tests OK。
