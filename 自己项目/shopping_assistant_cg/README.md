# 智能购物助手（HelloAgents + FastAPI + Vue）

## 项目结构

- backend/main.py：FastAPI 聊天和 SSE 接口。
- backend/agents/coordinator.py：主 Agent 及三个子 Agent 的任务委派。
- backend/browser/browser_manager.py：受管理的 Edge 浏览器与登录状态检查。
- frontend/src/App.vue：聊天状态、选择题回复、SSE 订阅和进度分发。
- frontend/src/components/ChatPanel.vue：左侧聊天区。
- frontend/src/components/ProgressPanel.vue：右侧真实执行进度。
- frontend/src/services/api.ts：普通聊天 HTTP 请求。
- frontend/src/composables/useChatEvents.ts：SSE 事件订阅。
- docs/DESIGN.md：完整设计及接口协议。

## 首次准备（Windows）

当前开发机已准备本项目的 .env、独立 Python .venv 和前端依赖。不要把 .env 提交到 Git，也不要把密钥贴到聊天中。

在新电脑或重建环境时：

1. 将 .env.example 复制为 .env，填写 LLM_MODEL_ID、LLM_API_KEY、LLM_BASE_URL 和 EDGE_PATH。
2. 在项目根目录创建并安装 Python 环境：

       py -3.13 -m venv .venv
       .\.venv\Scripts\python.exe -m pip install -r requirements.txt

3. 安装前端依赖：

       cd frontend
       npm install

TAVILY_API_KEY 用于商品资料发现子 Agent。未配置时，product_search 会明确返回 MISSING_API_KEY；不要将其误判为真实搜索成功。

## 启动方式

后端：在项目根目录打开 PowerShell，运行：

    .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

前端：在项目的 frontend 目录打开另一个 PowerShell，运行：

    npm run dev

然后使用本机浏览器打开 http://127.0.0.1:5173 。

开发服务器将 /api 转发到 FastAPI 8000 端口，POST /api/chat 提交购物需求；
GET /api/chat/{conversation_id}/events 订阅实时进度。需要运行在支持有头 Edge 的本机桌面环境。

## 人工登录流程

比价前，主 Agent 先调用 check_platform_login 检查目标平台。明确未登录时，询问用户登录后继续还是跳过；浏览器/网络异常或页面证据不足属于检测失败，不得当成未登录。
用户选择「登录」后，答案仍走 POST /api/chat，主 Agent 自己决定调用 open_platform_login 工具。用户在弹出的有头 Edge 内完成操作后，在聊天中确认；主 Agent 再次检查真实页面，只有账号身份信号确认成功才继续。
比价子 Agent 必须如实报告工具错误、验证码、登录失效、无有效报价等结果；只有主 Agent 决定是否询问用户。前端不会直接调用登录 HTTP 接口，也不会把「窗口已打开」或「页面读取成功」当成登录/报价成功。

## 当前配置与验证状态

- 已配置本机模型接口与 Edge 路径；模型服务的 /models 返回 HTTP 200，配置中的模型 ID 存在于返回列表中。
- 已创建独立 Python .venv 并安装 requirements.txt 中的依赖。
- 已安装前端依赖并生成 frontend/package-lock.json。
- npm run build（包含 vue-tsc --noEmit）已通过。
- 后端配置读取、模块导入和聊天/SSE/登录路由检查已通过。
- 已完成真实端到端联调：Tavily 商品发现（真实来源）、三平台登录检测、拼多多人工登录后继续比价、推荐结论。
- 主 Agent 可通过受限的 Read/Edit 工具把用户给出的 TAVILY_API_KEY 写入本地 .env，写完即刻生效，无需重启后端。
- 遇到页面持续“加载中”等无法判断的异常时，主 Agent 可以打开对应平台的有头登录窗口，请用户检查是否有人机验证；用户处理完后用 close_platform_login 关闭窗口再继续。
- 已知限制：淘宝搜索页在无头 Edge 下常返回“加载中”骨架屏或价格脱敏（`¥2???`），属平台反自动化策略；工具会如实返回，不会编造价格。
- 对话与进度当前保存在内存中，后端重启或刷新浏览器后不保证恢复。SSE 断线时先点“重新连接进度”，不要重复提交任务；若后端已重启，可选择“放弃并新建对话”。
- 后端通过 FastAPI lifespan 在正常退出时关闭共享 Edge；进程被强制结束时仍可能残留，必要时手动清理占用 .edge-profile 的 msedge 进程。
