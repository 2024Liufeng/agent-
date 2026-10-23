# 智能购物助手 — 系统设计文档 V1.1

**技术框架：** HelloAgents + FastAPI + Vue 3 + DrissionPage

**文档状态：** 核心设计已确认，按完整后端 → 完整前端 → 真实联调实施

**新项目目录：** `shopping_assistant_cg/`

---

## 1. 项目目标

开发一个基于 HelloAgents 的多 Agent 智能购物助手。

用户只需要通过自然语言描述购物需求，主 Agent 自主理解任务、调用专业子 Agent、处理异常、询问用户，并最终输出购物结果。

系统支持：

- **商品推荐**：例如“预算 3000 元，推荐一款拍照好的手机”。
- **商品比价**：例如“帮我比较 iPhone 在京东、淘宝和拼多多的价格”。
- **购物清单**：例如“2000 元以内帮我配置一份宿舍用品清单”。

项目不采用固定的 Python 购物工作流。

**核心原则：Agent 决策，工具执行，后端传递，前端展示。**

## 2. 系统总体架构

~~~text
用户 → Vue 3（左：对话区；右：实时进度区）
          │
          ├─ POST /api/chat：提交消息、立即返回 conversation_id
          └─ GET /api/chat/{conversation_id}/events：SSE 实时进度
          ↓
        FastAPI
          ↓
  SessionManager + AgentRunner
  （同一对话复用主 Agent；每轮一个 Queue）
          ↓
  ShoppingCoordinatorAgent（自主决定）
       ├─ ProductDiscoveryAgent → Tavily
       ├─ PriceComparisonAgent → 京东/淘宝/拼多多
       │                           ↓
       │                    共享 BrowserManager
       │                    一个无头 Edge，独立标签页并行
       └─ RecommendationAgent → Calculator
~~~

### 2.1 前端职责

左边 ChatPanel 展示用户消息、Agent 提问、用户回复、最终推荐及错误；右边 ProgressPanel 展示主/子 Agent 与工具的真实执行进度。**不另设最终结果区**；不展示私有推理或编造进度，不做业务决策。

### 2.2 后端职责

FastAPI 接收消息并转发 SSE；SessionManager 找到原主 Agent；AgentRunner 启动原生 Agent，转换公开事件并放入 Queue。Python 负责通信、状态和安全，不写死购物顺序。

同一主 Agent 不能并发执行两轮；三个电商平台工具可以在一个无头 Edge 的不同标签页并行搜索。

### 2.3 HelloAgents 职责

使用框架原生 ReActAgent、TaskTool、ToolRegistry、arun_stream 和 History。只对提问后的等待边界作最小适配，不重新实现 ReAct 循环或聊天历史。

不增加 RAG、MemoryTool。工具层不主动截断网页正文，保留 HelloAgents 默认 51,200 字节工具输出截断与上下文管理。

## 3. 多 Agent 设计

### 3.1 ShoppingCoordinatorAgent — 主 Agent

系统的唯一购物决策中心。

主要职责：

1. 理解用户当前需求和已有对话上下文。
2. 判断是否需要搜索、比价或推荐。
3. 自主选择、调用一个或多个子 Agent。
4. 接收子 Agent 的结果与错误。
5. 判断错误是否可以自行解决。
6. 必要时主动询问用户。
7. 用户回复后继续此前未完成的任务。
8. 判断任务是否已经完成。
9. 整合最终结果。

比价任务的最小前置规则：

1. 先确定用户要求查询的平台；未指定平台时，默认使用京东、淘宝和拼多多。
2. 第一次调用 `price_comparison_agent` 前，必须调用 `check_platform_login` 检查目标平台。
3. `check_platform_login` 只回答登录态，不判断商品搜索结果。明确检测成功后返回 `authenticated=true/false`；工具报错或逐平台 `status=error/authenticated=null` 表示无法确认，不能当作未登录。
4. 只有 `authenticated=true` 的平台才允许进入比价。明确返回 `authenticated=false` 时，主 Agent 必须用 `request_user_input` 询问用户登录后继续还是跳过该平台；检测错误则如实说明检测失败，不要直接要求用户重新登录。
5. 用户说“已登录”不等于检测成功；用户完成登录后必须再次调用 `check_platform_login`。用户选择跳过后，只把已确认登录且用户允许的平台交给比价 Agent。

