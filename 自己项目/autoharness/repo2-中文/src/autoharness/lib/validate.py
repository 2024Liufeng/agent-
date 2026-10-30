"""六个确定性的 linter 类，运行内存中的成形结果（最终全文 + 意图），无 LLM 调用（快速、精确、防注入）。

六个类（验证存储§验证）：安全技能_防护/结构#416/LED存在/
内容完整/与全局仓库无关/自制标签（仅触摸自制）。产生一个
判决{好的，调查结果：[（家庭，细节）]}；非空结果=拒绝。创建不受
“自产”检查（在所有六个类别通过后，由发起人盖上其标签）。

当给出 base_dir 时，添加#416“引用的 .py 语法”检查（引用的现有 .py
必须解析），加上子文件引用检查：正文中提到的白名单目录路径必须是
包含在意图的“文件”中或已经存在于 base_dir 下。 target_is_agent_created 传入
由发起人阅读 sidecar 后；创建时它是 None 并且可以豁免。当body=None时（删除/
删除_文件形状没有身体变化），四个身体相关类（安全/结构/完整/
global) 被跳过，留下 LED + 自行生成的检查 —remove_file 添加其路径门
（check_remove_path：子文件白名单+证据切片拒绝）。

文件夹技能“文件”（相对路径→内容）获得自己的“文件”系列（check_files：形状，路径
通过layer.check_subfile进行门，计数/大小上限）+指针规则（每个携带的子文件必须是
正文中引用）+每个子文件的安全性和全局扫描 - 否则子文件将是微不足道的
绕过两个大门。发起人具体化的“参考/证据-*”切片是意图的禁区
双向：在“files”中携带一个并通过remove_file删除一个都会被拒绝。"""
import ast
import re

from autoharness import config
from autoharness.lib import layer, redact, skills_guard

_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n)?", re.DOTALL)
_PLACEHOLDER = re.compile(r"\b(TODO|FIXME|XXX):|<(?:TODO|FIXME|XXX|TBD|PLACEHOLDER|REPLACE[_ ]?ME|INSERT[_ ]?HERE|FILL[_ ]?IN)>")
_ABS_PATH = re.compile(r"(?:/home/|/Users/|/root/)[^\s`)\]]+|[A-Za-z]:\\[^\s`)\]]+")
_PY_REF = re.compile(r"[\w./-]+\.py")
_SUBFILE_REF = re.compile(r"(?<![A-Za-z0-9_./-])(?:\./)?(?:{})/[A-Za-z0-9._/-]+".format("|".join(layer.SUBFILE_DIRS)))
_MODIFY = ("update", "patch", "remove_file", "delete")
# 描述作为触发代理：触发描述命名何时使用它（“在……时使用”）或列出一个
# 用户将输入的文字短语（引用）。裸露的主题标签两者都没有，也永远不会触发。
_QUOTED_PHRASE = re.compile(r'"[^"]+"|\'[^\']+\'|`[^`]+`')
_WHEN = re.compile(r"(?i)\bwhen")


def _has_cue(text):
    return bool(_WHEN.search(text) or _QUOTED_PHRASE.search(text))


def _block_scalar(lines, start, parent_indent, header):
    """解码平面字符串字段的 YAML 文字/折叠标量，而不是一般的 YAML 文档。"""
    modifiers = header.split("#", 1)[0].strip()[1:]
    explicit = next((int(ch) for ch in modifiers if ch.isdigit()), None)
    end = start
    while end < len(lines) and (not lines[end].strip(" ")
                                or len(lines[end]) - len(lines[end].lstrip(" ")) > parent_indent):
        end += 1
    raw = lines[start:end]
    first = next((i for i, line in enumerate(raw) if line.strip(" ")), None)
    indent = parent_indent + explicit if explicit else (
        len(raw[first]) - len(raw[first].lstrip(" ")) if first is not None else max([parent_indent + 1, *(len(line) for line in raw)])
    )
    if explicit is None and first is not None and any(len(line) > indent for line in raw[:first]):
        raise ValueError("leading empty scalar line exceeds detected indentation")
    for offset, line in enumerate(raw):
        if (line.lstrip(" ").startswith("#")
                and len(line) - len(line.lstrip(" ")) < indent):
            raw, end = raw[:offset], start + offset
            break  # 缩进的尾随注释位于标量之外
    content = []
    for line in raw:
        if line.strip(" ") and len(line) - len(line.lstrip(" ")) < indent:
            raise ValueError("block scalar line is less indented than its content")
        content.append(line[indent:] if len(line) >= indent else "")
    chunks, index = [], 0
    while index < len(content):
        line = content[index]
        if not line:
            chunks.append("\n")
            index += 1
            continue
        chunks.append(line)
        following = index + 1
        while following < len(content) and not content[following]:
            following += 1
        if (header[0] == ">" and following < len(content)
                and not line.startswith((" ", "\t"))
                and not content[following].startswith((" ", "\t"))):
            chunks.append(" " if following == index + 1 else "\n" * (following - index - 1))
        else:
            chunks.append("\n" * (following - index))
        index = following
    value = "".join(chunks)
    if "-" in modifiers:
        value = value.rstrip("\n")
    elif "+" not in modifiers:
        value = value.rstrip("\n")
        if value:
            value += "\n"
    return value, end


