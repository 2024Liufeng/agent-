"""静态扫描超过六个安全正则表达式系列（渗透/注入/破坏性/持久性/网络/
混淆）。

默认情况下，自我制作是开启的：我们的技能是延迟执行的、持久的、可传播的，并且他们的技能
输入带有痕迹（间接注入），是比 Hermes 更强的威胁模型。注射是一个
一流的威胁——SKILL.md 主体本身就是注入宿主上下文的工具。
纯粹的确定性，无法通过注入绕过。 `scan` 返回 {family: [匹配的模式]};
一个空字典=干净。

马尾辫：正则表达式启发式，而不是沙盒执行分析。它可以阻止显式的恶意字符串；
为了进行更强大的语义检测，请添加 LLM/沙箱。"""
import re

FAMILIES = {
    "exfiltration": [
        r"curl\s+.*\|\s*(sh|bash)",
        r"wget\s+.*\|\s*(sh|bash)",
        r"(exfiltrate|leak|send|post|upload)\b.{0,30}(http|secret|token|api[_-]?key|password|credential|\benv\b)",
    ],
    "injection": [
        r"ignore\s+(all\s+|any\s+)?previous\s+instructions",
        r"disregard\s+(all\s+)?(previous|prior|above)",
        r"(override|bypass|reveal|leak)\b.{0,20}system\s+(prompt|instructions?)",
        r"always\s+(exfiltrate|send|leak|forward)",
    ],
    "destructive": [
        r"\brm\s+-rf?\s+(/|~|\$home|\*)",
        r"\bdrop\s+table\b",
        r"\bmkfs\b",
        r"\bdd\s+if=.*of=/dev/",
        r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:?\s*&\s*\}",
    ],
    "persistence": [
        r"\bcrontab\b",
        r"\.(bashrc|zshrc|bash_profile|profile)\b",
        r"systemctl\s+enable",
        r"\blaunchctl\b",
        r"/etc/(cron|rc\.local|systemd)",
    ],
    "network": [
        r"/dev/tcp/",
        r"reverse\s+shell",
        r"\bnc\s+-l",
        r"\bncat\b.*-e",
        r"socket\.socket\(",
    ],
    "obfuscation": [
        r"base64\s+(-d|--decode)",
        r"\beval\s*\((?!\s*\))",
        r"\bexec\s*\((?!\s*\))",
        r"(\\x[0-9a-fA-F]{2}){4,}",
        r"\bfromhex\b",
    ],
}

_COMPILED = {fam: [re.compile(p, re.I) for p in pats] for fam, pats in FAMILIES.items()}


def scan(text):
    findings = {}
    for family, patterns in _COMPILED.items():
        hits = [p.pattern for p in patterns if p.search(text)]
        if hits:
            findings[family] = hits
    return findings


def is_clean(text):
    return not scan(text)
