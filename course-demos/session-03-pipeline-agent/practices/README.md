# L3 课后作业参考答案

同目录另附 [L2 rate_limit 作业参考答案与测试说明](rate_limit_reference.md)。

保留原始模板，参考答案供完成作业后核对。

- 作业 1：[双受众摘要](summary_two_audiences_reference.md)
- 作业 2：[Single / Map-Reduce 对照](chunk_comparison_reference.md)
- 作业 3：[L4 事故摘要交接](l4_handoff_reference.md)
- [完整实测证据](reference_results.json)，真实模型 `deepseek-chat`，时间 `2026-09-16T06:22:35.051359+00:00`。

## 从仓库根目录运行

```powershell
python course-demos/session-03-pipeline-agent/practices/run_reference.py
```

默认只读取已保存结果，不调用 API，也不代表刚重新生成。新实验需按项目 README 配置模型和依赖，然后显式运行：

```powershell
python course-demos/session-03-pipeline-agent/practices/run_reference.py --live --output course-demos/outputs/l3-reference.json
```

真实运行包含 9 次应用层模型调用（不计底层重试），无 mock 回退；不会发送 Slack 消息。
temperature=0 也不保证服务端每次输出相同。新实验另存，勿把本参考的旧结论贴到新输出上。
