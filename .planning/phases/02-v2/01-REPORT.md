# 双因子 v2 阶段报告（草稿）

状态：`draft_preregistered`
协议：`goratio-2a-v1`

## 本阶段交付

- 双因子定义：
  - F1 滚动 5 年金油比分位；
  - F2A 黄金 252 日动量确认；
  - F2B 无前视在线结构稳定性。
- Episode 级事件研究：
  - 63/126/252 三个期限；
  - OOS episode 门槛；
  - 95% / 98.33% bootstrap 差值区间。
- 成本后回测：
  - `--cost-bps`
  - `--roll-cost-bps`
  - `--t1-close`
  - 真实主力链换月收益与 T+1 open gap。
- 组合/资金研究：
  - 保证金估算；
  - 单笔/多笔逐日盯市；
  - 简单资金曲线。
- 只读 Web 工作台：
  - HTML 导出；
  - 本地 HTTP 服务；
  - 近期金油比走势图；
  - 60 秒自动刷新。

## 运行方式

```bash
goratio formal --period 10y --cost-bps 20 --roll-cost-bps 5 --json
goratio evidence --period 10y --cost-bps 20 --roll-cost-bps 5 --json
goratio web serve --period 10y --host 127.0.0.1 --port 8765
```

## 当前边界

- 所有结论仍为研究/诊断，不构成投资建议。
- 尚未完成外部评审与日期戳冻结。
- 真实合约级回测仍需在完整组合资金约束下验证。
