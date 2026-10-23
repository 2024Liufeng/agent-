"""运行主 Agent：把 HelloAgents 原生事件变为前端易懂的进度事件。"""

import asyncio
import json
import re

from backend.app.session_manager import ChatSession


def _decode_result(value) -> dict:
    """解析结构化工具结果，也识别 HelloAgents 的标准错误文本。"""
    if not isinstance(value, str):
        return value if isinstance(value, dict) else {}
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        # ToolResponse.error 在没有 data 时会输出此格式，而不是 JSON。
        match = re.match(r"^❌ 错误 \[([A-Z0-9_]+)\]:\s*(.*)$", value.strip(), re.DOTALL)
        if not match:
            return {}
        code, message = match.groups()
        return {
            "status": "error",
            "text": message,
            "error": {"code": code, "message": message},
        }


class AgentRunner:
    """start() 启动一轮执行；run() 负责接收原生事件并推送进度。"""

    def start(self, session: ChatSession, message: str) -> None:
        # 同一个主 Agent 不允许同时运行两轮，防止其历史被并发修改。
        if session.active_task is not None and not session.active_task.done():
            raise RuntimeError("主 Agent 正在执行，请等待本轮结束")

        # 用户回复 Agent 的问题时，仍交给原来的主 Agent。
        # 例如：Agent 问“登录还是跳过淘宝？”，用户回复“跳过”。
        if session.pending_input is not None:
            question = session.pending_input["question"]
            message = f"针对你刚才的问题「{question}」，我的回答是：{message}"
            session.pending_input = None

        session.queue = asyncio.Queue()  # 每轮新建进度队列，防止混入旧消息
        session.status = "running"
        session.result = None
        session.error = None

        # 让 run() 独立执行：HTTP POST 可以立即返回，不需要等购物任务完成。
        session.active_task = asyncio.create_task(self.run(session, message))

    async def run(self, session: ChatSession, message: str) -> None:
        pending_question = None
        final_answer = None

        # 绑定本轮 Queue。子 Agent 工具得到的是这个对话的 reporter.emit，
        # 所以即使有多个用户并行购物，进度也不会发送到其他对话。
        session.reporter.bind(asyncio.get_running_loop(), session.queue)

        try:
            # HelloAgents 每执行一步，就会产生原生事件。
            async for event in session.agent.arun_stream(message):
                event_type = event.type.value
                data = event.data

                if event_type == "agent_start":
                    await session.queue.put({
                        "type": "agent_started",
                        "text": "主 Agent 开始处理购物需求",
                    })

                elif event_type == "tool_call_start":
                    # 比如：主 Agent 开始调用 price_comparison_agent。
                    name = data.get("tool_name") or data.get("name")
                    if not name or name in {"Thought", "Finish"}:
                        continue  # 不显示内部推理和 Finish 工具

                    await session.queue.put({
                        "type": "tool_started",
                        "tool": name,
                        "text": f"{name} 开始执行",
                    })

                elif event_type == "tool_call_finish":
                    # 比如：比价子 Agent 已经返回搜索结果。
                    name = data.get("tool_name") or data.get("name")
                    if not name or name in {"Thought", "Finish"}:
                        continue

                    result = _decode_result(data.get("result"))
                    status = result.get("status", "unknown")

                    # 只把工具名称和状态推送前端；不泄露完整网页、Cookie 或密钥。
                    await session.queue.put({
                        "type": "tool_completed",
                        "tool": name,
                        "status": status,
                        "text": f"{name} 执行结束：{status}",
                    })

                    # Agent 主动提问时，保存真正由工具生成的问题。
                    if name == "request_user_input":
                        question = result.get("data")
                        if (
                            status == "success"
                            and isinstance(question, dict)
                            and question.get("question")
                        ):
                            pending_question = question

                elif event_type == "agent_finish":
                    if data.get("status") != "completed":
                        raise RuntimeError("Agent 本轮未正常完成")
                    final_answer = data.get("result")

            # 某些不可继续的前置配置错误由运行时强制暂停，而不是依赖模型自行决定。
            forced_question = getattr(session.agent, "pending_user_input", None)
            if (
                pending_question is None
                and isinstance(forced_question, dict)
                and forced_question.get("question")
            ):
                pending_question = forced_question
                session.agent.pending_user_input = None

            if pending_question is not None:
                # 情况 A：本轮已经提问，等待用户回复。
                session.pending_input = pending_question
                session.status = "waiting_user"
                await session.queue.put({
                    "type": "ask_user",
                    "question": pending_question["question"],
                    "kind": pending_question.get("kind", "text"),
                    "options": pending_question.get("options", []),
                })
            else:
                # 情况 B：主 Agent 正常完成，输出购物推荐。
                if not final_answer:
                    raise RuntimeError("Agent 没有生成最终回答")
                session.status = "completed"
                session.result = final_answer
                await session.queue.put({"type": "final", "text": final_answer})

        except Exception as exc:
            # 不直接把原始异常发给浏览器，避免泄露上游密钥和请求细节。
            detail = str(exc).lower()
            if "429" in detail or "rate limit" in detail or "rate_limit" in detail:
                public_error = "上游模型限流（429），请稍后重试"
            else:
                public_error = f"Agent 执行失败：{type(exc).__name__}"

            session.status = "failed"
            session.error = public_error
            await session.queue.put({"type": "error", "text": public_error})

        finally:
            session.reporter.clear()  # 当前轮结束，不再接收工具进度
            # 结束当前轮 SSE。None 是队列结束标记，不是用户可见事件。
            await session.queue.put(None)
