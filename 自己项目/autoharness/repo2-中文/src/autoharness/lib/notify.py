"""运行帐户通知：告诉操作员运行到达或拒绝的时刻，而不是下一个会话。

SessionStart 摘要行是唯一的另一个表面，它晚于一个会话到达并进行计数
但没有名字。一旦耗尽完成，这将推出相同的运行帐户 - 选择加入，默认情况下关闭：

- AUTOHARNESS_NOTIFY=桌面 → 本机通知（macOS 上的 osascript，Linux 上的通知发送）
  存在；其他任何事情都是静默的无操作）。
- AUTOHARNESS_NOTIFY_CMD="<argv>" → 使用 stdin 上的运行记录 JSON 运行该命令以及
  AUTOHARNESS_NOTIFY_SUMMARY 中的一行摘要 — Slack/webhooks/其他任何内容的钩子。

通过构造失败打开：drain 仅在写入帐户并清除队列后调用此函数，
并且 send() 吞噬了所有内容，因此缺少二进制文件、非零退出或挂起命令（由
每个通道的 NOTIFY_TIMEOUT_S）可以延迟耗尽，但永远不会失败或重放。没有什么经过
shell：技能名称来自模型提出的意图（被拒绝的意图可以携带任何字符串），因此它们
仅作为 argv / stdin 数据传输，在所有其他出口进行相同的编辑后。命令运行
设置了递归保护，因此本身启动“claude”的通知程序不会被捕获或反映。"""
import json
import os
import shlex
import shutil
import subprocess
import sys

from autoharness import config
from autoharness.lib import redact

_TITLE = "autoharness"
_MAX_NAME = 64
_MAX_LISTED = 5  # “+N more”之前每个摘要存储桶的名称：通知正文，而不是报告


def _clean(name):
    # 截断前编辑：剪切可以分割秘密，因此其规则不再匹配
    s = redact.redact("".join(ch for ch in str(name or "?") if ch.isprintable()))
    return s[:_MAX_NAME] or "?"


def _listing(items):
    shown = ", ".join(items[:_MAX_LISTED])
    return shown + (f" +{len(items) - _MAX_LISTED} more" if len(items) > _MAX_LISTED else "")


def summary(rows):
    """一行命名了运行的内容：“create foo, patch bar·rejected: baz”。"""
    landed = [f"{r.get('action')} {_clean(r.get('name'))}" for r in rows if r.get("ok")]
    rejected = [_clean(r.get("name")) for r in rows if not r.get("ok")]
    parts = []
    if landed:
        parts.append(_listing(landed))
    if rejected:
        parts.append("rejected: " + _listing(rejected))
    return " · ".join(parts)


def _run(argv, *, stdin=None, env=None):
    subprocess.run(argv, input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, env=env,
                   timeout=config.NOTIFY_TIMEOUT_S, check=False)


def _desktop(line):
    if sys.platform == "darwin":
        # argv，不是内插的 -e 字符串：消息是 AppleScript 永远不会解析的数据
        _run(["osascript", "-e", "on run argv", "-e",
              "display notification (item 1 of argv) with title (item 2 of argv)", "-e", "end run",
              line, _TITLE])
    elif shutil.which("notify-send"):
        _run(["notify-send", _TITLE, line])


def _command(cmd, record, line):
    # POSIX shlex 规则会吃掉 Windows 路径的反斜杠；字符串去那里
    # 按原样创建进程（仍然没有 shell），目标按本机规则解析它。
    argv = cmd.strip() if os.name == "nt" else shlex.split(cmd)
    if not argv:
        return
    rows = [{**r, "name": _clean(r.get("name"))} for r in record.get("verdicts") or []]
    env = {**os.environ, "AUTOHARNESS_NOTIFY_SUMMARY": line, config.CHILD_SESSION_ENV: "1"}
    _run(argv, stdin=json.dumps({**record, "verdicts": rows}, ensure_ascii=False), env=env)


def send(record):
    """将一条运行记录 ({"run_id", "verdicts"}) 推送到启用的任一通道。从不加注。"""
    mode, cmd = config.NOTIFY, config.NOTIFY_CMD
    if mode != "desktop" and not cmd:
        return
    try:
        line = summary(record.get("verdicts") or [])
    except Exception:
        return
    if not line:
        return
    for enabled, channel in ((mode == "desktop", lambda: _desktop(line)),
                             (bool(cmd), lambda: _command(cmd, record, line))):
        if not enabled:
            continue
        try:
            channel()
        except Exception:
            pass  # 通知者是一种礼貌；该帐户已经是持久的并且队列已清除
