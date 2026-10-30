"""回归：_PLACEHOLDER 不得与合法的 Markdown 标注标签匹配。"""
from autoharness.lib.validate import _PLACEHOLDER


def test_placeholder_still_catches_real_placeholders():
    """仍会检测到已知的占位符标签。"""
    for tag in ["<TODO>", "<FIXME>", "<PLACEHOLDER>", "<TBD>", "<REPLACE_ME>", "<INSERT_HERE>"]:
        assert _PLACEHOLDER.search(f"fill in {tag} later"), f"should match {tag}"


def test_placeholder_ignores_markdown_callouts():
    """合法的 Markdown 标注标签不得触发完整性检查。"""
    for tag in ["<NOTE>", "<IMPORTANT>", "<WARNING>", "<EXAMPLE>", "<CAUTION>", "<TIP>"]:
        assert not _PLACEHOLDER.search(f"see {tag} for details"), f"should NOT match {tag}"


def test_placeholder_still_catches_todo_fixme_colon():
    """TODO:/FIXME:/XXX: 前缀形式仍然有效。"""
    assert _PLACEHOLDER.search("TODO: implement this")
    assert _PLACEHOLDER.search("FIXME: broken")
    assert _PLACEHOLDER.search("XXX: needs review")
