# Research Assistant

Stage2 产出：资料研究助手。输入主题后自动搜索、筛选、总结并输出引用链接。

## 项目结构参考

本项目结构抽取 gpt-researcher 的核心命名和分层：

```text
research_assistant/
├─ main.py
├─ search_agent.py
├─ skills/
│  └─ researcher.py
├─ retrievers/
│  └─ tavily.py
├─ tools/
└─ memory/
```

对应关系：

```text
gpt_researcher/skills/researcher.py
-> research_assistant/skills/researcher.py

gpt_researcher/retrievers/tavily/tavily_search.py
-> research_assistant/retrievers/tavily.py
```

## Step 1: Search Agent

目标：

```text
用户输入 topic
-> Search Agent 调用 TavilySearch 工具
-> 处理失败、空结果、重复调用
-> 输出 search_response
```

主依据：复用 stage2 已学代码和资料。

- Goal2：`stage2/goal2/1_Tavily search.py`，把 TavilySearch 接成工具给 agent 调用。
- Goal4-1/4-2：`stage2/goal4/1_and_2_处理工具失败,空结果.py`，使用 `ToolRetryMiddleware` 和 `wrap_tool_call`。
- Goal4-3：`stage2/goal4/教学版_4-3_重复调用.md`，使用 `ToolCallLimitMiddleware`。

次依据：借鉴 gpt-researcher 的搜索器结构。

- `stage2/xm/gpt-researcher/gpt_researcher/retrievers/tavily/tavily_search.py`
- 抽取核心结构：

```python
search_response = [
    {"href": obj["url"], "body": obj["content"]} for obj in sources
]
```

当前 Search Agent 的结构化输出：

```python
[
    {"href": "...", "body": "..."}
]
```

注意：

- 搜索阶段只负责发现候选 URL 和搜索片段。
- 不在搜索阶段依赖 Tavily `raw_content`。
- 完整网页正文放到 Step 2 Content Extractor 处理。

## 开发顺序记录

当前先用 CLI 循环连接报告后对话，让 Goal3 的 Checkpointer 和 `thread_id`
进入主项目并可以实际验证。CLI 循环是当前 MVP 的入口层适配，不是
gpt-researcher 原有入口实现。
当前本地单用户阶段固定使用 Goal3 示例中的 `user_id="1"`，入口层升级时再替换为真实登录用户。

后续按以下顺序实现：

1. 长期 Store。
2. SourceCurator 来源去重与质量筛选。
3. 确定性引用校验。
4. 文件和数据库保存报告与记忆。
5. Python 工具。
6. 最后将入口层改为参考 gpt-researcher 的报告聊天 API 结构。

实现规则：业务能力优先复用 Stage2 Goal 的资料和代码；架构、结构、
职责与命名优先抽取 gpt-researcher 的核心实现；必要的工程适配要单独说明。


## 本地配置

运行前请在环境中配置所需的 `DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`、`TAVILY_API_KEY`；运行 AgentQL 调试脚本时还需配置 `AGENTQL_API_KEY`。请勿将实际密钥提交到仓库。
