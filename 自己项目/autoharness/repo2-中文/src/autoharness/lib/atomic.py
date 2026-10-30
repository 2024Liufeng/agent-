"""POSIX 原子写入原语：same-dir temp + fsync + os.replace — live 永远不会写一半。

validate-store的“持久化的唯一方法= same-dir temp + os.replace”在这里单独实现；
Skill_store / sidecar / counters都重用它。写入过程中发生崩溃仅留下相同目录的 .tmp 孤儿
（扫过skill_store启动）；目标文件要么是旧内容，要么是新内容，永远不会
写了一半。"""
import os
import stat
import tempfile
from pathlib import Path


def write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = None
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            if mode is not None:
                os.chmod(tmp, mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_text(path, text):
    write_bytes(path, text.encode("utf-8"))
