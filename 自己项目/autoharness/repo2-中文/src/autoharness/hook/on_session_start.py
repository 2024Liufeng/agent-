"""MNG 延迟重新计算：在会话开始时，立即计算累积的账本 → 归档非活动符号，在该会话调用之前运行。

mng.md：非常驻主机没有后台扫描，因此驱逐会在 SessionStart 上进行 — 阅读 sidecar
（使用/查看计数器+锚点）+层请求计数器（分母）累积水印，运行
生命周期决策，并将要归档的列表一一移出活动树（归档=将
目录已失忆，可逆）。该决定仅读取累计数量（而不是此数量）
session 碰巧看到）→任何 repo 的 SessionStart 都会得出相同的结论。每次会话一次，无
节流。仅管理自行生成的符号（本地/用户技能保留在池之外，保留
零入侵）。

马尾辫：孤儿会话计数（崩溃会话的残留）的 GC 需要会话活跃信号来安全扫描（天真的扫描会错误地删除并发会话的实时计数），因此它会被推迟，直到该信号存在为止 - clear_session 原语已准备好（第 4 阶段），策略在 cap.md/mng.md 中保持打开状态。"""
import json
import uuid
from pathlib import Path

from autoharness import config
from autoharness.lib import counters, layer, lifecycle, sidecar, skill_store, validate

# 回忆自我注入（mng.md §认知面自持）：主机的原生描述回忆保持不变；
# 这个自产技能的紧凑索引依赖于 SessionStart extraContext，因此“无论
# 提供库”是我们自己的配置，而不是主机行为。按 frontmatter 类别分组
# （开放集，缺席 -> 一般），组内按字母顺序，每行分层标记。
INDEX_HEADER = (
    "Self-accumulated skills (autoharness-managed). When the task at hand matches a "
    "description below, you MUST consider loading that skill before proceeding."
)


def _sanitize(text, limit):
    return " ".join(str(text).split())[:limit]  # 基于行的表面：换行符是伪造的，折叠它们


def _fit(text, limit):
    """用省略号截断，以便剪切线读作剪切（hermes 的索引也是如此）。

    新的描述由发起人保留在预算内，因此这只会激发以下技能：
    早于大门——重要的是读者可以看出线路被切断了
    而不是为整个触发器取一个片段。"""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit - 3] + "..."


def _read_hint(roots, cwd):
    """链接的工作树的项目层被重新映射到主签出（layer.default_root），
    主机不会扫描技能 - 因此从工作树会话中列出了这些技能
    但技能工具无法加载它们。相反，将模型指向文件。"""
    if not cwd:
        return None
    skills = layer.skills_dir(layer.PROJECT, roots.get(layer.PROJECT)).resolve()
    if Path(cwd).resolve().is_relative_to(skills.parent.parent):
        return None
    return (f"[project] skills live outside this checkout, so the Skill tool cannot load them: "
            f"Read {skills}/<name>/SKILL.md instead.")


def recall_index(roots, cwd=None):
    if config.INDEX_SUSPENDED:
        return None
    groups, has_project = {}, False
    for lyr in config.active_layers():
        root = roots.get(lyr)
        skills = layer.skills_dir(lyr, root)
        if not skills.exists():
            continue
        for path in skills.glob(f"*/{skill_store.SKILL_FILE}"):
            name = path.parent.name
            if not sidecar.is_agent_created(lyr, name, root):
                continue
            fm = validate._frontmatter(path.read_text(encoding="utf-8")) or {}
            desc = _fit(fm.get("description") or "(no description)", config.INDEX_DESC_MAX_CHARS)
            cat = _sanitize(fm.get("category") or "general", 64) or "general"
            groups.setdefault(cat, []).append(f"- {_sanitize(name, 64)} [{lyr}]: {desc}")
            has_project = has_project or lyr == layer.PROJECT
    if not groups:
        return None  # 空库->零注入
    lines = [INDEX_HEADER, ""]
    for cat in sorted(groups):
        lines.append(f"## {cat}")
        lines.extend(sorted(groups[cat]))
    hint = _read_hint(roots, cwd) if has_project else None
    if hint:
        lines += ["", hint]
    return "\n".join(lines)


def last_run_summary(roots):
    """前一个耗尽的单行反沉默摘要（验证存储§判决可见性）：
    读取一次，然后使用——运行/下的帐户文件保留持久记录。"""
    p = layer.state_dir(layer.PROJECT, roots.get(layer.PROJECT)) / "last_run.json"
    if not p.exists():
        return None
    # 每个索赔人都拥有一个不同的目的地：另一个排水口可能会发布一个新的目的地
    # 在该消费者完成读取其声明的记录之前的last_run.json。
    consumed = p.with_name(f"{p.name}.{uuid.uuid4().hex}.consuming")
    try:
        p.rename(consumed)
    except OSError:
        return None
    try:
        last = json.loads(consumed.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    finally:
        try:
            consumed.unlink()
        except OSError:
            pass
    line = (f"autoharness last run: landed {last.get('landed', 0)}, "
            f"rejected {last.get('rejected', 0)}")
    if last.get("families"):
        line += f" ({', '.join(last['families'])})"
    if last.get("absorbed"):
        line += f"; merged {last['absorbed']} into umbrellas"
    if last.get("uncategorized"):
        line += f"; {last['uncategorized']} landed with no category (grouped under general)"
    return line


def _members(lyr, root):
    skills = layer.skills_dir(lyr, root)
    if not skills.exists():
        return []
    members = []
    for path in skills.glob(f"*/{skill_store.SKILL_FILE}"):
        name = path.parent.name
        if not sidecar.is_agent_created(lyr, name, root):
            continue
        s = sidecar.read(lyr, name, root)
        members.append({"name": name, "use": s.get("use", 0), "view": s.get("view", 0),
                        "anchor": s.get("anchor", 0)})
    return members


def on_session_start(event=None, *, roots=None):
    roots = roots or {}
    archived = {}
    for lyr in config.active_layers():
        root = roots.get(lyr)
        names = lifecycle.evaluate(
            _members(lyr, root), counters.request_count(lyr, root),
            maturity=config.MATURITY_THRESHOLD[lyr], capacity=config.CAPACITY[lyr],
            review_suspended=config.GRADUATION_REVIEW_SUSPENDED,
        )
        for name in names:
            skill_store.archive(lyr, name, root)
        archived[lyr] = names
    parts = [last_run_summary(roots), recall_index(roots, (event or {}).get("cwd"))]  # 归档后建立索引
    context = "\n\n".join(p for p in parts if p) or None
    return {"archived": archived, "context": context}
