import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from autoharness import config
from autoharness.hook import dispatch
from autoharness.lib import counters, layer, sidecar, skill_store


@pytest.fixture(autouse=True)
def _unguard(monkeypatch):
    monkeypatch.delenv(config.CHILD_SESSION_ENV, raising=False)  # 环境可以设置它


def _roots(tmp_path):
    return {layer.GLOBAL: tmp_path / "g", layer.PROJECT: tmp_path / "p"}


def test_routes_each_event_to_its_handler(tmp_path, monkeypatch):
    seen = {}

    def spy(key, ret):
        def fake(e, **k):
            seen[key] = (e, k)
            return ret
        return fake

    monkeypatch.setattr(dispatch.on_session_start, "on_session_start", spy("start", {"archived": {}}))
    monkeypatch.setattr(dispatch.on_skill_call, "on_skill_call", spy("skill", {"counted": False}))
    monkeypatch.setattr(dispatch.on_stop, "on_stop", spy("stop", {"triggered": False}))
    monkeypatch.setattr(dispatch.on_session_end, "on_session_end", spy("end", {"triggered": False}))
    roots = _roots(tmp_path)

    dispatch.dispatch({"hook_event_name": "SessionStart"}, roots=roots)
    dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Skill"}, roots=roots)
    dispatch.dispatch({"hook_event_name": "Stop"}, roots=roots)
    dispatch.dispatch({"hook_event_name": "SessionEnd"}, roots=roots)

    assert set(seen) == {"start", "skill", "stop", "end"}
    assert seen["stop"][1]["root"] == roots[layer.PROJECT]
    assert seen["skill"][1]["roots"] == roots


def test_unknown_event_is_ignored_safely(tmp_path):
    assert dispatch.dispatch({"hook_event_name": "Nope"}, roots=_roots(tmp_path))["ignored"] is True


def test_missing_event_name_is_ignored(tmp_path):
    assert dispatch.dispatch({}, roots=_roots(tmp_path))["ignored"] is True


def test_subagent_stop_is_ignored(tmp_path):
    # 反射器完成是 SubagentStop (E6 S4)：从不转弯，从不计数
    assert dispatch.dispatch({"hook_event_name": "SubagentStop"}, roots=_roots(tmp_path))["ignored"] is True


def test_child_session_stop_bumps_nothing(tmp_path, monkeypatch):
    # 反射孩子的转弯不得使 MNG 分母膨胀（后卫在碰撞之前跑动）
    monkeypatch.setenv(config.CHILD_SESSION_ENV, "1")
    roots = _roots(tmp_path)
    out = dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s1"},
                            roots=roots, reflect=lambda *a: None)
    assert out["result"]["triggered"] is False
    assert counters.request_count(layer.PROJECT, roots[layer.PROJECT]) == 0
    assert counters.request_count(layer.GLOBAL, roots[layer.GLOBAL]) == 0


def test_stop_bumps_both_layer_denominators(tmp_path):
    roots = _roots(tmp_path)
    dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s1"},
                      roots=roots, reflect=lambda *a: None)
    assert counters.request_count(layer.PROJECT, roots[layer.PROJECT]) == 1
    assert counters.request_count(layer.GLOBAL, roots[layer.GLOBAL]) == 1  # 全局分母也是如此


def test_triggered_stop_fires_reflect(tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch.on_stop, "on_stop",
                        lambda e, **k: {"triggered": True, "session_id": "s1", "count": 10, "window_n": 10})
    calls = []
    dispatch.dispatch({"hook_event_name": "Stop", "transcript_path": "/t.jsonl"},
                      roots=_roots(tmp_path), reflect=lambda ev, res, roots: calls.append(res))
    assert calls and calls[0]["session_id"] == "s1"


def test_triggered_session_end_fires_reflect(tmp_path, monkeypatch):
    # tail-catch：会话结束时节奏以下的活动仍然通过调度程序反映出来
    monkeypatch.setattr(dispatch.on_session_end, "on_session_end",
                        lambda e, **k: {"triggered": True, "session_id": "s1", "count": 3, "window_n": 3})
    calls = []
    out = dispatch.dispatch({"hook_event_name": "SessionEnd", "transcript_path": "/t.jsonl"},
                            roots=_roots(tmp_path), reflect=lambda ev, res, roots: calls.append(res))
    assert out["handled"] == "SessionEnd"
    assert len(calls) == 1 and calls[0]["session_id"] == "s1"


def test_untriggered_session_end_does_not_reflect(tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch.on_session_end, "on_session_end", lambda e, **k: {"triggered": False})
    calls = []
    dispatch.dispatch({"hook_event_name": "SessionEnd", "transcript_path": "/t.jsonl"},
                      roots=_roots(tmp_path), reflect=lambda *a: calls.append(a))
    assert calls == []


