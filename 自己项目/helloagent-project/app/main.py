"""FastAPI entrypoint for the local shopping assistant web app."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from shopping_assistant.config import AppConfig

from .task_manager import TaskManager, TaskRecord


class TaskCreate(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class MessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
task_manager = TaskManager()
app = FastAPI(title="智能购物助手", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _task_or_404(task_id: str) -> TaskRecord:
    task = task_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "shopping-assistant"}


@app.get("/api/platforms/status")
async def platform_status() -> dict[str, Any]:
    config = AppConfig.from_env()
    profile_exists = config.drission_profile.exists()
    return {
        "headless": config.drission_headless,
        "profile_exists": profile_exists,
        "platforms": [
            {"id": key, "name": name, "status": "profile_ready" if profile_exists else "login_required"}
            for key, name in (("jd", "京东"), ("taobao", "淘宝"), ("pdd", "拼多多"))
        ],
    }


@app.post("/api/platforms/{platform}/login")
async def platform_login(platform: str) -> dict[str, str]:
    if platform not in {"jd", "taobao", "pdd"}:
        raise HTTPException(status_code=404, detail="不支持的平台")
    script = PROJECT_ROOT / "scripts" / "login_platforms_drission.py"
    try:
        subprocess.Popen([sys.executable, str(script)], cwd=str(PROJECT_ROOT))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"无法启动登录浏览器：{exc}") from exc
    return {"status": "manual_login_required", "platform": platform, "message": "已打开本机可见 Edge 窗口，请完成平台登录；完成后回到对话框发送“继续”。"}


@app.post("/api/tasks", status_code=202)
async def create_task(payload: TaskCreate) -> dict[str, Any]:
    task = task_manager.create(payload.query)
    import asyncio
    asyncio.create_task(task_manager.run(task))
    return {"task_id": task.task_id, "status": task.status}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    return _task_or_404(task_id).snapshot()


@app.get("/api/tasks/{task_id}/events")
async def task_events(task_id: str) -> StreamingResponse:
    task = _task_or_404(task_id)

    async def stream():
        async for event in task_manager.subscribe(task):
            yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/tasks/{task_id}/messages")
async def send_message(task_id: str, payload: MessageCreate) -> dict[str, str]:
    task = _task_or_404(task_id)
    await task_manager.send_message(task, payload.message)
    return {"status": "accepted"}


@app.post("/api/tasks/{task_id}/resume")
async def resume_task(task_id: str) -> dict[str, str]:
    task = _task_or_404(task_id)
    task.status = "running"
    await task_manager.publish(task, "progress", {"message": "任务已恢复"})
    return {"status": "resumed"}


frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
