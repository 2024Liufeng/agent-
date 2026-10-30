"""回归：归档/恢复不得破坏名称冲突时的现有数据。"""
from pathlib import Path
from unittest.mock import patch

from autoharness.lib import skill_store


def _make_tree(root, lyr, name, marker="live"):
    """使用标记文件创建一个假技能目录。"""
    skills = Path(root) / lyr / "skills" / name
    skills.mkdir(parents=True, exist_ok=True)
    (skills / "SKILL.md").write_text(f"# {name}\nmarker={marker}")
    return skills


def test_archive_collision_preserves_old(tmp_path):
    """当存在同名存档时存档技能不得破坏旧存档。"""
    root = str(tmp_path)
    # 模拟：技能存在于存档和现场
    _make_tree(root, "global", "foo", marker="archived")
    archive_dest = Path(root) / "global" / ".archive" / "foo"
    archive_dest.mkdir(parents=True, exist_ok=True)
    (archive_dest / "SKILL.md").write_text("# foo\nmarker=old-archive")

    # 修补层助手以使用我们的 tmp 布局
    with patch("autoharness.lib.skill_store.layer") as lyr_mod:
        lyr_mod.symbol_dir.return_value = Path(root) / "global" / "skills" / "foo"
        lyr_mod.archive_dir.return_value = Path(root) / "global" / ".archive"
        result = skill_store.archive("global", "foo", root)

    # 旧存档必须仍然存在
    assert (archive_dest / "SKILL.md").read_text(encoding="utf-8") == "# foo\nmarker=old-archive"
    # 新档案落在带时间戳的路径上
    assert result is not None
    assert result != archive_dest
    assert (result / "SKILL.md").read_text(encoding="utf-8") == "# foo\nmarker=archived"


def test_restore_collision_preserves_live(tmp_path):
    """当Live Copy存在时恢复技能不得破坏Live Copy。"""
    root = str(tmp_path)
    _make_tree(root, "global", "foo", marker="live-current")
    archive_src = Path(root) / "global" / ".archive" / "foo"
    archive_src.mkdir(parents=True, exist_ok=True)
    (archive_src / "SKILL.md").write_text("# foo\nmarker=from-archive")

    with patch("autoharness.lib.skill_store.layer") as lyr_mod:
        lyr_mod.symbol_dir.return_value = Path(root) / "global" / "skills" / "foo"
        lyr_mod.archive_dir.return_value = Path(root) / "global" / ".archive"
        result = skill_store.restore("global", "foo", root)

    # 原始 Live 副本必须仍然存在
    live = Path(root) / "global" / "skills" / "foo"
    assert (live / "SKILL.md").read_text(encoding="utf-8") == "# foo\nmarker=live-current"
    assert result is not None
    assert result != live
    assert (result / "SKILL.md").read_text(encoding="utf-8") == "# foo\nmarker=from-archive"


def test_archive_repeated_timestamp_collision_gets_unique_suffix(tmp_path):
    root = str(tmp_path)
    archive_dest = Path(root) / "global" / ".archive" / "foo"
    archive_dest.mkdir(parents=True)
    (archive_dest / "SKILL.md").write_text("# foo\nmarker=old-archive")

    with (
        patch("autoharness.lib.skill_store.layer") as lyr_mod,
        patch("autoharness.lib.skill_store.time.strftime", return_value="20260929T120000"),
    ):
        live = Path(root) / "global" / "skills" / "foo"
        lyr_mod.symbol_dir.return_value = live
        lyr_mod.archive_dir.return_value = archive_dest.parent

        _make_tree(root, "global", "foo", marker="first")
        first = skill_store.archive("global", "foo", root)
        _make_tree(root, "global", "foo", marker="second")
        second = skill_store.archive("global", "foo", root)

    assert first.name == "foo.20260929T120000"
    assert second.name == "foo.20260929T120000.2"
    assert (archive_dest / "SKILL.md").read_text(encoding="utf-8") == "# foo\nmarker=old-archive"
    assert (first / "SKILL.md").read_text(encoding="utf-8") == "# foo\nmarker=first"
    assert (second / "SKILL.md").read_text(encoding="utf-8") == "# foo\nmarker=second"
