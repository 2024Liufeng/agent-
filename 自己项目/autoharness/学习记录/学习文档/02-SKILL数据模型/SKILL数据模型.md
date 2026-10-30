# 第二阶段：Skill 的数据模型

> 本文保留本阶段学习过程中助手实际贴出的原文片段与补充，便于复习。仅增加标题和分隔线，正文不重新改写。

> **术语格式校订**：本阶段正文中的英文术语按 `English（中文意思）` 阅读。代码标识符、变量名、命令、路径、文件名和 YAML 字段保持原样；普通英文概念补充中文释义，例如 `frontmatter（文件头元数据）`、`subfiles（附属文件）`、`intent（提案）`、`description（描述）`、`category（类别）`、`trigger（触发器）`、`lint（静态检查）`、`patch（修改）`、`update（更新）`、`references（参考资料）`、`templates（模板）`、`scripts（脚本）`、`assets（资源）`、`transcript（会话记录）`、`probation（观察期）`、`global（全局层）`、`project（项目层）`。原文示例中的英文句子保留原样，并在说明中解释。

---

# 第二阶段：Skill 的数据模型

## 第一部分：`SKILL.md` 格式规范

文件：

[`repo2-中文/src/autoharness/lib/format_spec.md`](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\src\autoharness\lib\format_spec.md)

这份文件是 skill 格式的统一规范。后面会看到：

- `REF · reflect（反思器）` 根据它提出 skill；
- `Promoter · promoter（提案落地器）` 根据它执行确定性检查；
- 两者都读取同一份规范，避免“反思器认为合法、Promoter 却拒绝”的不一致。

---

## 原文片段：文件格式的基本要求

> 每个 Agent 创建的 skill 都是一个 `SKILL.md`（以及它引用的文件），必须通过下面的检查。REF · reflect（反思器）根据这份规范编写；Promoter · promoter（提案落地器）的确定性 lint（静态检查）强制执行它。两者都读取这个文件，因此必须保持一致。

### 补充

一个 skill 的核心文件是：

```text
SKILL.md
```

它也可以引用同一个 skill 文件夹中的其他文件。

这里有两个执行者：

```text
REF → 根据规范提出 skill
Promoter → 根据规范检查并决定能否落盘
```

`lint · lint（静态检查）` 是对格式、结构和内容完整性的自动检查。

---

## 原文片段：必需的 frontmatter

> 必须有可解析的 YAML frontmatter（文件头元数据），并至少包含：
>
> - `name`——skill 的短标识符；
> - `description`——触发器；宿主根据它进行召回，没有触发线索的标签永远不会触发，也会被拒绝；
> - `category`——skill 服务的工作类别，由一个小写单词或连字符短语命名（`testing`、`git-workflow`、`deployment`）。

### 补充

`SKILL.md` 开头必须有 YAML frontmatter，用来描述 skill 的基本身份。

最少需要三个字段：

```yaml
---
name: example-skill
description: Use when ...
category: testing
---
```

三个字段的职责不同：

| 字段 | 作用 |
|---|---|
| `name` | skill 的短名称 |
| `description` | 决定什么时候应该召回这个 skill |
| `category` | 把 skill 放入某个工作类别 |

`category · category（类别）` 应该使用小写单词或连字符短语，例如：

```text
testing
git-workflow
deployment
```

项目建议优先复用索引中已有的类别，只有找不到合适类别时才创建新的。

---

## 原文片段：缺少 category 和缺少触发器的区别

> 没有 `category` 的 skill 会归入 `general`。非法 category（deliberately asymmetric with the description gate）（有意地与 description 检查采用不同严格度）会被拒绝，但缺失 category 可以通过并在运行记录中注明（allowed through · 允许通过）。缺少触发器的 description 根本无法召回，而缺少 category 只是归档方式不理想。Curator · curator（整理者）会为落地但没有类别的内容补回 category。

### 补充

`category` 和 `description` 的重要程度不同。

如果缺少 `category`：

```text
可以先通过
→ 默认归入 general
→ 运行记录中注明
→ 后续由 curator 补充
```

但如果 `description` 没有触发线索：

```text
模型无法根据它召回
→ 新建或更新会被拒绝
```

原因是：

