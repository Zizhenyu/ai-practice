# L4 作业 1：覆盖率与单处 Prompt A/B（参考答案）

## 方法与数据身份

实测时间（UTC）`2026-09-16T06:23:09.747300+00:00`；生成与裁判均为 `deepseek/deepseek-chat`，temperature=0。
使用 `judge.py` 的严格 `evaluate_points`，逐点只接受 YES/NO；错误另列，不当作漏项。不是 token-overlap mock。
完整生成请求、裁判请求及逐点原始回答见 [reference_results.json](reference_results.json)。命令见 [README](README.md)。

任务 A：直接评价 L3 的 [engineer / manager 原始输出](../../session-03-pipeline-agent/practices/l4_handoff_reference.md)，输入为同一份 #incidents 24 条。
任务 B：A/B 同时使用 #incidents 24 条加 #customer-support 的 m024，共25条；m024提供“无重复扣款”证据。
两组的输入范围不同，不能把 engineer 的80%到A的100%解释为 Prompt 改进；受控比较仅限 A 对 B。

## 固定五点评分标准（本次保留现有标签）

- P1：SEV-2 payment outage, impact window 08:55-09:58 (~63 min degraded checkout)
- P2：Root cause: v2.14.0 saved-payment-methods endpoint introduced N+1 query, exhausting the DB connection pool (200/200) and starving /charges
- P3：Mitigation: rollback to v2.13.2 completed 09:58, metrics recovered (p99 720ms, 5xx 0.3%)
- P4：No double charges: failed requests errored before capture
- P5：4 postmortem action items assigned (fix+flag by 7/20, pool alert by 7/17, CI load test by 7/24, runbook by 7/15); postmortem 7/15

## 实测结果

| 版本 | 覆盖率 | 命中 | 漏掉 | 一句话结论 |
|---|---:|---|---|---|
| engineer | 4/5 = 80% | P1, P2, P3, P5 | P4 | 输入不含 P4 的证据，不能据此认定摘要失实 |
| manager | 4/5 = 80% | P1, P2, P3, P5 | P4 | 输入不含 P4 的证据，不能据此认定摘要失实 |
| A | 5/5 = 100% | P1, P2, P3, P4, P5 | 无 | 五点均命中，指标已达上限 |
| B | 5/5 = 100% | P1, P2, P3, P4, P5 | 无 | 五点均命中，指标已达上限 |


### 任务 A 思考题：高管版更差吗？

本次两版同为80%，没有出现高管版更低，不应为了符合预期改写数据。
即使高管版更低，也只说明它较少覆盖当前偏技术的要点，不能直接等同于较差。
管理者还关注影响、恢复、剩余风险和客户沟通，应另外评价这些维度、事实正确性和简洁程度。

P4 漏项源于输入范围：m024不在本题 #incidents 输入中，不是模型忘记读过的事实。
P3 标签把回滚完成写成09:58，但 m020 是09:52，m021 才是09:58恢复。裁判仍判 YES，表明“fully or in substance”覆盖判断不足以保证细节准确。
manager 还把宣布时间写成09:58（原文10:02宣布09:58缓解），五点分数未捕捉这项错误。
应在下一版修正 P3 并增加事实核对，给评分标准标版本；本报告没有中途改标签后重算冒充同一实验。

## 任务 B：只改一处要求

复用 `compare_prompts.py` 的 `summarize_with`；原脚本预置 V1/V2 改了多个维度，因此在薄封装中仅追加下面一句，固定其他参数。

### A Prompt（完整）

```text
Summarize this Slack conversation.
```

### B Prompt（完整）

```text
Summarize this Slack conversation.
Include each follow-up action with its owner and due date.
```

唯一变化是要求每个后续行动包含负责人和期限。输入、模型、temperature、max_output_tokens=1500、五点标准及裁判完全一致。
每版生成一次，未筛选最佳输出；两版都是英文，符合原始 Prompt，未额外加入语言要求。

### A 完整输出

