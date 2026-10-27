# 自动化深度研究智能体 — 架构设计

**技术栈：** HelloAgents 0.2.9 + FastAPI + Vue 3 + TypeScript

**项目目录：** `deepresearch_agent/`

---

## 1. 项目是什么

输入一个研究主题，输出一份带引用的 Markdown 报告。

```
"调研 2025 年大模型多模态能力"
    ↓
拆成 3~5 个子任务 → 逐个搜索真实网页 → 提炼要点 → 汇总成报告
```

和单次问答的区别：**检索真实发生**（每条结论对应 URL）、**过程可见**（能看到做到哪一步）、**产物可复用**（每个子任务笔记落盘）。

---

## 2. 整体结构

```
Vue 3 (5174)  ──HTTP/SSE──  FastAPI (8001)  ──  DeepResearchAgent
                                                      │
                                    ┌─────────────────┼─────────────────┐
                              研究规划专家       任务总结专家       报告撰写专家
                                                      │
                                      SearchTool（搜索） + NoteTool（笔记）
                                                      │
                                        Tavily / DuckDuckGo 等 + LLM
```

**四层职责**：

| 层 | 做什么 | 不做什么 |
|---|---|---|
| 前端 | 输入主题、订阅 SSE、渲染进度和报告 | 不做规划、不调搜索 |
| FastAPI | 路由、SSE 封包、错误兜底 | 不存业务状态 |
| Agent 层 | 规划、总结、写报告 | 不碰 HTTP |
| 工具/外部 | 真实检索与生成 | — |

**两个关键约束**：
- 每个请求新建一个 `DeepResearchAgent`，用完即弃——不做跨请求复用
- `SearchTool` 是模块级单例，跨请求共享

---

## 3. 核心设计：TODO 驱动

系统的骨架是**把大问题拆小，逐个解决，最后汇总**。

### 三个阶段

```
① 规划：研究规划专家
     主题 → 3~5 个子任务（title / intent / query）
        ↓
② 执行：对每个子任务
     搜索 → 格式化上下文 → 任务总结专家提炼 → 写笔记
        ↓
③ 报告：报告撰写专家
     所有任务的总结与笔记 → 五段式 Markdown 报告
```

### 为什么这样拆

| 好处 | 说明 |
|---|---|
| 检索可控 | 每个任务自带 `query`，执行时不再由模型临场决定搜什么 |
| 进度可见 | 按 `task_id` 独立更新状态，前端能画看板 |
| 失败隔离 | 某任务搜不到就标记 `skipped`，不影响其他任务 |
| 上下文可控 | 每次只把一个任务的搜索结果喂给模型，不会撑爆窗口 |

### 任务数量为什么是 3~5

写死在提示词里。少于 3 个覆盖面不够，多于 5 个既费时间又产生重复内容。

---

## 4. 三个 Agent

三者代码完全一样，都是 `ToolAwareSimpleAgent`，共用同一个 LLM 实例和工具表。**差别只在提示词。**

```python
ToolAwareSimpleAgent(
    name=name,
    llm=self.llm,                          # 共用
    system_prompt=system_prompt,           # ← 唯一的差异
    tool_registry=self.tools_registry,     # 共用
    tool_call_listener=self._tool_tracker.record,
)
```

| Agent | 输入 | 输出 | 提示词核心约束 |
|---|---|---|---|
| 研究规划专家 | 主题 + 日期 | `List[TodoItem]` | 3~5 个任务；强制 JSON；必须建笔记 |
| 任务总结专家 | 任务 + 搜索结果 | Markdown 总结 | 3~5 条关键发现；先读笔记再更新；禁留工具指令 |
| 报告撰写专家 | 所有任务信息 | Markdown 报告 | 五段固定结构；逐个读取笔记 |

**生命周期差异**：规划和报告 Agent 常驻；总结 Agent **每个任务新建一个**，用完丢弃，避免上一个任务的检索内容污染下一个。

---

## 5. 关键机制：笔记即共享状态

这是整个系统最值得说的设计。

### 问题

三个 Agent 是独立的实例，怎么共享“任务做到哪了”？

### 做法

不用 Python 变量传，而是让 Agent 自己写笔记：

```
规划阶段：创建 task_state 笔记，tags = ["deep_research", "task_1"]
    ↓
总结阶段：先读笔记，追加总结，再写回
    ↓
报告阶段：按 note_id 逐个读取，整合成报告，最后存成 conclusion 笔记
```

**笔记 ID 通过 `task_1` 这样的 tag 约定关联**，不需要额外维护映射表。

### 为什么值得这样做

