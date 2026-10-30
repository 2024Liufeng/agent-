from autoharness import config


def test_format_spec_exists_and_states_required_fields():
    assert config.FORMAT_SPEC.is_file()
    text = config.FORMAT_SPEC.read_text(encoding="utf-8")
    assert text.strip()
    # 必需的字段名称是 #416 linter 和反射器创作之间的共享契约——省略一个，它们就会漂移
    for token in ["name", "description", "global"]:
        assert token in text


def test_redaction_rules_exists():
    assert config.REDACTION_RULES.is_file()


def test_format_spec_states_subfile_contract():
    text = config.FORMAT_SPEC.read_text(encoding="utf-8")
    # 子文件类别+指针规则是验证和反射器创作之间的共享契约
    for token in ["scripts/", "templates/", "assets/", "references/", "Pointer rule"]:
        assert token in text


def test_format_spec_states_altitude_cap():
    text = config.FORMAT_SPEC.read_text(encoding="utf-8")
    # 高度规则是验证线帽和反射器创作之间的共享契约
    for token in ["Altitude", "SKILL_BODY_MAX_LINES"]:
        assert token in text


def test_format_spec_states_description_trigger_contract():
    text = config.FORMAT_SPEC.read_text(encoding="utf-8")
    # 描述作为触发器是验证提示/预算检查和反射器创作之间的共享契约
    for token in ["trigger", "use when", "INDEX_DESC_MAX_CHARS"]:
        assert token.lower() in text.lower()


def test_format_spec_states_category_field():
    text = config.FORMAT_SPEC.read_text(encoding="utf-8")
    # 类别是经过验证的 frontmatter 和自注入召回指数的分组键；
    # 此处未说明，REF 永远不会发出它，并且每个技能都归为一组
    for token in ["category", "INDEX_DESC_MAX_CHARS"]:
        assert token in text
    # 故意与描述门不对称：非法被拒绝，丢失通过
    assert "deliberately asymmetric" in text
    assert "**rejected**" in text and "**allowed through**" in text


def test_format_spec_states_the_one_sentence_rule():
    text = config.FORMAT_SPEC.read_text(encoding="utf-8")
    # 借鉴自hermes：描述是索引行，所以规则是在
    # 预算先触发——旧的四元素配方产生了 385 个字符的描述，
    # 指数削减中间条款（E11，第一次真正的重播）
    for token in ["one sentence", "trigger first", "user would actually type", "body"]:
        assert token in text
