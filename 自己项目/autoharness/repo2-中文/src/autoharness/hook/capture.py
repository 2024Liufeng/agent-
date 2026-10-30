"""CAP 切换窗口：自上次反射以来主机记录的原始字节切片 - 零解析。

cap.md + docs/plans/raw-capture.md：记录是主机的内部事件日志，而不是聊天日志；
这里的任何角色/文本提取都是一种格式假设，实时窗口被证明是错误的（元记录为
空角色，工具结果为伪用户轮流）。所以 capture 根本不解释格式 -
反射器（法学硕士）可以很好地读取原始 JSONL。 capture 仅移动字节：从会话字节中切片
水印到 EOF，剪辑超大记录和窗口总数（工具转储/base64 不得破坏
子上下文），传递出口红线（编辑），并将文本加上新水印返回给
来电者。 **永远不要写回主机原始日志**（它不是我们的）。缺失/陈旧/负面
水印（压缩重写文件）无法安全地在窗口上限范围内完全重新读取。"""
import json
from pathlib import Path

from autoharness import config
from autoharness.lib import redact

TRUNCATION_MARK = "...[truncated]"


def _clip(line, cap):
    """剪辑 *line*，使其 UTF-8 编码保持在 *cap* 字节以内。"""
    encoded = line.encode("utf-8")
    if len(encoded) <= cap:
        return line
    truncated = encoded[:cap].decode("utf-8", errors="ignore")
    return truncated + TRUNCATION_MARK


def window(transcript_path, offset=0, *, max_record_bytes=None, max_window_bytes=None,
           rules_path=None):
    record_cap = max_record_bytes or config.CAPTURE_MAX_RECORD_BYTES
    window_cap = max_window_bytes or config.CAPTURE_MAX_WINDOW_BYTES
    path = Path(transcript_path)
    if not path.exists():
        return "", 0
    # 寻找过去的偏移量，而不是读取文件来将其切掉：一个钩子
    # 每轮运行一次，一个长会话的记录是兆字节的历史记录
    # 打电话已经知道不需要了。
    with open(path, "rb") as f:
        new_offset = f.seek(0, 2)
        if not 0 <= offset <= new_offset:
            offset = 0
        f.seek(offset)
        tail = f.read(new_offset - offset)
    lines = [_clip(line, record_cap)
             for line in tail.decode("utf-8", errors="replace").splitlines()]
    kept, total = [], 0
    for line in reversed(lines):
        total += len(line.encode("utf-8")) + 1
        if total > window_cap:
            kept.append(TRUNCATION_MARK)
            break
        kept.append(line)
    return redact.redact("\n".join(reversed(kept)), rules_path), new_offset


def _digest_record(line, max_chars):
    record = json.loads(line)
    if record.get("type") not in ("user", "assistant"):
        return None
    role = record["type"]
    content = record["message"]["content"]
    if isinstance(content, str):
        parts = [content]
    else:
        parts = []
        for block in content:
            kind = block.get("type")
            if kind == "text" and block.get("text"):
                parts.append(block["text"])
            elif kind == "tool_use":
                parts.append(f"[tool: {block.get('name', '?')}]")
    if not parts:
        return None
    text = " ".join(p.strip() for p in parts if p.strip())
    if len(text) > max_chars:
        text = text[:max_chars] + TRUNCATION_MARK
    return role, text


def digest(transcript_path, end_offset, *, max_exchanges=None, max_record_chars=None,
           max_digest_bytes=None, rules_path=None):
    exchanges = max_exchanges or config.DIGEST_EXCHANGES
    record_chars = max_record_chars or config.DIGEST_MAX_RECORD_CHARS
    digest_cap = max_digest_bytes or config.DIGEST_MAX_BYTES
    path = Path(transcript_path)
    if not path.exists() or end_offset <= 0:
        return ""
    with open(path, "rb") as f:
        data = f.read(end_offset)
    kept, total, users_seen = [], 0, 0
    for line in reversed(data.decode("utf-8", errors="replace").splitlines()):
        try:
            entry = _digest_record(line, record_chars)
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            continue
        if entry is None:
            continue
        role, text = entry
        rendered = f"{role}: {text}"
        total += len(rendered) + 1
        if total > digest_cap:
            kept.append(TRUNCATION_MARK)
            break
        kept.append(rendered)
        if role == "user":
            users_seen += 1
            if users_seen >= exchanges:
                break
    return redact.redact("\n".join(reversed(kept)), rules_path) if kept else ""
