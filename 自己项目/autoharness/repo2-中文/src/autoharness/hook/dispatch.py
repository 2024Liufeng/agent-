"""单一调度程序：所有插件挂钩事件的一个入口点，按事件名称路由到匹配的“on_*”。

架构§执行仅存在于钩子全局层：“hooks.json”仅指向此文件，每个
管道执行步骤通过这一扇门进入并由“hook_event_name”调度；未知/
丢失的事件名称将被安全地忽略（故障安全 - 新的主机事件不得使该插件崩溃）。 E6
平台合约固定详细信息：
- `Stop` = 每回合一次 (S6) → 在停止时，两层的请求计数器各+1（MNG 速率）
  分母），然后运行 CAP 触发； `SubagentStop`（反射器完成，S4）不被路由，不被计数。
- `PreToolUse`：`Skill` → MNG 分子检测（`tool_input` 中的标识，S5）； ‘读入’
  托管符号目录 → 相同分子（主要消耗路径，E8），反射器除外
  读取（库比较，而不是使用）；反射器“agent_type”（在 S3 负载中携带）
  `Write`/`Edit` → 拒绝（插件顶级后备方案 - 插件代理不遵守其自己的钩子，S1）。
- 触发反射在分离的后台作业中启动（主机分离：不阻止主机停止）；
  生成 CLI 条目连接到启动器。

马尾辫：独立发射是一种一劳永逸的 Popen；孤儿/超时隔离的稳健性有待观察。"""
import hashlib
import json
import os
import re
import subprocess
import sys

MIN_PYTHON = (3, 11)  # tomllib (lib/redact.py) 在这里输入了 stdlib； README 徽章和 CI 矩阵引脚同一层


def _below_floor(version):
    return (f"autoharness: needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+, got "
            f"{version[0]}.{version[1]} at {sys.executable}. Every hook is off for this session; "
            f"point the hooks.json commands at a newer interpreter.")


# 此防护在故意导入包之前运行：下面的链是模块级别的端到端
# （调度 -> 启动子 -> redact -> tomllib），因此在较旧的解释器上，进程在导入时终止
# 并且dispatch()中的故障安全永远没有机会捕获它——主机显示了一个通用的钩子
# 错误并且插件内没有任何内容指出原因。退出 0：主机挂钩不得使会话失败。
if sys.version_info[:2] < MIN_PYTHON:
    print(_below_floor(sys.version_info), file=sys.stderr)
    raise SystemExit(0)

from autoharness import config  # noqa: E402
from autoharness.hook import (  # noqa: E402
    on_session_end,
    on_session_start,
    on_skill_call,
    on_stop,
    promoter,
)
from autoharness.lib import counters, layer  # noqa: E402

_SANITIZE = re.compile(r"[^A-Za-z0-9_-]")
_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def _roots(roots):
    return roots or {lyr: layer.default_root(lyr) for lyr in layer.LAYERS}


def _run_id(result):
    raw = str(result.get("session_id") or "")
    sid = _SANITIZE.sub("", raw)
    if not sid:
        sid = hashlib.sha256(raw.encode()).hexdigest()[:8] if raw else "run"
    return f"{sid}-{result.get('count', 0)}"


def _curate_run_id(event, pcount):
    raw = str(event.get("session_id") or "")
    sid = _SANITIZE.sub("", raw)
    if not sid:
        sid = hashlib.sha256(raw.encode()).hexdigest()[:8] if raw else "run"
    return f"{sid}-c{pcount}"  # 以单调请求计数为关键 → 每个策展人发布的内容都是唯一的


def _is_reflector(event):
    at = str(event.get("agent_type") or "")
    return at == config.REFLECTOR_AGENT or at.endswith(":reflector")


