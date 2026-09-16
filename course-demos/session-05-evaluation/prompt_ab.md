# Prompt A/B 评估报告 · 讲师示例

## 1. 实验身份与结论

这是 L4 的**离线教学示例**，不是学员作业或真实模型实验。工程师摘要来自 `judge.DEFAULT_SUMMARY`，高管摘要为人工编写；V1/V2 来自 `compare_prompts.py` 的预设 mock。下列分数实际使用 `judge.token_overlap()` 计算，阈值为 0.35，没有调用模型。

观察：工程师版为 5/5，高管版为 2/5；预设 V1/V2 为 0/5 和 5/5。它们说明词面评分器如何工作，**不能证明 Prompt 优化提升了模型效果**。本文件可作为报告格式示范；学员需替换为自己的输入、输出和真实记录。

## 2. 输入与固定评分标准

- 原文：[sample_messages.jsonl](../../slack-simulator/data/sample_messages.jsonl) 中的 CloudCart 事故记录。人工核对客户影响时也查看 `#customer-support` 的 m024。
- 标注：[ground_truth.json](../../slack-simulator/data/ground_truth.json) 的 `summaries.incident_2026_07_13`。
- 覆盖率：命中要点数 / 5。词面命中条件：摘要和要点的英文/数字 token 交集，占该要点 token 集合的比例 ≥ 0.35。
- 所有版本用相同标注和阈值；不使用 long 场景或木兰的标注。英文示例避免将旧评分器不支持中文误认为摘要差。
- 此离线指标不验证事实、否定关系、文笔或受众适配，也未检查 `must_not_include`。

| 编号 | 要点 | 人工核对的原文位置 |
|---|---|---|
| P1 | SEV-2，影响 08:55–09:58，约 63 分钟 | m006、m023 |
| P2 | v2.14.0 saved-payment-methods 的 N+1 查询耗尽连接池，阻塞 /charges | m007、m010、m014 |
| P3 | 回滚至 v2.13.2，09:58 恢复，p99 720ms、5xx 0.3%（标注将回滚完成时间写为 09:58，原文 m020 为 09:52） | m020、m021、m023 |
| P4 | 失败发生在 capture 前，没有重复扣款 | m024 |
| P5 | 四项行动及期限、7/15 复盘 | m023、m028 |

## 3. 任务 A：两类读者摘要

### 工程师版（仓库内置示例）

```text
SEV-2 payment outage on 7/13, impact window 08:55-09:58 (~63 minutes of degraded checkout).
Root cause: v2.14.0's saved-payment-methods endpoint had an N+1 query that exhausted the DB
connection pool (200/200), starving the /charges path. Tom rolled back to v2.13.2 at 09:58;
metrics recovered (p99 720ms, 5xx 0.3%). No double charges — failed requests errored before capture.
Postmortem set for 7/15 with four action items: Jake fixes the query behind a feature flag (7/20),
Tom adds pool saturation alerts (7/17), Aisha adds a CI load test (7/24), Priya updates the runbook (7/15).
```

### 高管版（人工编写示例）

```text
SEV-2 payment outage caused degraded checkout for about 63 minutes, from 08:55 to 09:58. A bad deploy was rolled back and checkout recovered. No double charges: failed requests errored before capture. A postmortem is scheduled for 7/15; engineering follow-ups have owners and deadlines.
```

### 结果与失败分析

| 版本 | 覆盖率 | 命中的要点 | 未命中的要点 | 一句话结论 |
|---|---|---|---|---|
| 工程师版 | 100%（5/5） | P1–P5 | 无 | 技术细节覆盖高，但仍需人工核对事实 |
| 高管版 | 40%（2/5） | P1、P4 | P2、P3、P5 | 保留影响与扣款结论，省略技术细节和具体待办 |

高管版的实际缺失：P2 没解释 N+1 与连接池机制；P3 提到回滚和恢复，但没有版本号与恢复指标；P5 提到复盘及跟进，却没有列出四项任务和期限。因此，“未命中”不等于完全没有相关内容。

**高管版覆盖率低，是否就更差？** 不能这样推断。这份标注偏向工程师需要的细节。管理者可能更关注客户影响、恢复状态、后续责任和未决风险。应另定受众标准再评估，同时保留事实准确性检查；不能仅凭“面向高管”就接受关键遗漏。

