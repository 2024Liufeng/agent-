"""将图层名称解析为其在磁盘上的位置 - 图层作为路径出现的位置。

代码的其余部分与层无关，并将层作为参数传递。未知层/不安全
符号名称总是被拒绝（自动防故障、默认拒绝），因为这是
构建文件系统路径：权限升级/路径遍历必须在此处停止。

项目层的标识是会话 cwd — 除了在链接的 git 工作树内，它位于何处
重新映射到主工作树根，因此来自一个存储库的所有工作树的计数器/意图/技能
降落在一处并在工作树移除后幸存下来。仅重新映射链接工作树的情况（git-dir
与 git-common-dir 不同）：普通存储库、存储库子目录和非 git 目录保留 cwd
逐字记录，因此嵌套项目永远不能归因于封闭的存储库。任何 git 失败都会发生
回到cwd（自动防故障）。"""
import re
import subprocess
from functools import cache
from pathlib import Path

GLOBAL = "global"
PROJECT = "project"
LAYERS = (GLOBAL, PROJECT)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _check_layer(layer):
    if layer not in LAYERS:
        raise ValueError(f"unknown layer: {layer!r} (expected one of {LAYERS})")


# 名称成为目录或文件，原子写入将 `.<8 chars>.tmp` 添加到其中：留在里面
# NAME_MAX（255 字节），并远离 Windows 拒绝的内容（保留的设备名称、尾随点）
MAX_NAME_LEN = 100
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def _check_name(name):
    if not isinstance(name, str) or ".." in name or not _SAFE_NAME.match(name):
        raise ValueError(f"unsafe symbol name: {name!r}")


def check_new_name(name):
    """autoharness 即将创建一个名称：安全且可在每个文件系统上使用。现有名称
    （用户的“con”技能，一项长期遗留的技能）仅保留在 _check_name 中，因此读取永远不会中断。"""
    _check_name(name)
    if len(name) > MAX_NAME_LEN or name.endswith(".") or name.split(".")[0].lower() in _WINDOWS_RESERVED:
        raise ValueError(f"unusable new name: {name!r} (over {MAX_NAME_LEN} chars, a trailing dot, or "
                         "reserved on Windows)")


def _main_worktree_root(cwd):
    return _main_worktree_root_resolved(str(Path(cwd).resolve()))


@cache
def _main_worktree_root_resolved(cwd):
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-dir", "--git-common-dir"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        lines = proc.stdout.splitlines()
        if proc.returncode != 0 or len(lines) < 2:
            return Path(cwd)
        git_dir, common_dir = ((Path(cwd) / line).resolve() for line in lines[:2])
        if git_dir != common_dir:
            return common_dir.parent
    except (OSError, subprocess.SubprocessError):
        pass
    return Path(cwd)


def default_root(layer):
    _check_layer(layer)
    if layer == GLOBAL:
        return Path.home() / ".claude"
    return _main_worktree_root(str(Path.cwd())) / ".claude"


def _root(layer, root):
    _check_layer(layer)
    return Path(root) if root is not None else default_root(layer)


def skills_dir(layer, root=None):
    return _root(layer, root) / "skills"


def archive_dir(layer, root=None):
    return skills_dir(layer, root) / ".archive"


def state_dir(layer, root=None):
    return _root(layer, root) / "autoharness"


def symbol_dir(layer, name, root=None):
    _check_name(name)
    return skills_dir(layer, root) / name


SUBFILE_DIRS = ("scripts", "templates", "assets", "references")
EVIDENCE_PREFIX = "references/evidence-"


def check_subfile(rel, *, new=False):
    if not isinstance(rel, str) or not rel or ".." in rel or "\\" in rel:
        raise ValueError(f"unsafe subfile path: {rel!r}")
    segments = rel.split("/")
    if len(segments) < 2 or segments[0] not in SUBFILE_DIRS:
        raise ValueError(f"subfile path must sit under one of {SUBFILE_DIRS}: {rel!r}")
    for segment in segments:
        (check_new_name if new else _check_name)(segment)


def subfile_path(layer, name, rel, root=None):
    check_subfile(rel)
    return symbol_dir(layer, name, root) / rel