```text
# Incident Summary: payment-api P1 — 2026-07-13

## Overview
A **SEV-2** incident affecting customer-facing checkout (`POST /v2/charges`) was declared at 09:06 and mitigated at 09:58. Total impact window: **~63 minutes (08:55–09:58)** of degraded checkout.

## Timeline
- **09:02** — PagerDuty P1 fires: payment-api p99 latency 8.4s (SLO 800ms), 5xx rate 12% and climbing. Started ~08:55.
- **09:06** — Sarah declares SEV-2. Priya = investigation lead, Tom = mitigation, Jake = deploy analysis.
- **09:07** — Jake notes v2.14.0 (deployed 08:45) added the saved-payment-methods endpoint; doesn't touch `/charges` directly but shares the same DB.
- **09:10** — Priya finds payment-db connections pinned at max (200/200) since 08:52 — suspected pool exhaustion, not a traffic spike.
- **09:25** — **Root cause identified:** hundreds of `idle in transaction` sessions from payment-service, all from the new saved-payment-methods endpoint. It runs **one query per stored payment method (N+1)** and holds the connection for the whole request. Under morning traffic this exhausts the pool and starves `/charges`.
- **09:27** — Jake confirms the N+1 (fetching methods in a loop instead of a single JOIN).
- **09:28–09:29** — Priya: "Rollback first, fix later." Sarah approves rollback to v2.13.2.
- **09:30** — Tom begins rollback.
- **09:52** — Rollback complete; connections draining (200 → 121 → 64); p99 down to 1.9s and falling.
- **09:58** — Metrics recovered: p99 720ms, 5xx 0.3%, pool at 41/200. **Mitigated.**
- **10:00** — Elena confirms frontend checkout error rate back to baseline; test transactions clean.

## Customer Impact
- ~63 minutes of degraded checkout.
- David confirmed with Priya that failed requests errored **before capture** — **no double charges**; failed orders simply didn't go through.
- Acme Corp replied to on CS-4821; status page updated to "resolved."

## Action Items (pre-postmortem)
1. **Jake** — Fix the N+1 query, re-ship saved-payment-methods behind feature flag `saved_payment_methods_v2`. Due **7/20**.
2. **Tom** — Add connection-pool saturation alert (warn 70%, page 90%). Due **7/17**.
3. **Aisha** — Add payment-path load test to CI. Due **7/24**.
4. **Priya** — Update payment-service runbook with pool-exhaustion playbook. Due **7/15**.

## Next Steps
- **Blameless postmortem:** Wednesday 7/15 at 10am (invite from Sarah).
- Reminder from Sarah: *"we're fixing systems, not people."*
```

### B 完整输出

```text
# Incident Summary: payment-api P1 / SEV-2 — 2026-07-13

## Overview
A customer-facing P1 incident affecting the `payment-api` charge path (`POST /v2/charges`), declared SEV-2 by Sarah. Mitigated in ~63 minutes via rollback.

## Timeline
- **08:55** — Incident begins (degraded checkout)
- **09:02** — PagerDuty P1 fires: p99 latency 8.4s (SLO 800ms), 5xx rate 12% and climbing
- **09:06** — Sarah declares SEV-2; assigns Priya as investigation lead, Tom on mitigation
- **09:10** — Priya identifies DB connection pool exhaustion (200/200 since 08:52)
- **09:25** — Root cause found: N+1 query in new saved-payment-methods endpoint holds connections as `idle in transaction` (187 rows)
- **09:29** — Sarah orders rollback to v2.13.2
- **09:52** — Rollback complete; connections draining (200 → 121 → 64), p99 down to 1.9s
- **09:58** — Metrics recovered: p99 720ms, 5xx 0.3%, pool at 41/200. **Mitigated.**
- **10:00** — Elena confirms frontend checkout error rate back to baseline
- **10:10** — David confirms no double charges (failed requests errored before capture); status page updated to "resolved"

## Root Cause
v2.14.0 introduced a saved-payment-methods endpoint that runs one query per stored payment method (N+1) and holds the DB connection for the entire request. Under morning traffic, this exhausted the connection pool and starved the `/charges` path.

## Impact
- **Window:** 08:55–09:58 (~63 minutes of degraded checkout)
- Customer-facing checkout failures; no double charges (failed orders simply didn't go through)
- Acme Corp replied to on ticket CS-4821

## Resolution
Rolled back to v2.13.2. Fix deferred to post-incident (no heroics during incident).

---

## Follow-Up Actions

| # | Action | Owner | Due Date |
|---|--------|-------|----------|
| 1 | Fix the N+1 query; re-ship saved-payment-methods behind feature flag `saved_payment_methods_v2` (single JOIN + explicit connection release) | **Jake** | 7/20 |
| 2 | Add connection-pool saturation alert (warn at 70%, page at 90%) | **Tom** | 7/17 |
| 3 | Add payment-path load test to CI (baseline checkout; checkout + saved-methods at 5x; assert pool utilisation < 70%) | **Aisha** | 7/24 |
| 4 | Update payment-service runbook with pool-exhaustion playbook + "first 10 minutes" checklist | **Priya** | 7/15 (before postmortem) |
| 5 | Update affected customers and status page | **David** | ✅ Done (10:10) |

## Next Steps
- **Blameless postmortem:** Wednesday 7/15 at 10am (invite from Sarah)
- Reminder from Sarah: *"we're fixing systems, not people."*
```

### 解释与下一步

A、B 均为100%，差值0个百分点。A本来已经覆盖四项后续任务，追加要求主要改变呈现，不能声称提升了覆盖率。
B 把已完成的客户沟通也放入 Follow-Up 表；其 Due Date 列写完成时间，混淆“期限”和“完成状态”。满分仍需人工审阅。
下一轮可以另设 owner/due/status 的字段级准确率，并增加不同事故样本、多次运行，统计均值和波动。
这应作为预先固定新指标的新实验，不能为让B获胜而事后调整本次分数。生成与裁判同模型也可能有共同偏差，需人工抽查。
