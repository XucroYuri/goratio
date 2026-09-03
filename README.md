# goratio

[![CI](https://github.com/XucroYuri/goratio/actions/workflows/ci.yml/badge.svg)](https://github.com/XucroYuri/goratio/actions/workflows/ci.yml)
[![CodeQL](https://github.com/XucroYuri/goratio/actions/workflows/codeql.yml/badge.svg)](https://github.com/XucroYuri/goratio/actions/workflows/codeql.yml)
[![GitHub Release](https://img.shields.io/github/v/release/XucroYuri/goratio?include_prereleases)](https://github.com/XucroYuri/goratio/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/XucroYuri/goratio/blob/main/LICENSE)

`goratio` 是一个可复现的金油比价历史统计与概率分析 CLI。它把黄金与 WTI 原油连续期货按共同交易日对齐，展示滚动中枢，并按冻结协议执行均值回归、结构稳定性和条件远期收益研究。

项目的目标是检验假设，而不是证明某个结论。结果为零、反向、不稳定或数据不足时都会原样保留。

> 仅供历史统计研究与方法复现，不构成投资建议。项目不提供方向性交易指令、仓位计算或收益承诺。

## 当前范围

第一阶段 1A 已实现：

- 默认大陆可直连的 `cn_public` 同源 GC/CL 日线；
- 用户明确选择后才访问的 `yahoo_futures`；
- 标准 CSV 导入、本地原子缓存、SHA-256 完整性校验和在线失败降级；
- 日期、缺失、重复、非有限值、非正价格、异常候选与错位交易日审计；
- 3/5/10 年展示周期、5 年滚动中位数、经验分位和偏离度；
- 预注册 ADF(1)、单均值断点 Sup-F 诊断和 63/126/252 交易日事件研究；
- 70/30 时间顺序切分、边界标签清除、移动区块自助置信区间；
- 客观文本输出、严格 JSON 契约和可证伪研究报告。

宏观原因归因、图表、告警、交易回测、动态插件加载不在 1A 范围内；当前在 1A 之外新增了静态插件白名单与只读 MCP/SKILL 薄接口，详见下文。完整冻结规范见 [01-SPEC.md](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/.planning/phases/01-evidence-baseline/01-SPEC.md)，本次公开实证见 [01-RESULTS.md](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/.planning/phases/01-evidence-baseline/01-RESULTS.md)。

## 安装

需要 Python 3.11 或更高版本，无运行时第三方依赖。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
goratio --version
```

也可以不安装，直接在仓库根目录运行：

```bash
PYTHONPATH=src python3 -m goratio --version
```

## 快速使用

默认来源为 `cn_public`，默认周期为 `5y`：

```bash
goratio now
goratio now --period 10y --json
goratio analyze --period 5y
goratio analyze --period 10y --json
goratio update --source cn_public
```

Yahoo 仅在命令中明确选择时访问：

```bash
goratio now --source yahoo_futures --period 5y
goratio update --source yahoo_futures
```

若 Yahoo 出现超时、限流或空响应，CLI 会说明海外网络与代理排障方向，并尝试该来源的本地缓存。程序不会静默切换来源。需要代理时，可按本机环境配置 `HTTPS_PROXY` 后重试；不要把凭据写入仓库。

## 插件、MCP 与 SKILL（只读 MVP）

MVP 只提供静态插件白名单，不提供任意动态加载。插件列表可以被审计，插件不能修改已冻结协议：

```bash
goratio plugin list
goratio plugin list --kind agent_tool --json
```

只读 MCP 服务按行读取 JSON-RPC 消息，只查询本地缓存，不发起在线请求，也不写缓存：

```bash
goratio update --source cn_public
goratio mcp serve
```

Agent 可调用的只读工具包括 `get_data_quality`、`get_ratio_snapshot`、`run_research_protocol`、`get_risk_flags` 和 `list_protocols`。MCP 输出不包含交易指令。

SKILL 是给 Agent 的约束手册，用于限制其只引用冻结协议、保留数据不足与风险、避免生成投资建议：

```bash
goratio skill render
```

## Episode 级事件诊断

1A 的 H3 事件研究按日频状态计数；同一段低分位区间会产生大量重叠样本。作为协议 v2 的前置诊断，`episode` 命令先把连续低分位状态压缩成 episode：

```bash
goratio episode --period 10y --horizon 126
goratio episode --period 10y --horizon 252 --json
```

该命令输出日频低状态事件数、episode 数、每个 episode 的平均收益和 70/30 切分下的样本外 episode 数。它尚未进入冻结协议，只能作为“样本独立性”诊断使用。

如需把 episode 作为事件研究样本并查看 63/126/252 三个期限的 OOS 门槛诊断：

```bash
goratio episode-study --period 10y --json
```

该命令输出每个期限的样本内/样本外 episode 数、边界清除数、episode 相对全样本基线的平均差值、95% 与 98.33% 差值区间，以及 `insufficient_data / supported / not_supported` 诊断状态。当前 bootstrap 使用 trade-level iid 近似，后续可在真实合约数据上升级为更复杂的时间依赖结构。

## 可交易性诊断

`tradability` 命令把当前数据在“能否被真实交易者执行”上的已知约束显式化：

```bash
goratio tradability --period 10y --json
goratio tradability --period 10y --json --usdcny 7.2
```

输出包括：

- GC/CL 合约乘数与名义对应关系；
- 保证金/名义敞口与真实主力链持仓 P&L 估算；
- 相邻收盘价缺口的保守代理；
- 原始数据中的负油价/零价事件列表；
- 人民币计价披露状态；
- 当前缺少的换月日历、成交量/持仓量、开盘价、官方结算价等执行要素。

若传入 `--usdcny`，会在人民币披露层输出美元金价/油价的 CNY 等价价格；该换算只用于执行/展示，不进入双因子核心。

`stress` 命令会检查原始数据中的负油价/零价事件是否落在当前研究窗口，并显式标记其不能在 log ratio 模型中正常参与：

```bash
goratio stress --period 10y --json
```

该模块仍不提供仓位建议，也不把连续期货序列伪装成真实可执行合约。

## 合约级数据模型与换月日历

为了从“连续指数”走向“真实可执行合约链”，项目新增标准合约记录模型：

```text
date,instrument,symbol,contract_month,close,volume,open_interest,open,settle
```

`contracts` 模块可以：

- 解析标准合约记录；
- 按成交量/持仓量选择主力合约；
- 自动检测换月事件；
- 输出换月日期、新旧合约与同日的换月价差（bps）；
- 汇总可量化换月 gap 的均值/中位数/最大值成本统计。

当前内置在线来源仍未提供这些字段，因此该模块是后续接入官方结算/合规合约数据源的接口地基，不会把已有连续序列伪装成真实合约。

可用 CLI 检查自有合约级 CSV：

```bash
goratio contracts inspect --csv /path/to/contracts.csv --json
goratio contracts backtest --csv /path/to/contracts.csv --roll-adjusted --json
```

同一份合约 CSV 也可桥接为现有研究管线可消费的 `RawMarketData`，从而用真实主力合约链而不是连续指数进入 `analyze`/`backtest` 流程。另有 `build_roll_adjusted_series()` 可把主力链调整为“换月无虚假跳空”的连续收益序列，供跨换月收益计算使用；其调整后绝对价格不能用于真实金油比水平。桥接函数也支持 `roll_adjusted=True`，直接生成带换月无跳空调整的 RawMarketData。`roll_aware_contract_return()` 则显式模拟换月结算与重开仓，可用于验证真实合约链持有期收益。`contract_episode_return_summary()` 可将一组 episode 的连续序列收益与真实换月收益对比。若合约 CSV 提供 `open`/`settle`，`t1_open_settle_gap()` 可计算信号日收盘到下一交易日 open/settle 的执行缺口；episode 对比摘要也会输出 T+1 open gap 统计，并给出扣减 open gap 后的多头真实换月净收益。

## 双因子 v2（预注册草案）

v2 以 `goratio-2a-v1` 为协议草案，先固定定义，再允许数据说话：

- F1 估值因子：滚动 5 年金油比分位；
- F2 趋势确认因子：黄金 252 个共同交易日动量；
- 低估值 + 正动量 → `positive_research_trigger`；
- 高估值 + 负动量 → `negative_research_trigger`；
- 若动量不确认，只保持观察状态。

当前输出研究状态，不构成买入/卖出建议：

```bash
goratio factor status --period 10y --json
goratio factor status --period 10y --variant b --json
```

变体 B“机会 + 结构稳定性”已加入无前视稳定性因子：使用滚动 5 年与最近 252 日的中位数漂移 `median_shift_z` 判断结构是否稳定；估值极端但结构不稳定时只报告 `*_structure_unstable`，不生成研究触发。

## 成本后 episode 回测与风控门控诊断

`backtest` 先把低分位状态压缩成 episode，再只保留符合 v2 趋势确认的交易，并扣除单次往返成本：

```bash
goratio backtest --period 10y --horizon 126 --cost-bps 20 --json
goratio backtest --period 10y --horizon 126 --cost-bps 20 --t1-close --roll-cost-bps 5 --json
```

输出交易数、平均毛收益/净收益、正收益比例、累计净值最大回撤，以及最小交易数、成本后正收益、回撤上限等风控门控。加 `--t1-close` 后，以信号后一个共同交易日收盘价作为执行价，是 T+1 执行缺口在现有日线数据上的可落地近似。

当前仍是诊断回测，不是冻结协议证据；真实换月、保证金、市场冲击和 T+1 open/settle 执行缺口尚未接入。

`evidence_gates` 模块把 episode OOS 门槛、98.33% 家族区间、成本后正收益和回撤门控组合为协议 v2 的证据判断入口，用于后续正式验收前的方法闭环。CLI 可运行：

```bash
goratio evidence --period 10y --cost-bps 20 --roll-cost-bps 5 --json
```

`formal_v2.generate_v2_formal_report()` 可作为协议 v2 正式验收前的可审计报告入口，汇总三期限 status 与总体状态。

```bash
goratio formal --period 10y --cost-bps 20 --roll-cost-bps 5 --json
```

只读 Web 工作台以本地 HTML 导出形式开始落地：

```bash
goratio web export --period 10y --output dashboard.html
```

该页面包含近期金油比 SVG 走势图、当前比值、双因子状态、v2 证据门槛和风险标记；仍不包含下单或交互式交易能力。也可启动本地只读 HTTP 工作台：

```bash
goratio web serve --period 10y --host 127.0.0.1 --port 8765
```

该本地 HTTP 页面默认每 60 秒自动刷新，适合作为只读研究监控。

## 数据来源与口径

| 来源 | 黄金 | 原油 | 口径 | 启用方式 |
| --- | --- | --- | --- | --- |
| `cn_public` | 新浪全球期货 `GC` | 新浪全球期货 `CL` | 服务商拼接连续期货日收盘价 | 默认 |
| `yahoo_futures` | Yahoo `GC=F` | Yahoo `CL=F` | 服务商连续近月期货日收盘价 | 用户明确选择 |

两者均以美元计价，黄金单位为金衡盎司，原油单位为桶。两者都不是交易所官方结算数据；换月拼接、历史修订、交易日历和服务可用性可能不同。

数据处理规则固定为：

1. 去除无效日期、未完成的当日 K 线、空值、非有限值和非正价格；
2. 完全相同的重复记录折叠，冲突重复日期整日剔除；
3. 黄金与原油按共同完成的同一交易日作内连接；
4. 不做前向填充；异常对数收益只标记，不自动删除；
5. 共同有效跨度不足 1,825 天或少于 1,000 条时，只展示价格和覆盖信息，研究结论标为 `insufficient_data`。

## 自有 CSV 与缓存

标准 CSV 必须包含：

```csv
date,gold_close,oil_close
2024-01-02,2040.50,72.25
2024-01-03,2042.10,73.10
```

仓库中的 [sample-import.csv](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/examples/sample-import.csv) 是纯合成格式样例，不代表真实历史价格。导入命令：

```bash
goratio update --source cn_public --import-csv /path/to/your-owned-data.csv
```

导入记录会明确标为 `user_csv`，不会伪装成在线来源。默认缓存位于 `~/.goratio/cache`；可用 `GORATIO_CACHE_DIR` 指向其他本地目录。缓存超过 72 小时标为陈旧，但仍可在在线访问失败时用于覆盖展示，输出会保留陈旧标记。

本仓库不打包或再分发在线价格历史。只有在你有权使用数据时才应导入；LBMA 等受许可约束的历史数据不得未经许可加入仓库。

## 研究协议

协议版本固定为 `goratio-1a-v1`，共六项试验：

- H1：对数金油比的 ADF(1) 均值回归证据；
- H2：单均值断点 Sup-F 结构变化诊断；
- H3a/H3b/H3c：滚动 5 年低 20% 分位状态后的黄金 63/126/252 个共同交易日收益，相对无条件基线的差异；
- H4：跨时间段和两个同口径来源的复现。

事件研究使用前 70% / 后 30% 的时间顺序切分。标签结果跨越切分边界的样本会从样本内集合清除；滚动状态只使用当日及此前信息。均值和差值使用固定种子的移动区块自助区间，三期限结论同时要求 98.33% 家族区间通过且样本外低状态事件不少于 30 条。

结论只有三种：

- `supported`：满足预注册通过条件；
- `not_supported`：数据门槛满足，但条件未通过；
- `insufficient_data`：历史、事件数或复制来源不足。

任何新窗口、阈值或过滤器都必须进入新的研究协议版本，不能用于修饰当前结果。

## JSON 契约

`now --json` 与 `analyze --json` 至少包含：

- `schema_version`、`protocol_version`、`as_of` 和 `snapshot_sha256`；
- 来源、价格口径、标的和本地/在线 provenance；
- 请求周期、实际共同样本期、总可用期、观测数与跨度；
- 完整质量审计、错位计数、缓存新鲜度和警告；
- 当前比值、滚动中枢、偏离度、分位与全周期参考；
- 假设状态、条件远期收益、结构诊断、复制状态和未通过项；
- 风险标记、方法局限和免责声明。

JSON 使用严格有限数值；无法估计的字段为 `null`，不会输出 `NaN` 或 `Infinity`。

## 开发与验证

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m compileall -q src tests
```

测试覆盖固定快照复现、非法记录、错位交易日、短历史、陈旧缓存、摘要篡改、Yahoo 失败提示、时间顺序切分、无前瞻状态构造、JSON 契约和合规措辞。

## 参与项目

- 数据来源、接口稳定性和再分发边界见 [DATA_SOURCES.md](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/DATA_SOURCES.md)；
- 提交代码或研究协议前请阅读 [CONTRIBUTING.md](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/CONTRIBUTING.md)；
- 安全问题请按 [SECURITY.md](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/SECURITY.md) 私下报告；
- 参与项目即表示同意遵守 [CODE_OF_CONDUCT.md](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/CODE_OF_CONDUCT.md)；
- 版本变化见 [CHANGELOG.md](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/CHANGELOG.md)，学术引用元数据见 [CITATION.cff](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/CITATION.cff)。

## 局限

- 连续期货的换月拼接可能产生非经济含义的跳跃；
- 同日内连接会改变样本构成，且不能消除跨市场收盘时点差异；
- ADF 临界值采用预注册的大样本近似；Sup-F 是简化单断点诊断；
- 自助区间缓解但不能消除时间依赖、重叠持有期和小样本问题；
- 历史统计关系不能证明因果，也不能保证未来复现；
- 在线接口可能限流、变更或停止服务。

## 许可

代码以 [MIT License](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/LICENSE) 发布。在线数据仍受各数据服务商自身条款约束，MIT 许可不授予第三方数据的再分发权。
