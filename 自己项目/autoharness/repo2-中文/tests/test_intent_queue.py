import pytest

from autoharness.lib import intent_queue


def test_append_read_clear_roundtrip(tmp_path):
    intent_queue.append("run1", {"action": "create", "name": "a"}, tmp_path)
    intent_queue.append("run1", {"action": "patch", "name": "a"}, tmp_path)
    got = intent_queue.read("run1", tmp_path)
    assert [i["action"] for i in got] == ["create", "patch"]
    intent_queue.clear("run1", tmp_path)
    assert intent_queue.read("run1", tmp_path) == []  # 处理后清除


def test_read_does_not_delete_at_least_once(tmp_path):
    # 读取不会删除 -> 下次重新处理陆地和清除之间的崩溃（至少一次）
    intent_queue.append("run1", {"action": "create"}, tmp_path)
    assert intent_queue.read("run1", tmp_path)
    assert intent_queue.read("run1", tmp_path)  # 仍在重读中


def test_orphans_lists_undrained_runs(tmp_path):
    intent_queue.append("run1", {"action": "create"}, tmp_path)
    intent_queue.append("run2", {"action": "create"}, tmp_path)
    assert set(intent_queue.orphans(tmp_path)) == {"run1", "run2"}
    intent_queue.clear("run1", tmp_path)
    assert intent_queue.orphans(tmp_path) == ["run2"]


def test_read_missing_run_empty(tmp_path):
    assert intent_queue.read("nope", tmp_path) == []
    assert intent_queue.orphans(tmp_path) == []


def test_run_id_traversal_rejected(tmp_path):
    with pytest.raises(ValueError):
        intent_queue.append("../evil", {"a": 1}, tmp_path)


class _SplitWriter:
    """将每条记录分为两部分写入，因此会捕获未序列化的附加程序
    中线而不是依靠操作系统为我们分割大量写入。"""

    def __init__(self, handle, pause):
        self._handle = handle
        self._pause = pause

    def write(self, text):
        half = len(text) // 2
        self._handle.write(text[:half])
        self._handle.flush()
        self._pause()
        return self._handle.write(text[half:])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._handle.__exit__(*exc)


def test_append_does_not_interleave_concurrent_writers(tmp_path, monkeypatch):
    # O_APPEND 仅保留 PIPE_BUF 以内的写入整体，以及分阶段的技能主体
    # 跑过去了。两个重叠的反射器运行可以交错中间记录，
    # 然后 read() 在不可解析的行上引发，因此以后每次耗尽
    # 这次运行堵塞在同一个字节上。
    import json
    import threading
    import time
    from pathlib import Path

    real_open = Path.open

    def splitting_open(self, mode="r", *args, **kwargs):
        handle = real_open(self, mode, *args, **kwargs)
        if "a" in mode:
            return _SplitWriter(handle, lambda: time.sleep(0.05))
        return handle

    monkeypatch.setattr(Path, "open", splitting_open)

    def stage(name):
        intent_queue.append("run1", {"action": "create", "name": name, "body": "x" * 8192}, tmp_path)

    writers = [threading.Thread(target=stage, args=(f"skill{i}",)) for i in range(2)]
    for w in writers:
        w.start()
    for w in writers:
        w.join()

    monkeypatch.undo()

    raw = tmp_path / "autoharness" / "intents" / "run1.jsonl"
    lines = [ln for ln in raw.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for line in lines:
        json.loads(line)  # 一张撕破的唱片在这里升起
    assert sorted(i["name"] for i in intent_queue.read("run1", tmp_path)) == ["skill0", "skill1"]
