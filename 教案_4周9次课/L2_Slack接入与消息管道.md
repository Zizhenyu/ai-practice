# L2 · Slack 接入与消息管道

**第 1 周 · 周日 · 120 分钟 · 🖥️ 远程在线（小班 5–10 人）**
**对应代码**：`session-02-slack-api/`（verify_signature.py、echo_server.py、echo_server_ws.py）、`session-03-pipeline-agent/`（pipeline.py、slack_pipeline_demo.py、slack_adapter.py）、`common/message_pipeline.py`、`common/message_store.py`

> 🖥️ 线上通用纪律见 `00_总览与排课.md` 第二节，本文只写本节课特有的执行点。

---

## 学习目标

课后学员能够：

1. 构造 HMAC 签名基串并用代码验证，说清为什么校验必须包含时间戳
2. 对比 HTTP Events API 与 Socket Mode，能根据本地开发/生产部署场景选择接入方式
3. 画出 "3 秒 ack + 异步处理" 的时序图，并说明不这么做会发生什么
4. 把一坨 if-else 的消息处理重构成中间件管道，并给新中间件写单测
5. 跑通“普通消息 → Pipeline → 存储 → 摘要命令 → thread 回帖”，说明 mock 与真实接入分别验证了什么

---

## 课前准备（讲师，提前 15 分钟开播）

**本教案命令统一从仓库根目录执行**，使用已安装课程依赖的 Python；Windows 可用 `.venv/Scripts/python.exe` 替代 `python`。

```bash
python course-demos/session-02-slack-api/verify_signature.py
python course-demos/session-02-slack-api/echo_server.py --test
python course-demos/session-02-slack-api/echo_server_ws.py --test
python course-demos/session-03-pipeline-agent/pipeline.py
python course-demos/session-03-pipeline-agent/slack_pipeline_demo.py --offline
```

**必须课前留好**：合法/篡改/过期三种验签结果；HTTP ack 与慢处理对比；离线 Pipeline 的 6 条 `stored` 和 1 条 `replied`；一份真实 thread 回帖及 `trace.jsonl`。

**真实 demo 检查**：Bot Token 有 `channels:history`、`channels:read`、`app_mentions:read`、`chat:write`；App Token 有 `connections:write`；开启 Socket Mode，订阅 `message.channels` 和 `app_mention`；Bot 已加入 `#l2_demo`。换 workspace 时替换频道 ID。不要同时运行 echo server 和新 demo 争用同一 App 的连接。

**🖥️ 本节课特有的线上执行点**：

- **在线白板提前画好两张三泳道时序图**（HTTP / Socket Mode；泳道均为 Slack / 你的服务 / 后台线程）。这两张图是本节课最重要的产出，**课上只填箭头和耗时标注**。
- 讲"坏代码"那一段（01:00 前后）**提前把那段 if-else 打成文字放好**，不要现场手打——远程看着讲师打字是纯粹的时间浪费。
- `echo_server.py --test` 的时间戳和 `echo_server_ws.py --test` 的 `thread_ts` **字很小**。跑之前先把字号再调大一档，或直接用截图放大讲。
- 上节课有人一直没开口的，**这节课优先点他**。第二节课还沉默，基本就沉默到结营了。

---

## 当前 Bot 权限与 L2 / L3 的关系

**核验时间：2026-09-12。** 使用本地保存的 `SLACK_BOT_TOKEN` 调用只读 `auth.test`，返回 `ok: true`；Workspace 为 `Slack_WS_Demo_2026`，Bot 为 `slack_assistant`。下表来自响应头 `x-oauth-scopes`，是当时实际授予的权限，不是拟申请清单。本文不记录任何 token 或 secret。

| 已授予的 Bot scope | 能力 | 与本课程的关系 |
|---|---|---|
| `app_mentions:read` | 读取所在会话中直接提及 App 的消息 | L2 现有 `@bot hello` 演示；后续可用 `@bot summary` 触发摘要 |
| `chat:write` | 通过 Web API 发送消息 | L2 在原 thread 回 echo；L3 集成后回传摘要 |
| `channels:history` | 读取 Bot 已加入的公开频道消息；支持 `message.channels` 事件 | 为 L2 自动收集普通频道消息、L3 使用真实讨论生成摘要提供权限基础 |
| `channels:read` | 查看公开频道基本信息 | 选择演示频道、将频道 ID 对应到名称；已知频道 ID 时不必为每条消息重复查询 |
| `users:read` | 查询用户资料 | 可将消息中的用户 ID 转为显示姓名，使 L3 摘要中的发言者和负责人更易读；基础 demo 也可直接保留 ID |
| `channels:manage` | 管理公开频道 | 当前记录、echo 和摘要链路不需要；已授予不表示教学运行必须使用，也不要求学生额外申请 |

