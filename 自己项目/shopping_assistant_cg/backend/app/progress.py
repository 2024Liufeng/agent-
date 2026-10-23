"""每个对话的进度发送器：显式传入子 Agent，不需要全局 ContextVar。"""

import asyncio
from threading import Lock


class ProgressReporter:
    """绑定当前轮次的 Queue，跨线程安全报告实际工具事件。"""

    def __init__(self):
        self._lock = Lock()
        self._loop = None
        self._queue = None

    def bind(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        # AgentRunner 每轮开始时，把本轮 Queue 显式绑定给这个对话。
        with self._lock:
            self._loop = loop
            self._queue = queue

    def emit(self, event: dict) -> None:
        # 子 Agent 可以在工作线程中执行，这里先取得绑定的事件循环。
        with self._lock:
            loop, queue = self._loop, self._queue

        if loop is None or queue is None:
            return  # 当前对话没有运行的任务，忽略进度

        # asyncio.Queue 不应直接跨线程 put。
        # 通过所属的事件循环安全投递，绝不包含工具原始输出。
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            pass  # 服务关闭时 loop 可能已经关闭，不再投递

    def clear(self) -> None:
        # 任务结束，解除当前轮次的 Queue 绑定。
        with self._lock:
            self._loop = None
            self._queue = None