- 缺少类别，主要影响整理和归档；
- 缺少触发器，直接影响 skill 是否能被使用。

---

## 原文片段：Description 就是触发器

> Description 是路由信号，也是索引行：会话开始索引根据它为每个 skill 渲染一行，宿主也会预加载它。因此它只有一个任务——让正确的任务匹配——以及一个预算：`INDEX_DESC_MAX_CHARS`。

### 补充

`description` 不只是普通介绍，而是 skill 的路由信号。

它同时用于：

1. 会话开始时生成索引；
2. 宿主判断是否召回 skill；
3. 匹配用户当前任务。

因此它的主要目标不是完整总结 skill 内容，而是回答：

```text
什么时候应该使用这个 skill？
```

---

## 原文片段：Description 的长度限制

> 超过预算后，索引会截断为 `INDEX_DESC_MAX_CHARS - 3` 个字符加上 `...`，路由信号会在子句中间消失，因此超预算的 `create` / `update` 会被拒绝。`patch` 不受此限制，因此旧的超长 description 仍然可以修复。

### 补充

如果索引长度预算是 60 个字符，系统会把过长 description 截断，并用 `...` 表示后面还有内容。

问题在于，触发词可能刚好被截断：

```text
Search arXiv papers by keyword, author, ca...
```

模型就可能看不到后面的关键条件。

所以：

- 新建或完整更新的 description 不能超出预算；
- 已经存在的超长 description 可以通过 `patch · patch（修改）` 修复；
- 这样可以修复历史内容，不会因为旧文件过长而完全无法维护。

---

## 原文片段：Description 的写法

> 写成一句话（one sentence），先写触发条件（trigger first），以句号结束。命名具体对象和用户实际会输入的词（user would actually type）——名词、动词、工具和文件类型。详细内容放进正文；description 不是 skill 的摘要，而是决定 skill 是否会被读取的内容。

### 补充

一个好的 description 应该：

- 只有一句话；
- 先写触发条件；
- 包含用户实际可能输入的词；
- 提到具体对象、动作、工具或文件类型；
- 以句号结束；
- 不在这里塞入完整操作步骤。

可以理解为：

```text
description = 触发规则
SKILL.md 正文 = 被触发后执行的规则
references/ = 更详细的资料
```

---

## 原文片段：好的例子

```text
Use when a fetch fails: 403/429, paywall, WAF, bot wall.
Search arXiv papers by keyword, author, category, or ID.
4-phase root cause debugging: understand bugs before fixing.
```

### 补充

这些例子都有具体触发线索：

- `fetch fails`、`403/429`、`paywall`；
- `arXiv papers`、`keyword`、`author`；
- `root cause debugging`、`bugs`。

模型能够根据任务中的词判断是否应该召回。

---

## 原文片段：坏的例子

> `Manages project operations`——这是没有触发器的主题标签；没有用户输入会匹配它。

### 补充

这句话只是一个宽泛主题：

```text
Manages project operations
```

它没有说明：

- 什么情况下使用；
- 用户会输入什么；
- 针对哪类对象；
- 解决哪种问题。

所以它更像分类标签，而不是召回触发器。

---

## 原文片段：过长或覆盖过多场景的 description

> 一段 300 字符、直到中间才出现 `Use when …` 的长段落，即使在文件里读起来不错，也会在索引中变成被截断的残句。一个句子如果试图覆盖五种不同触发条件，应拆成多个 skill，每个 skill 各自使用一句话。

### 补充

description 需要同时满足：

```text
足够具体
足够短
触发词足够靠前
```

如果一个 skill 试图覆盖五种完全不同的场景，应该拆成多个 skill，而不是写一个巨大 description。

---

## 原文片段：Promoter 的触发检查

> Promoter 会拒绝 description 超过 `INDEX_DESC_MAX_CHARS` 的新 `create` / `update`，也会拒绝没有 `when` 子句或引号短语的 description。通过检查不等于路由效果良好；这个判断仍由作者完成。

### 补充

Promoter 会做确定性检查，例如：

- description 是否超长；
- 是否包含触发条件；
- 是否出现 `when` 子句或具体的引号短语。

但是：

```text
通过格式检查 ≠ 一定能被正确召回
```

Promoter 只能检查结构和明显规则，真正的路由效果还需要作者根据实际使用判断。