def test_real_onstop_triggers_at_cadence(tmp_path):
    roots = _roots(tmp_path)
    for _ in range(config.REFLECT_EVERY_N):  # PreToolUse 累积的活动；只停止法官
        counters.bump_session("s1", roots[layer.PROJECT])
    seen = []
    dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s1", "transcript_path": "/t.jsonl"},
                      roots=roots, reflect=lambda ev, res, roots: seen.append(res))
    assert len(seen) == 1 and seen[0]["window_n"] == config.REFLECT_EVERY_N


def test_curate_run_id_sanitized_and_unique_per_count():
    assert dispatch._curate_run_id({"session_id": "abc/1"}, 5) == "abc1-c5"


def test_curator_fires_at_consolidate_cadence(tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch.config, "CONSOLIDATE_EVERY_N", 3)
    roots = _roots(tmp_path)
    fired = []
    for _ in range(3):
        dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s1", "transcript_path": "/t.jsonl"},
                          roots=roots, reflect=lambda *a: None,
                          consolidate=lambda run_id, r: fired.append(run_id))
    assert fired == ["s1-c3"]  # 一旦，在回合中请求计数器达到 N 的倍数


def test_curator_not_fired_off_cadence(tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch.config, "CONSOLIDATE_EVERY_N", 3)
    roots = _roots(tmp_path)
    fired = []
    for _ in range(2):
        dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s1"},
                          roots=roots, reflect=lambda *a: None,
                          consolidate=lambda run_id, r: fired.append(run_id))
    assert fired == []


def test_curator_not_fired_in_child_session(tmp_path, monkeypatch):
    monkeypatch.setenv(config.CHILD_SESSION_ENV, "1")
    monkeypatch.setattr(dispatch.config, "CONSOLIDATE_EVERY_N", 1)  # 如果无人看守，每个回合都会开火
    fired = []
    dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s1"}, roots=_roots(tmp_path),
                      reflect=lambda *a: None, consolidate=lambda run_id, r: fired.append(run_id))
    assert fired == []  # 递归防护：策展人/反射器子代永远不会生成另一个策展人


def test_untriggered_stop_does_not_reflect(tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch.on_stop, "on_stop", lambda e, **k: {"triggered": False, "count": 1})
    calls = []
    dispatch.dispatch({"hook_event_name": "Stop"}, roots=_roots(tmp_path),
                      reflect=lambda ev, res, roots: calls.append(res))
    assert calls == []


def test_pretooluse_skill_counts_numerator(tmp_path):
    roots = _roots(tmp_path)
    root = roots[layer.PROJECT]
    skill_store.write_body("project", "foo", "b", root)
    sidecar.create("project", "foo", anchor=0, root=root)
    out = dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Skill",
                             "tool_input": {"name": "foo"}}, roots=roots)
    assert out["result"]["counted"]
    assert sidecar.read("project", "foo", root)["use"] == 1


def test_pretooluse_read_of_skill_counts_numerator(tmp_path):
    roots = _roots(tmp_path)
    root = roots[layer.PROJECT]
    skill_store.write_body("project", "foo", "b", root)
    sidecar.create("project", "foo", anchor=0, root=root)
    out = dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Read",
                             "tool_input": {"file_path": str(root / "skills" / "foo" / "SKILL.md")}},
                            roots=roots)
    assert out["result"]["counted"]
    assert sidecar.read("project", "foo", root)["view"] == 1


def test_reflector_read_not_counted(tmp_path):
    roots = _roots(tmp_path)
    root = roots[layer.PROJECT]
    skill_store.write_body("project", "foo", "b", root)
    sidecar.create("project", "foo", anchor=0, root=root)
    out = dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Read",
                             "agent_type": "autoharness:reflector",
                             "tool_input": {"file_path": str(root / "skills" / "foo" / "SKILL.md")}},
                            roots=roots)
    assert not out["result"]["counted"]
    assert sidecar.read("project", "foo", root).get("view", 0) == 0


def test_reflector_write_is_denied(tmp_path):
    out = dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Write",
                             "agent_type": "autoharness:reflector"}, roots=_roots(tmp_path))
    assert out["deny"] is True


def test_non_reflector_write_is_ignored(tmp_path):
    out = dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Write",
                             "agent_type": "main"}, roots=_roots(tmp_path))
    assert out["ignored"] is True