def _frontmatter(body):
    """读取平面字符串字段：普通/引用值和 YAML 文字/折叠块标量。"""
    m = _FRONTMATTER.match(body)
    if not m:
        return None
    fm = {}
    lines = (m.group(1) + "\n").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        s = line.strip()
        if not s or s.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        v = value.strip()
        if re.fullmatch(r"[>|](?:[1-9][-+]?|[-+][1-9]?)?(?:[ \t]+#.*)?", v):
            try:
                v, index = _block_scalar(lines, index, len(line) - len(line.lstrip(" ")), v)
            except ValueError:
                return None
        elif len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        fm[key.strip()] = v
    return fm


def _body_lines(body):
    """非空白的身体线条，排除前线——高度代理。"""
    m = _FRONTMATTER.match(body)
    rest = body[m.end():] if m else body
    return sum(1 for ln in rest.splitlines() if ln.strip())


def description_findings(desc):
    """描述是主机的回忆键。超长截断；无提示的标签永远不会触发。"""
    findings = []
    if len(desc) > config.INDEX_DESC_MAX_CHARS:
        findings.append(("description",
                         f"description is {len(desc)} chars — a new skill must fit the "
                         f"{config.INDEX_DESC_MAX_CHARS}-char index budget (one sentence, trigger "
                         f"first, ends with a period). The session-start index truncates longer "
                         f"descriptions to {config.INDEX_DESC_MAX_CHARS - 3} chars + '...', which "
                         "destroys the routing signal. Move the detail into the body"))
    if not _has_cue(desc):
        findings.append(("trigger",
                         "description has no trigger cue: add 'use when …' and/or a literal phrase "
                         "the user would type — an abstract topic-label never fires"))
    return findings


def _evidence_slice_denied(rel):
    if rel.startswith(layer.EVIDENCE_PREFIX):
        return [("files", f"{rel}: promoter-materialized evidence slices are off-limits to intents")]
    return []


def check_remove_path(rel):
    try:
        layer.check_subfile(rel)
    except ValueError as exc:
        return [("files", str(exc))]
    return _evidence_slice_denied(rel)


def check_files(files, *, base_dir=None, creating=False):
    """携带子文件。仅保留正在创建的名称（创建或尚未在 base_dir 中的文件）
    新名称限制；现有的遗留文件必须保持可更新。"""
    if files is None:
        return []
    if not isinstance(files, dict):
        return [("files", "files must be a map of relative path -> content")]
    findings = []
    if len(files) > config.STAGE_MAX_FILES:
        findings.append(("files", f"more than {config.STAGE_MAX_FILES} subfiles"))
    total = 0
    for rel, content in files.items():
        try:
            layer.check_subfile(rel, new=creating or (base_dir is not None and not (base_dir / rel).exists()))
        except ValueError as exc:
            findings.append(("files", str(exc)))
            continue
        if not isinstance(content, str):
            findings.append(("files", f"{rel}: content must be a string"))
            continue
        findings += _evidence_slice_denied(rel)
        size = len(content.encode("utf-8"))
        total += size
        if size > config.STAGE_MAX_FILE_BYTES:
            findings.append(("files", f"{rel} exceeds {config.STAGE_MAX_FILE_BYTES} bytes"))
    if total > config.STAGE_MAX_FILES_TOTAL_BYTES:
        findings.append(("files", f"subfiles exceed {config.STAGE_MAX_FILES_TOTAL_BYTES} bytes total"))
    return findings


def _backtick_spans(text):
    """平衡反引号代码跨度；无与伦比的/转义的开场白是普通的散文。"""
    ticks = list(re.finditer(r"`+", text))
    spans, index = [], 0
    while index < len(ticks):
        opener = ticks[index]
        prefix = text[:opener.start()]
        if (len(prefix) - len(prefix.rstrip("\\"))) % 2:
            index += 1
            continue
        closer = next((i for i in range(index + 1, len(ticks))
                       if ticks[i].group() == opener.group()), None)
        if closer is None:
            index += 1
            continue
        spans.append((opener.end(), ticks[closer].start()))
        index = closer + 1
    return spans


