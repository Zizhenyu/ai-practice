# 第1课 · 环境搭建

**演示要点**：企业级项目从环境自检开始——依赖、密钥、连通性都应可一键验证，而不是"在我机器上能跑"。

```bash
python check_env.py            # 环境自检，输出每项 OK / MISSING
python hello_bot.py            # 无Slack token时进入控制台模式
```

有真实 Slack token 时（`SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN`，App 需开启 Socket Mode），`hello_bot.py` 会连上 workspace 响应 @mention。被 @mention 后，同一 thread 里的后续消息不需要再次 @mention，bot 会继续回复。
