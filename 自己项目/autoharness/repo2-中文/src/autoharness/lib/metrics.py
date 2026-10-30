"""运行时运行状况指标：管道已保留的帐户的只读派生。

metrics.md：不断回答“这个维护层在做什么吗”——lara 事后分析
核心失败是“calls≈0”几周以来都没有被注意到，因为没有任何报告。区别于
eval（带有预算的离线判断）：这是已在磁盘上的每个会话的簿记，请重新读取。

**仅观察。** 这里没有任何内容可以提供生命周期决策 - 驱逐保持 mng 的速率
标准。更改度量定义绝不能改变系统行为。

派生的，从未新检测过：sidecar 三路计数器（use/view/patch +reused_gen），
每个交易品种仅附加分类账（删除条目带有absolute_into），运行级别判决账户
发起者写入，层请求计数器。死亡原因分区归档集：吸收
（合并为保护伞）/修剪（有意退休）/生命周期（MNG 率或容量，其中
不留下删除条目）——合并是形状收敛，而不是死亡，因此分裂是承载的。

马尾辫：窗口粒度是自创建以来累积的（镜像速率分母）；滚动的
窗口因 mng.md 中相同的开放问题而被推迟。"""
import json

from autoharness import config
from autoharness.lib import layer, ledger, sidecar, skill_store, validate


def _live_symbols(lyr, root):
    skills = layer.skills_dir(lyr, root)
    if not skills.exists():
        return []
    return [p.parent.name for p in skills.glob(f"*/{skill_store.SKILL_FILE}")
            if sidecar.is_agent_created(lyr, p.parent.name, root)]


def _archived_symbols(lyr, root):
    adir = layer.archive_dir(lyr, root)
    if not adir.exists():
        return []
    return [p.parent.name for p in adir.glob(f"*/{skill_store.SKILL_FILE}")]


def _deaths(lyr, root, names):
    causes = {"absorbed": 0, "pruned": 0, "lifecycle": 0}
    for name in names:
        entries = ledger.read(lyr, name, root, archived=True)
        deletes = [e for e in entries if e.get("action") == "delete"]
        if not deletes:
            causes["lifecycle"] += 1  # 由 MNG 存档：速率/容量，背后没有意图
        elif deletes[-1].get("absorbed_into"):
            causes["absorbed"] += 1
        else:
            causes["pruned"] += 1
    return causes


def _funnel(lyr, root):
    runs = layer.state_dir(lyr, root) / "runs"
    proposed = landed = 0
    families = {}
    if runs.exists():
        for path in runs.glob("*.json"):
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue  # 腐败的帐户永远不会中断报告
            for v in run.get("verdicts", []):
                proposed += 1
                if v.get("ok"):
                    landed += 1
                for family in v.get("findings", []):
                    families[family] = families.get(family, 0) + 1
    return {"proposed": proposed, "landed": landed, "rejected": proposed - landed}, families


def _category(lyr, name, root):
    body = skill_store.read_body(lyr, name, root) or ""
    return (validate._frontmatter(body) or {}).get("category") or "general"


def _by_category(lyr, root, live, cards, requests):
    """每个类别的召回率，基于层自己的分母。

    回答了图书馆级数字无法回答的一个问题：哪些类别的工作实际上是
    被拉动以及哪些是自重——表明是否继续存款的唯一证据
    归入一个类别。没有用途的类别在报告中保持为零；删除它会读作
    “没有这样的类别”而不是“这个类别已经死了”。

    与指数降级排名 (mng.md) 的统计数据不同，后者按条目划分，而不是
    比请求：一个问一个类别的成本是多少，这个问如何
    通常它是可以达到的。"""
    groups = {}
    for name, card in zip(live, cards, strict=True):
        g = groups.setdefault(_category(lyr, name, root), {"live_symbols": 0, "use_total": 0, "view_total": 0})
        g["live_symbols"] += 1
        g["use_total"] += card.get("use", 0)
        g["view_total"] += card.get("view", 0)
    for g in groups.values():
        g["recall_rate"] = g["use_total"] / requests if requests else 0
        g["view_rate"] = g["view_total"] / requests if requests else 0
    return dict(sorted(groups.items()))


def _layer_metrics(lyr, root):
    from autoharness.lib import counters

    live = _live_symbols(lyr, root)
    cards = [sidecar.read(lyr, name, root) for name in live]
    use_total = sum(c.get("use", 0) for c in cards)
    view_total = sum(c.get("view", 0) for c in cards)
    requests = counters.request_count(lyr, root)
    patched = [c for c in cards if c.get("patch", 0) > 0]
    reused = [c for c in patched if c.get("reused_gen", 0) >= c.get("patch", 0)]
    archived = _archived_symbols(lyr, root)
    funnel, families = _funnel(lyr, root)
    return {
        "live_symbols": len(live),
        "use_total": use_total,
        "view_total": view_total,
        "requests": requests,
        "recall_rate": use_total / requests if requests else 0,
        "view_rate": view_total / requests if requests else 0,
        "used_symbol_share": sum(1 for c in cards if c.get("use", 0)) / len(cards) if cards else 0,
        "archived_total": len(archived),
        "deaths": _deaths(lyr, root, archived),
        "funnel": funnel,
        "reject_families": families,
        "reuse_after_patch": len(reused) / len(patched) if patched else 0,
        "by_category": _by_category(lyr, root, live, cards, requests),
    }


def collect(roots=None):
    roots = roots or {}
    return {lyr: _layer_metrics(lyr, roots.get(lyr)) for lyr in config.active_layers()}