人工审阅还发现标注及工程师版都将回滚完成时间写为 09:58，而 m020 在 09:52 已明确说回滚完成；09:58 是指标恢复时间。这是具体的事实错误，即使工程师版得满分也应修正。本报告保留原始被评文本和分数以展示问题，不能把有误的标注当事实依据。

## 4. 任务 B：Prompt A/B 的离线对照

现有脚本的两个完整 Prompt 见 [compare_prompts.py](compare_prompts.py)：V1 为 `Summarize this Slack conversation.`；V2 增加工程师受众、影响窗口、根因、恢复、客户影响和行动项等要求。

它同时改了多个要求，属于组合 Prompt 对照，**不满足课后“只改一处”的因果实验要求**。本示例保留这一点，避免把现有 Demo 当成严格单因素实验。

### 固定输出

V1（`MOCK_V1`）：

```text
There was a payment incident caused by a deploy. The team investigated, rolled it back, and things recovered. Follow-ups were assigned.
```

V2（`MOCK_V2`）：

```text
SEV-2, impact 08:55-09:58 (~63 min degraded checkout). Root cause: N+1 query in v2.14.0 saved-payment-methods endpoint exhausted the DB connection pool (200/200), starving /charges. Rolled back to v2.13.2 at 09:58; p99 720ms, 5xx 0.3%. No double charges (failed before capture). Action items: Jake fix+flag by 7/20, Tom pool alert by 7/17, Aisha CI load test by 7/24, Priya runbook by 7/15. Postmortem 7/15.
```

| 版本 | 覆盖率 | 命中 | 未命中 |
|---|---|---|---|
| V1 预设输出 | 0%（0/5） | 无 | P1–P5 |
| V2 预设输出 | 100%（5/5） | P1–P5 | 无 |

V1 不是毫无信息，而是细节不足，均未达到阈值。V2 细节多，词面命中全部要点；这不证明没有事实错误。两份文本是程序预设，分差 100 个百分点不能用于声称模型改进或写成真实优化成果。

另一个数据边界：现有 `compare_prompts.py` 只选 `#incidents`，P4 的明确依据在 `#customer-support` 的 m024。真实实验前应统一修正两组输入的频道范围，并记录新的固定输入，不能要求模型补出输入中没有的事实。

### 下一步真正的单因素实验（尚未运行）

固定上述完整事故输入、模型版本、生成温度和同一个评分器。A 使用 V1；B 只在 V1 后增加一句 `Include each follow-up action with its owner and due date.`。记录完整响应、逐点判断、失败与调用参数，重点看 P5 是否改善、其他要点是否退化。用更多独立事故样本复验，不挑最好的一次。

## 5. 复现本报告的离线分数

从仓库根目录运行以下 Python（可保存到自己的临时脚本）。直接调用纯函数，不依赖 Key，也不会调用真实 API。脚本从本报告读取两份摘要，V1/V2 从源码读取。

```python
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "course-demos/session-05-evaluation")
import judge
import compare_prompts as cp

report = Path("course-demos/session-05-evaluation/prompt_ab.md").read_text(encoding="utf-8")
texts = re.findall(r"```text\n(.*?)\n```", report, re.S)
points = json.loads(judge.GROUND_TRUTH.read_text(encoding="utf-8"))["summaries"]["incident_2026_07_13"]["must_include"]
for name, summary in zip(
    ("engineer", "manager", "V1", "V2"),
    (texts[0], texts[1], cp.MOCK_V1, cp.MOCK_V2),
):
    scores = [judge.token_overlap(summary, p) for p in points]
    hits = [score >= 0.35 for score in scores]
    print(name, [round(s, 3) for s in scores], hits, f"{sum(hits)}/5")
```

实测输出：

```text
engineer [0.929, 0.864, 0.812, 1.0, 0.737] [True, True, True, True, True] 5/5
manager [0.786, 0.136, 0.312, 1.0, 0.158] [True, False, False, True, False] 2/5
V1 [0.071, 0.136, 0.062, 0.0, 0.105] [False, False, False, False, False] 0/5
V2 [0.857, 0.864, 0.688, 0.75, 0.895] [True, True, True, True, True] 5/5
```

本报告只有一个事故、五个要点。每变动一个命中，覆盖率就变 20 个百分点。它展示报告方法和评分边界，不构成模型准确率、统计显著性或生产效果证明。