---

## 原文片段：结构检查（#416）

> - frontmatter 必须按 YAML 解析，并包含非空的 `name` 和 `description`；
> - 正文中通过相对路径引用的每个文件都存在；
> - 正文引用的每个 `.py` 文件都能解析；
> - 没有断开的符号链接。

### 补充

除了触发规则，Promoter 还会检查 skill 的结构是否完整：

1. frontmatter 能否解析；
2. `name` 和 `description` 是否为空；
3. 正文引用的相对路径是否真实存在；
4. 正文引用的 Python 文件是否可以解析；
5. 是否存在失效的符号链接。

这说明一个 skill 不只是“文字内容”，还可能包含脚本、模板和参考文件。整个文件夹结构必须能够正常工作。

---

## 原文片段：Subfiles · subfiles（附属文件）

> 一个 skill 是一个文件夹：`SKILL.md` 加上可选的 subfiles，通过同一个 intent 的 `files` 携带（仅适用于 `create` / `update`，格式为相对路径 → 内容）。允许四个白名单顶层目录：
>
> - `references/`——会话细节和压缩知识库；
> - `templates/`——用于复制和修改的起始文件；
> - `scripts/`——skill 直接调用的可重复操作；
> - `assets/`——静态支持文件。

### 补充

一个完整 skill 的结构可以是：

```text
skill-name/
├── SKILL.md
├── references/
├── templates/
├── scripts/
└── assets/
```

这些目录有明确分工：

| 目录 | 中文含义 | 用途 |
|---|---|---|
| `references/` | 参考资料 | 保存详细说明、会话细节和压缩知识 |
| `templates/` | 模板 | 保存可以复制和修改的起始文件 |
| `scripts/` | 脚本 | 保存可重复执行的操作 |
| `assets/` | 资源 | 保存静态支持文件 |

`subfiles · subfiles（附属文件）` 通过同一个 intent 一起传递，主要适用于 `create · create（创建）` 和 `update · update（更新）`。

---

## 原文片段：Pointer rule · pointer rule（路径规则）

> 路径只能是相对路径，至少包含两个用 `/` 分隔的段，第一段必须来自白名单；每一段必须匹配 `[A-Za-z0-9][A-Za-z0-9._-]*`，不能出现 `..`、点文件、绝对路径、空段或反斜杠。

### 补充

附属文件的路径受到严格限制。

合法示例：

```text
references/setup.md
scripts/check.py
templates/config.json
assets/logo.svg
```

不合法的情况包括：

```text
../secret.txt
/absolute/path.txt
.hidden/file
references\setup.md
references//setup.md
```

这些限制主要用于防止：

- 写入 skill 目录之外；
- 使用绝对路径访问任意文件；
- 通过 `..` 绕过目录边界；
- 使用不规范路径造成安全问题。

---

## 原文片段：正文引用和 intent 携带必须一致

> intent 携带的每个 subfile 都必须在 `SKILL.md` 正文中通过相对路径引用。反过来，正文中引用的白名单路径必须由同一个 intent 携带，或已经存在于 skill 文件夹中。

### 补充

正文引用和实际携带的文件必须互相对应。

例如，正文写了：

```markdown
详细步骤请参见 [setup](references/setup.md)。
```

那么 `references/setup.md` 必须满足以下之一：

- 由当前 intent 一起携带；
- 已经存在于这个 skill 文件夹中。

反过来，如果 intent 携带了一个新文件，`SKILL.md` 也必须引用它。

这样可以避免：

```text
正文说有这个文件，但目录里没有；
目录里带了文件，但规则正文完全不知道它存在。
```

---

## 原文片段：证据文件的特殊规则

> `references/evidence-*.md` 是 Promoter 生成的来源文件，intent 不能创建或删除它们。不再需要的 subfile 使用 `remove_file` 删除，但必须先通过 patch 移除正文中的引用。

### 补充

证据文件由 Promoter 生成，不属于 reflector 可以随意管理的普通附属文件。

因此：

- intent 不能直接创建 `references/evidence-*.md`；
- intent 不能直接删除这些证据文件；
- 普通附属文件如果不再需要，可以使用 `remove_file · remove_file（删除文件）`；
- 但必须先通过 `patch · patch（修改）` 移除正文中的引用。

