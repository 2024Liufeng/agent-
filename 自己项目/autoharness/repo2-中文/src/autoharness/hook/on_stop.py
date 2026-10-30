"""CAP触发（每轮判断）：停止钩子+递归防护+活动计数门，完全确定性，无LLM调用。

cap.md（方向 H）：分子是活动量程 - 工具调用，由
PreToolUse 的调度员 — 不是轮流。 stop只读取计数器并判断阈值
（一个沉重的转弯在结束时触发；仅限聊天的转弯永远不会推进计数器），发出一个触发器
一旦达到reflect_every_n，就会做出判决并重置。 Cadence故意保守
（阈值错误稀疏 - 降水是维持性的，而不是实时的；SessionEnd 刷新捕获
尾巴）。递归防护：反射器子会话的 Stop 不得重新触发反射
也不重置，否则无限的自我反省。错误/丢失会话 ID -> 无触发器（故障安全）。"""
import os

from autoharness import config
from autoharness.lib import counters


def on_stop(event, *, root=None, n=None):
    if os.environ.get(config.CHILD_SESSION_ENV):
        return {"triggered": False, "reason": "recursion_guard"}
    session_id = event.get("session_id")
    if not session_id:
        return {"triggered": False, "reason": "no_session"}
    n = n or config.REFLECT_EVERY_N
    try:
        count = counters.session_count(session_id, root)
    except ValueError:
        return {"triggered": False, "reason": "bad_session"}
    if count >= n:
        counters.reset_session(session_id, root)
        return {"triggered": True, "session_id": session_id, "window_n": n, "count": count}
    return {"triggered": False, "session_id": session_id, "count": count, "n": n}
