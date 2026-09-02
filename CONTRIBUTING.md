# 贡献指南

感谢你帮助改进 `goratio`。本项目优先保证统计协议可追溯、数据来源透明和输出边界客观。

## 开始之前

- 安全漏洞不要提交公开 Issue，请按 [SECURITY.md](SECURITY.md) 私下报告。
- 先搜索现有 Issue 和 Pull Request，避免重复工作。
- 数据接口、许可或符号口径问题使用“数据来源问题”表单。
- 改动统计假设、窗口、阈值、过滤器或通过标准前，先使用“研究协议提案”表单讨论。

## 本地开发

项目要求 Python 3.11 或更高版本，运行时不依赖第三方包：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

提交前运行：

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m compileall -q src tests
python -m build
python -m twine check dist/*
```

行为变更应先增加能失败的测试，再实现最小修复。网络来源测试必须使用固定响应或替身，不得依赖实时接口。

## 数据与研究约束

- 不提交第三方原始价格历史、真实缓存、凭据、访问令牌或含个人信息的数据。
- 示例数据必须是明确标注的合成数据，或附有允许再分发的许可证据。
- 不把历史分位映射成买卖、仓位或收益保证。
- 已冻结协议不得为改善结果而事后调整。新假设或参数需要新的协议版本和预注册文档。
- 负面、反向、不稳定和数据不足的结果都是有效结果，不得选择性隐藏。
- 来源变更必须同步更新来源元数据、质量审计、测试和 [DATA_SOURCES.md](DATA_SOURCES.md)。

## 提交与 Pull Request

提交应按模块拆分，主题使用简洁中文，例如：

```text
feat(data): 增加新的字段完整性审计
test: 覆盖冲突重复日期
docs: 澄清连续期货换月局限
```

Pull Request 应说明问题、改动范围、验证证据及兼容性影响，并完成模板检查项。维护者可能要求把无关改动拆分到独立 PR。

提交贡献即表示你有权按仓库的 [MIT License](LICENSE) 提供该贡献，并同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