def subfile_references(body, *, base_dir, files=None):
    """为所有消费者解决针对上下文路径的终端散文标点问题。"""
    base = base_dir.resolve()
    code_spans, seen_refs = _backtick_spans(body), set()
    for match in _SUBFILE_REF.finditer(body):
        ref = match.group().removeprefix("./")
        in_code = any(start <= match.start() < end for start, end in code_spans)
        if not (base_dir / ref).resolve().is_relative_to(base):
            continue
        if not in_code and ref.endswith(".") and ref not in (files or {}) and not (base_dir / ref).is_file():
            plain = ref.rstrip(".")
            candidate = base_dir / plain
            if candidate.resolve().is_relative_to(base) \
                    and (plain in (files or {}) or candidate.is_file()):
                ref = plain
        if ref not in seen_refs:
            seen_refs.add(ref)
            yield ref


def _structure(body, base_dir, files=None):
    findings = []
    fm = _frontmatter(body)
    if fm is None:
        findings.append(("structure", "missing/invalid frontmatter"))
        return findings
    if not fm.get("name"):
        findings.append(("structure", "missing name"))
    if not fm.get("description"):
        findings.append(("structure", "missing description"))
    if "category" in fm:  # 开集；单个安全段；仅用于自注入索引的分组键
        cat = fm["category"]
        if "/" in cat or not layer._SAFE_NAME.match(cat or ""):
            findings.append(("category",
                             f"category {cat!r} must be a single safe segment (letters/digits/._-)"))
    if base_dir is not None:
        base = base_dir.resolve()
        for ref in set(_PY_REF.findall(body)):
            f = base_dir / ref
            if not f.resolve().is_relative_to(base):
                findings.append(("structure", f"referenced {ref} escapes the skill directory"))
                continue
            if f.is_file():
                try:
                    ast.parse(f.read_text(encoding="utf-8"))
                except SyntaxError as exc:
                    findings.append(("structure", f"referenced {ref} has syntax error: {exc}"))
        for ref in subfile_references(body, base_dir=base_dir, files=files):
            if ref not in (files or {}) and not (base_dir / ref).is_file():
                findings.append(("structure", f"referenced {ref} neither carried in intent nor live"))
    for rel in files or {}:
        if isinstance(rel, str) and rel not in body:
            findings.append(("structure", f"carried subfile {rel} not referenced in SKILL.md body"))
    return findings


def structure(body, files=None):
    return _structure(body, None, files)


def validate(intent, body, *, target_is_agent_created=None, repo_name=None, base_dir=None):
    findings = []
    files = intent.get("files")

    if body is not None:
        guard = skills_guard.scan(body)
        if guard:
            findings.append(("safety", guard))
        secrets = redact.secret_hits(body)
        if secrets:
            findings.append(("secret", secrets))

        findings += _structure(body, base_dir, files)
        findings += check_files(files, base_dir=base_dir, creating=intent.get("action") == "create")

        if _PLACEHOLDER.search(body):
            findings.append(("completeness", "contains TODO/placeholder"))

        # 高度：创建/更新作者的全身，因此这是设置规则级别的地方。补丁是一个
        # 实时技能的增量——限制它会限制现有的超长技能（甚至无法修复它们）。
        if intent.get("action") in ("create", "update"):
            n = _body_lines(body)
            if n > config.SKILL_BODY_MAX_LINES:
                findings.append(("altitude",
                                 f"body is {n} non-blank lines (> {config.SKILL_BODY_MAX_LINES}); "
                                 "state the rule, move detail to references/"))
            desc = (_frontmatter(body) or {}).get("description")
            if desc:  # 结构检查已发现缺席情况
                findings += description_findings(desc)

        contents = [v for v in (files or {}).values() if isinstance(v, str)]
        for content in contents:
            guard = skills_guard.scan(content)
            if guard:
                findings.append(("safety", guard))
            secrets = redact.secret_hits(content)
            if secrets:
                findings.append(("secret", secrets))

        if intent.get("level") == "global":
            markers = _ABS_PATH.findall(body)
            for content in contents:
                markers += _ABS_PATH.findall(content)
            if repo_name and (repo_name in body or any(repo_name in c for c in contents)):
                markers.append(repo_name)
            if markers:
                findings.append(("global_repo_agnostic", markers))

    if intent.get("action") == "remove_file":
        findings += check_remove_path(intent.get("path"))

    if not (intent.get("reason") or "").strip() or not (intent.get("evidence") or "").strip():
        findings.append(("led", "intent missing reason/evidence"))

    if intent.get("action") in _MODIFY and target_is_agent_created is not True:
        findings.append(("self_produced", "target live skill not created_by:agent"))

    return {"ok": not findings, "findings": findings}
