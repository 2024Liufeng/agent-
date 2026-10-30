"""每次运行意图队列：writer=stage_skill(append) / reader=promoter(read+clear)，一个共享源。

持久（崩溃后恢复）：仅附加到存储库层状态区域中的每次运行文件，从不附加
触及技能树。启动子运行读取→陆地（原子，幂等）→清除：陆地之间的碰撞
并清除将文件保留在原位，下一次运行的孤立扫描将恢复它（至少一次+
原子地=有效地恰好一次）；在没有运行的极端情况下，零着陆（自动防故障）。"""
import json
import re

from autoharness.lib import layer, lock

_SAFE_RUN = re.compile(r"^[A-Za-z0-9_-]+$")


def _path(run_id, root=None):
    if not isinstance(run_id, str) or not _SAFE_RUN.match(run_id):
        raise ValueError(f"unsafe run id: {run_id!r}")
    return layer.state_dir(layer.PROJECT, root) / "intents" / f"{run_id}.jsonl"


def append(run_id, intent, root=None):
    p = _path(run_id, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    # O_APPEND只保留一个写到PIPE_BUF的整体，以及一个阶段性的技能体
    # 远远超过了这一点。两个重叠的反射器运行可以交错
    # 中线，并且不可解析的线会堵塞此运行的每个后续排水管。
    with lock.file_lock(p.with_suffix(p.suffix + ".lock")):
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(intent, ensure_ascii=False) + "\n")


def read(run_id, root=None):
    p = _path(run_id, root)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def clear(run_id, root=None):
    p = _path(run_id, root)
    if p.exists():
        p.unlink()


def orphans(root=None):
    d = layer.state_dir(layer.PROJECT, root) / "intents"
    if not d.exists():
        return []
    return sorted(f.stem for f in d.glob("*.jsonl"))
