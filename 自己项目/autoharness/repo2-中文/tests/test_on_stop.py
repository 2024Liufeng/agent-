from autoharness import config
from autoharness.hook import on_stop
from autoharness.lib import counters

EV = {"session_id": "sess-1"}


def _unguard(monkeypatch):
    monkeypatch.delenv(config.CHILD_SESSION_ENV, raising=False)


def test_stop_reads_activity_without_advancing(monkeypatch, tmp_path):
    _unguard(monkeypatch)
    counters.bump_session("sess-1", tmp_path)
    for _ in range(3):
        v = on_stop.on_stop(EV, root=tmp_path, n=10)
        assert not v["triggered"] and v["count"] == 1  # 停止评判，永不进步


def test_triggers_and_resets_at_n(monkeypatch, tmp_path):
    _unguard(monkeypatch)
    for _ in range(3):
        counters.bump_session("sess-1", tmp_path)
    v = on_stop.on_stop(EV, root=tmp_path, n=3)
    assert v["triggered"] and v["window_n"] == 3
    assert counters.session_count("sess-1", tmp_path) == 0  # 触发复位
    assert not on_stop.on_stop(EV, root=tmp_path, n=3)["triggered"]  # 下一轮开始为空


def test_recursion_guard_early_exit_no_count(monkeypatch, tmp_path):
    monkeypatch.setenv(config.CHILD_SESSION_ENV, "reflector-xyz")
    v = on_stop.on_stop(EV, root=tmp_path, n=3)
    assert not v["triggered"]
    assert counters.session_count("sess-1", tmp_path) == 0  # 子停止不计算在内


def test_platform_child_var_does_not_gate_judging(monkeypatch, tmp_path):
    _unguard(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")  # 主机在每个钩子子进程上设置它，而不仅仅是反射器
    counters.bump_session("sess-1", tmp_path)
    assert on_stop.on_stop(EV, root=tmp_path, n=10).get("count") == 1


def test_missing_session_safe(monkeypatch, tmp_path):
    _unguard(monkeypatch)
    assert not on_stop.on_stop({}, root=tmp_path, n=3)["triggered"]


# ---活动量子触发（hermes-parity阶段11，方向H）：分子是工具调用，
# 由PreToolUse累积； Stop仅判断阈值。仅聊天的回合永远不会推进它。 ---

def test_stop_without_activity_never_triggers(tmp_path):
    for _ in range(50):
        r = on_stop.on_stop({"session_id": "s1"}, root=tmp_path, n=3)
    assert not r["triggered"]  # 纯聊天轮流：计数器未受影响


def test_tool_calls_accumulate_and_stop_judges(tmp_path):
    from autoharness.lib import counters
    for _ in range(3):
        counters.bump_session("s1", tmp_path)  # 现在每个 PreToolUse 的调度执行什么操作
    r = on_stop.on_stop({"session_id": "s1"}, root=tmp_path, n=3)
    assert r["triggered"] and r["count"] == 3
    # 射击后重置
    assert counters.session_count("s1", tmp_path) == 0