商品证据规则（不变量，不是触发条件清单）：

1. 在给出具体商品型号、推荐结论或比价对象前，必须有真实证据来源；用户自己明确指定的型号除外。
2. 如果任务需要具体型号而手上没有可靠证据，先调用 `product_discovery_agent` 取证；不得凭记忆或猜测填写型号、价格和链接。
3. 如果还不确定该查哪些商品，可以先向用户确认需求，而不是猜测。

主 Agent 可以调用：

~~~text
product_discovery_agent
price_comparison_agent
recommendation_agent
request_user_input
check_platform_login
open_platform_login
close_platform_login
Read                # 仅限 .env
Edit                # 仅限 .env
~~~

**主 Agent 不受 Python 固定购物流程控制。**

### 3.2 ProductDiscoveryAgent — 搜索 Agent

负责根据用户要求查找商品候选。

拥有：

- Tavily 搜索工具。

正常输出：商品名称、型号、规格、推荐理由以及信息来源。

异常输出：例如 Tavily 配额不足、API Key 缺失、网络错误、检索无结果。

搜索 Agent 可以自行使用已有工具尝试合理替代方案，但不能伪造搜索结果。无法解决时，将错误及已取得的有效信息返回主 Agent。

### 3.3 PriceComparisonAgent — 比价 Agent

负责根据指定商品和平台获取真实报价。

拥有：

- 京东搜索工具。
- 淘宝搜索工具。
- 拼多多搜索工具。

正常输出：

- 平台和商品名称。
- 商品型号、规格。
- 实际可确认的报价。
- 店铺、优惠和购买条件。
- 证据来源。

异常输出：

- 工具返回的登录页、验证码/风控页面或其他页面异常；
- 页面读取失败；
- 无法确认价格；
- 其他实际工具错误。

比价 Agent 必须阅读平台工具返回的真实内容：工具 `status=error` 时保留错误码与原因；工具 `status=success` 只表示页面读取成功，仍须检查页面正文是否有匹配商品和可验证报价。遇到登录失效、验证码/风控、空页面、无有效商品/价格或其他异常时，逐平台向主 Agent 如实汇报错误、证据及其他平台已有结果。最终汇报尽量控制在 450 个字符以内，先列错误/未确认平台，再列有效报价；HelloAgents TaskTool 的摘要默认只保留子 Agent 最终回复前 500 个字符，避免关键错误被截断。

比价 Agent 不调用用户交互工具，也不替用户决定是否需要人工参与；只有主 Agent 根据子 Agent 的真实报告决定是否询问用户。不能因为一个平台失败就把整个比价任务标记为成功，也不能编造价格或把工具错误写成“没有商品”。主 Agent 不能把 price_comparison_agent 外层 status=success 当成所有平台都成功，必须阅读逐平台摘要。

### 3.4 RecommendationAgent — 推荐 Agent

根据搜索 Agent 和比价 Agent 已获取的证据：

- 分析商品优缺点。
- 比较同规格商品。
- 结合用户预算进行推荐。
- 调用 Calculator 计算总价。
- 输出推荐理由和局限。

不编造实时价格或商品链接。

## 4. 子 Agent 错误与主 Agent 决策

真实工具使用 HelloAgents 原生 ToolResponse（success/partial/error），子 Agent 将有效证据和无法解决的错误返回主 Agent。**不另定义必须包含 retryable 等额外字段的强制 JSON 格式。**

示例（结构示意，不表示实际查询成功）：

~~~json
{
  "status": "error",
  "text": "Tavily API 额度已耗尽",
  "data": {},
  "error": {"code": "QUOTA_EXCEEDED", "message": "Tavily API 额度已耗尽"}
}
~~~

业务上是否重试、换工具、询问用户，由主 Agent 自主决定；错误内容中潜在凭据和网页正文不能直接作为前端进度输出。

### 4.1 Tavily 额度不足

~~~text
用户提出商品推荐任务
   ↓
主 Agent 调用搜索 Agent
   ↓
搜索 Agent 调用 Tavily
   ↓
返回 QUOTA_EXCEEDED
   ↓
搜索 Agent 报告主 Agent
   ↓
