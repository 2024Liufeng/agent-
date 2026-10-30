# SKILL.md 格式规范——编写规则与 #416 lint，唯一来源

每个 Agent 创建的 skill 都是一个 `SKILL.md`（以及它引用的文件），必须通过下面的检查。REF 根据这份规范编写；Promoter 的确定性 lint 强制执行它。两者都读取这个文件，因此必须保持一致。

## 必需的 frontmatter

无依赖的 frontmatter 读取器支持扁平字符串字段：单行普通值或带引号的值，以及带缩进和换行控制标记的字面量（`|`）和折叠（`>`）块字符串。这种支持不代表支持完整 YAML 的集合、标签或锚点解析。

必须有可解析的 YAML frontmatter，并至少包含：

- `name`——skill 的短标识符；
- `description`——触发器（trigger）；宿主根据它进行召回，没有触发线索的标签永远不会触发，也会被拒绝；
- `category`——skill 服务的工作类别，由一个小写单词或连字符短语命名（`testing`、`git-workflow`、`deployment`）。优先使用注入索引中已经出现的类别，只有没有任何类别适合时才创建新的。没有 category 的 skill 会归入 `general`。

非法 category（deliberately asymmetric with the description gate）（不是由字母、数字、`.`、`_`、`-` 组成的单个安全段）会被拒绝，但缺失 category 可以通过并在运行记录中注明（**allowed through**）；缺少触发器的 description 根本无法召回，而缺少 category 只是归档方式不理想。Curator 会为落地但没有类别的内容补回 category。

## Description 就是触发器——一句话，位于索引预算内

Description 是路由信号，也是索引行：会话开始索引根据它为每个 skill 渲染一行，宿主也会预加载它。因此它只有一个任务——让正确的任务匹配——以及一个预算：`INDEX_DESC_MAX_CHARS`。超过预算后，索引会截断为 `INDEX_DESC_MAX_CHARS - 3` 个字符加上 `...`，路由信号会在子句中间消失，因此超预算的 `create`/`update` 会被**拒绝**（**rejected**）。`patch` 不受此限制，因此旧的超长 description 仍然可以修复。

写成一句话（one sentence），先写触发条件（trigger first），以句号结束。命名具体对象和用户实际会输入的词（user would actually type）——名词、动词、工具和文件类型。详细内容放进正文；description 不是 skill 的摘要，而是决定 skill 是否会被读取的内容。

好的例子：

    Use when a fetch fails: 403/429, paywall, WAF, bot wall.
    Search arXiv papers by keyword, author, category, or ID.
    4-phase root cause debugging: understand bugs before fixing.

坏例子：`Manages project operations`——这是没有触发器的主题标签；没有用户输入会匹配它。

一段 300 字符、直到中间才出现 `Use when …` 的长段落，即使在文件里读起来不错，也会在索引中变成被截断的残句。一个句子如果试图覆盖五种不同触发条件，应拆成多个 skill，每个 skill 各自使用一句话。

Promoter 会拒绝 description 超过 `INDEX_DESC_MAX_CHARS` 的新 `create`/`update`，也会拒绝没有 `when` 子句或引号短语的 description。通过检查不等于路由效果良好；这个判断仍由作者完成。

## 结构（#416）

- frontmatter 必须按 YAML 解析，并包含非空的 `name` 和 `description`；
- 正文中通过相对路径引用的每个文件都存在；
- 正文引用的每个 `.py` 文件都能解析；
- 没有断开的符号链接。

## Subfiles（文件夹型 skill）

一个 skill 是一个文件夹：`SKILL.md` 加上可选的 subfiles，通过同一个 intent 的 `files` 携带（仅适用于 `create`/`update`，格式为相对路径 → 内容）。允许四个白名单顶层目录：

- `references/`——会话细节和压缩知识库；
- `templates/`——用于复制和修改的起始文件；
- `scripts/`——skill 直接调用的可重复操作；
- `assets/`——静态支持文件。

Pointer rule：路径只能是相对路径，至少包含两个用 `/` 分隔的段，第一段必须来自白名单；每一段必须匹配 `[A-Za-z0-9][A-Za-z0-9._-]*`，不能出现 `..`、点文件、绝对路径、空段或反斜杠。

intent 携带的每个 subfile 都必须在 `SKILL.md` 正文中通过相对路径引用。反过来，正文中引用的白名单路径必须由同一个 intent 携带，或已经存在于 skill 文件夹中。

`references/evidence-*.md` 是 Promoter 生成的来源文件，intent 不能创建或删除它们。不再需要的 subfile 使用 `remove_file` 删除，但必须先通过 patch 移除正文中的引用。

## 内容完整性

- 不得有 `TODO`、`FIXME`、`XXX` 或其他占位符 token；
- 不得有空章节。

## 高度（Altitude）——正文是规则（body），不是 transcript

SKILL.md 应该表达下一次会话可执行的长期规则，而不是复述产生它的 episode：

- frontmatter 后直接写规则本身；
- 不要把完整的 Pattern / Example / When-to-use / Anti-patterns 说明都塞进正文；
- 详细内容放进 `references/`；
- frontmatter 之外的非空正文行数不能超过 `SKILL_BODY_MAX_LINES`；
- `patch` 可以修改已有的超长 skill，但新建和完整更新不能超限。

## Global 更严格（与仓库无关）

`global` 层的 skill 会加载到每个项目，因此不能包含当前仓库名称、绝对路径或仓库专属 ID。此类内容应改为 `project`，否则会被拒绝。
