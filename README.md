# AI Training — Session 1

第 1 次课：项目全景、环境检查、Hello Bot 与统一 LLM 调用入口。

本次仅发布第 1 课代码及必要共享模块。ARCHITECTURE.md 展示完整课程的架构；其中后续课次的代码尚未包含在本次发布中。

## Quick start (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r course-demos/requirements.txt
.\.venv\Scripts\python.exe course-demos/session-01-setup/check_env.py
.\.venv\Scripts\python.exe course-demos/session-01-setup/hello_bot.py
.\.venv\Scripts\python.exe -m pytest -q
```

建议使用 Python 3.12。没有 Slack token 时，Hello Bot 使用控制台模式；输入 quit 退出。可选模型 SDK 或密钥显示 MISSING 不影响离线练习。

## LLM mock exercise

从 course-demos 目录运行 Python：

```python
from common.llm import call_llm
print(call_llm("You are a helpful assistant.", "Hello", mock="Hello from mock"))
```

未配置模型密钥时，上述调用返回固定结果。真实模型可按需安装 openai 或 anthropic 并在本地配置密钥；不要提交 .env 或密钥。测试会移除模型密钥，使用离线模式。