def test_handler_exception_is_failsafe(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(dispatch.counters, "bump_request", boom)
    out = dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s1"}, roots=_roots(tmp_path))
    assert "error" in out  # 永远不会传播导致主机钩子崩溃


def test_reflect_builds_run_id_and_skips_without_transcript(tmp_path):
    launched = []
    result = {"session_id": "abc", "count": 7, "window_n": 7}
    dispatch._reflect({"transcript_path": "/t.jsonl"}, result, _roots(tmp_path),
                      launch=lambda tp, sid, run_id, roots: launched.append((tp, sid, run_id)))
    assert launched == [("/t.jsonl", "abc", "abc-7")]

    launched.clear()
    dispatch._reflect({}, result, _roots(tmp_path), launch=lambda *a: launched.append(a))
    assert launched == []  # 没有成绩单 → 没有什么可反思的


def test_default_roots_resolve_both_layers():
    roots = dispatch._roots(None)
    assert set(roots) == set(layer.LAYERS)
    assert all(isinstance(p, Path) for p in roots.values())


# --- SessionStart 上下文发射（hermes-parity 第 9 阶段）---

def test_emit_session_start_additional_context(capsys):
    dispatch._emit({"handled": "SessionStart", "result": {"context": "INDEX", "archived": {}}})
    out = capsys.readouterr().out
    payload = json.loads(out)
    hso = payload["hookSpecificOutput"]
    assert hso["hookEventName"] == "SessionStart"
    assert hso["additionalContext"] == "INDEX"


def test_emit_session_start_no_context_prints_nothing(capsys):
    dispatch._emit({"handled": "SessionStart", "result": {"context": None, "archived": {}}})
    assert capsys.readouterr().out == ""


# --- _emit拒绝输出：主机读取stdout，而不是返回值，因此写入
# backstop 的 stdout JSON 是安全边界，需要自己的覆盖范围 (#138) ---


def test_emit_deny_writes_permission_decision_to_stdout(capsys):
    dispatch._emit({"deny": True, "reason": "reflector may only stage intents, not write files"})
    payload = json.loads(capsys.readouterr().out)
    hso = payload["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert hso["permissionDecisionReason"] == "reflector may only stage intents, not write files"


def test_emit_deny_falls_back_to_a_reason_when_absent(capsys):
    # 没有理由的拒绝仍然必须拒绝，并且主持人可以显示一个非空的理由
    dispatch._emit({"deny": True})
    hso = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert hso["permissionDecisionReason"]


def test_emit_deny_is_single_line_json_on_stdout_only(capsys):
    # 主机每次钩子调用都会解析一个 JSON 对象：包装的有效负载不会解析
    dispatch._emit({"deny": True, "reason": "no"})
    captured = capsys.readouterr()
    assert len(captured.out.strip().splitlines()) == 1
    assert captured.err == ""


def test_denied_reflector_write_reaches_the_host_as_deny_json(tmp_path, capsys):
    # 端到端通过调度程序：dispatch()决定，_emit是主机实际读取的内容
    dispatch._emit(dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Write",
                                       "agent_type": "autoharness:reflector"}, roots=_roots(tmp_path)))
    hso = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "stage intents" in hso["permissionDecisionReason"]


def test_denied_child_write_reaches_the_host_as_deny_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(config.CHILD_SESSION_ENV, "1")
    dispatch._emit(dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Write",
                                       "session_id": "s7"}, roots=_roots(tmp_path)))
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---第11阶段(H)：每次PreToolUse都会推进活动计数器；停止不再碰撞它——

def test_pretooluse_advances_activity_counter(tmp_path):
    roots = _roots(tmp_path)
    dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                       "session_id": "s7"}, roots=roots)
    assert counters.session_count("s7", roots["project"]) == 1


def test_child_session_pretooluse_does_not_advance(tmp_path, monkeypatch):
    monkeypatch.setenv(config.CHILD_SESSION_ENV, "1")
    roots = _roots(tmp_path)
    dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                       "session_id": "s7"}, roots=roots)
    assert counters.session_count("s7", roots["project"]) == 0


def test_stop_does_not_advance_activity(tmp_path):
    roots = _roots(tmp_path)
    dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s7",
                       "transcript_path": "x"}, roots=roots)
    assert counters.session_count("s7", roots["project"]) == 0  # 分母是，活动否


# --- 阶段 11 (G)：子会话（分叉）写入工具被拒绝 ---

def test_child_session_write_denied(tmp_path, monkeypatch):
    monkeypatch.setenv(config.CHILD_SESSION_ENV, "1")
    v = dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Write",
                           "session_id": "s7"}, roots=_roots(tmp_path))
    assert v.get("deny")


def _interactive_intent(name="learned"):
    return {"action": "create", "name": name, "level": "project", "reason": "r", "evidence": "e",
            "body": f"---\nname: {name}\ndescription: Use when a learned thing applies.\n---\nRule.\n"}