| | 只用内存变量 | 用笔记 |
|---|---|---|
| 上下文完整度 | 只有摘要 | 完整内容可反复读取 |
| 进程重启 | 全丢 | 落盘保留 |
| 可追溯 | 困难 | 每个任务有独立文件 |

代价是：模型必须乖乖按 `[TOOL_CALL:note:{...}]` 格式调用，所以提示词里反复强调格式，代码里还有 `strip_tool_calls()` 做兜底清理。

---

## 6. 协调器怎么串流程

`DeepResearchAgent` 只做编排。**前端实际入口是 `run_stream()`**（`POST /research/stream`）：

```python
def run_stream(self, topic):
    state = SummaryState(research_topic=topic)

    # ① 规划
    state.todo_items = self.planner.plan_todo_list(state)
    yield {"type": "todo_list", "tasks": [...]}          # 先把任务列表推给前端

    # ② 执行：每个任务一个线程
    for task in state.todo_items:
        Thread(target=worker, args=(task, step)).start()

    # 从 Queue 取事件，边跑边推
    while finished_workers < active_workers:
        yield event

    # ③ 报告
    report = self.reporting.generate_report(state)
    yield {"type": "final_report", "report": report}
    yield {"type": "done"}
```

### 为什么用多线程 + Queue

每个任务是**搜索 + 一次 LLM 总结**，串行时 5 个任务要等 5 轮。开线程并行后总耗时取决于最慢的任务。

线程和主流程的沟通方式：各线程把事件（工具调用、任务状态、总结片段）塞进同一个 `Queue`，主线程从 `Queue` 取出来 `yield` 给 SSE。这样**线程负责干活，主线程只转发**，不会阻塞生成器。

多线程并发写 `state.web_research_results` 和 `research_loop_count`，所以加了 `_state_lock`。

### 单任务逻辑

抽成 `_execute_task()`，因为 `run()` 和 `run_stream()` 都要用：

```
搜索 → 格式化上下文 → 总结 → 更新 state → 推事件
```

### 两种模式对比

| 模式 | 入口 | 执行 | 用途 |
|---|---|---|---|
| **流式** | `run_stream()` | 多线程并行 + Queue 推送 | **前端实际使用** |
| 同步 | `run()` | 串行，结束后一次性返回 | `POST /research` 备用 |

---

## 7. 搜索与工具

### SearchTool

按 `SEARCH_API` 配置切换后端（tavily / duckduckgo / perplexity / searxng）。统一返回结构：

```json
{
  "results": [{"title": "...", "url": "...", "content": "..."}],
  "backend": "tavily",
  "answer": null,
  "notices": []
}
```

拿到结果后 `prepare_research_context()` 做两件事：去重（按 URL）+ 格式化（限制单来源 token 数，防止上下文超限）。

### NoteTool

笔记的增删改查。研究流程用到三种 `note_type`：

| 类型 | 谁创建 | 用途 |
|---|---|---|
| `task_state` | 规划 / 总结 | 单个任务的过程记录 |
| `conclusion` | 报告 | 最终结论沉淀 |

### ToolCallTracker

所有 Agent 的工具调用都经过它记录，转成 SSE 事件推给前端。这样用户能看到“正在读笔记”“正在写笔记”这类真实动作。

---

## 8. 前端

单文件 `App.vue`（2304 行），三个区域：

| 区域 | 内容 |
|---|---|
| 输入区 | 主题输入 + 搜索引擎选择 |
| TODO 看板 | 每个任务一张卡片，状态 `pending → in_progress → completed` |
| 报告区 | 实时日志 + 最终报告 Markdown 渲染 |

**SSE 事件驱动**：前端不轮询，收到事件就更新对应任务卡片。

---

## 9. 技术选型

| 选择 | 原因 |
|---|---|
| `hello-agents==0.2.9` | 提供 `ToolAwareSimpleAgent` 和 `NoteTool`，1.x 已移除 |
| 不用 function calling | 0.2.9 的工具体系基于 `[TOOL_CALL:...]` 文本协议 |
| 非 LangGraph | 流程简单（三阶段线性），自写协调器足够，依赖更少 |
| Vue 单文件 | 状态集中在 App.vue，组件拆分收益不大 |

---

## 10. 已知限制

| 限制 | 影响 |
|---|---|
| 无持久化任务队列 | 请求中断则本次研究丢失 |
| 单机单进程 | 无法水平扩展 |
| 串行或线程级并行 | 任务多耗时，无线程池限流 |
| 依赖模型遵守文本协议 | 模型不听话时需要代码兜底 |