主 Agent 自主决策
   ├── 使用其他工具继续
   ├── 向用户询问是否配置 API
   └── 说明当前能力限制
~~~

Python 不编写：

~~~python
if error_code == "QUOTA_EXCEEDED":
    ask_user_for_api_key()
~~~

因为是否询问用户应由主 Agent 决定。

### 4.2 平台未登录

~~~text
主 Agent 确定目标平台
   ↓
主 Agent 调用 check_platform_login
   ↓
返回逐平台检测结果
   ├─ authenticated=true：该平台可以进入比价
   ├─ authenticated=false：询问用户登录后继续还是跳过
   └─ status=error/authenticated=null：说明检测失败，不当成未登录
   ↓
主 Agent 只把确认登录且用户允许的平台交给比价 Agent
   ↓
比价 Agent 调用平台搜索工具
   ↓
平台工具返回页面内容或真实工具错误
   ↓
比价 Agent 阅读结果，先汇报各平台错误/未确认原因，再列有效报价
   ↓
主 Agent 决定自行继续、重试或询问用户

Agent：淘宝需要登录，你想如何继续？

用户：登录后继续 / 跳过淘宝
   ↓
主 Agent 接收回复
   ↓
自主决定后续工具调用
~~~

第一次比价前调用 `check_platform_login` 是固定前置步骤，不由主 Agent 自由省略。

`check_platform_login` 只判断登录态。未触发验证码/风控时，明确跳转登录页或明确登录提示返回 `authenticated=false`；浏览器、网络、验证码/风控或页面无法确认身份时返回检测错误，不能伪装成未登录。平台搜索工具如果遇到登录页、验证码/风控、空页面或其他异常，必须返回真实页面证据或工具错误。比价 Agent 将其如实报告给主 Agent；是否重试、继续其他平台或询问用户，均由主 Agent 决定。平台工具不得把异常页面当成正常搜索成功，也不得反复打开相同页面。


## 5. 用户交互与任务续接

### 5.1 request_user_input

主 Agent 需要用户协助时，使用该通用工具询问是否登录、商品规格、预算等；是否询问由主 Agent 决定。

~~~json
{
  "question": "淘宝需要登录，要登录还是跳过？",
  "kind": "choice",
  "options": [
    {"id": "login", "label": "登录后继续"},
    {"id": "skip", "label": "跳过淘宝"}
  ]
}
~~~

### 5.2 提问与续接

~~~text
主 Agent 调用 request_user_input
  ↓
最小交互适配类停止本轮后续业务调用
  ↓
HelloAgents 保存原生历史；pending_input 保存唯一问题
  ↓
AgentRunner 发送 ask_user → SSE → 左侧显示问题
  ↓
用户回复（原 conversation_id）
  ↓
AgentRunner 启动原主 Agent 的新一轮
  ↓
主 Agent 使用历史自主决定接下来做什么
~~~

不长期阻塞 Python 等待用户，也不只靠提示词保证暂停。

### 5.3 标识

只保留 conversation_id，保证一个对话对应同一个主 Agent；同时最多一个 pending_input。当前不使用 request_id、task_id、event_id，不实现用户消息自动重试。旧 ID 不存在时明确报错，不创建没有历史的新 Agent。

## 6. 后端运行机制

**只需要 SessionManager + AgentRunner + FastAPI SSE，不需要 EventStore/TaskRecord。**

### 6.1 SessionManager（backend/app/session_manager.py）

- conversation_id 对应原主 Agent，不同对话的 HelloAgents 历史隔离。
- status：idle/running/waiting_user/completed/failed，标记本轮阶段。
- active_task：保存本轮主 Agent asyncio.Task，阻止同一个 Agent 被同时执行两轮。**不是三个平台搜索标签页。**
- pending_input：当前唯一待回答问题。
- queue：本轮 asyncio.Queue，AgentRunner 放进度，SSE 取进度。
- result/error：保存当前最终结果或公开错误。
- 所有对话共享一个 BrowserManager；当前 Session 仅保存在单进程内存中，重启后不恢复。

### 6.2 AgentRunner（backend/app/agent_runner.py）

