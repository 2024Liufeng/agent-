import importlib

import pytest

from autoharness import config
from autoharness.lib import layer


def test_cadence_positive():
    assert isinstance(config.REFLECT_EVERY_N, int) and config.REFLECT_EVERY_N > 0


def test_consolidate_cadence_sparser_than_reflect():
    # 管理像反射一样定期运行，但更罕见——合并库是一个更粗糙的节拍
    assert isinstance(config.CONSOLIDATE_EVERY_N, int)
    assert config.CONSOLIDATE_EVERY_N > config.REFLECT_EVERY_N


def test_curator_agent_named_and_distinct():
    assert config.CURATOR_AGENT and isinstance(config.CURATOR_AGENT, str)
    assert config.CURATOR_AGENT != config.REFLECTOR_AGENT


def test_env_overrides_consolidate_cadence(monkeypatch):
    monkeypatch.setenv("AUTOHARNESS_CONSOLIDATE_EVERY_N", "7")
    importlib.reload(config)
    try:
        assert config.CONSOLIDATE_EVERY_N == 7
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_layered_knobs_cover_both_layers_and_positive():
    for knob in (config.MATURITY_THRESHOLD, config.CAPACITY):
        assert set(knob) == set(layer.LAYERS)
        assert all(isinstance(v, int) and v > 0 for v in knob.values())


def test_contract_data_pointers_named_in_lib():
    assert config.REDACTION_RULES.name == "redaction_rules.toml"
    assert config.FORMAT_SPEC.name == "format_spec.md"
    assert config.REDACTION_RULES.parent == config.FORMAT_SPEC.parent


def test_spawn_pointers_present_and_distinct():
    assert config.REFLECTOR_AGENT and isinstance(config.REFLECTOR_AGENT, str)
    assert config.CLAUDE_BIN and isinstance(config.CLAUDE_BIN, str)
    envs = {config.RUN_ID_ENV, config.PROJECT_ROOT_ENV, config.CHILD_SESSION_ENV}
    assert len(envs) == 3 and all(e and isinstance(e, str) for e in envs)


def test_env_overrides_knobs_else_defaults(monkeypatch):
    monkeypatch.setenv("AUTOHARNESS_REFLECT_EVERY_N", "2")
    monkeypatch.setenv("AUTOHARNESS_MATURITY_PROJECT", "3")
    monkeypatch.setenv("AUTOHARNESS_CAPACITY_PROJECT", "1")
    importlib.reload(config)
    try:
        assert config.REFLECT_EVERY_N == 2
        assert config.MATURITY_THRESHOLD[layer.PROJECT] == 3
        assert config.CAPACITY[layer.PROJECT] == 1
        assert config.CAPACITY[layer.GLOBAL] == 20  # 取消设置 → 默认保留
    finally:
        monkeypatch.undo()
        importlib.reload(config)  # 恢复套件其余部分的默认设置


# #150：自述文件将这些记录为操作员可设置的，但没有覆盖测试
# 到达他们那里。没有设置的旋钮总是读取其默认值，因此每个默认值
# 该文件中的断言仍然通过，而记录的环境变量可能有
# config.py 中拼写错误，没有什么值得注意的。
@pytest.mark.parametrize(
    ("env_var", "attribute", "raw", "expected"),
    [
        # 模块属性为GRADUATION_REVIEW_SUSPENDED；环境变量不是。
        ("AUTOHARNESS_GRADUATION_SUSPENDED", "GRADUATION_REVIEW_SUSPENDED", "1", True),
        ("AUTOHARNESS_INDEX_SUSPENDED", "INDEX_SUSPENDED", "1", True),
        ("AUTOHARNESS_SNAPSHOT_KEEP", "SNAPSHOT_KEEP", "11", 11),
        ("AUTOHARNESS_CARRIER", "REFLECTOR_CARRIER", "fork", "fork"),
    ],
)
def test_documented_knob_reads_its_env_var(
    monkeypatch, env_var, attribute, raw, expected
):
    # 守卫守卫：如果发货的默认值等于我们设置的值，则
    # 下面的情况会通过忽略环境变量，所以大声说出来。
    assert getattr(config, attribute) != expected, (
        f"{attribute} already defaults to {expected!r}, so this case cannot prove "
        f"{env_var} is read — pick a value the default does not already hold"
    )
    monkeypatch.setenv(env_var, raw)
    importlib.reload(config)
    try:
        assert getattr(config, attribute) == expected
    finally:
        monkeypatch.undo()
        importlib.reload(config)  # 恢复套件其余部分的默认设置


def test_int_knob_falls_back_to_default_on_non_numeric(monkeypatch):
    # _int_env 吞下 ValueError 并返回默认值，因此是一个拼写错误的值
    # 与未设置的没有区别。固定那个，所以后备是
    # 记录下来的决定而不是无人注意的事故。
    monkeypatch.setenv("AUTOHARNESS_SNAPSHOT_KEEP", "five")
    with pytest.warns(UserWarning, match="not a valid integer"):
        importlib.reload(config)
    try:
        assert config.SNAPSHOT_KEEP == 5
    finally:
        monkeypatch.undo()
        importlib.reload(config)
