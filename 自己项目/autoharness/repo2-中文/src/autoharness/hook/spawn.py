"""REF 运载火箭：确定性地组装反射器输入→分离生成子会话→连接到promote.drain。

架构第 29 行 / [reflector-subagent] / [cap]：在触发时间 CAP 给出“编辑的情节窗口 +
触发节奏”；这一步将三部分组装起来（窗口+现有技能描述索引
（比较第一个重复数据删除源，跳过存档）+单源格式规范）并通过
stdin 到跨进程反射器 — 没有任何内容被持久化；该束仅存在于管道中。生成集 CHILD_SESSION_ENV （递归防护）+
通过 env 注入 run_id/root （stage_skill 使用这些来追加回队列），然后排出意图
子会话结束后排队到磁盘。创作和登陆完全跨流程分开
这里：反射器仅附加意图，发起者专门验证和着陆。

马尾辫：run()是“分离后台作业”的主体（同步spawn→wait→drain）； “不阻止主机停止”分离是由调用 run() 的第 7 阶段调度在挂钩顶层的后台启动的。 spawn_fn 是可注入的（系统测试使用假反射器脚本代替真正的 claude）。在 v0 中仍然可以容忍对转录本上限竞争（cap.md open）的精确处理。"""
import json
import logging
import os
import subprocess
import sys
import tarfile
from pathlib import Path

from autoharness import config
from autoharness.hook import capture, promoter
from autoharness.lib import (
    atomic,
    counters,
    layer,
    redact,
    sidecar,
    skill_store,
    validate,
)

log = logging.getLogger(__name__)


def description_index(roots=None, *, agent_only=False):
    roots = roots or {}
    lines = []
    for lyr in config.active_layers():
        root = roots.get(lyr)
        skills = layer.skills_dir(lyr, root)
        if not skills.exists():
            continue
        for path in sorted(skills.glob(f"*/{skill_store.SKILL_FILE}")):
            symbol = path.parent.name
            if agent_only and not sidecar.is_agent_created(lyr, symbol, root):
                continue  # 策展人只看到自己的本事；本地人/用户远离池
            fm = validate._frontmatter(path.read_text(encoding="utf-8")) or {}
            name = fm.get("name") or symbol
            desc = fm.get("description") or "(no description)"
            lines.append(f"- {name} [{lyr}]: {desc}")
    return "\n".join(lines) if lines else "(no live skills yet)"


def build_bundle(window, index, spec, digest=""):
    preamble = (
        "# Prior context digest (older exchanges, tool outputs omitted — background only,"
        " never an evidence source)\n\n" + digest + "\n\n"
    ) if digest else ""
    return (
        preamble
        + "# Episode window (redacted)\n\n" + window
        + "\n\n# Existing skills (compare-first: dedupe / patch / where)\n\n" + index
        + "\n\n# Authoring + format spec (write to satisfy this)\n\n" + spec + "\n"
    )


def build_curator_bundle(index, spec):
    # 策展人整合了整个特工创作的图书馆，而不是一集——所以没有窗口。
    return (
        "# Agent-authored skills (consolidate: merge narrow siblings into class-level umbrellas)\n\n"
        + index
        + "\n\n# Authoring + format spec (merged skills must satisfy this)\n\n" + spec + "\n"
    )


# Fork-Carrier 反映指令（G 方向）：随着 -p 提示符到达（新用户打开
# 分叉对话）——永远不要作为 --agent/--system-prompt，这会使父前缀无效。
# 履行 F1 协调义务：新规则必须取代相矛盾的旧声明。
FORK_INSTRUCTION = (
    "Autoharness reflection pass (forked session: the conversation above is your evidence source).\n"
    "Compare-first against the skill index below: prefer patching an existing skill over creating a\n"
    "new one; distill only class-level reusable lessons, never session narratives. When you distill\n"
    "a new rule or preference, search the managed skill trees for overlapping or contradicting\n"
    "statements and stage updates so the new supersedes the old. Propose every change exclusively\n"
    "via the stage_skill tool — never write files directly. Evidence must quote this session\n"
    "verbatim. If nothing is worth keeping, stage nothing.\n"
)


def build_fork_command(*, session_id, claude_bin):
    return [claude_bin, "-p", "--resume", str(session_id), "--fork-session",
            "--dangerously-skip-permissions"]


def build_fork_prompt(index, spec):
    return (FORK_INSTRUCTION
            + "\n# Existing skills (compare-first: dedupe / patch / where)\n\n" + index
            + "\n\n# Authoring + format spec (write to satisfy this)\n\n" + spec + "\n")


def build_command(*, agent, claude_bin):
    # 反射是一项无人值守的后台工作——没有人批准工具调用，因此请跳过
    # 权限提示。安全边界由代理工具白名单控制
    # (Read/Grep/Glob/stage_skill) + 顶级 PreToolUse 写 backstop，而不是按提示。
    # （实时 e2e：反射器的真实 stage_skill 调用被权限门阻止，只能
    # “叙事”;只有带着这面旗帜才能落地。）
    return [claude_bin, "-p", "--agent", agent, "--dangerously-skip-permissions"]


def child_env(run_id, root, *, base_env=None):
    env = dict(os.environ if base_env is None else base_env)
    env[config.CHILD_SESSION_ENV] = "1"
    env[config.RUN_ID_ENV] = run_id
    env[config.PROJECT_ROOT_ENV] = str(root)
    return env


