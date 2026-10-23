"""FastAPI 入口：聊天、实时 SSE 进度以及本机人工登录窗口。"""

import asyncio
import json
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.agent_runner import AgentRunner
from backend.app.session_manager import SessionManager
from backend.browser.browser_manager import BrowserBusyError


sessions = SessionManager()  # 所有 conversation_id 对应的主 Agent
runner = AgentRunner()       # 执行主 Agent 并把进度写到 Queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务关闭时释放本项目启动的 Edge。

    否则进程被强杀后 Edge 会残留并占住 .edge-profile，
    下次启动会因为 Profile 被占用而报 BrowserConnectError。
    """
    yield
    try:
        await asyncio.to_thread(sessions.browser.close)
    except BrowserBusyError:
        pass  # 仍有活动标签页，交给操作系统回收
    except Exception:
        pass


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str                     # 用户输入，例如“帮我比较 iPhone 17”
    conversation_id: str | None = None  # 首次不传，后续带原来的 ID


@app.post("/api/chat")
async def send_message(request: ChatRequest):
    """收到用户消息后立即启动主 Agent，不等待购物任务完全结束。"""

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    try:
        # 新聊天创建主 Agent；旧聊天找回原 Agent 和历史。
        session = sessions.get_or_create(request.conversation_id)
        runner.start(session, request.message.strip())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # 前端获得 ID 后，通过 SSE 接口订阅执行进度。
    return {
        "conversation_id": session.conversation_id,
        "status": session.status,
    }


@app.get("/api/chat/{conversation_id}/events")
async def stream_events(conversation_id: str):
    """前端订阅这个接口，持续接收 Agent 的执行进度。"""

    # 比如 GET /api/chat/chat001/events，就找到 chat001 的 Queue。
    session = sessions.get(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="对话不存在")

    queue = session.queue  # 此轮 AgentRunner 正在往这个 Queue 放进度

    def final_state_event():
        # 只返回已经保存的公开状态，不重启 Agent，不重新调用工具。
        if session.status == "waiting_user":
            return {"type": "ask_user", **(session.pending_input or {})}
        if session.status == "completed":
            return {"type": "final", "text": session.result}
        if session.status == "failed":
            return {"type": "error", "text": session.error}
        return None

    async def generate():
        # 本轮结束且 Queue 为空，重连时直接返回最终状态快照。
        if session.status in {"waiting_user", "completed", "failed"} and queue.empty():
            event = final_state_event()
            if event is not None:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            return

        sent_terminal = False
        while True:
            # AgentRunner 的 queue.put() 放事件；这里的 get() 负责取出。
            event = await queue.get()

            if event is None:
                # 极端断线场景：前一条 SSE 消费者已取走终止事件，
                # Queue 只剩 None，重连时也必须能拿到最后的公开状态。
                if not sent_terminal:
                    snapshot = final_state_event()
                    if snapshot is not None:
                        yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                return

            if event.get("type") in {"ask_user", "final", "error"}:
                sent_terminal = True
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 减少反向代理缓冲导致的进度延迟
        },
    )


@app.post("/api/platforms/{platform}/login/open")
async def open_platform_login(platform: str):
    """用户主动要求登录时，打开项目专用 Edge 的登录窗口。"""

    # 真实 Edge 启动、页面加载是同步阻塞操作：
    # 放进工作线程，不阻塞 FastAPI 的其他对话和 SSE。
    try:
        return await asyncio.to_thread(sessions.browser.open_login, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="不支持的平台") from exc
    except BrowserBusyError as exc:
        # 无头搜索仍在进行、或已有其他登录窗口。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        # 浏览器底层异常不直接返回用户，避免泄漏路径等细节。
        raise HTTPException(status_code=500, detail="打开登录窗口失败") from exc


@app.post("/api/platforms/login/close")
async def close_platform_login():
    """用户主动关闭项目登录窗口；关闭不代表已经成功登录。"""

    try:
        await asyncio.to_thread(sessions.browser.close_login)
    except BrowserBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="关闭登录窗口失败") from exc

    # 这里只表示窗口已经关闭，登录状态应通过真实页面另外验证。
    return {"status": "login_window_closed"}
