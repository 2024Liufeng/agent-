import json
import os
import subprocess
import sys
from pathlib import Path

from autoharness import config
from autoharness.hook import spawn
from autoharness.lib import counters, layer, ledger, sidecar, skill_store

_SRC = str(Path(__file__).resolve().parents[1] / "src")

GOOD = "---\nname: {n}\ndescription: {d}\n---\n# {n}\nbody\n"


def _roots(tmp_path):
    return {"global": tmp_path / "g", "project": tmp_path / "p"}


def test_main_parses_argv_and_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(spawn.capture, "window", lambda tp, off, **k: (f"WIN[{tp}|{off}]", 42))
    monkeypatch.setattr(spawn.capture, "digest", lambda tp, off, **k: f"DIG[{tp}|{off}]")
    seen = {}
    monkeypatch.setattr(spawn, "run",
                        lambda w, rid, **k: seen.update(w=w, rid=rid, roots=k["roots"], digest=k["digest"]))
    spawn.main(["/t.jsonl", "sess-1", "run-9", str(tmp_path / "p"), str(tmp_path / "g")])
    assert seen["w"] == "WIN[/t.jsonl|0]"
    assert seen["digest"] == "DIG[/t.jsonl|0]"  # 摘要覆盖窗口偏移之前的字节
    assert seen["rid"] == "run-9"
    assert seen["roots"][layer.PROJECT] == tmp_path / "p"
    assert seen["roots"][layer.GLOBAL] == tmp_path / "g"
    assert counters.session_offset("sess-1", tmp_path / "p") == 42


