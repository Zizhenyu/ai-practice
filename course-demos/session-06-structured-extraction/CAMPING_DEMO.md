# L5 课堂运行说明：露营群聊 → 筹备清单

本例已实现。主线是 Session 06 提取/校验/重试，Session 07 去重/排序/模拟提醒。课堂只由讲师操作，所有独立实践放在课后。[设计与边界](CAMPING_ACTION_ITEMS_SPEC.md)

## 1. 开场材料

打开 [camping_chat.json](fixtures/camping_chat.json)，展示 12 条虚构群聊。

- 两次确认领取帐篷，负责人相同，但截止日期从 9 月 18 日提前到 17 日。
- 归还帐篷是另一件事，不能与领取合并。
- “准备音箱”已确认需要做，但无人认领，日期未知。
- “我负责吃”是玩笑，买无人机还没确定，都不应新增行动项。

固定上下文：2026-09-16（周三），活动在 9 月 19 日（周六）。使用原文日期，不读本机今天。明确 high/low，否则 medium；不替人猜优先级。

## 2. 快速跑通（从仓库根目录）

以下使用项目已有 Windows 虚拟环境；其他环境用已安装课程依赖的 `python` 替代 `.venv/Scripts/python.exe`。

```powershell
.venv/Scripts/python.exe course-demos/session-06-structured-extraction/extract_tasks.py --scenario camping --mock
```

终端会打印本次 `extracted_tasks.json` 的完整路径。将它复制到下方变量，明确选择本次成功产物：

```powershell
$campingInput = '替换为终端打印的本次 extracted_tasks.json 完整路径'
.venv/Scripts/python.exe course-demos/session-07-action-items/task_system.py --scenario camping --input $campingInput
```

不要自动挑“最新文件”，更不要在失败后改用某个旧成功文件。下游只接受显式成功的露营 bundle，不会悄悄读取事故文件或内置任务。

预期：8 条记录 → 7 项任务；重复领取合并来源 m02/m06，截止日取 9 月 17 日；音箱单独进入待分配清单。高优先级最先，同级按日期排序。打印提醒，没有真实消息发送或定时服务。

## 3. 一次展示一个故障

```powershell
.venv/Scripts/python.exe course-demos/session-06-structured-extraction/extract_tasks.py --scenario camping --mock --case prose
.venv/Scripts/python.exe course-demos/session-06-structured-extraction/extract_tasks.py --scenario camping --mock --case repair
.venv/Scripts/python.exe course-demos/session-06-structured-extraction/extract_tasks.py --scenario camping --mock --case exhausted
.venv/Scripts/python.exe course-demos/session-06-structured-extraction/extract_tasks.py --scenario camping --mock --case semantic-error
```

| 场景 | 预期 | 讲解问题 |
|---|---|---|
| normal | 首次通过，8 条 | 能解析就是正确吗？ |
| prose | 首次通过 | JSON 前后有说明文字属于容错成功 |
| repair | 尾逗号失败 → 未知 owner/不可能日期失败 → 第三次通过 | 每一轮反馈包含什么？ |
| exhausted | 三次后失败，退出码 1，无成功任务文件 | 谁负责接管失败？ |
| semantic-error | 首次通过，但第一条 owner 从 jie 改为 yu | 名字合法、引文真实，为什么仍然错？ |

故障场景必须显式 `--mock`。回放是人工编排，不代表模型会照此犯错或修复。真实模型由本节第 7 段的命令运行，按实际结果解释。

提取报告保存每轮原始输出、完整请求和错误。修正请求包含原始输入、上次响应、错误清单；最多三次业务尝试。API 错误不在此循环里当语法问题重试，公共客户端可能另行重试网络请求。

## 4. 阈值如何让“归还帐篷”消失

仍使用 normal 或 repair 成功文件，不使用 semantic-error 文件：

```powershell
.venv/Scripts/python.exe course-demos/session-07-action-items/task_system.py --scenario camping --input $campingInput --threshold 0.5
.venv/Scripts/python.exe course-demos/session-07-action-items/task_system.py --scenario camping --scan-pairs
```

默认 0.6 保留领取/归还两项；降为 0.5，两者误合并，清单只剩 6 项，9 月 21 日的归还提醒消失。这是词面相似度失误，不能把任务减少当成改善。

