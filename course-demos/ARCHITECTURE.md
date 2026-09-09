# 项目架构：Session 1 文件级关系

第 1 课作业「阅读脚手架架构文档并画出模块依赖图」的参考答案。本文只解释当前已发布代码的文件级关系；完整课程（14 个 session、6 大模块）的长期架构见 [ARCHITECTURE_FULL.md](ARCHITECTURE_FULL.md)。

## 文件树

```text
.
├── README.md
├── pytest.ini
├── conftest.py
├── course-demos/
│   ├── .env.example
│   ├── ARCHITECTURE.md
│   ├── ARCHITECTURE_FULL.md
│   ├── requirements.txt
│   ├── assets/
│   │   └── session-01-module-flow.png
│   ├── common/
│   │   ├── __init__.py
│   │   └── llm.py
│   ├── session-01-setup/
│   │   ├── README.md
│   │   ├── check_env.py
│   │   └── hello_bot.py
│   └── tests/
│       ├── test_common_llm.py
│       └── test_session01_setup.py
└── slack-simulator/
    ├── README.md
    ├── generate_messages.py
    ├── inject_slack.py
    ├── config/
    ├── data/
    ├── kb/
    └── tests/
```

`course-demos/venv/`、`.venv/`、`.pytest_cache/`、`course-demos/.env` 是本地运行产生或保存密钥的文件，不属于架构，也不应该提交。

## Session 1 文件依赖图

```mermaid
flowchart TD
    root_readme["README.md<br/>课程总入口"]
    session_readme["course-demos/session-01-setup/README.md<br/>第1课运行说明"]
    arch["course-demos/ARCHITECTURE.md<br/>当前文件级架构"]
    full_arch["course-demos/ARCHITECTURE_FULL.md<br/>完整课程架构"]
    req["course-demos/requirements.txt<br/>Python依赖清单"]
    env_example["course-demos/.env.example<br/>本地.env模板"]
    env["course-demos/.env<br/>本地密钥, 不提交"]

    check_env["session-01-setup/check_env.py<br/>环境体检脚本"]
    hello_bot["session-01-setup/hello_bot.py<br/>Console/Slack bot入口"]
    llm["common/llm.py<br/>统一LLM调用入口"]
    common_init["common/__init__.py<br/>共享包标记"]

    tests_session["tests/test_session01_setup.py<br/>Session 1测试"]
    tests_llm["tests/test_common_llm.py<br/>LLM共享层测试"]
    conftest["../conftest.py<br/>pytest路径/fixture"]
    pytest_ini["../pytest.ini<br/>pytest配置"]

    root_readme --> session_readme
    root_readme --> arch
    arch --> full_arch
    session_readme --> check_env
    session_readme --> hello_bot
    session_readme --> env_example

    check_env --> req
    check_env --> env
    hello_bot --> llm
    hello_bot --> env
    llm --> env
    llm --> common_init

    tests_session --> conftest
    tests_session --> check_env
    tests_session --> hello_bot
    tests_llm --> llm
    conftest --> pytest_ini
```

## 运行链路 1：环境检查

```mermaid
sequenceDiagram
    participant User as 学生
    participant Check as check_env.py
    participant Dotenv as python-dotenv
    participant Env as course-demos/.env
    participant Packages as installed packages

    User->>Check: python course-demos/session-01-setup/check_env.py
    Check->>Dotenv: load_dotenv()
    Dotenv-->>Env: 读取本地环境变量文件(如果存在)
    Check->>Packages: importlib.util.find_spec(...)
    Check-->>User: 输出 Python / packages / env vars / summary
```

`check_env.py` 不调用 LLM，也不连接 Slack。它只回答三个问题：

- 当前 Python 版本是否满足 `>= 3.9`
- `yaml`、`flask`、`slack_sdk` 等依赖是否安装
- Slack/LLM 相关环境变量是否存在

## 运行链路 2：Hello Bot

```mermaid
flowchart TD
    start["python hello_bot.py<br/>可加 --mock / --console"]
    args["parse_args()<br/>解析CLI开关"]
    tokens{"存在 SLACK_BOT_TOKEN<br/>和 SLACK_APP_TOKEN<br/>且未传 --console?"}
    console["run_console()<br/>本地输入输出"]
    slack["run_slack()<br/>Slack Socket Mode"]
    mention["app_mention事件<br/>首次@机器人"]
    thread["message事件<br/>已追踪thread内回复"]
    gate["should_answer_thread_reply()<br/>过滤bot/未知thread/非thread消息"]
    handler["handle_message()<br/>统一消息处理"]
    clean["clean_message_text()<br/>去掉开头<@BOTID>"]
    mode{"传入 --mock?"}
    mock["mock_reply()<br/>离线echo回复"]
    llm_safe["common.llm.call_llm_safe()<br/>真实LLM失败时fallback"]
    provider{"common.llm.llm_provider()<br/>按key选择provider"}
    real["OpenAI / Anthropic / DeepSeek<br/>真实模型回复"]

    start --> args --> tokens
    tokens -- no --> console --> handler
    tokens -- yes --> slack
    slack --> mention --> handler
    slack --> thread --> gate --> handler
    handler --> clean --> mode
    mode -- yes --> mock
    mode -- no --> llm_safe --> provider
    provider -- key exists --> real
    provider -- no key or API failure --> mock
```

`hello_bot.py` 的核心设计是把「消息从哪里来」和「如何生成回复」分开：

