"""每个符号边车：created_by /三向计数器（使用/视图/补丁）/创建锚点/验证。

单一实现，与符号目录一起跨层传输（promote/archive 的 mv 带有
它，包括计数器，原子地）。操作元数据位于 sidecar 中，而不是 SKILL.md 中
frontmatter（保护召回，不污染用户的工作）。 created_by:agent 是 MNG 的
会员密钥+发起人“只碰自产”检查的依据。

计数器分割（mng.md，hermes-parity方向C——镜像Hermes use/view/patch）：`use`=实际负载
通过技能工具，唯一的生命周期率分子； `view` = main-session 读入托管
dir，仅观察（将实际消费与策展浏览混合在一起，因此它只原谅
毕业评审）； `patch` = 发起人发布了更新/补丁。 `reused_gen` 标记第一次使用
补丁之后（Hermes patch_ Generation 对）——最接近的可用“技能帮助”信号，
仅由指标消耗。传统的单分子“calls”在读取时迁移到“use”一次。

计数器碰撞在整个读取-修改-写入过程中持有独占的每个符号锁，因此并发
挂钩保留独立的使用/视图/补丁增量和重用生成。"""
import json

from autoharness.lib import atomic, layer, lock

FILENAME = ".sidecar.json"


def path(lyr, name, root=None):
    return layer.symbol_dir(lyr, name, root) / FILENAME


def _migrate(data):
    if "calls" in data:
        data["use"] = data.get("use", 0) + data.pop("calls")
    return data


def read(lyr, name, root=None):
    p = path(lyr, name, root)
    if not p.exists():
        return {}
    return _migrate(json.loads(p.read_text(encoding="utf-8")))


def write(lyr, name, data, root=None):
    atomic.write_text(path(lyr, name, root), json.dumps(data, ensure_ascii=False, indent=2))


def create(lyr, name, anchor, root=None):
    data = {"created_by": "agent", "use": 0, "view": 0, "patch": 0,
            "anchor": int(anchor), "verification": None}
    write(lyr, name, data, root)
    return data


def _bump(lyr, name, key, root=None):
    lock_path = path(lyr, name, root).with_suffix(".json.lock")
    with lock.file_lock(lock_path):
        data = read(lyr, name, root)
        data[key] = data.get(key, 0) + 1
        if key == "use" and data.get("patch", 0) > data.get("reused_gen", 0):
            data["reused_gen"] = data["patch"]  # 补丁后首次使用 = 改进后重用
        write(lyr, name, data, root)
    return data[key]


def bump_use(lyr, name, root=None):
    return _bump(lyr, name, "use", root)


def bump_view(lyr, name, root=None):
    return _bump(lyr, name, "view", root)


def bump_patch(lyr, name, root=None):
    return _bump(lyr, name, "patch", root)


def is_agent_created(lyr, name, root=None):
    return read(lyr, name, root).get("created_by") == "agent"
