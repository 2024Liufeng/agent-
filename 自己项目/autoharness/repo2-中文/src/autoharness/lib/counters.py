"""会话计数器（CAP 触发：每次停止 +1，在 N 时重置）+ 每层请求计数器（MNG 分母：每轮 +1）。

每层单一实现； O(1) 读-修改-写，立即持久化（每个钩子都是一个
单独的短暂进程，内存中没有任何内容保存）。分子（调用计数）属于
sidecar（与符号一起跨层移动），不是在这里。存储库层中的实时会话计数
状态区域（cap.md：会话范围，写入此存储库的 .claude，而不是实时技能）。

马尾辫：并发多仓库写入下的全局请求计数器仍然不受保护；的
一个根的计数器现在通过 lib.lock 进行序列化，这也是这种情况的接缝。"""
import re

from autoharness.lib import atomic, layer, lock

_SAFE_SESSION = re.compile(r"^[A-Za-z0-9_-]+$")


def _read_int(p):
    try:
        return int(p.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return 0


def _bump(p, delta=1):
    """在独占锁下进行读-修改-写，以便并发钩子进程
    不能既读取相同的值又丢失增量。"""
    with lock.file_lock(p.with_suffix(p.suffix + ".lock")):
        value = _read_int(p) + delta
        atomic.write_text(p, str(value))
    return value


def request_count(lyr, root=None):
    return _read_int(layer.state_dir(lyr, root) / "requests")


def bump_request(lyr, root=None):
    return _bump(layer.state_dir(lyr, root) / "requests")


def _session_path(session_id, root=None):
    if not isinstance(session_id, str) or not _SAFE_SESSION.match(session_id):
        raise ValueError(f"unsafe session id: {session_id!r}")
    return layer.state_dir(layer.PROJECT, root) / f"session-{session_id}"


def session_count(session_id, root=None):
    return _read_int(_session_path(session_id, root))


def bump_session(session_id, root=None):
    return _bump(_session_path(session_id, root))


def reset_session(session_id, root=None):
    atomic.write_text(_session_path(session_id, root), "0")


def clear_session(session_id, root=None):
    p = _session_path(session_id, root)
    if p.exists():
        p.unlink()


def _offset_path(session_id, root=None):
    if not isinstance(session_id, str) or not _SAFE_SESSION.match(session_id):
        raise ValueError(f"unsafe session id: {session_id!r}")
    return layer.state_dir(layer.PROJECT, root) / f"offset-{session_id}"


def session_offset(session_id, root=None):
    return _read_int(_offset_path(session_id, root))


def write_session_offset(session_id, offset, root=None):
    atomic.write_text(_offset_path(session_id, root), str(int(offset)))
