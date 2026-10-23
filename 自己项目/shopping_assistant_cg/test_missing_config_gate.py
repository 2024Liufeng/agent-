import asyncio
import json
from types import SimpleNamespace

from hello_agents import ReActAgent

from backend.agents.delegation import NamedTaskTool
from backend.agents.interactive import InteractiveCoordinatorAgent
from backend.app.agent_runner import _decode_result


def test_preflight_error_is_structured_and_does_not_create_subagent():
    factory_calls = []
    tool = NamedTaskTool(
        name="product_discovery_agent",
        description="search products",
        agent_factory=lambda: factory_calls.append(True),
        preflight_error=("MISSING_API_KEY", "Tavily API Key 未配置"),
    )

    response = tool.run({"task": "搜索真实商品"})
    result = json.loads(response.to_model_text())

    assert result["status"] == "error"
    assert result["error"]["code"] == "MISSING_API_KEY"
    assert result["data"]["fatal"] is True
    assert result["data"]["code"] == "MISSING_API_KEY"
    assert factory_calls == []


def test_progress_decoder_recognizes_hello_agents_error_text():
    result = _decode_result("❌ 错误 [MISSING_API_KEY]: Tavily API Key 未配置")

    assert result["status"] == "error"
    assert result["error"]["code"] == "MISSING_API_KEY"


def test_missing_tavily_error_stops_remaining_tools_and_asks_user(monkeypatch):
    executed = []
    tool_calls = [
        {
            "id": "call_discovery",
            "type": "function",
            "function": {
                "name": "product_discovery_agent",
                "arguments": '{"task":"搜索商品"}',
            },
        },
        {
            "id": "call_comparison",
            "type": "function",
            "function": {
                "name": "price_comparison_agent",
                "arguments": '{"task":"比较价格"}',
            },
        },
    ]
    error_result = json.dumps(
        {
            "status": "error",
            "text": "Tavily API Key 未配置",
            "data": {
                "code": "MISSING_API_KEY",
                "message": "Tavily API Key 未配置",
                "fatal": True,
            },
            "error": {
                "code": "MISSING_API_KEY",
                "message": "Tavily API Key 未配置",
            },
        },
        ensure_ascii=False,
    )

    async def fake_base_loop(self, messages, packets, stream, kwargs):
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        })
        messages.append({
            "role": "tool",
            "tool_call_id": "call_discovery",
            "content": error_result,
        })
        yield {
            "kind": "tool_finish",
            "name": "product_discovery_agent",
            "id": "call_discovery",
            "result": error_result,
            "step": 1,
        }
        executed.append("price_comparison_agent")
        yield {
            "kind": "tool_start",
            "name": "price_comparison_agent",
            "id": "call_comparison",
            "arguments": '{"task":"比较价格"}',
            "step": 1,
        }

    monkeypatch.setattr(ReActAgent, "_run_loop", fake_base_loop)
    agent = object.__new__(InteractiveCoordinatorAgent)
    agent.last_run = SimpleNamespace(answer="", status="running")
    messages = []
    seen = []

    async def consume():
        async for event in agent._run_loop(messages, [], False, {}):
            seen.append(event)

    asyncio.run(consume())

    assert executed == []
    assert len(seen) == 1
    assert agent.last_run.status == "completed"
    assert agent.pending_user_input["kind"] == "choice"
    assert [item["id"] for item in agent.pending_user_input["options"]] == [
        "configure",
        "skip_discovery",
    ]
    assert any(
        item.get("tool_call_id") == "call_comparison"
        and "未执行" in item.get("content", "")
        for item in messages
    )

def test_agent_runner_reports_error_and_waits_for_user():
    from backend.app.agent_runner import AgentRunner

    question = {
        "question": "商品发现需要 Tavily API Key，但当前没有配置。你希望怎么继续？",
        "kind": "choice",
        "options": [
            {"id": "configure", "label": "先配置 Tavily Key，暂停任务"},
            {"id": "skip_discovery", "label": "跳过商品发现，继续比价"},
        ],
    }

    class Reporter:
        def bind(self, loop, queue):
            pass

        def clear(self):
            pass

    class FakeAgent:
        async def arun_stream(self, message):
            yield SimpleNamespace(
                type=SimpleNamespace(value="agent_start"),
                data={},
            )
            yield SimpleNamespace(
                type=SimpleNamespace(value="tool_call_finish"),
                data={
                    "tool_name": "product_discovery_agent",
                    "result": "❌ 错误 [MISSING_API_KEY]: Tavily API Key 未配置",
                },
            )
            yield SimpleNamespace(
                type=SimpleNamespace(value="agent_finish"),
                data={"status": "completed", "result": "unused"},
            )

    agent = FakeAgent()
    agent.pending_user_input = question
    session = SimpleNamespace(
        agent=agent,
        reporter=Reporter(),
        queue=asyncio.Queue(),
        pending_input=None,
        status="running",
        result=None,
        error=None,
    )

    asyncio.run(AgentRunner().run(session, "帮我搜索手机"))

    events = []
    while not session.queue.empty():
        events.append(session.queue.get_nowait())

    assert session.status == "waiting_user"
    assert session.pending_input == question
    assert agent.pending_user_input is None
    assert any(
        event.get("type") == "tool_completed"
        and event.get("status") == "error"
        for event in events
    )
    assert any(
        event.get("type") == "ask_user"
        and event.get("options") == question["options"]
        for event in events
    )

