"""Async task and event orchestration for the local web application."""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


TERMINAL_EVENTS = {"completed", "failed"}


@dataclass
class TaskRecord:
    task_id: str
    query: str
    status: str = "queued"
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: set[asyncio.Queue[dict[str, Any] | None]] = field(default_factory=set)
    result: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "query": self.query,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskManager:
    def __init__(self, service_factory: Callable[[], Any] | None = None):
        self.tasks: dict[str, TaskRecord] = {}
        self.service_factory = service_factory

    def create(self, query: str) -> TaskRecord:
        task = TaskRecord(task_id=uuid.uuid4().hex, query=query.strip())
        self.tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        return self.tasks.get(task_id)

    async def publish(self, task: TaskRecord, event_type: str, data: Any) -> dict[str, Any]:
        event = {
            "id": len(task.events) + 1,
            "task_id": task.task_id,
            "type": event_type,
            "timestamp": time.time(),
            "data": data,
        }
        task.events.append(event)
        task.updated_at = event["timestamp"]
        if event_type == "completed":
            task.status = "completed"
            task.result = data.get("result", "") if isinstance(data, dict) else str(data)
        elif event_type == "failed":
            task.status = "failed"
            task.error = data.get("error", "任务执行失败") if isinstance(data, dict) else str(data)
        elif event_type in {"user_input_required", "auth_required"}:
            task.status = "waiting_user"
        elif event_type == "progress" and task.status == "queued":
            task.status = "running"
        for queue in list(task.subscribers):
            await queue.put(event)
        if event_type in TERMINAL_EVENTS:
            for queue in list(task.subscribers):
                await queue.put(None)
        return event

    async def run(self, task: TaskRecord) -> None:
        await self.publish(task, "progress", {"message": "已创建任务，准备调用购物 Agent"})
        await self.publish(task, "tool_started", {"name": "ShoppingAssistantService", "message": "开始分析需求"})
        try:
            if self.service_factory is None:
                from shopping_assistant.service import ShoppingAssistantService
                factory = ShoppingAssistantService
            else:
                factory = self.service_factory
            service = factory()
            answer = await asyncio.to_thread(service.ask, task.query)
            text = str(answer)
            await self.publish(task, "tool_completed", {"name": "ShoppingAssistantService", "message": "Agent 已返回结果"})
            # The service currently returns a complete string. The event contract
            # also supports true token streaming when the model adapter provides it.
            await self.publish(task, "assistant_delta", {"content": text, "streaming": False})
            await self.publish(task, "completed", {"result": text})
        except Exception as exc:  # the UI must receive a readable terminal event
            await self.publish(task, "failed", {"error": f"{type(exc).__name__}: {exc}"})

    async def subscribe(self, task: TaskRecord):
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        for event in task.events:
            yield event
        if task.events and task.events[-1]["type"] in TERMINAL_EVENTS:
            return
        task.subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
        finally:
            task.subscribers.discard(queue)

    async def send_message(self, task: TaskRecord, message: str) -> None:
        await self.publish(task, "progress", {"message": "收到补充信息，继续处理"})
        await self.publish(task, "user_message", {"content": message})
        if task.status == "waiting_user":
            task.status = "running"

