from pathlib import Path

from autoharness.lib import validate

AGENT = Path(__file__).resolve().parents[1] / "agents" / "reflector.md"


def test_reflector_frontmatter_present():
    fm = validate._frontmatter(AGENT.read_text(encoding="utf-8"))
    assert fm is not None and fm.get("name") and fm.get("model")


def test_reflector_tools_are_least_privilege():
    fm = validate._frontmatter(AGENT.read_text(encoding="utf-8"))
    tools = fm["tools"]
    for allowed in ("Read", "Grep", "Glob"):
        assert allowed in tools
    # 插件 MCP 工具被命名为 mcp__plugin_<plugin>_<server>__<tool> — 一个裸露的“stage_skill”
    # （甚至 mcp__stage_skill__stage_skill） 被默默地丢弃，留下反射器
    # 根本不写脸。直播 e2e 准确地捕捉到了这一点。
    assert "mcp__plugin_autoharness_stage_skill__stage_skill" in tools
    for forbidden in ("Write", "Edit", "Bash"):
        assert forbidden not in tools  # 作者≠验证者：没有通往实时技能树的路径


def test_reflector_body_binds_emit_only():
    body = AGENT.read_text(encoding="utf-8")
    assert "stage_skill" in body  # 唯一被认可的写脸


def test_reflector_body_teaches_folder_skill():
    body = AGENT.read_text(encoding="utf-8")
    for token in ("files", "scripts/", "templates/", "references/", "assets/", "class-level"):
        assert token in body


def test_reflector_prompt_has_no_authoring_gates():
    body = AGENT.read_text(encoding="utf-8").lower()
    for gate in ("at most one", "do not capture", "only valid if"):
        assert gate not in body


def test_reflector_prompt_encourages_generation():
    body = AGENT.read_text(encoding="utf-8").lower()
    assert "one intent per" in body
    assert body.index("patch") < body.index("`create`")


def test_reflector_create_is_umbrella_first():
    body = AGENT.read_text(encoding="utf-8").lower()
    assert "umbrella" in body  # 新技能作为一个类别诞生，而不是一个会话工件
    assert body.index("umbrella") > body.index("`create`")  # 重点落在创建梯级上


def test_reflector_can_consolidate_existing_overlap():
    body = AGENT.read_text(encoding="utf-8").lower()
    # (a) 廉价的全球整合：反射器可以折叠两个预先存在的重叠
    # 一起掌握技能——不仅仅是捕捉当前情节的教训。与此规则不同
    # 是它删除了该剧集从未触及的“多余的现有”技能。
    assert "redundant" in body
    assert "delete" in body


def test_reflector_requires_absorbed_into_on_delete():
    # 反射器也会删除（折叠预先存在的重叠），因此它需要相同的失败关闭
    # 合并会计作为策展人 - 否则折叠将被记录为简单的修剪
    assert "absorbed_into" in AGENT.read_text(encoding="utf-8")


def test_reflector_authors_category():
    # 类别对自注入回忆指数进行分组；从未发出，该索引是一组平坦的。
    # frontmatter 形式（“category:”）是将字段创作与单词区别开来的。
    assert "category:" in AGENT.read_text(encoding="utf-8")


def test_prompt_carries_reconcile_duty():
    # F1（新取代旧）：精炼的新规则必须找出相矛盾的旧陈述
    body = AGENT.read_text(encoding="utf-8").lower()
    assert "supersede" in body or "contradict" in body


def test_reflector_picks_category_from_the_injected_index():
    # 我们对类别膨胀的防御：爱马仕免费提供它（类别是目录
    # 模型已经看到）；我们必须这么说，因为该字段是自由文本
    body = AGENT.read_text(encoding="utf-8").lower()
    rule = next(ln for ln in body.splitlines() if "`category:`" in ln)
    assert "index" in rule  # 从索引重用指令位于类别规则本身


def test_reflector_may_not_claim_the_promoter_verdict():
    # E11：启动子在子进程退出后运行，一次重放有反射器报告
    # “两者都被发起人接受，没有任何错误”，而根本没有写任何东西。它
    # 无法观察判决，因此提示必须禁止断言。
    body = AGENT.read_text(encoding="utf-8").lower()
    assert "cannot know" in body or "do not claim" in body
    assert "promoter" in body