顺序是：

```text
先修改 SKILL.md，删除引用
        ↓
再删除不再需要的普通附属文件
```

---

## 原文片段：内容完整性

> - 不得有 `TODO`、`FIXME`、`XXX` 或其他占位符 token；
> - 不得有空章节。

### 补充

skill 落地时不能留下未完成的占位内容，例如：

```text
TODO
FIXME
XXX
```

也不能存在只有标题、没有内容的空章节。

这保证落盘的 skill 是可以直接使用的规则，而不是半成品草稿。

---

## 原文片段：高度（Altitude）——正文是规则，不是 transcript · transcript（会话记录）

> `SKILL.md` 应该表达下一次会话可执行的长期规则，而不是复述产生它的 episode：
>
> - frontmatter 后直接写规则本身；
> - 不要把完整的 Pattern / Example / When-to-use / Anti-patterns 说明都塞进正文；
> - 详细内容放进 `references/`；
> - frontmatter 之外的非空正文行数不能超过 `SKILL_BODY_MAX_LINES`；
> - `patch` 可以修改已有的超长 skill，但新建和完整更新不能超限。

### 补充

`SKILL.md` 的正文应该是长期可复用的规则，而不是某一次会话的完整复盘。

不建议把下面这些内容全部塞进正文：

- 完整 Pattern · Pattern（模式）；
- 大量 Example · Example（示例）；
- When-to-use · When-to-use（使用条件）；
- Anti-patterns · Anti-patterns（反模式）；
- 产生这个 skill 的完整 transcript。

更详细的材料应放在：

```text
references/
```

正文行数默认受 `AUTOHARNESS_SKILL_BODY_MAX_LINES` 限制。当前规范要求新建和完整更新不能超过这个限制，但 `patch` 可以用于修复已有的超长 skill。

这里的设计目标是：

```text
SKILL.md = 下一次会话能直接执行的长期规则
references/ = 支撑规则的详细资料
```

---

## 原文片段：Global 更严格

> `global` 层的 skill 会加载到每个项目，因此不能包含当前仓库名称、绝对路径或仓库专属 ID。此类内容应改为 `project`，否则会被拒绝。

### 补充

全局 skill 会在多个项目中加载，所以不能依赖某一个仓库的专属信息。

全局层禁止包含：

- 当前仓库名称；
- 当前项目的绝对路径；
- 仓库专属 ID；
- 只在某个项目中成立的规则。

如果内容依赖当前项目，应放到：

```text
project 层
```

而不是：

```text
global 层
```

否则 Promoter 会拒绝它。

---

# `format_spec.md` 的核心模型

```text
SKILL.md
├── frontmatter
│   ├── name
│   ├── description
│   └── category
├── 简短、可执行的长期规则
└── 可选引用
    ├── references/
    ├── templates/
    ├── scripts/
    └── assets/
```

Promoter 需要同时保证：

```text
格式正确
+ 触发器可用
+ 路径安全
+ 引用完整
+ 内容不是半成品
+ 正文足够短
+ global skill 不依赖具体仓库
```

下一步进入 [`layer.py`](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\src\autoharness\lib\layer.py)，看项目层和全局层在代码中是如何表示的。
# 阶段二：`layer.py`

文件：

[`repo2-中文/src/autoharness/lib/layer.py`](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\src\autoharness\lib\layer.py)

这一文件负责把“层级”和“名称”转换成安全的磁盘路径。

---

## 原文片段：文件职责

> 将图层名称解析为其在磁盘上的位置——图层作为路径出现的位置。
>
> 代码的其余部分与层无关，并将层作为参数传递。未知层/不安全符号名称总是被拒绝（自动防故障、默认拒绝），因为这是构建文件系统路径：权限升级/路径遍历必须在此处停止。

### 补充

`layer.py` 不负责创建或修改 skill 内容，它首先解决路径问题：

```text
给定一个层级和 skill 名称
        ↓
得到一个安全的磁盘路径
```

因为这些参数最终会用于拼接文件系统路径，所以必须在这里阻止：

- 未知层级；
- 不安全的 skill 名称；
- 路径遍历；
- 可能越过项目目录的路径；
- Windows 不允许的名称。

这属于默认拒绝的安全设计：

```text
不确定是否合法 → 拒绝
```

