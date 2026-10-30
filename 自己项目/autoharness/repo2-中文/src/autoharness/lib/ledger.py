"""LED：每个符号仅附加分类帐 (.ledger.jsonl)。仅追加，从未修改。

条目带有自己的意图数据（理由/证据），在发起人通过时附加；
MNG 记录退休情况；拒绝记录不会被记录。该模块仅附加/读取，不
裁决内容（密文在密文中，必填字段在验证中）。仅附加保证
不变性：现有行永远不会被重写。

`evidence` 是一个不透明的字符串。新条目带有符号文件夹的相对路径
（“references/evidence-<hash>.md”，启动子物化的编辑切片）而不是内联
切片；在文件夹技能之前写入的条目保留其内联字符串（仅附加，从不
重写）。读者不得采用任何一种形式。

马尾辫：每次写入一行 JSON 行，在小条目下，POSIX 附加实际上是原子的；
并发跨进程附加到同一符号的严格排序锁被推迟到 mng
与边车一起。"""
import json

from autoharness.lib import layer

FILENAME = ".ledger.jsonl"


def path(lyr, name, root=None):
    return layer.symbol_dir(lyr, name, root) / FILENAME


def append(lyr, name, entry, root=None):
    p = path(lyr, name, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read(lyr, name, root=None, *, archived=False):
    """archived=True 将随符号一起传输的分类帐读取到 .archive/ (whole-dir
    重命名带有它），因此退休出处在驱逐后仍然可读。"""
    p = (layer.archive_dir(lyr, root) / name / FILENAME) if archived else path(lyr, name, root)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