官方依据：[OAuth 响应头与 scope 查询](https://docs.slack.dev/authentication/installing-with-oauth/)、[`channels:history`](https://docs.slack.dev/reference/scopes/channels.history/)、[`app_mentions:read`](https://docs.slack.dev/reference/scopes/app_mentions.read/)。

### 权限、事件订阅、代码监听是三个不同条件

> **有权限表示允许访问，不代表 Slack 已经推送，也不代表程序已经处理。**

| 检查项 | 当前已知状态 | 对教学 demo 的影响 |
|---|---|---|
| Bot OAuth 权限 | 已确认具有 `channels:history`、`app_mentions:read` 和 `chat:write` | 公开频道普通消息收集所需的 Bot scope 已具备，无需为此要求用户逐条发送 `record` 命令 |
| App 后台 Event Subscriptions | 2026-09-12 已实测普通消息和提及均到达 | 每期开课仍核对 `message.channels` 与 `app_mention`；不能只看 token scopes |
| Python 事件监听 | 基础 echo 只监听提及；新 `slack_adapter.py` 已监听 `message` 和 `app_mention` | 普通消息保存；提及走命令分支；明确登记的模拟 Bot 素材可放行，其他 Bot 回复忽略 |
| Bot 是否已加入目标频道 | 已在 `#l2_demo` 完成发送、接收和回帖 | 新频道仍需邀请 Bot；不能将该权限理解为可读取所有公开频道 |

`message.channels` 是 Slack 后台的订阅名称，推送的事件类型是 `message`，因此 Bolt 中的对应监听通常是 `@app.event("message")`。权限检查没有验证事件实际送达；应通过目标频道中的普通消息做接入验收。

### 与课程链路的衔接：集成 demo 已实现

实现与运行说明见 [Pipeline demo README](../course-demos/session-03-pipeline-agent/README.md)，设计见 [Review spec](../course-demos/session-03-pipeline-agent/PIPELINE_DEMO_SPEC.md)。课堂先执行 `python course-demos/session-03-pipeline-agent/slack_pipeline_demo.py --offline`（仓库根目录），再演示真实 Socket 接入。新 demo 的摘要请求限流只作用于命令；下方原 `rate_limit` 练习作用于全部消息，两者不要混用。

已实现的自然交互为：

```text
用户在指定公开测试频道正常讨论
    → Bot 接收普通消息
    → L2：过滤、去重、清洗、保存统一消息记录
用户发送 @slack_assistant summary
    → L3：读取指定频道已保存的记录，生成摘要
    → chat.postMessage 将摘要回复到触发消息的 thread
```

- **L2 的重点**：说明消息从哪里来、怎样进入 Pipeline，以及权限与事件订阅如何共同决定可接收的消息范围。
- **L3 的重点**：把上述记录作为摘要输入。`summarize.py` 保留本地文件教学入口；新 Pipeline 从消息存储读取快照，两者复用 `common/summarization.py`。
- **摘要范围**：实时监听只能收集启动后实际收到的事件；不能宣称已经拥有完整历史。若要补齐历史，需要单独设计 `conversations.history` 拉取、分页及与实时事件去重的流程。
- **命令和数据分开**：摘要命令、Bot 自己的回复不进入摘要材料；同时监听 `message` 和 `app_mention` 时，还应按消息身份避免同一条提及被重复记录或触发。
- **公开频道边界**：本次核实的 scope 不含 `groups:history`，不将私有频道消息读取列为当前已具备的能力。

### 三种凭据的职责仍需分开

上述 scope 清单只针对 **Bot Token**。本地也配置了 App Token 和 Signing Secret，后续真实建连验收已成功；这证明该配置可用，不代表 Bot Token 的 scope 响应本身能证明 App Token 权限。

- `SLACK_BOT_TOKEN`：控制读取消息、查询信息和发送回复等业务权限。
- `SLACK_APP_TOKEN`：Socket Mode 建连使用，需单独确认 `connections:write`；不能用 Bot Token 的 scope 查询结果替代这项检查。
- `SLACK_SIGNING_SECRET`：HTTP 入站验签使用，不属于 OAuth scope，也不是 Socket Mode 读取消息的权限。

---

## 时间轴

### 00:00–00:10 ｜ 作业点评

共享 1–2 份依赖图（**课前已收好、已打开**）。重点讲**循环依赖**和**共享层方向**两个错误。

一句衔接：

> 「上节课我们让代码在你的机器上跑起来了。今天让它连上外面的世界——一旦连上外面，两个新问题立刻出现：**别人可以伪造请求**，以及**别人不等你**。」

---

### 00:10–00:30 ｜ 🎥 板书：为什么签名校验不是可选项

🎤 先提问（**点名，不要问"大家觉得呢"**——线上开放式提问 100% 换来沉默）：

> 「你的 bot 有一个公网 URL。我知道这个 URL。我能干什么？」

引导到：任何人都能 POST 一个假的 `message` 事件，让你的 bot 以为 CEO 说了某句话。

板书 HMAC 校验的三要素：

```
签名基串 = "v0:" + timestamp + ":" + raw_body
signature = "v0=" + HMAC_SHA256(signing_secret, 基串)
校验 = hmac.compare_digest(算出来的, 请求头里的)  且  |now - timestamp| < 5min
```

三个必须讲的细节：

| 细节 | 为什么 |
|---|---|
| 用 **raw body**，不是解析后的 JSON | JSON 重新序列化可能改变字节，进而导致签名不匹配。这是最常见的翻车点 |
| 用 `compare_digest`，不是 `==` | 防时序攻击。普通相等比较不保证常数时间，不能替代专用安全比较 |
| 时间戳窗口 | 没有它，攻击者可以**重放**一个合法的旧请求。签名合法 ≠ 请求新鲜 |

```bash
python course-demos/session-02-slack-api/verify_signature.py     # 演示三种 case：合法、被篡改、过期
```

**跑完再读源码**。让学员自己指出"过期"那条为什么签名是对的但仍然被拒。

---

### 00:30–00:50 ｜ 演示：HTTP vs Socket Mode + 3 秒 ack

先把两种实时接入方式说清楚：**它们收到的是同一套 Events API payload，区别只是 Slack 怎么把 payload 送到你的进程。**

| 方式 | 谁发起连接 | 需要什么 | 适合什么场景 |
|---|---|---|---|
| HTTP Events API | Slack POST 到你的服务 | 公网 HTTPS Request URL + `SLACK_SIGNING_SECRET` | 托管生产环境、横向扩容、Marketplace |
| Socket Mode | 你的服务连 Slack WebSocket | `SLACK_APP_TOKEN`（`connections:write`） | 本地开发、防火墙后、单 workspace 内部工具 |

三个 token/secret 的职责必须分开：

| 凭据 | 作用 |
|---|---|
| `SLACK_BOT_TOKEN` (`xoxb-`) | 调 Web API，例如 `chat.postMessage` 发回消息 |
| `SLACK_APP_TOKEN` (`xapp-`) | 调 `apps.connections.open`，建立 Socket Mode WebSocket |
| `SLACK_SIGNING_SECRET` | 只校验 HTTP 入站请求；Socket Mode 已在连接层认证，不使用它 |

再讲共同约束（**这是平台强加的，不是设计选择**）：

> 「不管走 HTTP 还是 WebSocket，Slack 都要求你快速确认收到。HTTP 回 2xx；Socket Mode 回 envelope ack，Bolt 帮你处理。**3 秒内不确认，Slack 就认为投递失败并重发。**而 LLM 调用五秒、十秒都正常，所以必须先 ack，再异步处理。」

在在线白板上填两张时序图，**填完导出 PNG 发聊天区**：

```
HTTP：
Slack ──POST event──> 公网 /slack/events ──立刻 200 OK──> Slack       (< 100ms)
                              │
                              └──后台处理──> 调 LLM ──> chat.postMessage

Socket Mode：
你的服务 ──建立 WebSocket（xapp）──> Slack
Slack ──event envelope────────────> 你的服务 ──Bolt ack──> Slack      (< 100ms)
                    │
                    └──后台处理──> 调 LLM ──> chat.postMessage
```

```bash
python course-demos/session-02-slack-api/echo_server.py --test       # HTTP：验签、200 ack、去重
python course-demos/session-02-slack-api/echo_server_ws.py --test    # Socket：构造 thread 回帖，完全离线
# 真实连接统一放到 01:20 的 Pipeline 环节；此处只展示基础 echo 截图。
```

观察两件事：ack 先于慢处理完成；真实 Socket Mode 演示中，`@bot hello` 两秒后在原 thread 收到 `echo: ...`。当前两份 echo server 都用两秒 sleep 代表未来的 LLM 调用，**本节不宣称已经接入真实 LLM**。

**必须点破的一句**：

> 「注意这里发生了一个架构上的转变：**收到事件和发送答案是两次独立通信**。先确认事件，再用 `chat.postMessage` 主动发答案；不要把 LLM 结果塞进 ack。HTTP 和 Socket Mode 在这一点上完全相同。」

**顺带处理重复投递**：

> 「Slack 重发时会带同一个 `event_id`。所以你必须去重——这正好是下半节课中间件管道要解决的问题之一。」

**为什么本课默认推荐 Socket Mode 实操**：不需要域名、TLS 或 ngrok，学员只要两种 token 和 Slack 后台订阅就能收第一条真实消息。**为什么仍保留 HTTP**：它更容易通过负载均衡做无状态横向扩容，也是 Slack 对常规生产和 Marketplace 的推荐路径。

> 📌 **ngrok 实操不在课上做**。🖥️ 线上版改为**讲师提前录一段 6 分钟的录屏**（Slack App 后台 → Event Subscriptions → 填 ngrok URL → 收到第一条真实事件），课前发到作业频道。
>
> 这是远程课比线下**更划算**的地方：这类"跟着点一遍"的操作，录屏比现场演示好——学员可以暂停、回退、按自己的节奏跟。而且**录一遍能用四期**。课堂时间留给不可录制的东西：讨论和排错。

---

### 00:50–00:57 ｜ 休息 7 分钟

> 🖥️ **线上把休息挪到了这里**（线下版在 01:15）。理由：下半场的中间件管道是本节课认知负荷最重的一段，**不要让学员带着 50 分钟的疲劳进去**；而且线上连讲 75 分钟必然掉线（注意力意义上的）。
>
> 「休息 7 分钟，回来打个 1。」休息时在聊天区贴好下半场练习的要求。

---

### 00:57–01:20 ｜ 🎥 演示：把 if-else 重构成中间件管道

先展示"坏代码"（🖥️ **课前打好的文字，直接共享**，故意写难看）：

```python
def handle(msg):
    if msg.get("bot_id"): return
    if msg["id"] in seen: return
    seen.add(msg["id"])
    log(msg)
    msg["text"] = msg["text"].strip().lower()
    ...   # 再来五条规则
```

🎤 **这里用投票**（线上最适合投票的一处）：

> 「这段代码有什么问题？它现在能跑。**在聊天区打一条你觉得最大的问题，都打完我再念。**」

让所有人同时打字，比轮流点名快，而且**每个人都真的想了一遍**。念的时候点名念，被念到的人自然会展开讲。

引导出三条（**顺序很重要，第三条最值钱**）：

1. **难以隔离测试** — 单测去重时混入其他规则和副作用
2. **不可插拔** — 加一条规则要改这个函数，改坏了影响全部规则
3. **规则顺序缺少解释** — 调换过滤、日志、去重可能改变行为，需要显式表达取舍

然后跑：

```bash
python course-demos/session-03-pipeline-agent/pipeline.py
```

读 `common/message_pipeline.py` 的 `Pipeline`，再看 `pipeline.py` 的四个最小中间件。它们用于解释模式；真实链路的来源过滤、双重去重和审计在 `DemoRuntime` 中：

| 中间件 | 职责 | 为什么单独一层 |
|---|---|---|
| `ignore_bots` | 过滤 bot 自己的消息 | 不过滤会**无限自我回复**，这是新人第一个生产事故 |
| `dedupe` | 基础示例按 `ts` 去重 | 新 demo 分开处理 `event_id` 和 `(team_id, channel, ts)`，不照搬全局 set |
| `logger` | 记录放行 | 出事时唯一能查的东西 |
| `normalize` | 清洗文本 | 下游所有模块都假设文本已清洗 |

**关键讲解点**：`next_` 参数。

> 「每个中间件拿到 `next_`，可以选择**调用它（放行）或不调用（拦截）**。这一个设计同时给了你三样东西：顺序是显式的（注册顺序就是执行顺序）、每层可以独立测试、加一层不用改别的层。这个模式叫责任链，Express、Django、gRPC 拦截器全是它。」

**面试话术**（让学员记下）：

> 「我把消息处理重构成了中间件管道，每一层职责单一、可独立测试，新增规则不需要改动已有代码。」

---

### 01:20–01:33 ｜ 主 demo：普通讨论到摘要回帖

**01:20–01:24：先跑离线，观察链路。**

```bash
python course-demos/session-03-pipeline-agent/slack_pipeline_demo.py --offline
```

预期：6 条模拟素材保存、1 条合成摘要命令回复。打开本次运行目录的 `messages.jsonl`、`trace.jsonl`、`summary_runs.jsonl`，让学员指出“材料在哪里、命令在哪里、摘要读了哪些记录”。离线 FakeClient 不向 Slack 发消息。

**01:24–01:30：切换真实传输，由讲师发送一批新素材。**

```bash
# 明确会向已创建的 #l2_demo 发布六条模拟消息；只由讲师执行一次。
python course-demos/session-03-pipeline-agent/slack_pipeline_demo.py --socket --channel C0C16PDBFHR --mock --seed short
```

等监听就绪和素材到达后，请一位学员正常发一条讨论，再通过提及选择器发送 `@slack_assistant summary`。观察原 thread 回复；普通消息只保存不回帖。终端里的 `posted=6` 仅证明发送成功，需核对 `trace.jsonl` 中六条 `stored` 才证明接收成功；加上学员讨论后应有七条材料。

**01:30–01:33：解释三处边界。**

- 来源白名单：Alice/Bob 模拟角色共用 Bot 身份。登记的 seed 消息放行；Bot 摘要回复未登记，被忽略；`[模拟]` 前缀不是通行证。
- ack 与业务：Bolt 的协议 ack 不等模型结果；单 worker 负责后台处理。内存队列不是持久任务系统，退出或队列满可能使覆盖不完整。
- 连续两课：本节使用 mock 摘录说明数据链路，L3 换真实模型评价摘要质量。保留本次运行目录，L3 通过 `--store-dir` 复用；重新启动不会自动补频道历史。

真实接入故障时立即回到离线，用课前真实证据讲解；不把剩余练习时间耗在权限后台。对话记忆移到文末选读，主课时长仍为 120 分钟。

---

### 01:33–01:55 ｜ 🖥️ 学员动手 + 讲评

> **组织方式**：01:33–01:50 静音自习（举手 → 拉进讨论室）；01:50–01:55 抽 1 人共享屏幕讲自己的中间件放在哪、为什么。
>
> 讲师每 6 分钟在聊天区问一次进度（「写完中间件的打 1，测试也绿了的打 2」）。

**练习（17 min）· 加一个中间件并给它写单测**

任务：在最小 `pipeline.py` 示例中加 `rate_limit`，练习 `next_` 的放行与拦截。采用滚动 60 秒窗口，同一作者最多 3 条，第四条拦截；恰好满 60 秒移出，拦截不增加计数。讲师提供函数骨架和可注入时钟，避免学生真实等待一分钟。

**范围区别**：这个保留练习限制所有示例消息；实际 demo 的 `SummaryRateLimit` 只限制摘要请求。不能将练习版本直接接到普通讨论采集链，否则摘要会缺材料。两种实现作用范围的解释是本次必答题。

要求：

1. 注册到管道里，位置自己决定，**并在注释里写明为什么放这个位置**
2. 在 `course-demos/tests/` 加测试：前三条放行、第四条拦截、另一作者独立、60 秒边界恢复
3. 先运行自己的测试，再运行 `python -m pytest -q course-demos/tests/test_pipeline_demo.py` 验证集成行为

**讨论室里重点看**：

- 混淆日志顺序：`logger → rate_limit` 时，下游拦截返回后 logger 仍会打印；`rate_limit → logger` 提前拦截时 logger 不执行。新 demo 用最外层 audit 记录最终原因
- 测试只写了 happy path
- 直接改 `handle()` 而不是写成中间件（说明责任链没理解）

> 🖥️ **第三种要优先捞出来**。它说明责任链根本没理解，而这个学员在线上不会主动说"我没懂"。**讲师要在聊天区主动要一次代码**：「把你的 `rate_limit` 函数签名贴出来看看」——一行就能判断他懂没懂，比问"有没有问题"有效得多。

---

### 01:55–02:00 ｜ 作业与预告

**作业 1（必做）**：完成练习并提交。
**验收**：测试通过；能解释中间件位置、返回顺序，以及全消息限流与摘要请求限流的区别。

**作业 2（必做）**：分别画出 HTTP 与 Socket Mode 的 "Slack 事件 → ack → 后台处理 → 回帖" 时序图，标出连接由谁发起、每一步的耗时量级，以及三种凭据分别出现在哪里。

**作业 3（必做）**：提交新 Pipeline demo 的链路证据：一条 `stored`、一条摘要命令 `replied`、一条 Bot 回复 `ignored`，以及同次运行的输入/摘要文件说明。有 Slack 环境者提交原 thread 截图；无权限者提交离线结果并明确 `manifest_replay/fixture`，不能冒充真实接入。运行产物目录被 Git 忽略，将精简截图和说明放进自己的作业提交目录。

**L3 交接**：记下实际运行目录供 `--store-dir` 重载。不要把多个练习批次混在一起后宣称摘要仅来自六条素材。

**作业 4（选做）**：跟着**课后录屏**配一次 ngrok，让 `echo_server.py` 收到一条真实 HTTP 事件；写三行说明它与 Socket Mode 的差异。卡住的在作业频道贴报错，助教异步回复。

**下节预告**：

> 「今天我们确认了消息如何变成摘要输入。下节课在同一条链路上检查摘要是否忠实、是否适合读者；先做好单次摘要，再通过对比决定什么时候需要分块。」

---

## 常见卡点（助教手册）

| 现象 | 原因 | 处理 |
|---|---|---|
| 签名怎么都对不上 | 用了解析后再序列化的 body | 必须用 raw bytes |
| `echo_server.py --test` 报 ModuleNotFoundError: flask | 依赖没装 | `pip install flask` |
| `echo_server_ws.py` 报 ModuleNotFoundError: slack_bolt | 依赖没装 | 在仓库根目录运行 `pip install -r course-demos/requirements.txt` |
| Socket Mode 报 `invalid_auth` / `not_allowed_token_type` | 把 xoxb 当成 xapp，或 App Token 没有 `connections:write` | `SLACK_APP_TOKEN` 必须是 `xapp-`；回 Slack 后台重新生成 App Token |
| WebSocket 已连接，但 `@bot` 没事件 | 未订阅 `app_mention`、缺 `app_mentions:read`、改 scope 后未重装，或 bot 不在频道 | 按 README 的四项清单逐项检查 |
| Socket Mode 能收到但回帖失败 `missing_scope` / `not_in_channel` | 缺 `chat:write` 或 bot 未加入频道 | 补 scope、重装 App、在频道 `/invite @bot` |
| Bot 回复又进入材料 | 来源过滤错误 | 基础示例过滤 Bot；新 demo 只接受已登记模拟素材，不能无条件放行所有自消息 |
| 中间件写成了返回值链而不是调 `next_` | 没理解责任链 | 对照 `pipeline.py` 的 `Pipeline.run` 重讲一遍 |
| 测试里 LLM 调用变慢/失败 | 忘了 mock | `conftest.py` 已自动清 key，检查是否绕过了 `call_llm` |
| 🖥️ `echo_server.py` 端口被占用 | 学员机器上有别的服务 | 换端口即可；**不要花时间帮他找是谁占的**，课后再说 |
| 🖥️ 学员看不清 ack 的时间戳 | 终端字号 / 共享分辨率 | 用截图放大讲。**这是本节课唯一必须看清的细节** |
| 🖥️ 讲评时学员共享屏幕但代码窗口太小 | 没提前调 | 提前跟被点名的人说一句「等下共享前把字号调大」 |

---

## 选读：对话记忆与成本（不占本课 120 分钟）

运行 `python course-demos/session-03-pipeline-agent/chat_agent.py`，观察 `ConversationMemory`。它保留最近最多 12 条消息；更早消息取前 60 字符拼接，缓冲只保留最后 500 字符。这是截短拼接，不是 LLM 语义摘要，也不能保证保留主线。

在每轮长度近似固定的假设下，反复发送全量历史的累计输入量可按 O(n²) 增长；固定窗口加固定大小缓冲可按 O(n) 增长。这里指累计输入量，不直接等同实际账单。把历史存到消息库、选择本次模型上下文、对原文生成摘要，是三个不同操作。

## 面试预埋

- 「如何设计一个能应对第三方平台超时限制的异步架构？」→ ack-then-process + 幂等去重 + 回调发送
- 「你怎么保证 webhook 的安全性？」→ HMAC + raw body + 常数时间比较 + 时间戳窗口
- 「Slack HTTP Events API 和 Socket Mode 怎么选？」→ 本地/防火墙后优先 Socket；常规生产/横向扩容/Marketplace 优先 HTTP；两者都要快速 ack、幂等去重、异步处理
- 「怎么证明消息链路跑通？」→ posted 与 stored 分开核对、source 区分真实和回放、thread 回帖与防循环、快照追踪到摘要输入
