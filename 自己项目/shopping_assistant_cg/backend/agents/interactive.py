"""主 Agent 提问后结束当前执行轮次；保留 HelloAgents 原生 ReAct 与历史。"""

import json
from contextlib import aclosing

from hello_agents import ReActAgent


class InteractiveCoordinatorAgent(ReActAgent):
    """request_user_input 成功后，本轮等待用户；不是结束整个购物目标。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 主 Agent 顺序调用工具：不能刚问用户就并行继续做其他操作。
        # 比价子 Agent 仍保留框架默认的并发工具能力。
        self._parallel_tools = False
        self.pending_user_input = None  # 运行时发现致命配置错误时，交给 AgentRunner 暂停本轮

    async def _run_loop(self, messages, packets, stream, kwargs):
        self.pending_user_input = None  # 每轮清空，避免把上一轮的问题带入新一轮
        # 原生 ReAct 循环负责模型调用/工具执行/默认截断/历史管理。
        async with aclosing(
            super()._run_loop(messages, packets, stream, kwargs)
        ) as source:
            async for event in source:
                yield event  # 真实事件照常交给 AgentRunner

                if event.get("kind") != "tool_finish":
                    continue

                try:
                    result = json.loads(event.get("result", ""))
                except (ValueError, TypeError):
                    result = {}
                if not isinstance(result, dict):
                    result = {}

                name = event.get("name")
                payload = result.get("data")
                error_info = result.get("error")
                error_code = (
                    payload.get("code") if isinstance(payload, dict) else None
                ) or (
                    error_info.get("code") if isinstance(error_info, dict) else None
                )

                # 缺少 Tavily Key 是已确认的致命前置条件错误。
                # 即使模型在同一批工具调用里还请求了比价，也必须先停下并询问用户。
                if (
                    name == "product_discovery_agent"
                    and result.get("status") == "error"
                    and (
                        error_code == "MISSING_API_KEY"
                        or (isinstance(payload, dict) and payload.get("fatal") is True)
                    )
                ):
                    question = (
                        "商品发现需要 Tavily API Key，但当前没有配置。你希望怎么继续？"
                    )
                    self.pending_user_input = {
                        "question": question,
                        "kind": "choice",
                        "options": [
                            {"id": "configure", "label": "先配置 Tavily Key，暂停任务"},
                            {"id": "skip_discovery", "label": "跳过商品发现，继续比价"},
                        ],
                    }

                    # 当前模型响应可能还包含 price_comparison_agent 等工具调用。
                    # 为所有未执行的调用补齐 tool 消息，然后关闭本轮，防止它们继续运行。
                    calls = next(
                        (
                            message["tool_calls"]
                            for message in reversed(messages)
                            if message.get("role") == "assistant"
                            and message.get("tool_calls")
                        ),
                        [],
                    )
                    answered = {
                        message.get("tool_call_id")
                        for message in messages
                        if message.get("role") == "tool"
                    }
                    for call in calls:
                        if call["id"] not in answered:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": call["id"],
                                "content": "因缺少必需配置，当前轮已暂停，未执行该工具。",
                            })

                    self.last_run.answer = question
                    self.last_run.status = "completed"
                    messages.append({
                        "role": "assistant",
                        "content": "检测到必需配置缺失，已暂停后续购物操作并等待用户选择。",
                    })
                    return

                if name != "request_user_input":
                    continue  # 其他工具正常运行

                if (
                    not isinstance(result, dict)
                    or result.get("status") != "success"
                    or not isinstance(result.get("data"), dict)
                    or not result["data"].get("question")
                ):
                    continue  # 提问失败时，让 Agent 自己决定如何处理

                # 如果模型同一轮还请求了其他工具，标记为未执行。
                # 避免留下一条没有对应 tool 消息的原生工具调用。
                calls = next(
                    (
                        message["tool_calls"]
                        for message in reversed(messages)
                        if message.get("role") == "assistant"
                        and message.get("tool_calls")
                    ),
                    [],
                )
                answered = {
                    message.get("tool_call_id")
                    for message in messages
                    if message.get("role") == "tool"
                }
                for call in calls:
                    if call["id"] not in answered:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": "等待用户回复，未执行该工具",
                        })

                # 标记“本轮正常结束”，下一轮仍然使用同一个 Agent 历史。
                # Session 的业务状态会由 AgentRunner 设成 waiting_user。
                self.last_run.answer = result["data"]["question"]
                self.last_run.status = "completed"
                messages.append({
                    "role": "assistant",
                    "content": "已向用户提出问题，等待用户回答。",
                })
                return
