# goratio

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

宏观原因归因、图表、告警、交易回测、动态插件、MCP 与 Agent 接口不在本阶段范围内。完整冻结规范见 [01-SPEC.md](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/.planning/phases/01-evidence-baseline/01-SPEC.md)，本次公开实证见 [01-RESULTS.md](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/.planning/phases/01-evidence-baseline/01-RESULTS.md)。

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

## 局限

- 连续期货的换月拼接可能产生非经济含义的跳跃；
- 同日内连接会改变样本构成，且不能消除跨市场收盘时点差异；
- ADF 临界值采用预注册的大样本近似；Sup-F 是简化单断点诊断；
- 自助区间缓解但不能消除时间依赖、重叠持有期和小样本问题；
- 历史统计关系不能证明因果，也不能保证未来复现；
- 在线接口可能限流、变更或停止服务。

## 许可

代码以 [MIT License](https://github.com/XucroYuri/goratio/blob/v0.1.0-rc1/LICENSE) 发布。在线数据仍受各数据服务商自身条款约束，MIT 许可不授予第三方数据的再分发权。
