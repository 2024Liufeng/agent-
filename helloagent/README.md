# HelloAgents 智能购物助手

这是一个基于 HelloAgents `ReActAgent` 的购物决策助手。它可以发现候选商品、读取淘宝、京东和拼多多的当前搜索页，并让 Agent 根据页面证据完成比价、推荐和购物清单计算。

完整的产品目标、四类 Agent 架构、三类业务流程和实现计划见 [统一项目设计文档](docs/PROJECT_DESIGN.md)。

当前核心链路已经跑通：三个平台通过独立的 DrissionPage Edge 会话搜索商品，工具返回页面可见正文，Agent 能从正文中识别商品、价格、规格、店铺和购买条件，并给出带证据边界的比较结果。

## 启动

```powershell
cd C:\Users\小敏\PycharmProjects\SpiderAgent\helloagent
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
# 编辑 .env，填写 LLM_API_KEY、LLM_BASE_URL 和模型名
python -m shopping_assistant
```

首次使用或会话失效时，先运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\login_platforms_drission.py
```

脚本使用独立的 `.drission-edge-profile` 打开三个平台。这个 profile 不与 Playwright 共用。登录完成后保持 Edge 会话可用，再启动 Agent。

## 当前架构

```text
ShoppingCoordinatorAgent（主 Agent）
   ├─ ProductDiscoveryAgent → ProductSearchTool / RAGTool
   ├─ PriceComparisonAgent → 京东 / 淘宝 / 拼多多工具（并行）
   └─ RecommendationAgent → 推荐、清单和预算
```

平台工具在一次比价任务中共享一个 Edge profile 和一个浏览器，三个平台分别使用不同标签页；三个工具完成后统一关闭浏览器。平台工具不依赖容易变化的商品卡片 XPath，也不在 Python 中猜测价格归属；比价 Agent 负责解析页面证据。

## 目录

```text
shopping_assistant/
├─ agent.py                 # ShoppingAssistantAgent 和系统提示词
├─ config.py                # LLM、Edge、profile 和超时配置
├─ service.py               # 应用层和记忆业务事件
├─ memory.py                # working/episodic/semantic 记忆
├─ rag.py                   # 商品知识库和 RAGTool
├─ schemas.py               # 领域数据结构
└─ tools/
   ├─ search.py             # ProductSearchTool
   ├─ drission_platform.py  # 淘宝、京东、拼多多页面工具
   └─ platform.py           # 旧 Playwright 实现，当前未注册
scripts/login_platforms_drission.py  # 登录三个平台并建立 Edge profile
data/traces/                         # HelloAgents 脱敏 trace
```

## 当前边界

- 已支持明确商品的三平台页面读取和 Agent 比价。
- 页面正文是浏览器渲染后的可见文字，包含导航、筛选、商品和价格文字，不包含 HTML、脚本、Cookie 或浏览器地址栏。
- 页面变化、登录失效或验证码仍可能导致某个平台不可用；工具会返回 `AUTH_REQUIRED` 或 `CAPTCHA_REQUIRED`。
- 没有稳定详情链接时，Agent 会明确说明链接缺失，不会猜链接。
- 当前不自动下单、支付、领券或执行不可逆操作。

最近一次完整验证已成功返回三个平台的明确价格，并区分容量、激活、版本和补贴条件。对应 trace 位于 `data/traces/`。

## 尚未完成的最终架构工作

核心可用不等于最终产品形态。后续需要补齐统一报价证据模型、页面就绪和会话健康检查、结果校验与回归测试、详情页补充读取、共享浏览器并发边界，以及更稳定的错误恢复和用户界面。
