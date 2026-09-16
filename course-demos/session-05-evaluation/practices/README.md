# L4 课后作业参考答案

- 作业 1（A + B）：[评分表、单处 Prompt 实验和失败分析](prompt_ab.md)
- 作业 2：[扩充 ground truth 的五行回答](ground_truth_expansion.md)
- [完整实测证据](reference_results.json)：含完整输入、输出和逐点裁判记录。

## 复现（仓库根目录）

```powershell
python course-demos/session-05-evaluation/practices/run_reference.py
```

默认读取归档结果，不调用模型。真实实验需配置项目模型及依赖，显式执行：

```powershell
python course-demos/session-05-evaluation/practices/run_reference.py --live --output course-demos/outputs/l4-reference.json
```

该命令沿用已保存的 L3 摘要，重新生成 A/B 并评估四份摘要：2 次生成 + 20 次逐点评价（不含底层重试）。
若先重新运行 L3，请追加 `--l3-results course-demos/outputs/l3-reference.json`；不要混用新输出与旧报告结论。
脚本复用 `compare_prompts.summarize_with` 和 `judge.evaluate_points`，固定单处 Prompt 变化；无 mock 回退。
`../prompt_ab.md` 是另一个离线词面评分教学示例，本目录是完整真实模型作业参考。满分不等于无事实错误。
