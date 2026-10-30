"""全技能生命周期沙箱：诞生→使用→竞争→存档→恢复，驱动通过
真正的调度+生成+启动子+生命周期。只有反射器模型是罐装存根
（fake_spawn 表现出一个意图）；其他所有内容都是隔离 tmp 目录上的生产路径。

这是实时主机运行手册的确定性对应部分 (experiments/E7_plugin_e2e)：
它监视磁盘上的每个生命周期转换。现场运行仅添加“真正的克劳德代码
hooks/MCP/recall 实际上会触发”。"""
import json

import pytest

from autoharness import config
from autoharness.hook import capture, dispatch, spawn
from autoharness.lib import counters, intent_queue, layer, ledger, sidecar, skill_store

LEARNED = "---\nname: learned\ndescription: Use when doing a specific repeatable thing.\n---\n# Learned\nSteps.\n"
WEAK = "---\nname: weak\ndescription: Use when the rare side note applies.\n---\n# Weak\nx.\n"


@pytest.fixture(autouse=True)
def _small_isolated(monkeypatch):
    monkeypatch.delenv(config.CHILD_SESSION_ENV, raising=False)
    monkeypatch.setattr(config, "REFLECT_EVERY_N", 2)
    monkeypatch.setattr(config, "MATURITY_THRESHOLD", {layer.GLOBAL: 2, layer.PROJECT: 2})
    monkeypatch.setattr(config, "CAPACITY", {layer.GLOBAL: 5, layer.PROJECT: 1})


def _roots(tmp_path):
    return {layer.GLOBAL: tmp_path / "g", layer.PROJECT: tmp_path / "p"}


def _transcript(tmp_path):
    p = tmp_path / "transcript.jsonl"
    lines = []
    for i in range(4):
        lines.append(json.dumps({"type": "user", "message": {"role": "user", "content": f"q{i}"}}))
        lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": f"a{i}"}}))
    p.write_text("\n".join(lines) + "\n")
    return p


def test_full_skill_lifecycle_through_dispatch(tmp_path, capsys):
    roots = _roots(tmp_path)
    proot = roots[layer.PROJECT]
    transcript = _transcript(tmp_path)
    stop = {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(transcript)}

    def land_learned(event, result, rts):  # 代表生成的反射器
        def fake_spawn(argv, env, bundle):
            intent_queue.append(env[config.RUN_ID_ENV],
                                {"action": "create", "name": "learned", "level": "project",
                                 "body": LEARNED, "reason": "captured repeat", "evidence": "slice"},
                                rts[layer.PROJECT])
        spawn.run(capture.window(event["transcript_path"])[0],
                  dispatch._run_id(result), roots=rts, spawn_fn=fake_spawn)

    # BEAT 1 — 诞生：工具调用累积活动；阈值停止触发反射
    act = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "s1"}
    dispatch.dispatch(act, roots=roots)
    dispatch.dispatch(stop, roots=roots, reflect=land_learned)            # 停止 1：活动 1 < N，无触发
    assert skill_store.read_body("project", "learned", proot) is None
    dispatch.dispatch(act, roots=roots)
    dispatch.dispatch(stop, roots=roots, reflect=land_learned)            # 停靠站 2：活动 2 ≥ N → 陆地
    assert skill_store.read_body("project", "learned", proot) is not None
    assert sidecar.is_agent_created("project", "learned", proot)
    assert ledger.read("project", "learned", proot)[0]["action"] == "create"
    assert counters.request_count(layer.PROJECT, proot) == 2              # 每站分母都会增长

    # BEAT 2 — 使用：PreToolUse(Skill) 碰撞分子
    for _ in range(2):
        dispatch.dispatch({"hook_event_name": "PreToolUse", "tool_name": "Skill",
                           "tool_input": {"name": "learned"}}, roots=roots)
    sc = sidecar.read("project", "learned", proot)
    assert sc["use"] == 2 and sc["view"] == 0

    # BEAT 3 — 竞争：较弱的未使用同行； MNG 重新计算（SessionStart）将失败者归档。
    # 学习者以真正的锚点着陆（= 2），因此首先再转两圈以使其脱离试用期。
    for _ in range(2):
        dispatch.dispatch(stop, roots=roots, reflect=lambda *a: None)
    skill_store.write_body("project", "weak", WEAK, proot)
    sidecar.create("project", "weak", anchor=0, root=proot)              # 成熟（面额 4），零跟注
    req = counters.request_count(layer.PROJECT, proot)
    mat = config.MATURITY_THRESHOLD[layer.PROJECT]
    for name in ("learned", "weak"):                                    # 都过了试用期：能力决定
        den = req - sidecar.read("project", name, proot)["anchor"]
        assert den >= mat, f"{name} still in probation: denominator {den} < maturity {mat}"
    out = dispatch.dispatch({"hook_event_name": "SessionStart"}, roots=roots)
    archived = out["result"]["archived"]["project"]
    assert "weak" in archived and "learned" not in archived            # 最低率棚屋，坚持保留
    assert not skill_store.exists("project", "weak", proot)             # 从活树中移出
    assert (layer.archive_dir("project", proot) / "weak").exists()
    assert skill_store.exists("project", "learned", proot)

    # BEAT 4 — 恢复：存档是可逆的
    skill_store.restore("project", "weak", proot)
    assert skill_store.exists("project", "weak", proot)
