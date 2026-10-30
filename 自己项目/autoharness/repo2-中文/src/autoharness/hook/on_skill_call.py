"""三向使用检测：`PreToolUse(Skill)` 碰撞 `use`（唯一的速率分子）；主会话“PreToolUse(Read)”进入托管符号目录会碰撞“view”（仅观察）。纯观察，无拦截。

mng.md：速率分子 = 使用次数，存储在所使用符号的 sidecar 中，与层无关
（身份决定哪一层）。测量（实验/E8_numerator_capture）：模型的主导
消耗路径是直接Read SKILL.md/子文件，几乎没有Skill工具，所以Read
路径是分子的承载一半。 **零入侵红线——只算自产
符号**，永远不要为本机/用户技能编写 sidecar（触摸它们违反了“请勿触摸
主人的工作”）。递归防护与 CAP 相同：反射器子会话不计算在内。坏/未知/
同名不明确的符号并在“.archive”故障安全下读取，而不会导致主机挂钩崩溃。

马尾辫：事件中符号身份的确切关键=阶段 0 尖峰（mng.md 打开）；现在，通过几个候选键的字段容错回退来提取。"""
import os
from pathlib import Path

from autoharness import config
from autoharness.lib import layer, sidecar, skill_store


def _skill_name(event):
    nested = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    for src in (event, nested):
        for key in ("skill_name", "skill", "name"):
            v = src.get(key)
            if isinstance(v, str) and v.strip():
                return v
    return None


def _name_from_read_path(event, roots):
    nested = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    file_path = nested.get("file_path") or event.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        return None
    target = Path(file_path)
    for lyr in config.active_layers():
        base = layer.skills_dir(lyr, roots.get(lyr))
        try:
            rel = target.resolve().relative_to(base.resolve())
        except (ValueError, OSError):
            continue
        if len(rel.parts) > 1 and rel.parts[0] != ".archive":
            return rel.parts[0]
    return None


def _count(name, roots, kind):
    if not name:
        return {"counted": False, "reason": "no_skill"}
    try:
        lyr = skill_store.find(name, roots)
    except ValueError:
        return {"counted": False, "reason": "bad_or_ambiguous"}
    if lyr is None:
        return {"counted": False, "reason": "not_managed"}
    root = roots.get(lyr)
    try:
        if not sidecar.is_agent_created(lyr, name, root):
            return {"counted": False, "reason": "not_agent_created"}
        bump = sidecar.bump_use if kind == "use" else sidecar.bump_view
        count = bump(lyr, name, root)
    except (OSError, ValueError, TypeError, AttributeError):
        return {"counted": False, "reason": "sidecar_unavailable"}
    return {"counted": True, "kind": kind, "level": lyr, "name": name, "count": count}


def on_skill_call(event, *, roots=None):
    if os.environ.get(config.CHILD_SESSION_ENV):
        return {"counted": False, "reason": "recursion_guard"}
    return _count(_skill_name(event), roots or {}, "use")


def on_skill_read(event, *, roots=None):
    if os.environ.get(config.CHILD_SESSION_ENV):
        return {"counted": False, "reason": "recursion_guard"}
    roots = roots or {}
    return _count(_name_from_read_path(event, roots), roots, "view")