- `run_console()` 负责本地终端输入输出，方便没有 Slack token 时练习。
- `run_slack()` 负责 Slack Socket Mode 连接和事件监听。
- `handle_message()` 是共享的 bot brain；Console 和 Slack 都调用它。
- `--mock` 强制跳过真实 LLM，直接走离线 echo 回复。
- 没有 `--mock` 时，`handle_message()` 调用 `common.llm.call_llm_safe()`，有模型密钥就请求真实 LLM；没有密钥或 API 失败就 fallback 到 `mock_reply()`。
- Slack 中第一次 `@mention` 会记录 thread；同一 thread 后续人类消息不需要再次 `@mention`，也会进入 `handle_message()`。

## 共享 LLM 层

```mermaid
flowchart LR
    caller["调用方<br/>hello_bot.py 或后续session"] --> call["call_llm_safe() / call_llm()"]
    call --> provider["llm_provider()"]
    provider --> openai{"OPENAI_API_KEY?"}
    provider --> anthropic{"ANTHROPIC_API_KEY?"}
    provider --> deepseek{"DEEPSEEK_API_KEY?"}
    openai --> openai_sdk["openai SDK"]
    anthropic --> anthropic_sdk["anthropic SDK"]
    deepseek --> deepseek_sdk["OpenAI-compatible DeepSeek API"]
    call --> mock["mock fallback"]
```

`common/llm.py` 是后续课程会持续复用的统一入口。它的职责不是业务逻辑，而是把 provider 选择、模型名、timeout、retry、mock fallback 收到一个地方，避免每个 session 都重复写一份「如果有 OPENAI_API_KEY 就调 OpenAI，否则调 mock」。

环境变量加载顺序：

- 先调用 `load_dotenv()`，允许从当前运行目录附近读取 `.env`
- 再显式加载 `course-demos/.env`
- 第二次加载不会覆盖已经存在的环境变量

## 测试关系

```mermaid
flowchart TD
    pytest["python -m pytest -q"] --> ini["pytest.ini"]
    pytest --> conf["conftest.py"]
    conf --> path["把 course-demos/ 和 slack-simulator/ 加入 sys.path"]
    conf --> mock_env["force_mock_mode fixture<br/>删除LLM key避免真实网络调用"]
    conf --> loader["load_session()<br/>加载hyphen目录里的脚本"]
    loader --> session_tests["test_session01_setup.py"]
    session_tests --> check_env["check_env.py"]
    session_tests --> hello_bot["hello_bot.py"]
    pytest --> llm_tests["test_common_llm.py"]
    llm_tests --> llm["common/llm.py"]
```

测试层有两个重要约束：

- `conftest.py` 会删除 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`DEEPSEEK_API_KEY`，保证测试不会误调真实模型。
- `load_session()` 用文件路径加载 `session-01-setup/hello_bot.py` 这类带连字符目录下的脚本，因为它们不能直接用普通 Python package import。

## 与 slack-simulator 的关系

Session 1 的 `hello_bot.py` 直接连接真实 Slack 或本地 console，不直接读取 `slack-simulator/`。`slack-simulator/` 是课程数据侧的输入系统，后续模块会围绕它生成、注入和评估 Slack 风格消息。

```mermaid
flowchart LR
    sim["slack-simulator/<br/>生成课程消息数据"] --> m1["模块1<br/>消息处理"]
    m1 --> m2["模块2<br/>摘要"]
    m1 --> m3["模块3<br/>任务提取"]
    m1 --> m4["模块4<br/>RAG + 风险"]
    m2 --> m5["模块5<br/>编排 / 集成"]
    m3 --> m5
    m4 --> m5
    m5 --> score["评分"]
```

当前仓库里已经能看到 `slack-simulator/` 的数据、配置和测试文件，但 Session 1 的代码目标仍然是把环境、凭据、Slack 连接、LLM 调用入口跑通。

## 每个文件的职责

| 文件 | 职责 | 被谁使用 |
| --- | --- | --- |
| `README.md` | 课程总入口、通用准备、GitHub auth、session 列表 | 学生/老师 |
| `course-demos/session-01-setup/README.md` | Session 1 的具体运行步骤和课堂练习 | 学生/老师 |
| `course-demos/ARCHITECTURE.md` | 当前已发布代码的文件级架构说明 | 学生/老师 |
| `course-demos/ARCHITECTURE_FULL.md` | 完整课程未来架构 | 学生/老师 |
| `course-demos/requirements.txt` | demo 运行和测试所需 Python 包 | `pip install -r ...` |
| `course-demos/.env.example` | `.env` 模板，不含真实密钥 | 学生复制为 `.env` |
| `course-demos/.env` | 本地真实密钥和配置，不提交 | `python-dotenv` 读取 |
| `course-demos/common/llm.py` | 统一 LLM 调用、provider 选择、mock fallback | `hello_bot.py`、后续 session、测试 |
| `course-demos/common/__init__.py` | 标记 `common` 为共享包 | Python import 系统 |
| `course-demos/session-01-setup/check_env.py` | 检查 Python、依赖和环境变量 | 学生运行、测试 |
| `course-demos/session-01-setup/hello_bot.py` | Console/Slack bot，线程回复，LLM 或 mock 响应 | 学生运行、测试 |
| `course-demos/tests/test_session01_setup.py` | Session 1 行为测试 | pytest |
| `course-demos/tests/test_common_llm.py` | LLM 共享层 mock/可用性测试 | pytest |
| `conftest.py` | pytest 路径、mock 环境、脚本加载工具 | pytest |
| `pytest.ini` | pytest 配置 | pytest |
| `course-demos/assets/session-01-module-flow.png` | 课程模块流程图图片 | 文档/课堂展示 |
| `slack-simulator/` | 课程 Slack 数据生成、注入、知识库和测试 | 后续模块 |