def test_main_offset_advances_only_after_run(tmp_path, monkeypatch):
    monkeypatch.setattr(spawn.capture, "window", lambda tp, off, **k: ("W", 99))
    monkeypatch.setattr(spawn.capture, "digest", lambda tp, off, **k: "")
    monkeypatch.setattr(spawn, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    counters.write_session_offset("sess-2", 7, tmp_path / "p")
    try:
        spawn.main(["/t.jsonl", "sess-2", "run-1", str(tmp_path / "p"), str(tmp_path / "g")])
    except RuntimeError:
        pass
    assert counters.session_offset("sess-2", tmp_path / "p") == 7  # 崩溃 -> 下次重新加载窗口


# --- U3 确定性组装 ---

def test_description_index_both_layers_skip_archive(tmp_path):
    roots = _roots(tmp_path)
    skill_store.write_body("global", "g1", GOOD.format(n="g1", d="global one"), roots["global"])
    skill_store.write_body("project", "p1", GOOD.format(n="p1", d="proj one"), roots["project"])
    skill_store.write_body("project", "p1", GOOD.format(n="p1", d="proj one"), roots["project"])
    skill_store.archive("project", "p1", roots["project"])  # p1 现已存档 → 必须消失
    skill_store.write_body("project", "p2", GOOD.format(n="p2", d="proj two"), roots["project"])

    idx = spawn.description_index(roots)
    assert "g1" in idx and "global one" in idx
    assert "p2" in idx and "proj two" in idx
    assert "global" in idx and "project" in idx
    assert "p1" not in idx  # 存档技能从未提供比较优先


def test_description_index_empty_is_placeholder(tmp_path):
    idx = spawn.description_index(_roots(tmp_path))
    assert idx.strip()  # 非空，空树上不会发生碰撞


def test_build_bundle_injects_three_pieces():
    b = spawn.build_bundle("WINDOW_MARK", "INDEX_MARK", "SPEC_MARK")
    assert "WINDOW_MARK" in b and "INDEX_MARK" in b and "SPEC_MARK" in b


def test_build_bundle_prepends_digest_when_present():
    b = spawn.build_bundle("WINDOW_MARK", "INDEX_MARK", "SPEC_MARK", digest="DIGEST_MARK")
    assert "DIGEST_MARK" in b
    assert b.index("DIGEST_MARK") < b.index("WINDOW_MARK")  # 按时间顺序：先有背景
    assert "DIGEST_MARK" not in spawn.build_bundle("W", "I", "S", digest="")  # 空 -> 无部分


def test_build_command_carries_agent_and_print():
    cmd = spawn.build_command(agent="autoharness:reflector", claude_bin="claude")
    assert cmd[0] == "claude"
    assert "--agent" in cmd and "autoharness:reflector" in cmd
    assert "-p" in cmd
    # 自主生成：无人批准工具调用 → 必须跳过权限提示
    assert "--dangerously-skip-permissions" in cmd


def test_child_env_sets_guard_and_coords_without_polluting():
    base = {"PATH": "/x"}
    env = spawn.child_env("run-1", Path("/repo"), base_env=base)
    assert env[config.CHILD_SESSION_ENV]
    assert env[config.RUN_ID_ENV] == "run-1"
    assert env[config.PROJECT_ROOT_ENV] == str(Path("/repo"))
    assert env["PATH"] == "/x"
    assert base == {"PATH": "/x"}  # 输入字典未受影响（无父污染）


# --- U4运行编排+系统（假反射器）---

def test_run_feeds_bundle_and_drains_no_handoff_persisted(tmp_path):
    roots = _roots(tmp_path)
    seen = {}

    def fake_spawn(argv, env, bundle):
        seen["env"] = env
        seen["bundle"] = bundle
        # 代表反射器：将一个预设的意图发送到运行队列中
        from autoharness.lib import intent_queue
        intent_queue.append(env[config.RUN_ID_ENV],
                            {"action": "create", "name": "learned", "level": "project",
                             "body": GOOD.format(n="learned", d="use when doing a specific thing"),
                             "reason": "compare-first new", "evidence": "window slice"},
                            roots["project"])

    verdicts = spawn.run("WINDOW", "run-x", roots=roots, spec_path=config.FORMAT_SPEC,
                         spawn_fn=fake_spawn)
    assert seen["env"][config.RUN_ID_ENV] == "run-x"
    assert "WINDOW" in seen["bundle"]
    assert [v["ok"] for v in verdicts] == [True]
    assert skill_store.read_body("project", "learned", roots["project"]) is not None
    assert not (layer.state_dir(layer.PROJECT, roots["project"]) / "handoff").exists()  # 包只存在于管道中


# --- curator：定期合并过程（重用反射器生成链）---

def test_description_index_agent_only_filters_native(tmp_path):
    roots = _roots(tmp_path)
    skill_store.write_body("project", "native1", GOOD.format(n="native1", d="native"), roots["project"])
    skill_store.write_body("project", "agent1", GOOD.format(n="agent1", d="agent made"), roots["project"])
    sidecar.create("project", "agent1", 0, roots["project"])  # 创建者：代理
    idx = spawn.description_index(roots, agent_only=True)
    assert "agent1" in idx
    assert "native1" not in idx  # 策展人只看到自己的技能


def test_curator_bundle_has_index_and_spec():
    b = spawn.build_curator_bundle("INDEX_MARK", "SPEC_MARK")
    assert "INDEX_MARK" in b and "SPEC_MARK" in b


def test_curate_main_parses_argv_and_runs(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(spawn, "run_curator",
                        lambda rid, **k: seen.update(rid=rid, roots=k["roots"]))
    spawn.main(["--curate", "run-c9", str(tmp_path / "p"), str(tmp_path / "g")])
    assert seen["rid"] == "run-c9"
    assert seen["roots"][layer.PROJECT] == tmp_path / "p"
    assert seen["roots"][layer.GLOBAL] == tmp_path / "g"


def test_run_curator_lands_merge_and_archives_narrow(tmp_path):
    roots = _roots(tmp_path)
    root = roots["project"]
    skill_store.write_body("project", "widgets", GOOD.format(n="widgets", d="widget umbrella"), root)
    sidecar.create("project", "widgets", 0, root)
    skill_store.write_body("project", "widget-delta", GOOD.format(n="widget-delta", d="narrow delta"), root)
    sidecar.create("project", "widget-delta", 0, root)

    def fake_curator(argv, env, bundle):
        from autoharness.lib import intent_queue
        rid = env[config.RUN_ID_ENV]
        intent_queue.append(rid, {"action": "patch", "name": "widgets",
                                  "old_string": "body", "new_string": "body\n## delta\nabsorbed",
                                  "reason": "fold widget-delta into the widgets umbrella",
                                  "evidence": "widgets [project] / widget-delta [project]"}, root)
        intent_queue.append(rid, {"action": "delete", "name": "widget-delta",
                                  "reason": "absorbed into widgets umbrella",
                                  "evidence": "widgets [project] / widget-delta [project]"}, root)

    verdicts = spawn.run_curator("run-c", roots=roots, spec_path=config.FORMAT_SPEC, spawn_fn=fake_curator)
    assert [v["ok"] for v in verdicts] == [True, True]
    assert "absorbed" in skill_store.read_body("project", "widgets", root)
    assert skill_store.read_body("project", "widget-delta", root) is None  # 从活树中移出
    assert (layer.archive_dir("project", root) / "widget-delta").exists()  # 存档是可恢复的
    assert any(e["action"] == "patch" for e in ledger.read("project", "widgets", root))


def test_run_curator_cannot_touch_native_skill(tmp_path):
    # 红队：共享发起人会员守卫拒绝对非代理技能进行任何修改
    roots = _roots(tmp_path)
    root = roots["project"]
    skill_store.write_body("project", "native", GOOD.format(n="native", d="native"), root)  # 没有边车

    def fake_curator(argv, env, bundle):
        from autoharness.lib import intent_queue
        intent_queue.append(env[config.RUN_ID_ENV],
                            {"action": "delete", "name": "native",
                             "reason": "tried to prune a native skill", "evidence": "native [project]"}, root)

    verdicts = spawn.run_curator("run-r", roots=roots, spec_path=config.FORMAT_SPEC, spawn_fn=fake_curator)
    assert verdicts and verdicts[0]["ok"] is False
    assert "self_produced" in str(verdicts[0]["findings"])
    assert skill_store.read_body("project", "native", root) is not None  # 原生未受影响


def _executable(script):
    """claude_bin 替身：POSIX 执行 shebang 脚本； Windows 不能，因此它有一个 .cmd shim。"""
    if os.name != "nt":
        script.chmod(0o755)
        return script
    shim = script.with_suffix(".cmd")
    shim.write_text(f'@"{sys.executable}" "{script}" %*\n')
    return shim


def _fake_reflector_script(tmp_path):
    script = tmp_path / "fake_reflector.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "from autoharness import config\n"
        "from autoharness.stage_skill import server\n"
        "sys.stdin.read()\n"  # 使用切换包（证明它到达了标准输入）
        "run_id = os.environ[config.RUN_ID_ENV]\n"
        "root = Path(os.environ[config.PROJECT_ROOT_ENV])\n"
        "params = {'action': 'create', 'name': 'learned', 'level': 'project',\n"
        "          'body': '---\\nname: learned\\ndescription: Use when doing a specific thing.\\n---\\n# x\\ny\\n',\n"
        "          'reason': 'compare-first new', 'evidence': 'window slice'}\n"
        "res = server.stage(params, run_id=run_id, root=root)\n"
        "sys.exit(0 if res['ok'] else 1)\n"
    )
    return _executable(script)


def test_system_fake_reflector_cross_process_lands(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", _SRC)  # 子子进程必须导入autoharness
    roots = _roots(tmp_path)
    script = _fake_reflector_script(tmp_path)

    verdicts = spawn.run("WINDOW", "run-sys", roots=roots, repo_name="myrepo",
                         claude_bin=str(script), spec_path=config.FORMAT_SPEC)

    assert [v["ok"] for v in verdicts] == [True]
    root = roots["project"]
    assert skill_store.read_body("project", "learned", root) is not None
    assert sidecar.is_agent_created("project", "learned", root)
    led = ledger.read("project", "learned", root)
    assert len(led) == 1 and led[0]["action"] == "create"


def _fake_curator_script(tmp_path):
    script = tmp_path / "fake_curator.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "from autoharness import config\n"
        "from autoharness.stage_skill import server\n"
        "sys.stdin.read()\n"  # 使用 curator 包（证明它到达了 stdin）
        "run_id = os.environ[config.RUN_ID_ENV]\n"
        "root = Path(os.environ[config.PROJECT_ROOT_ENV])\n"
        "ev = 'widgets [project] / widget-delta [project]'\n"
        "server.stage({'action': 'patch', 'name': 'widgets', 'old_string': 'body',\n"
        "              'new_string': 'body\\n## delta\\nabsorbed', 'reason': 'fold into umbrella',\n"
        "              'evidence': ev}, run_id=run_id, root=root)\n"
        "server.stage({'action': 'delete', 'name': 'widget-delta',\n"
        "              'reason': 'absorbed into widgets', 'evidence': ev}, run_id=run_id, root=root)\n"
        "sys.exit(0)\n"
    )
    return _executable(script)


def test_system_fake_curator_cross_process_merges(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", _SRC)  # 子子进程必须导入autoharness
    roots = _roots(tmp_path)
    root = roots["project"]
    for n, d in (("widgets", "widget umbrella"), ("widget-delta", "narrow delta")):
        skill_store.write_body("project", n, GOOD.format(n=n, d=d), root)
        sidecar.create("project", n, 0, root)
    script = _fake_curator_script(tmp_path)

    verdicts = spawn.run_curator("run-csys", roots=roots, repo_name="myrepo",
                                 claude_bin=str(script), spec_path=config.FORMAT_SPEC)

    assert [v["ok"] for v in verdicts] == [True, True]
    assert "absorbed" in skill_store.read_body("project", "widgets", root)
    assert skill_store.read_body("project", "widget-delta", root) is None  # 从活动树中归档
    assert (layer.archive_dir("project", root) / "widget-delta").exists()


# --- 叉车（hermes-parity Phase 11，G方向）：同型号叉车骑乘亲的温暖
# 前缀缓存；反射指令以 -p 提示符形式到达（无 --agent：交换系统
# 提示将使前缀无效）。默认载体保持“捆绑”状态，直到 G 尖峰通过。 ---

def test_build_fork_command_shape():
    argv = spawn.build_fork_command(session_id="sess-9", claude_bin="claude")
    assert argv[:5] == ["claude", "-p", "--resume", "sess-9", "--fork-session"]
    assert "--agent" not in argv  # 前缀约束：保持父系统提示


def test_run_fork_carrier_sends_instruction_not_window(tmp_path, monkeypatch):
    monkeypatch.setattr(spawn.config, "REFLECTOR_CARRIER", "fork")
    roots = {"project": tmp_path / "p", "global": tmp_path / "g"}
    seen = {}

    def fake(argv, env, payload):
        seen.update(argv=argv, env=env, payload=payload)

    spawn.run("WINDOW-TEXT", "r1", roots=roots, session_id="sess-9", spawn_fn=fake)
    assert "--fork-session" in seen["argv"]
    assert "WINDOW-TEXT" not in seen["payload"]  # fork 重播成绩单；没有物化窗口
    assert "stage_skill" in seen["payload"]      # 反映指令依赖于提示
    assert seen["env"][spawn.config.CHILD_SESSION_ENV] == "1"  # 递归守卫仍然设置


def test_run_bundle_carrier_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(spawn.config, "REFLECTOR_CARRIER", "bundle")
    roots = {"project": tmp_path / "p", "global": tmp_path / "g"}
    seen = {}

    def fake(argv, env, payload):
        seen.update(argv=argv, payload=payload)

    spawn.run("WINDOW-TEXT", "r1", roots=roots, session_id="sess-9", spawn_fn=fake)
    assert "--fork-session" not in seen["argv"]
    assert "WINDOW-TEXT" in seen["payload"]  # 捆绑后备仍然实现窗口


def test_fork_without_session_falls_back_to_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(spawn.config, "REFLECTOR_CARRIER", "fork")
    roots = {"project": tmp_path / "p", "global": tmp_path / "g"}
    seen = {}
    spawn.run("WINDOW-TEXT", "r1", roots=roots, session_id=None,
              spawn_fn=lambda argv, env, payload: seen.update(argv=argv, payload=payload))
    assert "--fork-session" not in seen["argv"]  # 没有会话可分叉 -> 捆绑链


# --- 策展人预运行快照（第 12 阶段，方向 E）：仅库级尾部风险 ---

def _snap_roots(tmp_path):
    roots = {"project": tmp_path / "p", "global": tmp_path / "g"}
    for root in roots.values():
        d = root / "skills" / "x"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: x\ndescription: d\n---\nb")
    return roots


def test_run_curator_snapshots_before_spawn(tmp_path):
    roots = _snap_roots(tmp_path)
    order = []
    spawn.run_curator("c1", roots=roots,
                      spawn_fn=lambda a, e, b: order.append("spawned"))
    snaps = list((roots["project"] / "autoharness" / "snapshots").glob("*.tar.gz"))
    assert snaps and order == ["spawned"]


def test_snapshot_rotation_keeps_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(spawn.config, "SNAPSHOT_KEEP", 2)
    roots = _snap_roots(tmp_path)
    for i in range(4):
        spawn.run_curator(f"c{i}", roots=roots, spawn_fn=lambda a, e, b: None)
    snaps = (roots["project"] / "autoharness" / "snapshots").glob("*.tar.gz")
    assert len(list(snaps)) <= 2 * 2  # 每层保留


def test_snapshot_failure_never_blocks_the_run(tmp_path, monkeypatch):
    roots = _snap_roots(tmp_path)
    bodies = {root: (root / "skills" / "x" / "SKILL.md").read_text(encoding="utf-8")
              for root in roots.values()}
    monkeypatch.setattr(spawn, "_snapshot_skills", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    called = []
    spawn.run_curator("c1", roots=roots, spawn_fn=lambda a, e, b: called.append(1))
    assert called  # 暂时性磁盘问题不得静默禁用管理
    assert all((root / "skills" / "x" / "SKILL.md").read_text(encoding="utf-8") == body
               for root, body in bodies.items())


def test_unexpected_snapshot_failure_is_logged(tmp_path, monkeypatch, caplog):
    roots = _snap_roots(tmp_path)
    monkeypatch.setattr(spawn, "_snapshot_skills",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("snapshot bug")))
    called = []

    spawn.run_curator("c1", roots=roots, spawn_fn=lambda a, e, b: called.append(1))

    assert called  # 报告编程错误不会改变馆长的日程安排
    assert "unexpected snapshot error" in caplog.text
    assert "RuntimeError: snapshot bug" in caplog.text


# --- #160：崩溃的反射器不能默默地失败（stderr 被捕获并丢弃）---

def test_detached_spawn_reports_child_crash_on_stderr(capsys):
    argv = [sys.executable, "-c",
            "import sys; print('reflector died', file=sys.stderr); raise SystemExit(3)"]
    proc = spawn._detached_spawn(argv, {}, "bundle")
    assert proc.returncode == 3
    assert "reflector died" in capsys.readouterr().err


def test_run_records_spawn_error_in_run_account(tmp_path):
    roots = _roots(tmp_path)
    secret = "ghp_" + "a" * 36
    crash = subprocess.CompletedProcess([config.CLAUDE_BIN], 3, "",
                                        f"Error: agent not found; token={secret}")
    verdicts = spawn.run("WINDOW", "run-x", roots=roots, spec_path=config.FORMAT_SPEC,
                         spawn_fn=lambda a, e, b: crash)
    assert verdicts == []
    account = json.loads((roots["project"] / "autoharness" / "runs" / "run-x.json").read_text(encoding="utf-8"))
    assert account["run_id"] == "run-x"
    assert account["spawn_error"]["returncode"] == 3
    assert "agent not found" in account["spawn_error"]["stderr_tail"]
    assert secret not in account["spawn_error"]["stderr_tail"]
    assert "REDACTED" in account["spawn_error"]["stderr_tail"]


def test_spawn_error_record_preserves_landed_verdicts(tmp_path):
    roots = _roots(tmp_path)

    def crashed_after_staging(argv, env, bundle):
        from autoharness.lib import intent_queue
        intent_queue.append(env[config.RUN_ID_ENV],
                            {"action": "create", "name": "learned", "level": "project",
                             "body": GOOD.format(n="learned", d="use when doing a specific thing"),
                             "reason": "compare-first new", "evidence": "window slice"},
                            roots["project"])
        return subprocess.CompletedProcess(argv, 3, "", "late crash")

    verdicts = spawn.run("WINDOW", "run-x", roots=roots, spec_path=config.FORMAT_SPEC,
                         spawn_fn=crashed_after_staging)
    assert [v["ok"] for v in verdicts] == [True]
    account = json.loads((roots["project"] / "autoharness" / "runs" / "run-x.json").read_text(encoding="utf-8"))
    assert account["spawn_error"]["returncode"] == 3
    assert account["verdicts"]  # 儿童诊断增强而不是取代发起人的裁决


def test_successful_spawn_writes_no_spawn_error(tmp_path):
    roots = _roots(tmp_path)
    ok = subprocess.CompletedProcess([config.CLAUDE_BIN], 0, "", "")
    spawn.run("WINDOW", "run-ok", roots=roots, spec_path=config.FORMAT_SPEC,
              spawn_fn=lambda a, e, b: ok)
    assert not (roots["project"] / "autoharness" / "runs" / "run-ok.json").exists()
