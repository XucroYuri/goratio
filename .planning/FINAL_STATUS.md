# goratio 当前开发状态（Round 75 快照）

## 核心开发已完成

- CLI + MCP + SKILL 只读薄接口与插件白名单
- 合约级数据模型、换月日历、roll-adjusted、真实换月收益
- T+1 close/open/settle 执行缺口与净收益回测
- Episode 级事件研究与 OOS bootstrap
- 双因子 v2（F1 估值 + F2A 趋势/F2B 稳定性）
- 成本后回测、风控门控、保证金、逐日盯市、组合资金监控
- 只读 Web 工作台（HTML 导出 + 本地 HTTP + 动态刷新）
- 全部模块通过 GitHub CLI/PR 推送合并

## 测试

- 116 tests OK
- `python3 -m compileall -q src tests` OK

## 待治理流程

- 外部评审
- review_url / reviewed_by 填写
- 日期戳签名冻结

## 目标完成状态

- [x] 守住极简与只读边界
- [x] 解决可交易性：合约级数据、换月成本、T+1、负油价、人民币披露
- [x] 用 episode 重做事件研究
- [x] 预注册双因子 v2
- [x] 成本后回测与风控门控
- [x] 只读 Web 工作台
- [x] 分阶段分模块提交推送到 GitHub