- start()：验证没有重复运行，识别用户对 pending_input 的回答，新建 Queue，设置 running，使用 asyncio.create_task 启动本轮主 Agent。
- run()：通过原生 arun_stream() 获取事件，转成适合展示的状态，用 queue.put() 发给 SSE。
- Agent 提问则 waiting_user；正常结束发送 final；失败发送安全错误；末尾用 Queue 的 None 标记本轮结束。
- 不保存第二套 LLM 历史，不固定购物流程。子 Agent 的真实工具开始/结束事件已通过每对话一个 ProgressReporter + ProgressTool 显式回调写入同一 Queue，不使用 ContextVar。子 Agent 私有推理和全部模型文字仍不展示。

### 6.3 FastAPI（backend/main.py）

- POST /api/chat：接收用户消息并启动主 Agent，立即返回 conversation_id/status。
- GET /api/chat/{conversation_id}/events：StreamingResponse 读取当前 Queue 并发送 SSE。
- SSE 断开不停止 Agent、重连不重新运行 Agent。
- 当前单对话仅支持一个 SSE 消费者；只保留未消费的事件，不做完整历史回放。任务已结束时，如果 Queue 为空或只剩结束标记 None，断线重连可返回最后的问题/结果/错误快照。

## 7. 前端设计

采用 Vue 3 + TypeScript。**左右两栏，无单独结果区。**

### 7.1 左边 ChatPanel

展示用户购物需求、主 Agent 提问与选项、用户回复、最终推荐及可公开的错误。最终结果作为主 Agent 的聊天消息显示，保留本次前端会话已有消息。

### 7.2 右边 ProgressPanel

展示主 Agent、子 Agent、工具的真实运行进度，例如委托比价、京东搜索、淘宝要求登录、工具返回错误。不展示私有推理，不伪造搜索状态。子 Agent 的工具开始/结束事件已经桥接；不展示内部推理或所有模型步骤。

### 7.3 Vue 状态

| 字段 | 作用 |
|---|---|
| chatMessages | 左侧聊天、提问、最终结果、错误 |
| progressEvents | 右侧实际运行进度 |
| conversationId | 原对话 ID |
| pendingQuestion | 正在等待用户答复的问题与选项 |
| isRunning | 当前主 Agent 是否运行，用于发送按钮 |

前端仅按事件类型展示，不负责购物策略。聊天和工具状态分别进入两个面板。

- App.vue 统一管理 messages、progressEvents、conversationId 和当前轮状态；新建对话仅清理前端，下一次消息带 null ID，由后端创建新 Agent。
- ChatPanel.vue 通过 props/emit 与 App.vue 通信；ProgressPanel.vue 只显示后端真实状态，不展示模型私有推理。
- services/api.ts 负责 POST /api/chat 和 HTTP 错误提示；useChatEvents.ts 负责 GET /api/chat/{conversation_id}/events，不自动 POST。
- 用户选择“登录淘宝”等选项通过原 conversation_id 发送给主 Agent，由主 Agent 自主调用 open_platform_login；前端不直接调用登录接口。
- 网络中断只允许用户主动重新订阅本轮 SSE，不重复发送上一个 POST；已被消费的 SSE 进度不保证完整回放。
- 当前前端聊天记录与后端 Session 均仅保存在内存中，页面刷新或后端重启后不保证恢复旧会话。


## 8. 浏览器设计

使用 BrowserManager 统一管理项目专用的 DrissionPage/Edge/Profile。

### 8.1 共享无头 Edge

- 全部对话共享一个 BrowserManager；搜索首次按需启动无头 Edge，之后复用。
- 京东、淘宝、拼多多工具各使用独立标签页，可并行搜索和读取。
- 仅在创建/关闭标签页时短暂加锁；页面导航与读取在锁外执行。
- 搜索完只关闭本工具标签页，**不关闭共享 Edge**。
- 共享无头 Edge 在后端服务退出时统一关闭（FastAPI lifespan 钩子）；多次搜索期间保持复用，避免反复启停浏览器。
- 工具层不截断网页正文，价格无真实证据不得编造。

### 8.2 人工登录与资源生命周期

