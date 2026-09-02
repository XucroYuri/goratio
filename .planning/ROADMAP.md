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
- [ ] 将合约级主力链自动用于 `backtest` 的真实换月收益计算。
- [x] T+1 close 执行近似已加入 `backtest --t1-close`（仍非 open/settle，真实缺口待合约数据接入）。
- [ ] 真实换月成本与 T+1 open/settle 执行缺口。
- [ ] 负油价/危机尾部事件接入回测与 protocol v2。
- [x] 人民币披露层支持可选 `--usdcny` 换算（未自动接入数据源，仍需调用方提供汇率）。
- [ ] Episode v2 的正式预注册证据门槛（已具备 episode 样本、OOS 门槛、95%/98.33% bootstrap 差值区间）。
- [ ] 双因子 v2 的 episode 级样本外证据门槛与成本后回测。
- [ ] 从诊断回测升级为真实合约级回测：换月、保证金、市场冲击、T+1 open/settle。
- [ ] 预注册正式成本后回测门槛与家族检验。
- [ ] 只读 Web 工作台（最后）。

## 验证

当前测试：`PYTHONPATH=src python3 -m unittest discover -s tests -v`

当前通过：78 tests OK。
