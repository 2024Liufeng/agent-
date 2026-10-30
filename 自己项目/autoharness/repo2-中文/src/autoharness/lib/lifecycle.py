"""MNG决策：纯确定性，调用率+试用期+毕业评审+容量竞争→产生“归档列表”。不触及任何磁盘。

mng.md：生存标准是**调用率**（自创建以来的调用次数/层请求），而不是
挂钟。缓刑保护新人（分母低于成熟度阈值=活着但不
被驱逐，不计入上限）。毕业审查恰好位于试用期边界：
零调用的成熟符号将被存档，并且永远不会进入池中 - 完全试用，没有
由于分子计算读取路径，因此使用真正的休眠。毕业生（调用≥1）死亡
仅按容量争用：当成熟池超过上限时，按升序归档最低的
率。该决策仅读取累积水印（sidecar调用+锚点、层请求计数），
所以任何 repo 的 SessionStart 都会得出相同的结论。 on_session_start 获取此列表并运行
每个上的 Skill_store.archive 。

马尾辫：滚动窗口速率被推迟（在 mng.md 中打开）。"""

import hashlib


def _rate(use, denom):
    return use / denom if denom else 0.0


def evaluate(members, request_count, *, maturity, capacity, review_suspended=False):
    archive = set()
    survivors = []
    for m in members:
        denom = max(0, request_count - m.get("anchor", 0))
        if denom < maturity:
            continue  # 缓刑：活着，没有被驱逐，不计入上限
        use = m.get("use", m.get("calls", 0))  # 价格仅供食用；遗留调用==使用
        if use == 0:
            # 毕业审查，软化（C方向/爱马仕“缺乏证据”）：已查看
            # 即使没有技能调用，符号也具有回忆值 - 仅使用 AND 查看两者
            # 零是真正的休眠。暂停门完全停止了审查，而
            # 召回表面已知已损坏（零使用归档将掩盖表面的故障）。
            if not review_suspended and m.get("view", 0) == 0:
                archive.add(m["name"])
            continue  # 不管怎样，幸存的零使用符号都不会出现在池中
        survivors.append((_rate(use, denom), m["name"]))
    if len(survivors) > capacity:
        survivors.sort(
            key=lambda rn: (rn[0], hashlib.sha256(rn[1].encode()).digest())
        )  # 速率然后确定性哈希
        archive.update(name for _, name in survivors[: len(survivors) - capacity])
    return sorted(archive)
