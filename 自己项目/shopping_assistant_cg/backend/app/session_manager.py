"""对话管理：一个 conversation_id 对应一个主 Agent，浏览器全局复用。"""

import asyncio
import uuid
from dataclasses import dataclass, field

from backend.agents.coordinator import build_coordinator
from backend.app.progress import ProgressReporter
from backend.browser.browser_manager import BrowserManager
from backend.config import Settings


@dataclass
class ChatSession:
    """一个对话的主 Agent、执行状态、以及前端进度消息。"""

    conversation_id: str          # 例如 chat001；后续消息带着它，才能找到原 Agent
    agent: object                 # 这个对话自己的 HelloAgents 主 Agent
    reporter: ProgressReporter = field(default_factory=ProgressReporter)  # 对话专属进度通道

    status: str = "idle"          # idle/running/waiting_user/completed/failed
    pending_input: dict | None = None  # Agent 等待用户回复的唯一问题

    # AgentRunner 负责放进度，SSE 接口负责取进度。
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    active_task: asyncio.Task | None = None  # 正在执行的主 Agent 协程，不是平台标签页
    result: str | None = None    # 主 Agent 最终回答
    error: str | None = None     # 适合给用户看的错误信息


class SessionManager:
    """负责创建对话，以及把新消息交给原来的主 Agent。"""

    def __init__(self):
        self.sessions: dict[str, ChatSession] = {}

        # 所有对话共享一个 BrowserManager：
        # 京东/淘宝/拼多多搜索工具共用一个无头 Edge，使用不同标签页。
        self.settings = Settings.from_env()
        self.browser = BrowserManager(self.settings)

    def get_or_create(self, conversation_id: str | None = None) -> ChatSession:
        # 第一次发消息没有 ID：创建新对话、新主 Agent。
        if conversation_id is None:
            conversation_id = uuid.uuid4().hex
            reporter = ProgressReporter()  # 新对话创建自己的进度回调
            session = ChatSession(
                conversation_id=conversation_id,
                agent=build_coordinator(
                    self.settings, self.browser, on_progress=reporter.emit,
                ),
                reporter=reporter,
            )
            self.sessions[conversation_id] = session
            return session

        # 后续发消息必须找到以前的对话，不能悄悄建一个没有历史的新 Agent。
        session = self.sessions.get(conversation_id)
        if session is None:
            raise KeyError("对话不存在，可能是后端重启导致会话丢失")
        return session

    def get(self, conversation_id: str) -> ChatSession | None:
        # 下一节 SSE 会用它找到当前对话的消息队列。
        return self.sessions.get(conversation_id)
