import os

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain.messages import HumanMessage
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver

from memory.long_term.context import Context
from memory.long_term.store import store
from tools.memory import save_user_memory


os.environ["DEEPSEEK_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")


model = ChatDeepSeek(
    model="deepseek-chat",
    temperature=0,
)


CHAT_SYSTEM_PROMPT = """
这是围绕你所创建的一份研究报告进行的对话。
请根据给定的上下文和研究报告回答问题。
你的回答必须包含基于该研究报告的引用。

研究报告：
{report}
"""


class ChatAgentWithMemory:
    def __init__(self, report: str):
        self.report = report
        system_prompt = CHAT_SYSTEM_PROMPT.format(
            report=self.report
        )

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
            memory_info = "\n".join(
                memory.value["data"]
                for memory in memories
            )

            base_prompt = (
                request.system_message.text
                if request.system_message
                else ""
            )

            return (
                f"{base_prompt}\n\n"
                "用户长期记忆：\n"
                f"{memory_info}"
            )

        self.agent = create_agent(
            model=model,
            tools=[save_user_memory],
            system_prompt=system_prompt,
            context_schema=Context,
            checkpointer=InMemorySaver(),
            store=store,
            middleware=[
                prompt_with_memory,
            ],
        )

    async def chat(
        self,
        messages: list[dict],
        thread_id: str,
        user_id: str,
    ) -> tuple[str, list[dict]]:
        """处理本轮新增消息；历史消息由 Checkpointer 根据 thread_id 恢复。"""
        tool_calls_metadata = []

        async with await self.agent.astream_events(
            {"messages": messages},
            config={
                "configurable": {
                    "thread_id": thread_id,
                }
            },
            context=Context(user_id=user_id),
            version="v3",
        ) as stream:
            async for item in stream.tool_calls:
                async for _ in item.output_deltas:
                    pass

                tool_result = str(item.output.content)

                tool_calls_metadata.append(
                    {
                        "tool": item.tool_name,
                        "args": item.input,
                        "call_id": item.tool_call_id,
                        "result": (
                            tool_result[:200] + "..."
                            if len(tool_result) > 200
                            else tool_result
                        ),
                    }
                )

            final_state = await stream.output()
            ai_message = final_state["messages"][-1].content

        return ai_message, tool_calls_metadata
