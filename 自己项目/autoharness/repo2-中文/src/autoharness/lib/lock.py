"""跨进程独占锁：目标旁边的一个空锁文件，为一个临界区保留。

每个跨进程临界区都有一个原语（计数器的读-修改-写、启动器的
排水）。钩子是一个单独的短暂进程，因此“串行单个编写器”仅包含在一个钩子中
过程；同一状态目录上的两个会话（并行工作树重新映射到一个根，或一个会话
在文件级别交错。

该锁是建议性的，存在于专用路径上，而不存在于数据文件上：数据文件被替换
原子地，因此旧索引节点上持有的锁不会排除打开新索引节点的写入者。的
锁文件永远不会被删除，因此服务员总是争用同一个 inode；它是空的并且没有
它自己的状态。"""
import errno
import sys
from contextlib import contextmanager
from pathlib import Path

if sys.platform == "win32":
    import msvcrt

    def _lock(f):
        # LK_LOCK 在约 10 秒后放弃 EDEADLOCK；重试匹配羊群的无限期等待。
        while True:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                return
            except OSError as e:
                if e.errno != errno.EDEADLOCK:
                    raise

    def _unlock(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(f):
        fcntl.flock(f, fcntl.LOCK_EX)

    def _unlock(f):
        fcntl.flock(f, fcntl.LOCK_UN)


@contextmanager
def file_lock(path):
    """在块的持续时间内持有由“path”命名的锁，并在任何退出时释放它。"""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock_fd:
        _lock(lock_fd)
        try:
            yield
        finally:
            _unlock(lock_fd)