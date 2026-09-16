# L4 / L5 课程演示入口

课程课次与代码目录的对应关系：

| 课程 | 代码目录 | 主例 |
|---|---|---|
| L4 评估入门与 Prompt 工程 | session-05-evaluation | 木兰同稿双评、摘要报告 |
| L5 结构化输出与行动项系统 | session-06-structured-extraction、session-07-action-items | 露营群聊、提取校验、合并与模拟提醒 |

课堂由讲师演示，独立运行、编码与报告均为课后作业。

## 安装与离线运行

从仓库根目录使用 Python 3.10+：

```bash
python -m pip install -r course-demos/requirements.txt
python -m pip install pytest
python course-demos/session-05-evaluation/compare_evaluators.py --mock
python course-demos/session-05-evaluation/judge_google.py --mock
python course-demos/session-06-structured-extraction/extract_tasks.py --scenario camping --mock
```

复制最后一个命令打印的本次成功 `extracted_tasks.json` 路径，再运行：

```bash
python course-demos/session-07-action-items/task_system.py --scenario camping --input "本次成功文件的完整路径"
python course-demos/session-07-action-items/task_system.py --scenario camping --scan-pairs
```

故障演示使用 `--scenario camping --mock --case repair`、`exhausted` 或 `semantic-error`。真实模型配置见 `.env.example` 与各目录 README，不提交 `.env` 或密钥。OpenAI/DeepSeek 的真实调用需安装 `openai`，Anthropic 需安装 `anthropic`。

## 配套说明

- [L4 运行说明](session-05-evaluation/README.md)
- [木兰教师说明](session-05-evaluation/MULAN_TEACHER_GUIDE.md)
- [prompt_ab.md 离线报告示例](session-05-evaluation/prompt_ab.md)
- [L5 完整运行说明](session-06-structured-extraction/CAMPING_DEMO.md)
- [L5 设计与验收](session-06-structured-extraction/CAMPING_ACTION_ITEMS_SPEC.md)
- [L4 Google Slides（24 页）](https://docs.google.com/presentation/d/1Wb6YAl_YPi3ncpfCaJpyFIv-cyAuHMh0wz_F3V5UYCE/edit)
- [L5 Google Slides（25 页）](https://docs.google.com/presentation/d/1hYZUKMl8dbwN-o6jr87A7CcMinOOzzGpGlpVPEFpsxE/edit)

Slides 的访问由 Google Drive 权限决定。课件中的 LLM 合并决策属于设计讨论，当前任务脚本采用词面相似度规则。

旧事故演示依赖仓库已有 `slack-simulator/data`；木兰与露营主例的输入、人工回放位于各自 fixtures。回放验证流程，不代表真实模型表现。各文档中的历史运行目录是讲师本地记录，运行后会生成自己的报告，不随仓库提交。

## 测试

```bash
python -m pytest -q course-demos/tests
```

此次同步后目标仓库的课程测试为 169 项通过。测试覆盖旧课程及本次新增的评估、回放身份校验、失败处理、任务合并和提醒行为。
