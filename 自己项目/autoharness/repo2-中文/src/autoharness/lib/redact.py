"""出口红线消费者：在秘密/PII 切片在下游实现时对其进行编辑。

规则集是配置指向的单一源（redaction_rules.toml，由 CAP egress + 共享）
LED）；该模块仅使用规则，但不拥有规则。每场比赛都被批量替换为
[已编辑：<类别>：<名称>]，为了安全而过度编辑是错误的。可以设定一个规则
`validate = "<name>"` 通过此处的命名检查器来控制其正则表达式匹配（例如 luhn for
Credit_card)，将未通过检查的序列保留在流中作为证据。

规则是根据原始文本收集的，并一次性应用，因此没有规则会遇到另一条规则
规则的占位符：占位符是删除内容的唯一记录，并且是顺序扫描
让后面的规则 (api_key_assignment) 与前面的规则占位符内的 `secret:<name>` 相匹配
并将其重写为嵌套的泛型。"""
import functools
import re
import tomllib
from pathlib import Path

from autoharness import config


def _passes_luhn(text):
    digits = re.sub(r"\D", "", text)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_VALIDATORS = {"luhn": _passes_luhn}


@functools.lru_cache(maxsize=4)
def _rules(rules_path):
    path = Path(rules_path) if rules_path else config.REDACTION_RULES
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    compiled = []
    for category in ("secret", "pii"):
        for rule in data.get(category, []):
            validate = rule.get("validate")
            if validate is not None and validate not in _VALIDATORS:
                raise ValueError(
                    f"unknown validator {validate!r} on rule {category}.{rule['name']}"
                )
            compiled.append(
                (category, rule["name"], re.compile(rule["pattern"]), _VALIDATORS.get(validate))
            )
    return compiled


def _token(category, name):
    return f"[REDACTED:{category}:{name}]"


def _overlaps(spans, start, end):
    return any(start < span[1] and span[0] < end for span in spans)


def redact(text, rules_path=None):
    spans = []
    key = str(rules_path) if rules_path else str(config.REDACTION_RULES)
    for category, name, rx, validator in _rules(key):
        for match in rx.finditer(text):
            if validator is not None and not validator(match.group(0)):
                continue
            if _overlaps(spans, match.start(), match.end()):
                continue
            spans.append((match.start(), match.end(), _token(category, name)))
    spans.sort(key=lambda span: span[0])

    out = []
    cursor = 0
    for start, end, token in spans:
        out.append(text[cursor:start])
        out.append(token)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def secret_hits(text, rules_path=None):
    """秘密规则的名称*文本*匹配 - 门，而不是重写（PII 保持仅编辑状态）。"""
    key = str(rules_path) if rules_path else str(config.REDACTION_RULES)
    return [
        name
        for category, name, rx, validator in _rules(key)
        if category == "secret"
        and any(validator is None or validator(match.group(0)) for match in rx.finditer(text))
    ]