中文基线是字符二元组 Jaccard，在连续汉字/字母/数字序列内取相邻字符，空白和标点作为边界。领取与归还的例子相似度为 0.5。它不理解语义；标注对中的购买食材/采购露营食品仍可能漏合并。

两个未知负责人不能因为都是 null 就自动合并。合并采用第一条描述、更早日期、更高优先级和所有来源；这不是通用任务更新算法，不自动解决延期、取消或转交。

## 5. 完成状态前后的周一提醒

```powershell
.venv/Scripts/python.exe course-demos/session-07-action-items/task_system.py --scenario camping --input $campingInput --start 2026-09-21 --end 2026-09-21
.venv/Scripts/python.exe course-demos/session-07-action-items/task_system.py --scenario camping --input $campingInput --done course-demos/session-07-action-items/fixtures/camping_done.json
```

两次都观察周一 9 月 21 日：第一次有 1 项当天到期、5 项逾期；人工完成状态将领取帐篷和确认拼车标记完成后，仍有 1 项当天到期、逾期减至 3 项。音箱没有负责人和日期，不会输出 @None。

完成状态是“截至 9 月 21 日”的快照。未指定起点时从快照日期开始；显式传入早于快照的日期会被拒绝，不能用后来知道的完成状态回写历史提醒。

`camping_done.json` 绑定原始输入指纹、提取记录指纹及稳定 task_id，只适用于内容相同的参考提取。真实结果措辞/引用变化时可能不匹配，应从对应 `task_report.json` 读取 task_id，人工创建新的状态文件，不能删掉指纹检查。不同阈值改变任务分组后，旧 task_id 也可能失效。

## 6. 文件与契约

- `common/task_contracts.py`：共享必填字段、类型、日历日期及引文存在性校验。
- `extract_tasks.py`：共享 `run_extraction()`；事故入口继续返回四字段数组，露营入口增加 evidence。
- `task_system.py`：可注入相似度、合并来源、程序生成的 task_id、完成状态及模拟提醒。
- 露营 `extracted_tasks.json` 是含 `status/input/tasks/指纹` 的对象；旧事故同名文件仍是数组。不得混用。
- 每次提取使用唯一目录 `course-demos/outputs/camping/<run-id>/`，失败只写 `extraction_report.json`；成功才写任务 bundle。
- 每次下游处理在该目录下创建 `task-runs/<run-id>/task_report.json`，不同阈值、日期和状态不覆盖前次结果。

回放绑定群聊及规则版本；自定义输入或提示词变化后必须用真实模型。结构通过只说明契约及引文存在性满足要求，不证明引用支持字段或提取完整。指纹用于发现文件混用，不是外部数据的身份认证机制。

## 7. 真实模式与实测记录

```powershell
.venv/Scripts/python.exe course-demos/session-06-structured-extraction/extract_tasks.py --scenario camping
```

有配置 Key 时真实调用，无 Key 则标注人工回放。真实失败不会自动降级为回放。`--input path/to/chat.json` 可替换群聊；需保留同样的数据契约和 Asia/Shanghai 带时区参考时间。

2026-09-16 UTC（本地 2026-09-15）单次 DeepSeek `deepseek-chat` 运行：第一次返回 8 条记录；核对原文，负责人、日期、优先级和来源符合本例参考，没有提取玩笑或无人机提议。下游默认阈值合并为 7 项。记录位于：

`course-demos/outputs/camping/20260916T023933Z-9e7b09df/extraction_report.json`

该次结果与人工参考一致，不表示其他群聊或后续运行一定一致；代码未硬编码任务数，也没有择优重采样。模拟状态、故障回放与真实提取在报告中分别标注。

## 8. 验证与课后任务

全课程测试实测：248 项通过；有 1 条现有 Starlette/httpx 弃用警告，与本例无关。

```powershell
.venv/Scripts/python.exe -m pytest -q course-demos/tests/test_camping_action_items.py course-demos/tests/test_session06_extract_tasks.py course-demos/tests/test_session07_task_system.py
```

课后 A：提交故障输入、反馈和调用次数，对比结构错与事实错。课后 B：提交标注任务对扫描、误合并/漏合并明细，以及同一天的完成状态前后提醒。不要只提交最终 JSON 或剩余数量。

现有默认事故入口仍可直接运行，无需 `--scenario`。新共享校验更严格：owner/due 字段必须出现（允许 null），日期必须有效，priority 类型错误返回错误列表。新的合并采用更高优先级；当天与逾期提醒都过滤已完成任务。