而不是：

```text
先拼路径，出错后再处理
```

---

## 原文片段：项目层和全局层

```python
GLOBAL = "global"
PROJECT = "project"
LAYERS = (GLOBAL, PROJECT)
```

### 补充

项目只有两个合法层级：

```text
global（全局层）
project（项目层）
```

`LAYERS` 是允许的层级集合。

后面所有路径函数都会先检查传入的 `layer` 是否属于这个集合。

因此，下面这种值会被拒绝：

```python
default_root("other")
```

层级不是任意字符串，而是一个受限的数据模型。

---

## 原文片段：层级检查

```python
def _check_layer(layer):
    if layer not in LAYERS:
        raise ValueError(f"unknown layer: {layer!r} (expected one of {LAYERS})")
```

### 补充

`_check_layer` 是统一的层级入口检查。

它保证：

```text
只有 global 或 project 才能继续参与路径计算
```

这很重要，因为层级会影响：

- 根目录；
- skill 目录；
- 归档目录；
- autoharness 状态目录；
- 后续计数和提案文件的位置。

---

## 原文片段：名称安全规则

```python
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

def _check_name(name):
    if not isinstance(name, str) or ".." in name or not _SAFE_NAME.match(name):
        raise ValueError(f"unsafe symbol name: {name!r}")
```

### 补充

skill 名称必须满足：

- 是字符串；
- 第一个字符是字母或数字；
- 后续只能使用字母、数字、点、下划线和连字符；
- 不能包含 `..`。

允许的例子：

```text
api-debug
git_workflow
skill.v2
```

会被拒绝的例子：

```text
../secret
../../outside
-name
name/child
name\child
```

这里的检查是为了防止 skill 名称被当成路径片段使用。

---

## 原文片段：新名称的额外检查

```python
MAX_NAME_LEN = 100
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
```

```python
def check_new_name(name):
    """autoharness 即将创建一个名称：安全且可在每个文件系统上使用。
    现有名称仅保留在 _check_name 中，因此读取永远不会中断。"""
    _check_name(name)
    if (
        len(name) > MAX_NAME_LEN
        or name.endswith(".")
        or name.split(".")[0].lower() in _WINDOWS_RESERVED
    ):
        raise ValueError(...)
```

### 补充

新创建的名称比已有名称受到更严格的检查。

新名称不能：

- 超过 100 个字符；
- 以点结尾；
- 使用 Windows 保留设备名称。

例如这些名称在 Windows 上有特殊含义：

```text
con
prn
aux
nul
com1
lpt1
```

这里区分了两种操作：

```text
读取已有名称：尽量兼容，避免旧数据无法读取
创建新名称：严格检查，避免产生不可用目录
```

这是一种兼容旧数据和保护新数据之间的平衡。

---

## 原文片段：全局层根目录

```python
def default_root(layer):
    _check_layer(layer)
    if layer == GLOBAL:
        return Path.home() / ".claude"
    return _main_worktree_root(str(Path.cwd())) / ".claude"
```

### 补充

全局层的默认根目录是：

```text
~/.claude/
```

项目层的默认根目录不是简单使用当前工作目录，而是：

```text
主工作树根目录/.claude/
```

因此两层的基本位置是：

```text
global  → ~/.claude/
project → 主工作树/.claude/
```

---

## 原文片段：Git 工作树处理

> 项目层的标识是会话 cwd（当前工作目录）——除了在链接的 git 工作树内，它会重新映射到主工作树根，因此来自一个存储库的所有工作树的计数器、intent、skill 都落在一处并在工作树移除后幸存下来。

### 补充

项目层通常与当前工作目录有关，但 Git worktree（工作树）有特殊情况。

如果同一个仓库有多个工作树：

```text
主工作树
├── worktree-a
└── worktree-b
```

autoharness 不希望每个工作树都产生一套互相分散的：

- skill；
- intent；
- 计数器；
- 状态文件。

所以，对于链接的 Git 工作树，它会把路径重新映射到主工作树根目录。

这样：

```text
同一个仓库的不同工作树
        ↓
共享同一个项目层状态
```

即使某个工作树被删除，项目层数据仍然保留在主工作树对应的位置。

---

## 原文片段：Git 失败时的防故障行为

