# L3 作业 3：给 L4 的事故摘要（参考答案）

这份输入来自 `slack-simulator/data/sample_messages.jsonl` 的 `#incidents`，共 24 条；与作业 1/2 的中文长消息是不同事故。
使用同次真实模型、temperature=0、single，为两类受众分别调用 `common.summarization.summarize`。
输出 JSON 的 `text` 字段是摘要，评分时取文本而非整个 JSON。全部输入、请求和结果在 [reference_results.json](reference_results.json)。

## engineer

[JSON 交接文件](l4_handoff/engineer.json)

```text
**事件摘要（工程师版）**

**时间线**
- 2026-07-13 08:55 起：payment-api p99 延迟升至 8.4s（SLO 800ms），5xx 率 12% 且上升；影响 checkout `POST /v2/charges`。
- 09:02 PagerDuty P1 触发；09:06 宣布 SEV-2，Priya 任调查负责人，Tom 负责缓解。
- 09:10 发现 payment-db 活跃连接自 08:52 起打满（200/200），初判为连接池耗尽而非流量激增。
- 09:25 定位：`pg_stat_activity` 显示大量来自 payment-service 的 idle-in-transaction 会话，均来自新增 saved-payment-methods 端点；该端点对每个已存支付方式执行一次查询（N+1），并在整个请求期间持有连接，早高峰流量下耗尽连接池，拖垮 `/charges`。
- 09:29 决定先回滚；09:30 开始回滚至 v2.13.2。
- 09:52 回滚完成，全部 pod 运行 v2.13.2；连接数 200→121→64，p99 降至 1.9s 并继续下降。
- 09:58 指标恢复：p99 720ms，5xx 0.3%，连接池 41/200；基础设施侧判定已缓解。
- 10:00 前端 checkout 错误率回到基线，测试交易正常。
- 10:02 宣布 09:58 缓解；影响窗口 08:55–09:58，约 63 分钟 checkout 降级。

**证据**
- DB 指标：连接池自 08:52 打满。
- `pg_stat_activity` 查询显示 187 行 idle-in-transaction 会话（payment-service）。
- Jake 确认 v2.14.0 新增 saved-payment-methods 端点，虽不直接触及 `/charges`，但访问同一 DB；其实现为循环逐条获取，未用单次 JOIN。

**已执行操作**
- 回滚 payment-api 至 v2.13.2（Tom，09:30–09:52）。
- 确认指标与前端 checkout 恢复。

**当前状态**
- 已缓解（09:58）。根因已定位为 N+1 查询导致连接池耗尽。客户沟通与状态页更新由 David 负责（已指示，未见完成确认）。

**待办（负责人 / 期限）**
1. Jake：修复 N+1，将 saved-payment-methods 置于 feature flag（`saved_payment_methods_v2`）后重新发布；改为单次 JOIN + 显式释放连接；PR 次日提交。期限 7/20。
2. Tom：新增连接池饱和告警（70% 警告，90% 告警）。期限 7/17。
3. Aisha：在 CI 中加入支付路径负载测试（基线 checkout、checkout+saved-methods 5x、断言池利用率 <70%）；先提交测试计划评审。期限 7/24。
4. Priya：更新 payment-service runbook，加入连接池耗尽处置手册及“前 10 分钟”清单。期限 7/15，postmortem 前。

**后续**
- 无责 postmortem：7/15（周三）10:00，Sarah 发邀请。
```

## manager

[JSON 交接文件](l4_handoff/manager.json)

```text
**管理者摘要（2026-07-13 支付事件）**

**业务影响**
- 08:55–09:58（约63分钟）结账路径降级，客户可见。
- payment-api p99 延迟峰值 8.4s（SLO 800ms），5xx 达 12% 并上升；受影响接口为 `POST /v2/charges`。
- 前端结账错误率同步升高，后于 10:00 恢复基线。

**根因（已确认）**
- 08:45 部署 v2.14.0 新增 saved-payment-methods 端点，其查询存在 N+1，每请求逐条查询并持有连接，导致 payment-db 连接池耗尽（200/200），拖垮 /charges。
- 证据：pg_stat_activity 显示 187 条 payment-service 的 idle-in-transaction 会话。
- 注：该端点不直接调用 /charges，但共用同一数据库。

**恢复情况**
- 09:29 决定回滚；09:30 执行；09:52 回滚完成，全部 Pod 回到 v2.13.2。
- 连接数 200→121→64；09:58 p99 720ms、5xx 0.3%、连接池 41/200，基础设施侧判定已缓解。
- 10:00 前端确认结账恢复正常，测试交易通过。
- 09:58 正式宣布缓解。

**客户沟通**
- 09:08 曾要求暂缓客户沟通，待确认影响范围。
- 10:02 指示更新受影响客户与状态页；具体发送情况未在材料中确认。

**剩余风险与未知项**
- 修复尚未上线：N+1 修复计划以 `saved_payment_methods_v2` 特性开关重新发布，PR 预计次日提交，截止 7/20。
- 连接池饱和告警（70% 警告、90% 页面）截止 7/17；支付路径 CI 负载测试截止 7/24；运行手册更新截止 7/15。
- 未知：受影响客户具体数量与范围、客户沟通是否已实际发出、回滚期间是否有失败交易需补偿。

**后续**
- 无责事后复盘定于 7/15（周三）10:00。
```

## 人工核查与评分边界

原文 m020 是 09:52 回滚完成，m021 是 09:58 指标恢复，m023 在 10:02 宣布 09:58 缓解。
manager 的“09:58 正式宣布缓解”混淆了缓解时间和宣布时间，应改成“10:02 宣布已于09:58缓解”；归档保留原输出以便评估。
“无重复扣款”来自其他频道的 m024，本题指定的输入不包含它，因此不能要求生成器猜到这个结论。
对应实测评分与分析见 [L4 报告](../../session-05-evaluation/practices/prompt_ab.md)。
