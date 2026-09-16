# L2 作业：rate_limit 中间件参考答案

这项作业属于 L2，代码目录为 session-03；与这里的 L3 摘要作业共用目录。
实现见 [rate_limit_reference.py](rate_limit_reference.py)，复用最小 `pipeline.py` 的 Pipeline、过滤器、logger 和 handler。

## 规则与实现

每个作者维护一个队列，仅保存已放行时间；使用可注入的单调时钟，不使用消息自带时间计算窗口。
每次先移除距今 **大于等于60秒** 的记录：有效窗口为 `(now-60, now]`。
剩余不足3条时记录当前时间，调用并返回 `next_(msg)`；否则返回 `rate_limited`，不调用下游，也不追加时间。
放行后即计数，即使下游失败也不撤销；拒绝不延长等待时间。

## 注册位置与返回顺序

```text
ignore_bots → dedupe → logger → rate_limit → normalize → handler
```

Bot、重复投递先过滤，避免占用作者额度；logger 放在限流之前，因此拒绝也会被记录。
放行时先执行 handler，再沿调用栈返回，logger 打印后将结果传回调用者。
拦截时 rate_limit 直接返回，normalize 和 handler 不执行，但上游 logger 仍继续执行。
如果把 logger 放在 rate_limit 后面，拒绝的消息就不会经过 logger。
参考实现将去重状态放在每个管道内部；与原最小示例一样，被拒绝的消息已进入去重集合，同一 ts 重试不会再次处理。

## 运行与预期结果

从仓库根目录运行，不需要 API Key 或 Slack，也不需要真实等待：

```powershell
python course-demos/session-03-pipeline-agent/practices/rate_limit_reference.py
python -m pytest -q course-demos/tests/test_rate_limit_reference.py
python -m pytest -q course-demos/tests/test_pipeline_demo.py
```

| 时间（秒） | 作者 | 结果 | 原因 |
|---|---|---|---|
| 0、10、20 | U1 | ok | 前三条放行 |
| 30 | U1 | rate_limited | 第四条拦截 |
| 30 | U2 | ok | 不同作者独立 |
| 59.999 | U1 | rate_limited | 第一条还未过期 |
| 60 | U1 | ok | 恰好移除时间0的记录 |

测试还验证时间60不能连放两条、时间70可以再次放行，确认这是滚动窗口且拒绝不占额度；并检查过滤、返回值、文本规范化和拒绝日志。

## 必答题：与 SummaryRateLimit 的区别

本作业限制所有通过 Bot/去重过滤的示例消息，以作者为键；用于练习中间件的放行与短路。
实际 Slack demo 的 `SummaryRateLimit` 只限制摘要请求，以 workspace/频道/用户为键；普通讨论仍须完整保存。
不能把本作业中间件直接加到真实讨论采集链，否则第四条起的有效讨论可能丢失，摘要材料会不完整。
这也不是 Slack API 返回429后的退避重试机制。这里是单进程、顺序执行的教学实现；没有分布式配额、并发保护或不活跃作者清理。