- 人工登录用有头 Edge。普通搜索用无头 Edge；人工登录窗口仍打开时，登录状态检查在同一个有头 Edge 的临时标签页中进行。登录检查只确认是否已登录；确认成功后关闭登录窗口，再复用同一 Profile 启动无头搜索。
- 登录和搜索使用同一受管理 Profile，但不允许两个进程冲突占用。
- 打开有头登录窗口前必须结束正在搜索的标签页，关闭无头 Edge；关闭登录窗口后搜索可重新启动。
- 浏览器清理只操作项目自己的 Edge，不误杀用户窗口。
- 已完成并发标签页/登录互斥的模拟验证；真实网站搜索和登录仍需联调确认。

### 8.3 登录态检测与错误边界

- 登录态检测通过账号专属 DOM：京东检查账号昵称与退出链接；淘宝仅检查首页账号专属退出链接和账号安全入口，证据成立后直接返回 `authenticated=true`，**不再访问账号安全页进行二次验证**；拼多多检查受保护的个人中心及其账号功能区。
- `_wait_ready()` 只等待页面渲染，等待标记本身不作为登录证据；`_account_evidence()` 负责账号身份信号。
- 只有明确的登录身份信号返回 `authenticated=true`；未触发验证码/风控时，明确跳转登录页或登录提示返回 `false`。浏览器/网络异常、验证码/风控或页面没有足够证据时返回检测错误，不猜测登录状态。
- 检测和搜索都使用本项目的 `.edge-profile`。不读取或复用参考项目的 Profile；登录后正常复用当前 Profile。
- 比价子 Agent 必须把工具错误、页面异常和有效结果逐平台如实汇报给主 Agent。是否重试、询问用户或继续其他平台由主 Agent 决定。

### 8.4 登录窗口的人工介入与关闭

比价工具返回的页面内容明显异常（一直显示"加载中"、空列表、没有商品区域、页面与商品无关）且主 Agent 无法判断原因时，允许其主动请用户介入：

~~~text
比价工具返回异常页面
   ↓
主 Agent 调用 open_platform_login，打开该平台有头登录窗口
   ↓
request_user_input 请用户检查是否遇到滑块验证/风控并处理
   ↓
用户确认后调用 close_platform_login 关闭窗口
   ↓
重新搜索
~~~

- **窗口打开期间禁止搜索**：搜索会返回 `BROWSER_BUSY`，必须先关闭窗口。
- `close_platform_login` 是独立工具，主 Agent 可主动调用；用户放弃该平台时同样需要关闭窗口，否则 Profile 被占用。
- 页面价格脱敏（如淘宝显示 `¥2???`）属于平台正常展示策略，不作为异常处理，也不得据此编造价格。

### 8.5 运行期配置更新

- 主 Agent 注册了受限的 `Read` / `Edit` 文件工具，**只能读写项目根目录的 `.env`**，其他路径一律拒绝，避免改写代码或读取任意文件。
- 用户在对话中提供 Tavily Key 时，主 Agent 可用 `Edit` 写入 `.env`；`TavilySearchTool` 每次执行前调用 `Settings.reload()` 重新读取配置。
- `product_discovery_agent` 的必需配置预检改为**每次委托前动态求值**，写 Key 后同轮即可继续，无需重启后端。

## 9. SSE 通信协议

前端 POST /api/chat 提交消息，通过 EventSource 连接 GET /api/chat/{conversation_id}/events 收进度。

| 事件 type | 说明 | 前端 |
|---|---|---|
| agent_started | 主 Agent 开始执行 | 右侧 |
| tool_started | 工具或子 Agent 委托开始 | 右侧 |
| tool_completed | 工具或子 Agent 委托结束，status 指明成功/失败等 | 右侧 |
| ask_user | 主 Agent 正在等待用户答复 | 左侧 |
| final | 主 Agent 最终回答 | 左侧 |
| error | 当前轮执行错误 | 左侧 |

FastAPI 将 Queue 中的字典序列化为 SSE 的 data: JSON + 两个换行。Queue 的 None 仅用于结束本轮订阅，不发送到浏览器。

不自动重试 POST，不实现事件编号或多 SSE 消费者广播。重连不重新运行 Agent，但已消费进度不保证回放。子 Agent 内工具执行的开始/结束状态已通过显式回调桥接，其他细粒度模型事件未接入。

## 10. 新项目目录