def _detached_launch(transcript_path, session_id, run_id, roots):
    try:
        subprocess.Popen(  # 主机分离：即发即忘，因此 Stop 挂钩立即返回
            [sys.executable, "-m", "autoharness.hook.spawn",
             str(transcript_path), str(session_id), run_id,
             str(roots[layer.PROJECT]), str(roots[layer.GLOBAL])],
            start_new_session=True, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return {"error": f"detached_launch failed: {type(exc).__name__}: {exc}"}
    return None


def _reflect(event, result, roots, launch=None):
    transcript_path = event.get("transcript_path")
    if not transcript_path:
        return
    (launch or _detached_launch)(transcript_path, result.get("session_id", ""), _run_id(result), roots)


def _consolidate_launch(run_id, roots):
    subprocess.Popen(  # 主机分离：与反射相同的即发即弃；馆长阅读图书馆，而不是文字记录
        [sys.executable, "-m", "autoharness.hook.spawn", "--curate", run_id,
         str(roots[layer.PROJECT]), str(roots[layer.GLOBAL])],
        start_new_session=True, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def dispatch(event, *, roots=None, reflect=None, consolidate=None):
    name = event.get("hook_event_name")
    roots = _roots(roots)
    proot = roots.get(layer.PROJECT)
    fire = reflect or _reflect
    curate = consolidate or _consolidate_launch
    try:
        if name == "SessionStart":
            return {"handled": name, "result": on_session_start.on_session_start(event, roots=roots)}
        if name == "Stop":
            if os.environ.get(config.CHILD_SESSION_ENV):
                return {"handled": name, "result": {"triggered": False, "reason": "recursion_guard"}}
            if not config.DISABLE_GLOBAL:
                counters.bump_request(layer.GLOBAL, roots.get(layer.GLOBAL))  # MNG 分母（每转）
            pcount = counters.bump_request(layer.PROJECT, proot)
            promoter.drain(config.INTERACTIVE_RUN_ID, roots=roots)  # /学习和其他会议期间提案；空时无操作
            result = on_stop.on_stop(event, root=proot)
            if result.get("triggered"):
                fire(event, result, roots)
            if config.CONSOLIDATE_EVERY_N and pcount % config.CONSOLIDATE_EVERY_N == 0:
                curate(_curate_run_id(event, pcount), roots)  # 定期内容级合并过程（比反射少见）
            return {"handled": name, "result": result}
        if name == "SessionEnd":
            result = on_session_end.on_session_end(event, root=proot)
            if result.get("triggered"):
                fire(event, result, roots)
            return {"handled": name, "result": result}
        if name == "PreToolUse":
            tool = event.get("tool_name")
            child = bool(os.environ.get(config.CHILD_SESSION_ENV))
            if tool in _WRITE_TOOLS and (child or _is_reflector(event)):
                return {"deny": True, "reason": "reflector may only stage intents, not write files"}
            if not child:  # 方向 H：每个主会话工具调用都会推进活动分子
                sid = event.get("session_id")
                if isinstance(sid, str) and sid:
                    try:
                        counters.bump_session(sid, proot)
                    except ValueError:
                        pass  # 不安全的会话 ID：跳过计数，永远不会使主机挂钩崩溃
            if tool == "Skill":
                return {"handled": name, "result": on_skill_call.on_skill_call(event, roots=roots)}
            if tool == "Read":
                if _is_reflector(event):
                    return {"handled": name, "result": {"counted": False, "reason": "reflector_read"}}
                return {"handled": name, "result": on_skill_call.on_skill_read(event, roots=roots)}
            return {"ignored": True, "reason": "untracked PreToolUse"}
    except Exception as exc:  # 故障安全：有缺陷的处理程序决不能使主机挂钩崩溃
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {"ignored": True, "reason": f"unrouted event: {name!r}"}


def _emit(verdict):
    if verdict.get("deny"):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": verdict.get("reason", "denied"),
        }}))
        return
    result = verdict.get("result") or {}
    if verdict.get("handled") == "SessionStart" and result.get("context"):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": result["context"],
        }}))
        return
    handled = verdict.get("handled")
    if handled:
        print(json.dumps({"handled": handled, "result": result}), file=sys.stderr)


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # 格式错误的钩子输入→忽略，永远不会使主机崩溃
    _emit(dispatch(event))
    return 0


if __name__ == "__main__":
    sys.exit(main())
