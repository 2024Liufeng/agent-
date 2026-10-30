import os
from collections.abc import Awaitable, Callable

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelRequest,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
    dynamic_prompt,
    wrap_tool_call,
)
from langchain.messages import HumanMessage, ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver

from memory.long_term.context import Context
from memory.long_term.store import store
from tools.browser import create_browser_tool
from tools.code import code_execution
from tools.database import create_database_tool
from tools.memory import save_user_memory
from tools.search import create_search_tool


os.environ["DEEPSEEK_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")


model = ChatDeepSeek(
    model="deepseek-v4-flash",
    temperature=0,
)

search_tool = create_search_tool(
    retriever="tavily",
    max_results=5,
)
SEARCH_TOOL_NAME = search_tool.name


@wrap_tool_call
async def handle_tool_errors(
    request: ToolCallRequest,
    handler: Callable[
        [ToolCallRequest],
        Awaitable[ToolMessage],
    ],
) -> ToolMessage:
    try:
        result = await handler(request)
        content = result.content
        if (
            content is None
            or (
                isinstance(content, str)
                and not content.strip()
            )
            or (
                isinstance(content, list)
                and not content
            )
        ):
            return ToolMessage(
                content="查询成功，但没有找到匹配的结果。请尝试更换关键词。",
                tool_call_id=request.tool_call["id"],
                name=request.tool_call["name"],
            )
        return result
    except Exception as e:
        return ToolMessage(
            content=f"Tool error: 工具调用失败，请检查输入后重试。({e})",
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
        )


RESEARCH_SYSTEM_PROMPT = """
你是资料研究助手。
你的任务是围绕用户给出的研究主题收集可引用资料。

要求：
1. 只基于工具返回的真实资料回答。
2. 不要编造 URL、标题、作者或数据。
3. 当前阶段只收集资料，不写最终研究报告。

"""


@dynamic_prompt
async def prompt_with_memory(request: ModelRequest) -> str:
    for message in reversed(request.state["messages"]):
        if isinstance(message, HumanMessage):
            user_message = message
            break

    user_id = request.runtime.context.user_id
    namespace = (user_id, "memories")

    memories = await request.runtime.store.asearch(
        namespace,
        query=user_message.content,
        limit=3,
    )
    info = "\n".join(memory.value["data"] for memory in memories)

    base_prompt = (
        request.system_message.text
        if request.system_message
        else ""
    )

    return (
        f"{base_prompt}\n\n"
        "用户长期记忆：\n"
        f"{info}"
    )


checkpointer = InMemorySaver()


def create_research_agent(researcher):
    browser_tool = create_browser_tool(
        researcher.browser_manager
    )
    database_tool = create_database_tool(
        researcher.database_manager
    )

    return create_agent(
        model=model,
        tools=[
            search_tool,
            database_tool,
            browser_tool,
            code_execution,
            save_user_memory,
        ],
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        context_schema=Context,
        checkpointer=checkpointer,
        store=store,
        middleware=[
            prompt_with_memory,
            ToolRetryMiddleware(
                max_retries=2,
                backoff_factor=2.0,
                initial_delay=1.0,
            ),
            handle_tool_errors,
            ToolCallLimitMiddleware(
                tool_name=SEARCH_TOOL_NAME,
                run_limit=3,
                thread_limit=5,
                exit_behavior="continue",
            ),
        ],
    )


async def get_research_sources(
    topic: str,
    thread_id: str,
    user_id: str,
    researcher,
) -> dict:
    research_agent = create_research_agent(researcher)

    return await research_agent.ainvoke(
        {"messages": [{"role": "user", "content": topic}]},
        config={"configurable": {"thread_id": thread_id}},
        context=Context(user_id=user_id),
    )