def test_main_session_stop_drains_the_interactive_queue(tmp_path, monkeypatch):
    # 没有其他东西会耗尽它：在子进程退出后，spawn 仅耗尽它自己的运行 ID。如果没有这个
    # /learn 提案永远位于队列中，而技能本身的承诺（“lands；接下来报告
    # 会话开始”）为假。
    from autoharness.lib import intent_queue, skill_store
    roots = {"global": tmp_path / "g", "project": tmp_path / "p"}
    monkeypatch.delenv(config.CHILD_SESSION_ENV, raising=False)
    intent_queue.append(config.INTERACTIVE_RUN_ID, _interactive_intent(), roots["project"])
    dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s1"}, roots=roots, reflect=lambda *a: None)
    assert skill_store.exists("project", "learned", roots["project"])
    assert not list(intent_queue.read(config.INTERACTIVE_RUN_ID, roots["project"]))


def test_child_session_stop_leaves_the_interactive_queue_alone(tmp_path, monkeypatch):
    # 一个孩子有自己的运行ID，并且spawn会耗尽它；从那里触摸用户的队列将是
    # 反射者以反射者身份登陆用户提案
    from autoharness.lib import intent_queue
    roots = {"global": tmp_path / "g", "project": tmp_path / "p"}
    monkeypatch.setenv(config.CHILD_SESSION_ENV, "1")
    intent_queue.append(config.INTERACTIVE_RUN_ID, _interactive_intent(), roots["project"])
    dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s1"}, roots=roots, reflect=lambda *a: None)
    assert len(list(intent_queue.read(config.INTERACTIVE_RUN_ID, roots["project"]))) == 1


def test_stop_with_empty_interactive_queue_writes_no_run_account(tmp_path, monkeypatch):
    # 每转一次都会流失；空排水管不得留下运行/文件或last_run摘要，
    # 或者下一个会话开始时会报告从未发生过的运行
    from autoharness.lib import layer
    roots = {"global": tmp_path / "g", "project": tmp_path / "p"}
    monkeypatch.delenv(config.CHILD_SESSION_ENV, raising=False)
    dispatch.dispatch({"hook_event_name": "Stop", "session_id": "s1"}, roots=roots, reflect=lambda *a: None)
    state = layer.state_dir("project", roots["project"])
    assert not (state / "last_run.json").exists()
    assert not list((state / "runs").glob("*.json")) if (state / "runs").exists() else True


def _run_under_old_python(tmp_path, version=(3, 9, 6, "final", 0)):
    # 主机的裸“python3”可能比 3.11 版本更旧（Xcode 发布了 3.9.6，位于
    # /usr/bin/python3);通过固定 version_info 并隐藏 tomllib 在子进程中模拟它，
    # 这是 3.11 中输入的 stdlib 模块，并且 redact.py 在模块级别导入
    probe = tmp_path / "old_python_probe.py"
    probe.write_text(
        "import sys\n"
        f"sys.version_info = {version!r}\n"
        "class _NoTomllib:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'tomllib':\n"
        "            raise ModuleNotFoundError(\"No module named 'tomllib'\", name='tomllib')\n"
        "        return None\n"
        "sys.meta_path.insert(0, _NoTomllib())\n"
        "import autoharness.hook.dispatch\n"
    )
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, str(probe)], capture_output=True, text=True,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(root / "src")},
    )


def test_below_floor_python_exits_clean_instead_of_crashing_at_import(tmp_path):
    # hooks.json 为所有四个事件调用裸“python3”，并且链中的每个导入都是
    # 模块级别，因此底层解释器在进入dispatch()之前就死掉了，并且
    # 故障安全处理程序永远没有机会捕获它：整个插件会默默地关闭
    r = _run_under_old_python(tmp_path)
    assert r.returncode == 0, f"expected a clean exit, got {r.returncode}:\n{r.stderr}"
    assert "Traceback" not in r.stderr
    assert "tomllib" not in r.stderr


def test_below_floor_python_names_the_floor_and_the_interpreter(tmp_path):
    # 防护的重点是操作员可以对其采取行动：通用主机钩子错误
    # 没有记录任何内容就是它所取代的
    r = _run_under_old_python(tmp_path)
    assert "3.11" in r.stderr
    assert "3.9" in r.stderr
    assert "hooks.json" in r.stderr


def test_supported_python_still_imports_and_dispatches(tmp_path):
    # 警卫不得向受支持的翻译开枪
    assert dispatch.dispatch({"hook_event_name": "Nope"}) == {
        "ignored": True, "reason": "unrouted event: 'Nope'"}