~~~text
shopping_assistant_cg/
├── backend/
│   ├── main.py                 # FastAPI 消息及 SSE
│   ├── config.py
│   ├── app/
│   │   ├── session_manager.py  # 原主 Agent 与状态
│   │   ├── agent_runner.py     # 原生事件 → Queue
│   │   └── progress.py         # 每个对话独立的进度回调
│   ├── agents/
│   │   ├── common.py
│   │   ├── coordinator.py
│   │   ├── interactive.py
│   │   ├── delegation.py
│   │   ├── discovery.py
│   │   ├── comparison.py
│   │   └── recommendation.py
│   ├── tools/
│   │   ├── product_search.py
│   │   ├── platform_search.py
│   │   ├── platform_login.py
│   │   ├── open_platform_login.py  # 打开/关闭有头登录窗口
│   │   ├── env_file_tools.py       # 限定只能读写 .env 的 Read/Edit
│   │   ├── request_user_input.py
│   │   └── progress_tool.py    # 不改变工具结果的进度包装器
│   └── browser/
│       └── browser_manager.py
├── frontend/                    # Vue 3 + Vite 前端工程
│   └── src/
│       ├── components/
│       │   ├── ChatPanel.vue
│       │   └── ProgressPanel.vue
│       ├── services/
│       │   └── api.ts
│       └── App.vue
├── docs/
│   └── DESIGN.md
├── memory/traces/               # 运行 trace（不入库）
├── .env.example
└── README.md
~~~

不设 EventStore、TaskRecord、ResultPanel 或独立 RAG 模块。

## 11. 开发顺序

**先完整后端，再完整前端，最后真实联调。每一批代码先解释对应设计、提供易懂的行内注释，审核后再写入。** 不使用伪造的商品报价或工具成功结果。

### 第一阶段：完整后端

- 主 Agent 与三个真实子 Agent：商品发现、平台比价、推荐，按主 Agent 自主决策调用。
- HelloAgents 原生 ReActAgent/TaskTool/ToolRegistry/History；最小交互适配支持用户提问后等待。
- 真正接入 Tavily、京东、淘宝、拼多多、Calculator、登录检查与 request_user_input。
- BrowserManager 一浏览器多标签并行搜索、人工登录互斥。
- SessionManager + AgentRunner + Queue + FastAPI POST/SSE。
- 已完成：子 Agent 具体工具开始/结束事件桥接、后端平台登录接口及前端聊天请求 api.ts；人工登录选择通过 /api/chat 交给主 Agent 工具处理。
- 已完成真实联调：Tavily 商品发现、三平台登录检测、拼多多人工登录后比价、工具错误如实回传。
- 已知限制：淘宝搜索页在无头 Edge 下常返回"加载中"骨架屏或价格脱敏，属平台反自动化策略；工具会如实返回，由主 Agent 决定是否请用户介入。

**阶段验收：** 真实业务可执行、真实错误可传达、Agent 可以提问并续接，进度来自真实事件。模拟单元测试不替代真实验收。

### 第二阶段：完整前端

已实现 Vue 3 + TypeScript + Vite 双栏：ChatPanel 显示对话、Agent 提问与最终结果，ProgressPanel 显示真实进度；App.vue 管理发送、续接、新建对话与 SSE 断线手动重连；api.ts 仅负责普通 HTTP 请求、useChatEvents.ts 负责 SSE。人工登录由主 Agent 调用工具，前端不直接调用登录接口。前端运行构建与真实体验仍待联调验证。

### 第三阶段：前后端联调

以“预算一万元，推荐苹果手机并比较京东、淘宝、拼多多报价”为例，检查主 Agent 自主委托、工具证据与错误传播、询问用户后的续接、一个 Edge 三标签并行、登录互斥、左侧对话历史保留、右侧真实进度、上游 429 反馈及浏览器资源释放。

问题定位到对应 Agent、工具、后端或前端修复，不重建复杂状态系统。

## 12. 最终架构原则

**主 Agent 管购物决策，专业子 Agent 处理专项任务，真实工具执行，FastAPI 管通信，Vue 管展示，HelloAgents 管原生执行和历史。**

不重复实现 ReAct、聊天历史或 RAG；不写死购物分支、不伪造结果。后端保持 SessionManager + AgentRunner + Queue + FastAPI 的简洁设计；前端仅左右双栏。先完成真实可运行、可观察、可续接的核心能力，再按需求考虑持久化、事件回放等扩展。
