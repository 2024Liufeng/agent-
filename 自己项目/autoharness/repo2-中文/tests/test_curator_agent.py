from pathlib import Path

from autoharness.lib import validate

AGENT = Path(__file__).resolve().parents[1] / "agents" / "curator.md"


def test_curator_frontmatter_present():
    fm = validate._frontmatter(AGENT.read_text(encoding="utf-8"))
    assert fm is not None and fm.get("name") and fm.get("model")


def test_curator_tools_are_least_privilege():
    fm = validate._frontmatter(AGENT.read_text(encoding="utf-8"))
    tools = fm["tools"]
    for allowed in ("Read", "Grep", "Glob"):
        assert allowed in tools
    # 与反射器相同的仅发射写入面 - 提出意图，切勿触摸活树
    assert "mcp__plugin_autoharness_stage_skill__stage_skill" in tools
    for forbidden in ("Write", "Edit", "Bash"):
        assert forbidden not in tools


def test_curator_ports_umbrella_levers():
    body = AGENT.read_text(encoding="utf-8").lower()
    for lever in ("umbrella", "class-level", "prefix", "references/", "templates/", "scripts/", "assets/"):
        assert lever in body


def test_curator_teaches_three_ways_to_consolidate():
    body = AGENT.read_text(encoding="utf-8").lower()
    assert "existing umbrella" in body   # (a) 合并到一个已经广泛的成员中
    assert "new umbrella" in body        # (b) 制作一把新伞
    assert "demote" in body              # (c) 将狭窄细节降级为支持子文件


def test_curator_delete_is_archive_not_destruction():
    body = AGENT.read_text(encoding="utf-8").lower()
    assert "archive" in body
    assert "recoverable" in body  # 删除阶段是存档移出，而不是硬删除


def test_curator_only_touches_agent_created():
    body = AGENT.read_text(encoding="utf-8").lower()
    assert "created_by:agent" in body or "agent-created" in body  # 本地/用户技能不足


def test_curator_is_iterative():
    body = AGENT.read_text(encoding="utf-8").lower()
    assert "iterate" in body or "next umbrella" in body


def test_curator_judges_by_maintainer_bar_not_pairwise():
    body = AGENT.read_text(encoding="utf-8").lower()
    assert "maintainer" in body  # “维护者会写 N 个技能还是一个有 N 个小节的技能？”


def test_curator_requires_absorbed_into_on_delete():
    body = AGENT.read_text(encoding="utf-8")
    assert "absorbed_into" in body  # 字段是策展人的强制语言（下游失败关闭）


def test_curator_carries_the_category_duties():
    # 策展人是唯一可以移动两个杠杆的机构：将内容折叠成雨伞，并且
    # 重新归档标签。如果没有这三个，它就永远不会写入类别，并且索引保持不变。
    body = AGENT.read_text(encoding="utf-8").lower()
    assert "category" in body
    assert "backfill" in body or "back-fill" in body  # (b) 随着时间的推移，现有技能得到一个类别
    assert "same category is not a reason" in body   # (c) 标签不得替代合并