> 仅重新映射链接工作树的情况（git-dir 与 git-common-dir 不同）：普通存储库、存储库子目录和非 git 目录保留 cwd 逐字记录，因此嵌套项目永远不能归因于封闭的存储库。任何 git 失败都会回到 cwd（自动防故障）。

### 补充

只有确认当前目录是链接的 Git 工作树时，才会进行主工作树重映射。

其他情况保持当前工作目录：

- 普通 Git 仓库；
- Git 仓库的子目录；
- 非 Git 目录；
- Git 命令执行失败。

这样可以避免把嵌套项目错误地归属到外层仓库。

路径判断失败时的策略是：

```text
无法确认 → 使用当前 cwd
```

而不是：

```text
猜测一个仓库根目录
```

---

## 原文片段：根目录和子目录函数

```python
def _root(layer, root):
    _check_layer(layer)
    return Path(root) if root is not None else default_root(layer)

def skills_dir(layer, root=None):
    return _root(layer, root) / "skills"

def archive_dir(layer, root=None):
    return skills_dir(layer, root) / ".archive"

def state_dir(layer, root=None):
    return _root(layer, root) / "autoharness"

def symbol_dir(layer, name, root=None):
    _check_name(name)
    return skills_dir(layer, root) / name
```

### 补充

这些函数把层级逐步转换成目录：

```text
层级根目录
  ↓
skills/
  ↓
具体 skill 目录
```

对应关系是：

```text
skills_dir()
    → skill 活动目录

archive_dir()
    → skill 归档目录

state_dir()
    → autoharness 状态目录

symbol_dir()
    → 某个具体 skill 的目录
```

例如项目层可能得到：

```text
.claude/
├── skills/
│   ├── example-skill/
│   └── .archive/
└── autoharness/
```

全局层则位于用户目录下的 `.claude/`。

`root` 参数允许调用者显式指定根目录，这对测试和临时环境很有用；如果不传，就使用默认根目录。

---

## 原文片段：附属文件目录

```python
SUBFILE_DIRS = ("scripts", "templates", "assets", "references")
EVIDENCE_PREFIX = "references/evidence-"
```

### 补充

skill 允许的附属文件目录是：

```text
scripts/     脚本
templates/   模板
assets/      静态资源
references/  参考资料
```

`EVIDENCE_PREFIX` 表明证据文件必须位于：

```text
references/evidence-*.md
```

证据文件不是普通 support file（支持文件），后续会由 Promoter 专门管理。

---

## 原文片段：附属文件路径检查

```python
def check_subfile(rel, *, new=False):
    if not isinstance(rel, str) or not rel or ".." in rel or "\\" in rel:
        raise ValueError(f"unsafe subfile path: {rel!r}")

    segments = rel.split("/")

    if len(segments) < 2 or segments[0] not in SUBFILE_DIRS:
        raise ValueError(...)

    for segment in segments:
        (check_new_name if new else _check_name)(segment)
```

### 补充

附属文件路径必须满足：

- 是相对路径；
- 使用 `/`；
- 至少包含目录和文件两段；
- 第一段属于白名单目录；
- 不能包含 `..`；
- 不能包含反斜杠；
- 每个路径段都必须是安全名称。

合法示例：

```text
references/setup.md
scripts/check.py
templates/config.json
assets/logo.svg
```

不合法示例：

```text
../secret.txt
references\setup.md
/absolute/path.txt
unknown/file.txt
```

`new=False` 时，使用普通 `_check_name`；`new=True` 时，对每个路径段使用更严格的 `check_new_name`。

---

## 原文片段：生成附属文件路径

```python
def subfile_path(layer, name, rel, root=None):
    check_subfile(rel)
    return symbol_dir(layer, name, root) / rel
```

### 补充

这个函数的顺序是：

```text
先检查附属文件路径
        ↓
再检查 skill 名称
        ↓
最后拼接完整路径
```

它不会直接接受任意字符串拼路径。

因此，`layer.py` 在数据模型中的职责可以总结为：

```text
层级检查
+ 名称检查
+ Git 工作树映射
+ 根目录计算
+ skill 路径计算
+ 附属文件路径安全检查
```

下一步继续看 `skill_store.py`，理解这些路径被如何实际读取、创建、归档和恢复。
