"""技能CRUD：原子SKILL.md写入+双层查找（当相同名称跨越两层时出现歧义错误）+应用增量+存档+孤儿.tmp扫描。

持久性在这一处使用原子（same-dir temp + os.replace），因此 live 永远不会写一半。
find 将 Hermes 的 `_find_skill` 扩展到全局+项目层的联合；跨界同名
两个层 → 错误（发起人在解决更新/删除时使用此来消除层的歧义）。
apply_delta 要求 old_string 唯一匹配（拒绝未找到和多重匹配
模糊性），确定性重建。 archive 以原子方式将 symbol_dir 移动到 `.archive` （保留
LED/边车）；登陆删除和MNG（第6阶段）驱逐共享这一路径。"""
import os
import shutil
import time

from autoharness import config
from autoharness.lib import atomic, layer

SKILL_FILE = "SKILL.md"


def _collision_safe_dest(dest):
    if not dest.exists():
        return dest
    suffix = time.strftime("%Y%m%dT%H%M%S")
    candidate = dest.with_name(f"{dest.name}.{suffix}")
    counter = 2
    while candidate.exists():
        candidate = dest.with_name(f"{dest.name}.{suffix}.{counter}")
        counter += 1
    return candidate


def skill_path(lyr, name, root=None):
    return layer.symbol_dir(lyr, name, root) / SKILL_FILE


def write_body(lyr, name, body, root=None):
    atomic.write_text(skill_path(lyr, name, root), body)


def read_body(lyr, name, root=None):
    p = skill_path(lyr, name, root)
    return p.read_text(encoding="utf-8") if p.exists() else None


def exists(lyr, name, root=None):
    return skill_path(lyr, name, root).exists()


def find(name, roots=None):
    roots = roots or {}
    hits = [lyr for lyr in config.active_layers() if exists(lyr, name, roots.get(lyr))]
    if len(hits) > 1:
        raise ValueError(f"ambiguous skill {name!r} present in layers {hits}")
    return hits[0] if hits else None


def apply_delta(body, old_string, new_string):
    count = body.count(old_string)
    if count == 0:
        raise ValueError("delta old_string not found in live body")
    if count > 1:
        raise ValueError("delta old_string is ambiguous (multiple matches)")
    return body.replace(old_string, new_string, 1)


def remove(lyr, name, root=None):
    sdir = layer.symbol_dir(lyr, name, root)
    if sdir.exists():
        shutil.rmtree(sdir)


def archive(lyr, name, root=None):
    sdir = layer.symbol_dir(lyr, name, root)
    if not sdir.exists():
        return None
    dest = layer.archive_dir(lyr, root) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest = _collision_safe_dest(dest)
    os.replace(sdir, dest)
    return dest


def restore(lyr, name, root=None):
    src = layer.archive_dir(lyr, root) / name
    if not src.exists():
        return None
    dest = layer.symbol_dir(lyr, name, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest = _collision_safe_dest(dest)
    os.replace(src, dest)
    return dest


def sweep_orphans(lyr, root=None):
    skills = layer.skills_dir(lyr, root)
    if not skills.exists():
        return []
    removed = []
    for tmp in skills.rglob("*.tmp"):
        tmp.unlink()
        removed.append(tmp)
    return removed
