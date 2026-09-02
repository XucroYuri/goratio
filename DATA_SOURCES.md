# 数据来源与使用边界

更新日期：2026-09-02

`goratio` 只发布数据获取与分析代码，不随仓库、Python 包或 GitHub Release 分发第三方价格历史。MIT 许可仅覆盖项目代码，不授予新浪、Yahoo、交易所或其他数据权利人的内容许可。

## 内置来源

| 来源 ID | 请求入口 | 标的 | 项目使用口径 | 状态 |
| --- | --- | --- | --- | --- |
| `cn_public` | `stock2.finance.sina.com.cn/futures/api/jsonp.php/...` | `GC` / `CL` | 服务商拼接连续期货日收盘价 | 默认、非交易所官方结算价 |
| `yahoo_futures` | `query1.finance.yahoo.com/v8/finance/chart/{symbol}` | `GC=F` / `CL=F` | 服务商连续近月期货日收盘价 | 仅在用户明确选择后访问 |

两种来源均按 USD 计价，黄金单位为金衡盎司、原油单位为桶。接口返回的换月处理、复权、历史修订、交易日历及时间戳定义可能不同，因此跨来源结果只用于复现检查，不能假定两组序列逐点相同。

## 来源说明

### 新浪财经全球期货日线

程序按需请求新浪财经公开可访问的全球期货 JSONP 入口。该入口没有被本项目视为稳定、受支持或承诺长期兼容的公共 API。新浪保留变更、中断或终止服务的权利，其财经用户协议也对部分抓取、统计所得数据的对外提供作出限制。使用者应在运行前自行确认当前条款、访问频率和使用场景是否被允许：

- [新浪网络服务使用协议](https://corp.sina.com.cn/chn/sina_item.html)
- [新浪财经用户协议](https://finance.sina.com.cn/roll/2021-05-12/doc-ikmxzfmm2033220.shtml)

### Yahoo Finance Chart

Yahoo 来源是可选项，程序不会在默认流程或跨来源复现时自动联网访问它。该 Chart 入口的可访问性不等于获得存储、商用或再分发许可；Yahoo API 条款规定许可可撤销，并对转让、商业使用及合规责任设有限制。使用者应根据所在地和用途核对最新文件：

- [Yahoo Developer API Terms of Use](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html)
- [Yahoo Developer Network Guidelines](https://legal.yahoo.com/us/en/yahoo/guidelines/ydn/index.html)
- [Yahoo Terms International](https://legal.yahoo.com/index.html)

## 本地缓存与自有 CSV

- 在线结果只写入用户本机配置的缓存目录，缓存不进入版本控制或发布包。
- 用户负责其缓存的保留期限、访问控制和合法使用；项目不提供数据再分发授权。
- 标准 CSV 导入适用于用户有权使用的数据。导入只记录 `user_csv` provenance，不改变原数据权利。
- 无法确认在线条款时，可完全不访问内置来源，改用自有 CSV 复现统计流程。

## 可复现性限制

项目记录获取时间、实际跨度、来源标识和输入 SHA-256，但不公开第三方原始快照。服务商修订历史后，相同命令可能得到不同摘要。论文、报告或 Issue 应同时披露来源、获取时间、符号、实际样本期和摘要值。

本文件用于说明项目边界，不构成法律意见。服务商条款可能随时变化，使用者需要自行核验最新版本。
