"""用户可调用的学习技能（第 12 阶段，方向 B1）：Hermes /learn 等效项 — 实时
代理通过 SAME 提案链按需提取（stage_skill -> 发起人），守卫未被丢弃。"""
from pathlib import Path

from autoharness.lib import validate

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "learn" / "SKILL.md"


def test_learn_skill_exists_and_passes_own_gate():
    body = SKILL.read_text(encoding="utf-8")
    v = validate.validate({"action": "create", "name": "learn", "level": "project",
                           "reason": "r", "evidence": "e"}, body)
    assert v["ok"], v["findings"]  # 我们自己的 linter：触发提示、高度、安全性、完整性
    assert "remember" in body and "distill" in body


def test_learn_skill_routes_through_stage_skill_not_writes():
    body = SKILL.read_text(encoding="utf-8")
    assert "stage_skill" in body
    for forbidden in ("Write(", "Edit("):
        assert forbidden not in body
