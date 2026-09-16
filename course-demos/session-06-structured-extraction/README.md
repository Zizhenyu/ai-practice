# 第6课 · 结构化输出与任务提取

L5 主例：把露营群聊提取为带原文依据的行动记录，演示解析、校验、有限重试，以及“结构合法但事实错误”。从仓库根目录运行：

```bash
python course-demos/session-06-structured-extraction/extract_tasks.py --scenario camping --mock
python course-demos/session-06-structured-extraction/extract_tasks.py --scenario camping --mock --case repair
```

正常回放得到 8 条记录，重复承诺交给 Session 07 合并。case 支持 normal、prose、repair、exhausted、semantic-error；故障案例须显式 `--mock`。回放证明流程，不代表真实模型修复能力。

去掉 `--mock` 后，有 Key 时调用真实模型，无 Key 时明确回放。每次生成独立报告，成功才生成下游任务文件；API 失败不静默切换回放。

- [完整运行说明与实测记录](CAMPING_DEMO.md)
- [设计、数据契约与验收](CAMPING_ACTION_ITEMS_SPEC.md)
- [Session 07](../session-07-action-items/README.md)

不传 `--scenario` 保留事故案例，可用 `--mock` 离线运行。共享校验已检查必填字段、真实日历日期及类型。课堂由讲师演示，学生实践放在课后。