def _spawn_error(proc, argv):
    """返回对运行帐户安全的有界、经过编辑的子诊断。"""
    stderr = redact.redact(str(proc.stderr or "")).strip()[-2000:]
    return {
        "argv0": redact.redact(str(argv[0])) if argv else None,
        "returncode": proc.returncode,
        "stderr_tail": stderr,
    }


def _detached_spawn(argv, env, bundle):
    """运行反射器子进程直至完成；在 stderr 上报告崩溃而不是丢弃它。"""
    proc = subprocess.run(argv, input=bundle, text=True, env=env, capture_output=True, check=False)
    if proc.returncode != 0:
        error = _spawn_error(proc, argv)
        print(f"reflector child {error['argv0']} exited {proc.returncode}: "
              f"{error['stderr_tail']}", file=sys.stderr)
    return proc


def _record_spawn_failure(run_id, roots, proc, argv):
    """将崩溃的反射器保留在运行帐户中（#160）。

    分离启动 DEVNULL 整个过程（dispatch.py），所以上面的打印和
    退出代码到达操作员。运行/帐户是已经运行的落地运行；判决
    （如果孩子在死前表现出意图）与事故记录一起保存。"""
    if proc is None or getattr(proc, "returncode", 0) == 0:
        return
    state = layer.state_dir(layer.PROJECT, roots.get(layer.PROJECT))
    runs = state / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    account = runs / f"{run_id}.json"
    record = json.loads(account.read_text(encoding="utf-8")) if account.exists() else {"run_id": run_id}
    record["spawn_error"] = _spawn_error(proc, argv)
    atomic.write_text(account, json.dumps(record, ensure_ascii=False, indent=2))


def run(window_text, run_id, *, roots, repo_name=None, agent=None, claude_bin=None,
        spec_path=None, digest="", session_id=None, carrier=None, spawn_fn=None):
    roots = roots or {}
    proot = roots.get(layer.PROJECT)
    spec = (spec_path or config.FORMAT_SPEC).read_text(encoding="utf-8")

    carrier = carrier or config.REFLECTOR_CARRIER
    if carrier == "fork" and session_id:  # 没有会话可分叉 -> 捆绑链（故障安全）
        argv = build_fork_command(session_id=session_id, claude_bin=claude_bin or config.CLAUDE_BIN)
        payload = build_fork_prompt(description_index(roots), spec)  # -p 从 stdin 读取提示
    else:
        argv = build_command(agent=agent or config.REFLECTOR_AGENT,
                             claude_bin=claude_bin or config.CLAUDE_BIN)
        payload = build_bundle(window_text, description_index(roots), spec, digest=digest)

    env = child_env(run_id, proot)
    proc = (spawn_fn or _detached_spawn)(argv, env, payload)
    verdicts = promoter.drain(run_id, roots=roots, repo_name=repo_name)
    _record_spawn_failure(run_id, roots, proc, argv)
    return verdicts


def _snapshot_skills(run_id, roots):
    """预运行库快照（E方向，镜像Hermes）：涵盖一风险原子着陆
    可逆归档不能——整个馆长都把库写错了。恢复是一个
    手动拆包；旋转使每层保持 SNAPSHOT_KEEP。"""
    snapdir = layer.state_dir(layer.PROJECT, roots.get(layer.PROJECT)) / "snapshots"
    snapdir.mkdir(parents=True, exist_ok=True)
    for lyr in config.active_layers():
        skills = layer.skills_dir(lyr, roots.get(lyr))
        if not skills.exists():
            continue
        with tarfile.open(snapdir / f"{run_id}-{lyr}.tar.gz", "w:gz") as tar:
            tar.add(skills, arcname="skills")
        kept = sorted(snapdir.glob(f"*-{lyr}.tar.gz"), key=lambda p: p.stat().st_mtime)
        for old in kept[: max(0, len(kept) - config.SNAPSHOT_KEEP)]:
            old.unlink()


def run_curator(run_id, *, roots, repo_name=None, agent=None, claude_bin=None,
                spec_path=None, spawn_fn=None):
    roots = roots or {}
    try:
        _snapshot_skills(run_id, roots)
    except OSError:
        pass  # 暂时性磁盘问题不得静默禁用管理
    except Exception:
        log.exception('unexpected snapshot error; curator running without safety net')
    spec = (spec_path or config.FORMAT_SPEC).read_text(encoding="utf-8")
    bundle = build_curator_bundle(description_index(roots, agent_only=True), spec)

    argv = build_command(agent=agent or config.CURATOR_AGENT,
                         claude_bin=claude_bin or config.CLAUDE_BIN)
    env = child_env(run_id, roots.get(layer.PROJECT))
    proc = (spawn_fn or _detached_spawn)(argv, env, bundle)
    verdicts = promoter.drain(run_id, roots=roots, repo_name=repo_name)
    _record_spawn_failure(run_id, roots, proc, argv)
    return verdicts


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--curate":
        run_id, proot, groot = argv[1:]
        return run_curator(run_id, roots={layer.PROJECT: Path(proot), layer.GLOBAL: Path(groot)})
    transcript_path, session_id, run_id, proot, groot = argv
    roots = {layer.PROJECT: Path(proot), layer.GLOBAL: Path(groot)}
    offset = counters.session_offset(session_id, roots[layer.PROJECT])
    window_text, new_offset = capture.window(transcript_path, offset)
    result = run(window_text, run_id, roots=roots, session_id=session_id,
                 digest=capture.digest(transcript_path, offset))
    counters.write_session_offset(session_id, new_offset, roots[layer.PROJECT])
    return result


if __name__ == "__main__":
    main()
