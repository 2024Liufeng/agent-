"""一个工程根部的两道通道不得在排水沟内交错。

钩子是一个单独的短暂进程，因此“串行单写入器”仅在一个进程中有效。
并行工作树重新映射到一个根（lib/layer.py），并且终止的会话可以留下分离的会话
升级正在运行，因此同一状态目录上的两个排水管是正常情况而不是异常。
如果没有锁，每个通行证都会读取图书馆，而不会看到对方的技能，并且每个通行证都会落地。"""
import threading
import time

from autoharness.hook import promoter
from autoharness.lib import intent_queue

GOOD_BODY = "---\nname: foo\ndescription: Use when formatting a date as ISO.\n---\n# Foo\nUse strftime.\n"


def _roots(tmp_path):
    return {"global": tmp_path / "g", "project": tmp_path / "p"}


def _create(name="foo"):
    return {"action": "create", "name": name, "level": "project", "body": GOOD_BODY,
            "reason": "captured repeat", "evidence": "led slice"}


def _wait(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)

    return False


def test_concurrent_drains_do_not_interleave(tmp_path, monkeypatch):
    roots = _roots(tmp_path)
    proot = roots["project"]
    intent_queue.append("run-a", _create("alpha"), proot)
    intent_queue.append("run-b", _create("beta"), proot)

    inside = threading.Event()
    release = threading.Event()
    entered = []

    real_promote = promoter.promote

    def blocking_promote(intent, **kwargs):
        entered.append(intent["name"])
        inside.set()
        release.wait(timeout=5.0)
        return real_promote(intent, **kwargs)

    monkeypatch.setattr(promoter, "promote", blocking_promote)

    first = threading.Thread(target=promoter.drain, args=("run-a",), kwargs={"roots": roots})
    first.start()
    assert inside.wait(timeout=5.0), "first drain never reached promote"

    second = threading.Thread(target=promoter.drain, args=("run-b",), kwargs={"roots": roots})
    second.start()

    # 第二个耗尽必须仍在等待锁，而不是并行读取库。
    assert not _wait(lambda: len(entered) > 1, timeout=0.5), "drains interleaved inside the critical section"

    release.set()
    first.join(timeout=5.0)
    second.join(timeout=5.0)

    assert not first.is_alive() and not second.is_alive()
    assert sorted(entered) == ["alpha", "beta"]


def test_lock_does_not_span_project_roots(tmp_path, monkeypatch):
    # 锁是针对每个根的，而不是进程范围的：对一个存储库的传递不得等待另一个存储库。
    roots = _roots(tmp_path)
    other = {"global": roots["global"], "project": roots["project"] / "other"}
    intent_queue.append("run-a", _create("alpha"), roots["project"])
    intent_queue.append("run-b", _create("beta"), other["project"])

    inside = threading.Event()
    release = threading.Event()
    entered = []

    real_promote = promoter.promote

    def blocking_promote(intent, **kwargs):
        entered.append(intent["name"])
        if intent["name"] == "alpha":
            inside.set()
            release.wait(timeout=5.0)
        return real_promote(intent, **kwargs)

    monkeypatch.setattr(promoter, "promote", blocking_promote)

    first = threading.Thread(target=promoter.drain, args=("run-a",), kwargs={"roots": roots})
    first.start()
    assert inside.wait(timeout=5.0), "first drain never reached promote"

    # 当第一个排水管仍停在其关键区域内时运行完成。
    other_thread = threading.Thread(target=promoter.drain, args=("run-b",), kwargs={"roots": other})
    other_thread.start()
    other_thread.join(timeout=5.0)

    assert not other_thread.is_alive(), "a drain on another root blocked behind the lock"

    release.set()
    first.join(timeout=5.0)

    assert sorted(entered) == ["alpha", "beta"]