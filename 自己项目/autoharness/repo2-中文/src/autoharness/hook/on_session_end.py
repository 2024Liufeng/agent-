"""CAP 触发（总结）：SessionEnd 刷新剩余部分 + 自删除会话计数器。

cap.md：如果不刷新，低于阈值的尾部将永远丢失；所以在会话结束时计数 > 0 意味着
有剩余需要反思，并且**当前计数值告诉 REF 到底要喂多少**
（窗口 N == 计数，而不是阈值）。然后，会话计数器会随会话的
生命周期。递归防护与 on_stop 相同：反射器子会话的 SessionEnd 不会刷新。

马尾辫：崩溃会话的孤立计数器在 SessionStart 上延迟 GC（在第 6 阶段构建此文件时着陆，cap.md 打开）。"""
import os

from autoharness import config
from autoharness.lib import counters


def on_session_end(event, *, root=None):
    if os.environ.get(config.CHILD_SESSION_ENV):
        return {"triggered": False, "reason": "recursion_guard"}
    session_id = event.get("session_id")
    if not session_id:
        return {"triggered": False, "reason": "no_session"}
    try:
        count = counters.session_count(session_id, root)
    except ValueError:
        return {"triggered": False, "reason": "bad_session"}
    counters.clear_session(session_id, root)
    if count > 0:
        return {"triggered": True, "session_id": session_id, "window_n": count, "count": count}
    return {"triggered": False, "session_id": session_id, "count": 0}
