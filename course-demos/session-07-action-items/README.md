# 第7课 · 行动项系统

L5 主例：接收露营行动记录，合并重复承诺、保留来源、排序，并模拟到期和周一逾期提醒。从仓库根目录运行，明确填写本次成功文件路径：

```bash
python course-demos/session-07-action-items/task_system.py --scenario camping --input <本次成功的extracted_tasks.json>
python course-demos/session-07-action-items/task_system.py --scenario camping --scan-pairs
```

正常参考记录在默认阈值 0.6 下从 8 条变为 7 项。`--threshold 0.5` 演示领取/归还帐篷的误合并；`--done` 接受人工完成状态，`--start` / `--end` 控制模拟日期。未分配任务单独显示，已完成任务不再提醒。只打印提醒，不发送消息。

[完整命令、完成状态对照与教学边界](../session-06-structured-extraction/CAMPING_DEMO.md)

中文字符二元组 Jaccard 是词面教学基线，不理解任务含义。替换语义相似度仍需重新评估阈值与误合并代价。本例没有持久化任务服务或真实定时器。

不传参数保留事故案例：读取旧提取文件，没有则用内置样例，模拟 7 月 13–27 日。露营入口必须显式指定成功文件，不用旧文件或内置任务兜底。
