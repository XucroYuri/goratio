# 变更日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构，并使用 [语义化版本](https://semver.org/lang/zh-CN/)。候选版本的命令行和 JSON 契约仍可能在正式版前调整。

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
