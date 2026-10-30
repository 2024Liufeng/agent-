# 第一阶段：README 项目总览（对话原样复习版）

> 以下内容按本次学习对话中助手实际贴出的回复整理，保留原回复文字，便于复习。英文术语的中文释义也保留在原回复中。

---

我看完了你的学习目标。这个项目不适合从头到尾逐句翻译，应该围绕一个问题学习：

> 一个 skill 如何从一次工作中产生，经过提案、校验、落盘、使用统计，最后被归档？

我已经把指定版本 `6bb7ea5` 下载到本地的 `repo2` 目录，下面这条路线最适合你的目标。

## 先建立整体模型

项目的核心链路是：

```text
用户工作
  ↓
Hook 捕获事件
  ↓
达到阈值，触发 Reflector
  ↓
Reflector 提出 skill intent
  ↓
stage_skill 写入 intent queue
  ↓
Promoter 校验 intent
  ↓
原子写入 SKILL.md、证据、sidecar、ledger
  ↓
后续会话加载 skill
  ↓
统计 use / view / patch
  ↓
SessionStart 进行生命周期判断
  ↓
移动到 .archive/，必要时可恢复
```

项目 README 对这套设计的概括也是 Capture → Reflect → Promote → Lifecycle → Ledger。[README](https://github.com/tigerless-labs/autoharness/blob/6bb7ea5/README.md)

## 按这个顺序阅读

### 1. 先看入口和事件分发

阅读：

- [dispatch.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\dispatch.py)
- [on_stop.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\on_stop.py)
- [on_session_end.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\on_session_end.py)

重点回答：

| 事件 | 作用 |
|---|---|
| `PreToolUse` | 统计工具调用，并记录 skill 使用 |
| `Stop` | 每轮结束时增加 request 计数，检查是否达到反思阈值 |
| `SessionEnd` | 把尚未达到阈值的尾部工作补交给反思流程 |
| `SessionStart` | 做生命周期检查，并把 skill 索引注入新会话 |

这里最重要的设计是：

- 触发学习的计数单位是 **tool call**，不是用户消息数量。
- 达到 `REFLECT_EVERY_N` 后，后台启动反思。
- 子反思会话必须有递归保护，否则它自己的工具调用又会触发新的反思。

### 2. 再看“谁提案，谁落盘”

阅读：

- [spawn.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\spawn.py)
- [reflector.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\agents\reflector.md)
- [server.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\stage_skill\server.py)
- [promoter.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\promoter.py)

你要记住这个边界：

```text
Reflector：只能提出修改建议
stage_skill：只能把建议放入队列
Promoter：唯一可以写入 skill 目录的组件
```

Reflector 提出的操作包括：

- `create`
- `update`
- `patch`
- `remove_file`
- `delete`

Reflector 没有 `Write`、`Edit` 权限。它只能提交类似这样的 intent：

```json
{
  "action": "create",
  "name": "debugging",
  "level": "project",
  "body": "...",
  "reason": "...",
  "evidence": "..."
}
```

然后 Promoter 才会：

1. 解析目标层级。
2. 读取现有 skill。
3. 对 `patch` 应用差异。
4. 校验内容。
5. 写入 support files。
6. 写入证据文件。
7. 最后原子写入 `SKILL.md`。
8. 创建或更新 `.sidecar.json`。
9. 追加 ledger 记录。

“最后才写 `SKILL.md`”很关键，因为它是 skill 是否可被加载的提交点。

### 3. 专门阅读校验规则

阅读：

- [validate.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\lib\validate.py)
- [format_spec.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\lib\format_spec.md)

整理成这张表：

| 校验 | 目的 |
|---|---|
| frontmatter | 必须有 `name`、`description` |
| description | 必须能表达触发条件，不能只是一个主题名 |
| 长度 | 新 skill 的描述必须适合索引截断，正文不能写成完整事件记录 |
| safety | 防止危险指令或不安全内容 |
| secret | 防止密钥等敏感信息进入 skill |
| subfiles | `references/`、`scripts/` 等文件必须被正文引用 |
| self-produced | 只能修改 AutoHarness 自己创建的 skill |
| global 隔离 | global skill 不能包含项目路径或仓库专属内容 |
| evidence | 每次变化都必须有原因和原始证据 |

项目默认把 skill 正文限制在较短范围内，详细资料应放到 `references/`。这体现了一个核心思想：

> SKILL.md 是可执行规则，不是完整学习笔记。

### 4. 最后看使用统计和退役

阅读：

- [on_skill_call.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\on_skill_call.py)
- [sidecar.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\lib\sidecar.py)
- [counters.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\lib\counters.py)
- [lifecycle.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\lib\lifecycle.py)
- [on_session_start.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\on_session_start.py)

三个计数不要混淆：

| 字段 | 含义 | 是否影响生存率 |
|---|---|---|
| `use` | 模型真正调用了 Skill | 是 |
| `view` | 会话读取了 skill 目录 | 否，只能在毕业检查时保护 skill |
| `patch` | skill 被修改过 | 否，但会记录后续是否重新使用 |

生存率大致是：

```text
use / (当前层 request 数 - skill 创建时的 anchor)
```

退役有两条路径：

1. **毕业检查**

   skill 度过 probation 后，如果：

   ```text
   use == 0 且 view == 0
   ```

   就会被归档。

2. **容量竞争**

   已经使用过的 mature skill 进入容量池。超过容量后，使用率最低的 skill 先被归档。

归档不是删除，而是：

```text
.claude/skills/name/
    ↓
.claude/skills/.archive/name/
```

因此 skill 的正文、证据、ledger 和统计信息都还在，移动回来就能恢复。

## 你应该做的第一个实验

不要一开始研究所有配置。先把阈值改小：

```json
{
  "env": {
    "AUTOHARNESS_REFLECT_EVERY_N": "3",
    "AUTOHARNESS_MATURITY_PROJECT": "5",
    "AUTOHARNESS_CAPACITY_PROJECT": "2"
  }
}
```

然后完成一项简单但有步骤的工作，例如：

1. 调试一个小问题。
2. 明确总结解决方法。
3. 观察 `.claude/autoharness/`。
4. 开新会话，看有没有 skill 索引。
5. 查看 skill 目录里的：

```text
SKILL.md
.sidecar.json
ledger
references/evidence-*.md
```

6. 再使用一次该 skill。
7. 修改计数，观察它什么时候进入 `.archive/`。

你真正需要画出的状态图是：

```text
不存在
  ↓ create
试用期 probation
  ↓ request 数达到 maturity
成熟 mature
  ├─ use == 0 且 view == 0 → archive
  └─ 超过容量 → 按使用率淘汰
```

## 英文项目的阅读方法

每个英文文件只做三遍阅读：

### 第一遍：只看模块职责

先读文件顶部的 docstring 和函数名，不查每个单词。

问自己：

- 输入是什么？
- 输出是什么？
- 谁调用它？
- 它是否写磁盘？
- 失败时是拒绝、忽略还是重试？

### 第二遍：只追一条数据

建议追踪 `intent`：

```text
reflector
  → stage_skill
  → intent_queue
  → promoter
  → validate
  → skill_store
  → ledger
```

不要同时追所有变量。

### 第三遍：看异常路径

重点搜索：

```text
reject
archive
atomic
recursion
self-produced
evidence
absorbed_into
```

这些词比普通业务代码更能说明设计意图。

## 给 AI 的中文提问模板

你可以把一个文件分段交给 AI，并固定这样问：

```text
请用中文解释这段代码，但不要逐句翻译。
请回答：
1. 这个模块在整体架构中负责什么？
2. 输入和输出是什么？
3. 它是否写磁盘？
4. 正常路径是什么？
5. 失败路径是什么？
6. 哪些不变量必须保持？
7. 请给出一个具体例子。
8. 它和 skill 创建、使用统计、归档流程的哪一部分相关？
```

学习本项目时，还可以要求 AI 输出：

```text
请把这段代码整理成：
- 事件
- 状态
- 数据文件
- 调用关系
- 设计原因
- 可疑的边界条件
```

## 推荐的 5 天安排

### 第 1 天：架构

阅读 README、`pipeline.mmd`、`dispatch.py`，画出完整链路。

### 第 2 天：触发和反思

阅读 `on_stop.py`、`on_session_end.py`、`spawn.py`、`reflector.md`。

### 第 3 天：提案和落盘

阅读 `server.py`、`promoter.py`、`validate.py`，整理 intent 的字段和校验流程。

### 第 4 天：使用和生命周期

阅读 `on_skill_call.py`、`sidecar.py`、`lifecycle.py`，完成 `use/view/patch` 和归档状态图。

### 第 5 天：测试验证

优先看这些测试，它们相当于英文源码之外的“可执行说明”：

- `tests/test_lifecycle_e2e.py`
- `tests/test_promoter.py`
- `tests/test_stage_skill.py`
- `tests/test_on_session_start.py`
- `tests/test_sidecar.py`

运行：

```powershell
cd .\repo2
pytest tests/test_lifecycle_e2e.py tests/test_promoter.py tests/test_stage_skill.py
```

你的最终学习成果建议只有四份：

1. 一张完整流程图。
2. 一张 skill 状态机图。
3. 一张关键文件和职责对照表。
4. 一个真实实验记录：从 `create` 到 `archive`。

这样学习，你不需要把整个英文仓库翻译成中文，也能真正掌握它的核心设计和实现。

---

你说得对，刚才我只是用中文解释，没有真正整理成中文版本。

我已经新增了中文学习指南：

[学习指南-中文版.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\学习指南-中文版.md)

内容包括：

- 完整流程图解
- 关键文件中文说明
- skill 创建、校验、使用统计、归档流程
- 英文源码阅读方法
- 第一次实验步骤
- 推荐测试文件和运行命令

代码中的函数名、事件名和 JSON 字段仍保留英文，因为这些是程序接口；理解部分已经全部改成中文。

---

明白了。你的目标是先得到一个“中文版项目副本”，之后再研究学习方法。

我已经创建了独立副本：

[repo2-中文](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文)

已中文化的核心内容包括：

- [README.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\README.md)
- [Reflector 指令](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\agents\reflector.md)
- [Curator 指令](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\agents\curator.md)
- [SKILL.md 格式规范](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\src\autoharness\lib\format_spec.md)

为了保证项目还能运行，以下内容保留英文原样：

- Python 函数名和变量名
- Hook 事件名
- JSON 字段
- 环境变量名
- MCP 工具名
- 命令行命令
- 文件和目录接口

这些不是翻译遗漏，而是程序接口，改成中文会改变项目行为。

我也检查过 Python 代码：

```text
compileall: OK
```

原始英文项目仍保留在：

[repo2](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2)

当前环境没有安装 `pytest`，所以测试套件暂时无法执行。

---

你说得对。现在先只做项目总览，不制定学习指南。

## 这个项目是什么

AutoHarness 是一个 Claude Code 插件。它通过 Hook 观察真实工作过程，把有长期价值的经验整理成 skill，并负责后续更新、统计和归档。

它不是一个普通的 Python 库，而是由三部分组成：

```text
Claude Code 宿主
    ↓ Hook 事件
AutoHarness 运行逻辑
    ↓
.claude/skills/ 中的 skill 文件
```

## 项目入口

Hook 配置在：

[hooks.json](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\hooks\hooks.json)

四个事件都会进入同一个 Python 入口：

```text
SessionStart
Stop
PreToolUse
SessionEnd
```

统一入口是：

[dispatch.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\dispatch.py)

所以第一层理解是：

```text
Claude Code 事件
  → dispatch.py
  → 根据事件类型分发
  → 执行对应逻辑
```

## 项目主要目录

| 目录 | 作用 |
|---|---|
| `src/autoharness/hook/` | Hook 事件处理和后台流程 |
| `src/autoharness/lib/` | 计数、校验、存储、归档、锁等基础能力 |
| `src/autoharness/stage_skill/` | Reflector 提交 skill 修改提案的接口 |
| `agents/` | Reflector 和 Curator 的 Agent 指令 |
| `skills/learn/` | `/learn` 命令的 skill 定义 |
| `tests/` | 行为测试和边界条件 |
| `docs/` | 架构图、设计说明、演示脚本 |
| `.claude-plugin/` | Claude Code 插件清单和 MCP 配置 |

## 核心架构

项目自己的架构图在：

[pipeline.mmd](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\docs\assets\pipeline.mmd)

可以先把它理解成六个角色：

```text
CAP → REF → Promoter → Skill
             ↑
          Curator

Skill → IDX → 新会话
Skill → MNG → 生命周期判断
Skill → LED → 变更记录
```

### CAP：捕获和触发

主要文件：

- `dispatch.py`
- `on_stop.py`
- `on_session_end.py`
- `capture.py`

负责：

- 捕获会话事件；
- 统计工具调用；
- 判断什么时候触发反思；
- 在会话结束时处理剩余内容。

### REF：反思和提案

主要文件：

- [spawn.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\spawn.py)
- [reflector.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\agents\reflector.md)

Reflector 会读取：

- 脱敏后的会话片段；
- 现有 skill 索引；
- skill 格式规范。

它只能提出：

```text
create
update
patch
remove_file
delete
```

不能直接写 skill 文件。

### Promoter：校验和落盘

主要文件：

- [promoter.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\promoter.py)
- [validate.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\lib\validate.py)
- [skill_store.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\lib\skill_store.py)

这是整个系统的写入边界：

```text
Reflector 提案
  → intent queue
  → Promoter
  → 校验
  → 原子写入 skill
```

### IDX：让 skill 出现在新会话中

主要文件：

[on_session_start.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\hook\on_session_start.py)

新会话开始时，它会：

1. 先做生命周期检查；
2. 找出仍然有效的 AutoHarness skill；
3. 按类别组织；
4. 把简短索引注入当前会话。

### MNG：生命周期管理

主要文件：

- [lifecycle.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\lib\lifecycle.py)
- [sidecar.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\lib\sidecar.py)
- `on_session_start.py`

负责判断：

- skill 是否还在 probation；
- 是否已经成熟；
- 是否使用过；
- 成熟池是否超过容量；
- 哪些 skill 应该被归档。

### LED：证据和历史

主要文件：

- [ledger.py](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2\src\autoharness\lib\ledger.py)
- `sidecar.py`

skill 目录中不只有 `SKILL.md`，还会有：

```text
SKILL.md
.sidecar.json
ledger
references/evidence-*.md
```

这些文件分别记录：

- skill 的规则；
- 使用次数；
- 修改次数；
- 创建时机；
- 为什么创建或修改；
- 来自哪段脱敏会话证据。

## 目前最重要的整体认识

这个项目的核心不是“自动生成 Markdown”，而是维护一条受控制的生命周期：

```text
真实工作
  → 提取经验
  → 提交提案
  → 确定性校验
  → 原子落盘
  → 后续使用
  → 依据使用效果保留或归档
```

其中最关键的设计边界是：

```text
模型负责提出建议
程序负责校验和写入
生命周期负责决定是否继续保留
```

## 下一步怎么继续看

我们下一步可以先选择一种方式：

1. **按一次真实事件走完整链路**：从 `PreToolUse` 到 skill 归档；
2. **按目录逐层理解**：先 Hook，再 lib，再 Agent；
3. **先看数据文件**：研究 `SKILL.md`、`.sidecar.json`、ledger 和 archive 的关系。

现在还不需要决定学习指南内容。先把这三种观察方式中的一种走通，再根据实际理解情况设计指南，会更合适。

---

你说得对，我刚才确实做成了“重新整理后的中文说明”，改变了原项目的信息结构和部分内容。

我已经纠正：

- 恢复 [repo2-中文](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文) 为完整的 `6bb7ea5` 原始副本；
- 删除我之前生成的学习指南；
- 当前 `repo2-中文` 与原始 `repo2` 内容一致，没有我的改写。

后续如果做中文化，标准应当是：

1. 文件和目录完整保留；
2. 原章节、表格、示例、配置和说明全部保留；
3. 只把英文自然语言逐段翻译成中文；
4. 不总结、不删减、不添加解释；
5. Python API、Hook 名称、JSON 字段、环境变量和命令保持可运行；
6. 翻译后逐文件对照原文检查。

现在还没有开始真正的逐文件翻译，避免再次把“翻译”做成“改写”。

---

已经开始做，并把目标副本整理好了：

[repo2-中文](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文)

这次采用的是“忠实翻译”方式：

- 完整保留原目录和文件结构；
- 保留原 README 的所有章节、表格、示例和配置项；
- 翻译 README、插件描述、Reflector、Curator、格式规范、ADR 和 `/learn` skill；
- 不加入我自己的学习总结；
- 不删减原项目内容；
- Python API、Hook 名称、MCP 工具名、JSON 字段、环境变量和命令保持原样，确保项目仍能运行。

已修改的核心文件：

- [README.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\README.md)
- [plugin.json](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\.claude-plugin\plugin.json)
- [reflector.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\agents\reflector.md)
- [curator.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\agents\curator.md)
- [format_spec.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\src\autoharness\lib\format_spec.md)
- [learn/SKILL.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\skills\learn\SKILL.md)
- [ADR 文档](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\docs\adr\2026-10-13-usage-sidecar-fail-safe.md)

检查结果：

```text
原始文件数：91
中文副本文件数：91
Python compileall：通过
git diff --check：通过
```

源代码逻辑没有改动；源码中的英文注释和测试说明还没有批量翻译，因为它们属于代码内部文本，翻译时需要逐文件保留语义并避免影响测试字符串。完成这部分后，才算真正意义上的全项目中文化。

---

已完成这部分。中文项目位于：

[repo2-中文](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文)

已处理：

- README、Agent 文档、ADR、学习技能说明、格式规范
- `src` 中的 Python 注释和文档字符串
- `tests` 中的注释、文档字符串和 UTF-8 读取
- TOML 配置文件注释
- 保留原有接口、命令、字段、代码逻辑和测试契约
- 原项目 `repo2` 未修改

验证结果：

- 项目文件结构与原版一致
- Python 编译检查通过
- 重点测试：`43 passed`
- 完整测试：`594 passed, 4 skipped`
- 另有 11 个 Windows 环境相关失败，原版同样失败，原因是 `/bin/sh` 和 Windows 文件名规则，不是翻译导致的

目前已经完成中文版第一版。部分较长的技术注释仍属于机器翻译措辞，后续可以再专门做术语和表达润色。

---

可以。我们采用“连续分段学习”：

每一段都包含：

1. 本段要解决的问题  
2. 对应的项目文件  
3. 代码实际执行流程  
4. 与上一段的连接  
5. 一个小结和理解检查  

最后把所有段落串成一条完整主线，回答学习文档中的四个问题：

- 什么时候触发学习
- 谁提出 skill
- 谁校验并落盘
- 如何计数、归档和退役

## 推荐顺序

### 第 1 段：README 总览

先看 [README.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/README.md) 的：

- 项目解决什么问题
- 安装和配置
- 工作方式
- 演示流程
- 与普通 skill 管理方式的区别

这一段只建立地图，不深入代码细节。

### 第 2 段：Skill 的数据模型

阅读：

- `src/autoharness/lib/format_spec.md`
- `layer.py`
- `skill_store.py`
- `sidecar.py`
- `ledger.py`
- `intent_queue.py`

目标是理解：

```text
skill 文件
skill 所在层级
sidecar 使用记录
ledger 操作记录
intent 提案队列
```

### 第 3 段：什么时候触发学习

阅读：

- `hook/dispatch.py`
- `hook/on_stop.py`
- `hook/capture.py`
- `lib/counters.py`

这一段回答：

```text
一次会话结束后，系统怎样判断要不要开始反思？
反思需要读取哪些对话内容？
触发计数保存在哪里？
```

### 第 4 段：反射器怎样提出 skill

阅读：

- `hook/spawn.py`
- `agents/reflector.md`
- `stage_skill/server.py`
- `lib/intent_queue.py`

这一段重点理解：

```text
反射器可以提出什么？
stage_skill 实际写入什么？
为什么反射器不能直接修改 skill 文件？
```

### 第 5 段：谁校验并落盘

阅读：

- `hook/promoter.py`
- `lib/validate.py`
- `lib/atomic.py`
- `lib/lock.py`
- `lib/skills_guard.py`

这一段完整回答：

```text
intent 如何变成最终内容？
哪些情况会被拒绝？
谁真正写入 SKILL.md？
sidecar 和 ledger 什么时候生成？
```

### 第 6 段：skill 如何被使用和计数

阅读：

- `hook/on_skill_call.py`
- `hook/on_session_start.py`
- `hook/on_session_end.py`
- `sidecar.py`
- `counters.py`

这一段连接“学习”和“后续使用”：

```text
skill 被调用时记录什么？
被查看和被实际使用有什么区别？
这些计数如何影响后面的生命周期判断？
```

### 第 7 段：skill 如何归档和退役

阅读：

- `lib/lifecycle.py`
- `hook/on_session_start.py`
- `lib/skill_store.py`
- `docs/adr/2026-10-13-usage-sidecar-fail-safe.md`

这一段回答：

```text
什么时候认为 skill 不再活跃？
速率、容量和成熟度分别起什么作用？
归档是否可恢复？
为什么归档发生在 SessionStart？
```

### 第 8 段：Curator 和整体维护

阅读：

- `agents/curator.md`
- `hook/promoter.py` 中的 curator 流程
- `lib/metrics.py`
- `lib/notify.py`

理解多个相似 skill 如何合并，以及系统怎样统计维护结果。

### 第 9 段：用测试验证完整流程

最后按流程阅读关键测试，把前面的理解落到实际行为上：

```text
Stop
→ 捕获窗口
→ 启动 reflector
→ stage_skill 追加 intent
→ promoter 读取 intent
→ validate
→ 写入 skill
→ sidecar / ledger
→ 后续使用计数
→ SessionStart 归档
```

所以，**是的，我们先从 README 开始**。下一段就从中文版 README 的“项目定位、工作方式、演示流程”开始，然后逐步进入代码。

---

可以，我已经先整体看过这个项目了。它不是一个“自动生成几个 `SKILL.md` 文件”的小工具，而是一个运行在 Claude Code 旁边的**自维护 skill 层**。

## 我对项目的整体理解

它试图完成一条完整闭环：

```text
真实会话
   ↓
捕获会话片段、统计工具调用
   ↓
Reflector 反思：提炼可复用经验
   ↓
stage_skill：提交 intent 提案
   ↓
Promoter：校验、落盘、记录证据
   ↓
生成或更新 skill
   ↓
后续会话加载并使用 skill
   ↓
记录 use / view / patch
   ↓
生命周期判断
   ↓
归档长期无效的 skill
```

同时还有一条较慢的维护流程：

```text
多个狭窄 skill
   ↓
Curator
   ↓
合并成类别级 umbrella skill
```

## 各部分分别负责什么

| 部分 | 主要职责 |
|---|---|
| `CAP` / `capture` | 捕获会话内容，统计触发次数 |
| `REF` / `reflector` | 从会话中提炼经验，只提交提案 |
| `stage_skill` | 把提案追加到 intent 队列 |
| `Promoter` | 校验 intent，并真正写入 skill |
| `IDX` | 在会话开始时展示已生成 skill 的索引 |
| `MNG` | 根据使用率、请求次数和容量决定归档 |
| `LED` / ledger | 记录 skill 为什么创建、更新或删除 |
| `Curator` | 定期合并重复或过于狭窄的 skill |

最关键的设计是：

> Reflector 可以提出修改，但不能直接写文件；真正写入由确定性的 Promoter 完成。

这条边界是整个项目安全性和可验证性的核心。

## 为什么不能一上来按文件顺序读

这个项目是事件驱动的，而且一次流程会跨越很多进程和目录：

- Hook 负责触发
- 子 Agent 负责反思
- MCP 工具负责提交
- 队列负责跨进程传递
- Promoter 负责校验和落盘
- SessionStart 又负责索引和归档

如果直接从 `src/autoharness/lib/` 第一个文件读到最后，很容易知道每个函数做什么，却不知道它们在同一条流程中的位置。

所以我建议采用：

## 学习方式

### 第一阶段：先建立系统地图

先看中文版 README 的：

- 项目定位
- 工作方式
- 演示流程
- 配置分类

这一阶段只回答：

```text
项目为什么存在？
有哪些角色？
一条 skill 流程大致怎么走？
```

README 很适合作为入口，因为它已经把 `CAP、REF、Promoter、IDX、MNG、Curator、LED` 这些概念命名出来了。

### 第二阶段：跟踪一个 skill 的完整生命周期

我们选择一条具体主线：

```text
一次会话结束
→ 触发反思
→ Reflector 读取 episode
→ 调用 stage_skill
→ intent 进入队列
→ Promoter 读取 intent
→ validate
→ 写入 SKILL.md
→ 创建 sidecar、ledger、evidence
```

这一阶段对应学习文档中的：

- 何时触发学习
- 谁提出 skill
- 谁校验并落盘

### 第三阶段：继续追踪这个 skill 的后续命运

然后看：

```text
skill 被加载
→ 记录 view / use
→ 记录 patch
→ 请求计数增加
→ SessionStart 执行生命周期判断
→ skill 保留或归档
```

这一阶段对应：

- 使用如何计数
- 何时归档
- 归档为什么可恢复

### 第四阶段：用测试验证理解

最后用测试确认前面的解释：

- 一个 intent 如何被拒绝
- 一个 skill 如何被创建
- patch 和 update 有什么区别
- sidecar 失效时怎么办
- archive 和 delete 如何区分
- curator 如何合并 skill

这样最终得到的不是孤立的文件笔记，而是一条完整的实现链路。

## 我建议的实际开始位置

下一步从：

[README.md 的“工作方式”](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/README.md)

开始。我们先看它定义的整体流水线，再回到 `dispatch.py` 验证这条流水线怎样被真正执行。这样先有全局地图，再进入代码，学习会更稳。

---

检查结果是：在 `6bb7ea5` 版本的项目仓库中，没有找到官方指定的源码阅读顺序。

README 提供了：

- 项目定位
- 配置说明
- 工作方式
- 演示流程

但没有规定“先读哪个源码文件、再读哪个源码文件”。

我已经把这个结论和建议学习路线写入：

[学习文档.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/学习文档.md)

写入内容包括：

- 为什么采用连续分段学习
- 先看 README 总览
- 再看 skill 数据模型
- 跟踪一次 skill 从创建到退役
- 最后用测试验证完整流程
- 每一段对应的具体源码文件
- 采用这个顺序的原因

后面我们就按这份文档进行，先从中文版 README 的“工作方式”开始。

---

对，我觉得这个方式更合适，也更不容易脱离项目实际。

我们确定采用下面的规则：

## 阅读材料

主要阅读：

[repo2-中文/README.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/README.md)

它保持了原版 README 的章节顺序和项目含义。遇到中文翻译不清楚的地方，再对照：

[repo2/README.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2/README.md)

## 学习方式

严格按照 README 原始分段推进：

1. 项目定位和功能概览
2. 安装、更新、卸载
3. 配置
4. 工作方式
5. 演示流程
6. 项目对比和其他说明

每一段都分成四部分：

- **原文解释**：说明这一段本身表达的内容
- **项目补充**：结合源码、配置和测试解释实现细节
- **连续连接**：说明它和前后段落的关系
- **本段小结**：记录已经理解的内容

补充内容会标明对应文件，例如：

```text
项目补充：
README 这里提到 Promoter 是唯一写入者，
对应实现位于 src/autoharness/hook/promoter.py。
```

这样 README 是主线，源码和测试负责验证，能减少脱离项目的推断。

我已经把这个规则补充到：

[学习文档.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/学习文档.md)

下一步我们就从 README 顶部开始，按原文第一段逐段学习。

---

这个方式很好，我建议就这样做。

当前目录可以这样分工：

```text
学习记录/
├─ 学习文档.md              # 总目标、总路线、学习规则
├─ 01-README-项目定位.md
├─ 02-README-安装与配置.md
├─ 03-README-工作方式.md
├─ 04-README-演示流程.md
├─ 05-Skill数据模型.md
├─ 06-触发与会话捕获.md
├─ 07-Reflector与Intent.md
├─ 08-Promoter校验与落盘.md
├─ 09-使用计数与归档.md
└─ 10-Curator与测试验证.md
```

这些阶段文档不会一次性写完。我们进入某个阶段后，边阅读、边核对源码、边记录。

每个阶段使用相同结构：

```markdown
# 阶段名称

## 1. 原文位置

## 2. 原文内容的理解

## 3. 项目补充

## 4. 与前后流程的连接

## 5. 本阶段已确认内容

## 6. 仍需确认的问题
```

补充内容必须能对应到：

- 具体源码文件
- 具体配置
- 具体测试
- 或 README 中明确写出的内容

暂时没有证据的内容会放进“仍需确认的问题”，不会直接写成结论。

这样，[学习记录/学习文档.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/学习记录/学习文档.md) 是总目录，每个阶段文档是实际学习过程的记录，最后再把各阶段连接成完整流程。

下一步我们从 README 的第一部分开始，并创建第一个阶段文档。

---

对，这样更简单，也更符合我们的目标。

每个阶段文档只保留两部分：

```markdown
# 阶段名称

## 原文

这里放对应的中文版 README 原文。

## 补充

这里解释：

- 原文具体是什么意思
- 对应哪些源码
- 实际运行时怎样连接
- 和上一阶段、下一阶段有什么关系
```

这样做有几个好处：

- 原文和解释始终对应，方便核对
- 不会把我们的理解误写成项目原话
- 分成多个文档后，原文长度完全可控
- 后面可以直接从这些阶段文档拼出完整学习记录

我已经把这个规则更新到：

[学习记录/学习文档.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/学习记录/学习文档.md)

接下来每开始一个阶段，我们就创建对应文档，然后边看原文边补充。

---

# 第一阶段：README 项目定位

本阶段对应 README 的第 1～19 行：

[README.md:1](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/README.md:1)

## 原文

> **autoharness 是 Claude Code 的自学习 skill 层。** 它从真实会话中学习 skill，把相同场景的 skill 合并起来，在使用过程中更新它们，并清理停止使用的 skill，让这一层自行保持整洁，并且只触碰它自己写入的 skill。
>
> 它的主要特点是：
>
> - 从真实工作中学习
> - 合并相同场景的 skill
> - 在会话开始时展示自己的 skill 索引
> - 通过实际使用情况判断 skill 是否保留
> - 只管理自己生成的 skill
> - 保存创建和更新时的证据

## 补充

### 1. 这里的“学习”具体指什么

这里的学习，是把真实会话中的经验提炼成新的或修改后的 skill 文件。

它最终会表现为：

```text
真实会话经验
→ skill 提案
→ 校验
→ 写入 SKILL.md
```

项目的核心产物仍然是普通的 `SKILL.md`，不是一种新的私有文件格式。

### 2. 它位于 Claude Code 的旁边

AutoHarness 不替换宿主原来的 skill 召回机制，而是在旁边增加维护流程：

```text
Claude Code 宿主
        ↓
AutoHarness 观察和维护
        ↓
普通的 .claude/skills/<name>/SKILL.md
        ↓
Claude Code 继续按照原有方式使用
```

所以它的目标是让 skill 库自动产生、更新、合并和归档。

### 3. “合并”是重要设计

新会话产生的经验不一定创建新 skill。

Reflector 会先查看现有 skill 的 description 和内容，判断这次经验是否应该：

- 更新已有 skill
- 合并到已有 skill
- 创建新的类别级 skill
- 删除已经被吸收的狭窄 skill

后面会在 [agents/reflector.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/agents/reflector.md) 中看到这套规则。

### 4. “使用情况”不是简单的时间判断

README 中提到，skill 是否保留取决于实际使用情况。

项目会把这些信号分开记录：

- `use`：模型真正加载并使用 skill
- `view`：会话查看过 skill
- `patch`：skill 被改进过

这些计数由 [sidecar.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/lib/sidecar.py) 保存，生命周期判断由 [lifecycle.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/lib/lifecycle.py) 完成。

### 5. “只管理自己的 skill”是安全边界

项目不会管理所有看到的 skill。

它会通过 `created_by:agent` 等标记区分：

```text
AutoHarness 创建的 skill  → 可以更新、合并、归档
用户手写的 skill          → 不触碰
其他插件安装的 skill      → 不触碰
```

这条边界会在 Promoter 和生命周期管理代码中再次检查。

### 6. 每个 skill 都保留原因和证据

创建或修改 skill 时，项目会保存：

- 为什么创建或修改
- 对应的会话证据
- 发生了什么生命周期变化

这些记录写入 `.ledger.jsonl`，具体实现位于：

[ledger.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/lib/ledger.py)

因此以后可以追溯一个 skill 为什么出现、为什么被修改或归档。

## 这一段形成的整体认识

现在可以把 AutoHarness 暂时理解成：

```text
一个围绕普通 SKILL.md 文件运行的自动维护层
```

它维护的完整对象包括：

```text
SKILL.md
.sidecar.json       # 使用和生命周期计数
.ledger.jsonl       # 创建、修改、归档记录
references/evidence-*  # 脱敏后的证据
```

本阶段先记住三点：

1. 真实会话是 skill 的经验来源。
2. Reflector 提出修改，后续的确定性组件负责校验和写入。
3. skill 的后续命运由使用记录和生命周期规则决定。

这一阶段的“原文＋补充”确认后，再写入：

`学习记录/01-README-项目定位.md`

下一段继续 README 的“安装”部分。

---

你说得对，我刚才把原文改成了摘要，违反了我们约定的记录方式。这里重新来：

- 先完整贴出当前中文版 README 的原文
- 再单独写补充说明
- 补充不混入原文
- 本阶段确认后再写入文档

# 第一阶段：README 项目定位

原文位置：

[README.md:1-19](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/README.md:1)

## 原文

```markdown
<h1 align="center">AutoHarness</h1>
<p align="center"><strong>Claude Code 的自学习 Skills</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Ftigerless-labs%2Fautoharness%2Fmain%2F.claude-plugin%2Fplugin.json&query=%24.version&label=release&prefix=v&color=brightgreen" alt="发布版本" /> <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 版本" /> <img src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS-lightgrey.svg" alt="平台" /> <img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="MIT 许可证" /> <a href="https://repositoryradar.dev/repo/tigerless-labs/autoharness"><img src="https://repositoryradar.dev/badge/tigerless-labs/autoharness.svg" alt="Repository Radar 推荐项目" /></a>
</p>

**autoharness 是 Claude Code 的自学习 skill 层。** 它从真实会话中**学习** skill，把相同场景的 skill **合并**起来，而不是不断堆叠近似副本，在使用过程中**更新**它们，并清理停止使用的 skill——让这一层**自行保持整洁**，并且**只触碰它自己写入的 skill**。

同一个模型，不同的 harness——CORE-Bench ([HAL](https://arxiv.org/abs/2510.11977)) 从 42% 提升到 78%。Harness 承担了大量工作（swyx 的 **Big Model vs Big Harness**），但每一代模型仍然需要手工重建。autoharness 选择其中一个切面下注：skill 层可以自己维护自己。

| | |
|---|---|
| **从真实工作中学习** | 每个 episode 都从你正在进行的会话中提炼成一个 skill——不需要单独的数据收集或回放循环。一次会话完成足够工作后，它会自动触发；想立即保存一条经验时，可以使用 `/learn` 按需提炼。 |
| **分组，而不是只会堆积** | 新 episode 不一定会新增 skill——reflector 会把它与现有内容比较，并把相同场景的 skill 合并到一起，因此这一层按类别收敛，而不是积累近似副本。每次合并都会记录哪个 skill 吸收了哪个 skill，因此不会把合并误认为死亡。 |
| **让自己的库保持可见** | 每个会话开始时都会打开一个按组整理的索引，列出它写入的 skill，因此召回不依赖宿主是否碰巧展示它们。宿主原生的召回机制保持完全不变；这个索引是在其上增加的一层。 |
| **通过使用验证，而不是基准测试** | 一个 skill 能否保留，取决于它在后续回合中是否被遵循（在它可用的请求中被加载的比例），而不是留出数据集上的分数。活跃路径上没有 oracle，也不需要为专门评估消耗 token。 |
| **只管理自己的 skill** | 只触碰这个插件生成的 skill——其他内容，无论是你写的还是安装的，都完全不受影响。 |
| **保留证据供以后使用** | 每次创建或更新都会把场景和决定记录到每个 skill 的 ledger 中——如果将来需要，可以用这些原材料从真实使用情况建立基准测试。 |
```

## 补充

这段原文说明了项目的总体定位：

1. AutoHarness 维护的是 Claude Code 的 skill 层。
2. skill 的经验来源是真实会话。
3. 新经验可能创建 skill，也可能合并、更新已有 skill。
4. 项目会在会话开始时展示自己生成的 skill 索引。
5. skill 是否保留，依据后续使用情况判断。
6. 项目只处理自己创建的 skill。
7. 每次创建或更新都会保存原因和证据。

对应的源码位置包括：

- skill 提案入口：`src/autoharness/stage_skill/server.py`
- 提案队列：`src/autoharness/lib/intent_queue.py`
- skill 校验和落盘：`src/autoharness/hook/promoter.py`
- 会话开始索引：`src/autoharness/hook/on_session_start.py`
- 使用计数：`src/autoharness/lib/sidecar.py`
- 生命周期判断：`src/autoharness/lib/lifecycle.py`
- 操作记录：`src/autoharness/lib/ledger.py`

这一阶段暂时只确认项目的总体定位，不深入这些源码文件。确认后，我们再把上面的“原文＋补充”写入：

`学习记录/01-README-项目定位.md`

---

你说得对。刚才的问题是我把 Markdown 源代码放进了代码块，所以 HTML 标签、图片链接和表格语法都原样显示出来了，阅读体验很差。

我们应该采用：

- 保留原文的句子和顺序
- 按 Markdown 的正常效果渲染
- 隐藏只负责页面排版的 HTML 标签和徽章链接
- 原文和补充分开
- 需要核对源代码时，再给出文件位置

例如这段应该这样阅读：

# AutoHarness

**Claude Code 的自学习 Skills**

**autoharness 是 Claude Code 的自学习 skill 层。** 它从真实会话中**学习** skill，把相同场景的 skill **合并**起来，在使用过程中**更新**它们，并清理停止使用的 skill——让这一层**自行保持整洁**，并且**只触碰它自己写入的 skill**。

同一个模型，不同的 harness——CORE-Bench（[HAL](https://arxiv.org/abs/2510.11977)）从 42% 提升到 78%。Harness 承担了大量工作，但每一代模型仍然需要手工重建。autoharness 选择其中一个切面下注：skill 层可以自己维护自己。

| 项目特点 | 原文说明 |
|---|---|
| **从真实工作中学习** | 每个 episode 都从你正在进行的会话中提炼成一个 skill。不需要单独的数据收集或回放循环。一次会话完成足够工作后，它会自动触发；也可以使用 `/learn` 按需提炼。 |
| **分组，而不是只会堆积** | 新 episode 不一定会新增 skill。reflector 会把它与现有内容比较，并把相同场景的 skill 合并到一起。 |
| **让自己的库保持可见** | 每个会话开始时都会打开一个按组整理的索引，列出它写入的 skill。 |
| **通过使用验证** | 一个 skill 能否保留，取决于它在后续回合中是否被遵循。 |
| **只管理自己的 skill** | 只触碰这个插件生成的 skill。 |
| **保留证据供以后使用** | 每次创建或更新都会把场景和决定记录到每个 skill 的 ledger 中。 |

这才是我们后面采用的“原文”展示方式。原文对应 README 的实际位置仍然会标出来，例如：

[README.md:1-19](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/README.md:1)

刚才那种完整 HTML 和 Markdown 源码不会再直接放进学习正文里。

---

好，后面都采用这种格式。

## 补充

这段 README 主要是在定义项目目标，还没有展开具体实现。

可以先建立这几个认识：

1. **“自学习”指维护 skill 文件**  
   项目把真实会话中的经验提炼成 `SKILL.md`，不涉及修改模型参数。

2. **skill 库会持续变化**  
   新经验可能创建 skill，也可能更新已有 skill，或者合并重复内容。

3. **使用情况会影响生命周期**  
   项目会记录 `use`、`view`、`patch` 等数据，后面用来判断 skill 是否继续保留。

4. **项目只管理自己创建的内容**  
   用户手写或其他插件提供的 skill 不属于 AutoHarness 的管理范围。

5. **每次变化都留下记录**  
   ledger 和 evidence 用来说明某个 skill 为什么创建、更新或归档。

对应实现主要在：

- [sidecar.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/lib/sidecar.py)
- [ledger.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/lib/ledger.py)
- [lifecycle.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/lib/lifecycle.py)
- [promoter.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/hook/promoter.py)

这部分的原文和补充已经整理清楚。确认后，我们就把它写入第一个阶段文档，然后继续 README 的下一段。

---

# 第二阶段：README 安装、更新和卸载

## 原文

### 安装

**要求 PATH 中的 `python3` 为 Python 3.11 或更高版本**——autoharness 完全使用 Python 运行（零第三方依赖）；没有它，Hook 和 MCP server 不会运行。Hook 会解析 PATH 中不带路径的 `python3`，因此如果较旧的解释器排在前面（Xcode 自带 `/usr/bin/python3` 3.9.6），整个会话的 Hook 都会关闭；autoharness 会在 stderr 中说明原因。

在 Claude Code 的输入框中执行：

```text
/plugin marketplace add tigerless-labs/autoharness
/plugin install autoharness@autoharness
```

然后运行 `/reload-plugins`（或重启 Claude Code）。

无需配置。现在它会在后台观察你的会话，并把学习到的 skill 放入 `.claude/skills/`。学习节奏和生命周期阈值可以调整——见[配置](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/README.md:66)。

通常不需要手动调用，但有一个入口可供你主动使用：**`/learn`** 会提炼你当前所在的会话——在解决问题后输入它，这条经验会经过与后台流程相同的提案和校验链。

**MCP server 命名。** `.claude-plugin/plugin.json` 将 server 注册为 `stage_skill`，但 Agent 定义引用的是完整名称 `mcp__plugin_autoharness_stage_skill__stage_skill`。这种转换是自动完成的：插件运行时根据插件名称（`autoharness`）和 server key 构造完整名称。在插件上下文之外（例如手动注册 server），工具名称会是 `mcp__stage_skill__stage_skill`——但 Agent 的 allowlist 仍然引用带插件命名空间的形式。请始终作为插件安装，以匹配这两个名称。Server 定义在 manifest 中，而不是根目录的 `.mcp.json` 中，因为插件根目录就是仓库根目录：如果那里有 `.mcp.json`，它也会成为这个 checkout 的项目配置，其优先级高于插件中相同命令的 server，导致在仓库内部运行的会话中 reflector 没有这个工具。

### 更新

下面使用终端形式展示更新和卸载命令（`claude plugin …`）；在 Claude Code 内部，相同操作位于 `/plugin` 菜单中。

从终端更新——先按 marketplace 名称刷新目录，再使用完整的 **`plugin@marketplace` ID** 更新插件，最后重启：

```text
claude plugin marketplace update autoharness
claude plugin update autoharness@autoharness
```

然后**重启 Claude Code** 使其生效——版本号变化代表新的缓存副本，不是热加载。

之所以先刷新，是因为如果不刷新，`update` 会检查过期的本地目录；即使已经发布了新版本，也可能报告 `already at the latest version`。

第三方 marketplace 默认关闭自动更新。想让以后自动更新，只需启用一次：`/plugin` → **Marketplaces** → **autoharness** → **Enable auto-update**。已安装副本由 `plugin.json` 中的 `version` 缓存；只有该字段递增，发布版本才会到达用户。

### 卸载

```text
claude plugin uninstall autoharness@autoharness
claude plugin marketplace remove autoharness
```

卸载只会停止插件运行——它已经写入的 skill 和自己的状态位于插件**之外**，仍然保留在磁盘上。如果也要清除这些内容，请删除状态目录（全局层为 `~/.claude/autoharness/`，项目层为 `<repo>/.claude/autoharness/`）以及 `.claude/skills/` 下由它创建的 skill（每个 skill 都带有 `self-authored` ledger 标记，因此很容易与自己的 skill 区分）。你自己的 skill 永远不会被触碰。

原文位置：

[README.md:21-64](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/README.md:21)

## 补充

### 1. Python 版本是运行前提

插件的 Hook 和 MCP server 都通过 `python3` 启动。

在 [dispatch.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/hook/dispatch.py) 中，项目明确要求 Python 3.11 以上版本。如果版本过低，当前会话的 Hook 会关闭，并通过 stderr 报告原因。

这与项目使用标准库 `tomllib` 有关。

### 2. 插件安装后，skill 会写入项目目录

默认情况下，项目层 skill 会出现在：

```text
.claude/skills/
```

AutoHarness 自己的运行状态则放在：

```text
.claude/autoharness/
```

这两个目录用途不同：

- `.claude/skills/`：实际的 skill
- `.claude/autoharness/`：计数、intent、运行记录和快照

### 3. `/learn` 走同一条提案链

`/learn` 不是绕过系统直接写文件。

它仍然会经过：

```text
/learn
→ stage_skill
→ intent queue
→ Promoter
→ validate
→ 写入 skill
```

相关实现可以在：

- [config.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/config.py)
- [dispatch.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/hook/dispatch.py)
- [skills/learn/SKILL.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/skills/learn/SKILL.md)

### 4. MCP 名称为什么比较长

`stage_skill` 是插件内部的 server key。安装成 Claude Code 插件后，宿主会自动加上插件命名空间，所以 Agent 看到的是：

```text
mcp__plugin_autoharness_stage_skill__stage_skill
```

这也是为什么项目强调要作为插件安装。

### 5. 卸载不会自动删除已经学习到的内容

插件代码停止运行后，之前生成的 skill、ledger、sidecar 和 evidence 仍然留在磁盘中。

这说明项目把：

```text
插件本身
```

和：

```text
插件生成的数据
```

分开保存。

这一点与前一阶段的“只管理自己生成的 skill”有关：卸载后，数据仍然存在，但用户可以自行决定是否清理。

这一阶段主要是运行前提和插件生命周期说明，还没有进入 skill 的内部学习流程。等这段内容确认后，再写入：

`学习记录/02-README-安装与更新卸载.md`

---

已经安装完成。

- **Claude Code CLI**：`2.1.309`
- **Claude Desktop Windows**：`2.42304.2`
- `claude doctor` 检查结果：没有安装问题
- 开始菜单中已经有 **Claude** 应用

Claude Code 确实有桌面端。官方 Claude Desktop 支持 Windows，并且可以直接在桌面应用中运行 Claude Code；CLI 和桌面端可以使用同一个账号。[官方说明](https://claude.com/download?m=1)

目前还差一步：**登录 Claude 账号**。CLI 检测到当前尚未登录。可以在 PowerShell 中运行：

```powershell
claude auth login
```

然后按浏览器提示登录。Claude Code 需要 Pro、Max、Team 或 Enterprise 计划，免费计划不包含 Claude Code。[官方安装文档](https://code.claude.com/docs/en/getting-started)

桌面端也可以从开始菜单打开 **Claude**，登录后直接使用。

---

分情况：

### 1. 使用 Anthropic 官方账号

CLI 和 Claude Desktop 都可以使用。

### 2. 使用自定义“中转”

通常应该使用 **Claude Code CLI**。官方 CLI 支持通过网关配置：

```powershell
$env:ANTHROPIC_BASE_URL="https://你的中转地址"
$env:ANTHROPIC_AUTH_TOKEN="你的中转密钥"
claude
```

具体使用 `ANTHROPIC_AUTH_TOKEN` 还是 `ANTHROPIC_API_KEY`，要看中转服务的要求。中转也必须兼容 Anthropic API，不能只有普通 OpenAI 格式接口。官方文档提供了 `ANTHROPIC_BASE_URL` 和网关配置方式。[LLM Gateway 官方文档](https://docs.anthropic.com/en/docs/claude-code/llm-gateway)

Claude Desktop 的官方流程主要是登录 Claude 账号，官方文档没有提供通用的自定义 `ANTHROPIC_BASE_URL` 配置入口。因此你的中转场景使用 CLI 更稳妥。桌面端适合官方账号登录使用 Claude Code。[Claude Desktop 官方说明](https://claude.com/download?m=1)

另外要注意：

- 设置了 `ANTHROPIC_API_KEY` 后，CLI 会优先使用 API Key，可能产生 API 费用
- 不要把真实密钥写进项目文件或学习文档
- 可以在 Claude Code 中使用 `/status` 检查当前走的是订阅还是 API Key。[官方认证说明](https://support.claude.com/en/articles/12304248-manage-api-key-environment-variables-in-claude-code)

所以我们学习 AutoHarness 时，建议直接使用 **CLI + 中转配置**。你只需要提供中转服务要求的地址格式和变量名，真实密钥可以隐藏。

---

现在已经满足要求。

当前状态：

```text
python  → Python 3.13.12
python3 → C:\Users\dummy\miniconda3\python3.exe
python3 → Python 3.13.12
```

AutoHarness 要求的是 **Python 3.11 或更高版本**，所以你的 Python 版本符合要求。

之前的问题是：

```text
python3 → WindowsApps\python3.exe
```

这是一个无效的 Microsoft Store 别名，无法运行。我已经把它修正为 Miniconda 的 Python，并确认：

```text
python3 --version
Python 3.13.12
```

现在 AutoHarness 使用 `python3` 启动 Hook 和 MCP server 时，可以找到正确的 Python。

---

对，我建议改成这种方式。它比“先贴完整原文，再统一补充”更适合学习。

## 采用的格式

```markdown
## 原文片段 1

原文内容……

### 补充

解释这段的意思，并说明对应的源码实现。

## 原文片段 2

原文内容……

### 补充

解释这段和上一段的连接。
```

README 中的表格也按这个方式处理：

```markdown
### 原文：从真实工作中学习

原文说明……

### 补充

这里的 episode 指什么，触发逻辑对应哪些文件。

### 原文：分组，而不是只会堆积

原文说明……

### 补充

这里对应 Reflector 的 compare-first 规则。
```

这样有几个好处：

- 每个解释紧跟对应原文
- 不需要在长原文和补充说明之间来回查找
- 能清楚区分项目原话和我们的理解
- 源码补充可以精确对应到当前概念
- 阶段之间仍然可以连续衔接

我已经把这个规则更新到：

[学习记录/学习文档.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/学习记录/学习文档.md)

之前第一阶段的内容，正式写入阶段文档时也会按这个格式整理。接下来继续 README 时，我们直接采用“原文片段 → 补充”的方式。

---

好，这次按“原文片段 → 紧接补充”的方式重来。

# 第一阶段：README 项目定位

> 下面的原文保持中文版 README 的原句和顺序，只去掉了页面徽章等排版代码。

## 原文片段 1

# AutoHarness

**Claude Code 的自学习 Skills**

## 补充

这是项目名称和一句话定位。这里的重点是：

```text
AutoHarness = Claude Code 的自学习 skill 层
```

它关注的是 skill 的产生、更新、合并和后续维护。

---

## 原文片段 2

**autoharness 是 Claude Code 的自学习 skill 层。** 它从真实会话中**学习** skill，把相同场景的 skill **合并**起来，而不是不断堆叠近似副本，在使用过程中**更新**它们，并清理停止使用的 skill——让这一层**自行保持整洁**，并且**只触碰它自己写入的 skill**。

## 补充

这句话定义了项目的核心目标：

- 从真实会话中提炼 skill
- 避免同类 skill 越积越多
- 允许后续修改已有 skill
- 清理长期没有价值的 skill
- 不修改用户自己写的 skill

所以它不是一次性的 skill 生成器，而是一个持续维护 skill 库的系统。

---

## 原文片段 3

同一个模型，不同的 harness——CORE-Bench ([HAL](https://arxiv.org/abs/2510.11977)) 从 42% 提升到 78%。Harness 承担了大量工作（swyx 的 **Big Model vs Big Harness**），但每一代模型仍然需要手工重建。autoharness 选择其中一个切面下注：skill 层可以自己维护自己。

## 补充

这里的 `harness` 可以理解为围绕模型运行的工作系统，包括：

- 工具调用
- 工作流程
- 规则
- 记忆和 skill
- 结果验证

AutoHarness 专门维护其中的 skill 层。它的目标是减少人工维护 skill 的工作。

---

## 原文片段 4

### 从真实工作中学习

每个 episode 都从你正在进行的会话中提炼成一个 skill——不需要单独的数据收集或回放循环。一次会话完成足够工作后，它会自动触发；想立即保存一条经验时，可以使用 `/learn` 按需提炼。

## 补充

这里的 `episode` 可以先理解为一段完整的工作会话。

经验来源有两种：

```text
正常工作达到触发条件
→ 后台自动反思

用户主动输入 /learn
→ 立即进入同一套提案和校验流程
```

`/learn` 不会直接把文字写进 `SKILL.md`，后面仍然要经过 `stage_skill`、intent 队列和 Promoter。

---

## 原文片段 5

### 分组，而不是只会堆积

新 episode 不一定会新增 skill——reflector 会把它与现有内容比较，并把相同场景的 skill 合并到一起，因此这一层按类别收敛，而不是积累近似副本。每次合并都会记录哪个 skill 吸收了哪个 skill，因此不会把合并误认为死亡。

## 补充

新经验可能对应以下几种动作：

```text
create
update
patch
delete
```

其中 `delete` 不一定代表 skill 没用了，也可能表示它已经被另一个更宽泛的 skill 吸收。

因此项目要记录：

```text
哪个 skill 被吸收
哪个 skill 保留下来
```

这样后面分析生命周期时，可以区分“被合并”和“被淘汰”。

相关规则主要在：

[agents/reflector.md](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/agents/reflector.md)

---

## 原文片段 6

### 让自己的库保持可见

每个会话开始时都会打开一个按组整理的索引，列出它写入的 skill，因此召回不依赖宿主是否碰巧展示它们。宿主原生的召回机制保持完全不变；这个索引是在其上增加的一层。

## 补充

AutoHarness 不替换 Claude Code 原来的 skill 召回机制。

它额外做了一件事：

```text
会话开始
→ 生成自己的 skill 索引
→ 注入当前会话
```

这样模型能够看到 AutoHarness 自己生成的 skill。对应实现是：

[on_session_start.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/hook/on_session_start.py)

---

## 原文片段 7

### 通过使用验证，而不是基准测试

一个 skill 能否保留，取决于它在后续回合中是否被遵循（在它可用的请求中被加载的比例），而不是留出数据集上的分数。活跃路径上没有 oracle，也不需要为专门评估消耗 token。

## 补充

项目不使用传统的离线测试分数来决定某个 skill 是否有价值。

它关注的是：

```text
skill 有机会被使用时
模型是否真正加载并遵循了它
```

项目会区分：

- `use`：实际使用
- `view`：查看过
- `patch`：被修改过

这些数据保存在：

[sidecar.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/lib/sidecar.py)

---

## 原文片段 8

### 只管理自己的 skill

只触碰这个插件生成的 skill——其他内容，无论是你写的还是安装的，都完全不受影响。

## 补充

这是项目的管理边界。

只有带有 AutoHarness 创建标记的 skill，才允许被：

- 更新
- 合并
- 归档
- 删除

用户自己写的 skill 和其他插件安装的 skill 不属于它的管理范围。

---

## 原文片段 9

### 保留证据供以后使用

每次创建或更新都会把场景和决定记录到每个 skill 的 ledger 中——如果将来需要，可以用这些原材料从真实使用情况建立基准测试。

## 补充

每个 skill 除了 `SKILL.md`，还会有生命周期记录，例如：

```text
创建原因
更新原因
合并关系
对应证据
```

这些内容写入 ledger，具体实现位于：

[ledger.py](C:/Users/dummy/PycharmProjects/agent-/自己项目/autoharness/repo2-中文/src/autoharness/lib/ledger.py)

所以以后可以追溯：

```text
这个 skill 为什么产生？
为什么被修改？
为什么被合并或归档？
```

这就是“原文片段下面紧接补充”的格式。等你确认这一版阅读方式合适后，我们再把这部分写入：

`学习记录/01-README-项目定位.md`

---

对，你说得对。我们现在只是完成了 README 第一部分“项目定位和功能概览”，总的第一阶段还没有结束。

总的第一阶段应该是：

```text
完整阅读 README
→ 项目定位
→ 安装、更新、卸载
→ 配置
→ 工作方式
→ 演示流程
→ 项目对比和结尾说明
```

所以目前的状态是：

```text
第一阶段：README 项目总览
├─ 项目定位和功能概览       已完成
├─ 安装、更新、卸载          未完成
├─ 配置                      未完成
├─ 工作方式                  未完成
├─ 演示流程                  未完成
└─ 对比、致谢、许可证        未完成
```

我们暂时不写入阶段文档。等 README 的所有原始章节都按“原文片段 → 对应补充”学习完，再一次性写入：

`学习记录/01-README-项目总览.md`

刚才我准备写入阶段文档的动作也被中断了，所以目前没有提前写入。接下来继续 README 的“安装、更新、卸载”部分。

---

# README 原文片段：安装

## 原文

**要求 PATH 中的 `python3` 为 Python 3.11 或更高版本**——autoharness 完全使用 Python 运行（零第三方依赖）；没有它，Hook 和 MCP server 不会运行。Hook 会解析 PATH 中不带路径的 `python3`，因此如果较旧的解释器排在前面（Xcode 自带 `/usr/bin/python3` 3.9.6），整个会话的 Hook 都会关闭；autoharness 会在 stderr 中说明原因。

在 Claude Code 的输入框中执行：

```text
/plugin marketplace add tigerless-labs/autoharness
/plugin install autoharness@autoharness
```

然后运行 `/reload-plugins`（或重启 Claude Code）。

无需配置。现在它会在后台观察你的会话，并把学习到的 skill 放入 `.claude/skills/`。学习节奏和生命周期阈值可以调整——见配置部分。

通常不需要手动调用，但有一个入口可供你主动使用：**`/learn`** 会提炼你当前所在的会话——在解决问题后输入它，这条经验会经过与后台流程相同的提案和校验链。

## 补充

这里有几个运行前提：

- Hook 和 MCP server 都由 Python 启动。
- 项目要求 `python3` 至少为 Python 3.11。
- AutoHarness 默认不需要额外 Python 第三方依赖。
- `/learn` 不是直接写入 skill，而是进入正常的提案、校验和落盘流程。

我们刚才已经检查过你的环境：

```text
python3 → Python 3.13.12
```

因此满足这个要求。

---

# README 原文片段：MCP server 命名

## 原文

**MCP server 命名。** `.claude-plugin/plugin.json` 将 server 注册为 `stage_skill`，但 Agent 定义引用的是完整名称 `mcp__plugin_autoharness_stage_skill__stage_skill`。这种转换是自动完成的：插件运行时根据插件名称（`autoharness`）和 server key 构造完整名称。在插件上下文之外（例如手动注册 server），工具名称会是 `mcp__stage_skill__stage_skill`——但 Agent 的 allowlist 仍然引用带插件命名空间的形式。请始终作为插件安装，以匹配这两个名称。

Server 定义在 manifest 中，而不是根目录的 `.mcp.json` 中，因为插件根目录就是仓库根目录：如果那里有 `.mcp.json`，它也会成为这个 checkout 的项目配置，其优先级高于插件中相同命令的 server，导致在仓库内部运行的会话中 reflector 没有这个工具。

## 补充

这里解释了为什么安装方式不能随意替换。

项目中的 server key 是：

```text
stage_skill
```

安装成插件后，Claude Code 会自动加上插件命名空间：

```text
mcp__plugin_autoharness_stage_skill__stage_skill
```

Reflector 和 Curator 的工具白名单引用的是完整名称，所以插件安装方式必须和 Agent 定义保持一致。

对应文件是：

- `.claude-plugin/plugin.json`
- `agents/reflector.md`
- `agents/curator.md`
- `src/autoharness/stage_skill/server.py`

---

# README 原文片段：更新

## 原文

下面使用终端形式展示更新和卸载命令（`claude plugin …`）；在 Claude Code 内部，相同操作位于 `/plugin` 菜单中。

从终端更新——先按 marketplace 名称刷新目录，再使用完整的 **`plugin@marketplace` ID** 更新插件，最后重启：

```text
claude plugin marketplace update autoharness
claude plugin update autoharness@autoharness
```

然后**重启 Claude Code** 使其生效——版本号变化代表新的缓存副本，不是热加载。

之所以先刷新，是因为如果不刷新，`update` 会检查过期的本地目录；即使已经发布了新版本，也可能报告 `already at the latest version`。

第三方 marketplace 默认关闭自动更新。想让以后自动更新，只需启用一次：`/plugin` → **Marketplaces** → **autoharness** → **Enable auto-update**。已安装副本由 `plugin.json` 中的 `version` 缓存；只有该字段递增，发布版本才会到达用户。

## 补充

更新过程有三个动作：

```text
刷新 marketplace
→ 更新具体插件
→ 重启 Claude Code
```

这里的重启很重要，因为插件是缓存副本。更新仓库中的代码，不代表正在运行的 Claude Code 会立即加载新版本。

项目版本号位于：

```text
.claude-plugin/plugin.json
```

当前中文副本中的版本号是：

```text
0.5.3
```

---

# README 原文片段：卸载

## 原文

```text
claude plugin uninstall autoharness@autoharness
claude plugin marketplace remove autoharness
```

卸载只会停止插件运行——它已经写入的 skill 和自己的状态位于插件**之外**，仍然保留在磁盘上。如果也要清除这些内容，请删除状态目录（全局层为 `~/.claude/autoharness/`，项目层为 `<repo>/.claude/autoharness/`）以及 `.claude/skills/` 下由它创建的 skill（每个 skill 都带有 `self-authored` ledger 标记，因此很容易与自己的 skill 区分）。你自己的 skill 永远不会被触碰。

## 补充

插件本身和它生成的数据是分开的：

```text
插件代码
├─ 可以卸载
└─ 停止 Hook 和 MCP server

插件生成的数据
├─ .claude/skills/
├─ .claude/autoharness/
├─ sidecar
├─ ledger
└─ evidence
```

所以卸载插件不会自动删除已经学习到的 skill。

这和前面“只管理自己生成的 skill”相互对应：AutoHarness 生成的 skill 带有自己的标记，用户可以之后单独清理这些内容。

这一部分说明的是运行前提、插件安装方式和数据保存位置。下一部分进入 README 的“配置”，开始解释项目如何控制学习节奏、召回和生命周期。

---

## 原文片段：配置总原则

> 每个配置项都是带有内置默认值的 `AUTOHARNESS_*` 环境变量——除非要改变运行节奏，否则无需配置。

### 补充

这句话说明了配置的基本方式：

- 配置项统一使用 `AUTOHARNESS_` 开头。
- 每个配置项都有默认值。
- 第一次学习时可以先不改配置，让项目按默认行为运行。
- 只有想调整学习频率、索引显示、生命周期或通知方式时，才需要设置环境变量。

例如：

```powershell
$env:AUTOHARNESS_REFLECT_EVERY_N="10"
```

这只会影响当前终端会话。也可以写入 Claude Code 的 `.claude/settings.json`。

---

## 原文片段：存放位置——它管理哪些层

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_DISABLE_GLOBAL` | `0` | 设为 `1` 时只部署项目层。全局 create intent 会在进入 staging 和落盘之前被拒绝；全局 request/use/view 计数、归档、孤儿清理、召回、curator 快照和 metrics 都会跳过。已有的全局 skill 保持不变。项目层学习正常继续。 |

### 补充

autoharness 把 skill 分成两层：

- **项目层**：只服务当前项目。
- **全局层**：可以被其他项目共同使用。

默认情况下，两层都会参与学习。

如果设置：

```powershell
$env:AUTOHARNESS_DISABLE_GLOBAL="1"
```

那么：

- 新的学习结果只进入项目层。
- 全局层不会新增 skill。
- 全局层的统计、归档和召回也会暂停。
- 已经存在的全局 skill 不会被删除。
- 项目层仍然正常学习。

因此，这个配置适合希望学习结果只留在当前项目中的情况。它是“停止管理全局层”，不是“删除全局层”。

---

## 原文片段：节奏——它何时学习

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_REFLECT_EVERY_N` | `50` | 反思节奏按**工具调用**计数，而不是按回合计数：主会话每调用一次工具，计数器就前进一次；把计数推过 N 的那个回合结束时，会触发后台反思。只有实际工作会触发，只聊天不会触发。值越低，学习越快，启动的子会话也越多。 |

### 补充

这里的 `N` 不是“对话轮数”，而是工具调用次数。

例如：

- 读文件一次，算一次工具调用。
- 执行命令一次，算一次工具调用。
- 连续聊天但没有调用工具，不会增加这个计数。
- 当累计工具调用数超过设定值时，会在该回合结束后触发反思。

默认值为 `50`，意味着大约完成 50 次工具调用后，才会触发一次反思。

如果改成：

```powershell
$env:AUTOHARNESS_REFLECT_EVERY_N="10"
```

反思会更频繁，但也会：

- 更快产生学习结果；
- 启动更多后台子会话；
- 消耗更多模型调用和资源。

---

## 原文片段：定期合并

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_CONSOLIDATE_EVERY_N` | `250` | curator 使用的相同计量单位，它会定期合并整个 skill 库。这个值明显高于反思节奏，因此 consolidation 比 distillation 更少发生。 |

### 补充

这里有两个不同层次的学习动作：

1. **反思**：分析最近的工作，尝试形成或修改某个 skill。
2. **合并**：定期检查整个 skill 库，把重复或相近的 skill 合并整理。

`AUTOHARNESS_CONSOLIDATE_EVERY_N` 默认是 `250`，明显高于反思的 `50`，所以：

- 反思发生得比较频繁；
- 整体 skill 库的合并整理发生得更少；
- curator 更像是周期性的库维护者。

可以先把它理解成：

```text
反思：最近这段工作有没有值得记录的经验？
合并：整个 skill 库中有没有重复、冲突或可以整理的内容？
```

---

## 原文片段：反思窗口

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_DIGEST_EXCHANGES` | `20` | episode 窗口**之前**有多少次 exchange 会被压缩进 reflector 的 prior-context digest（只保留文本和工具名称）。fork carrier 不使用它，因为 fork 会重放真实会话。 |

### 补充

当 autoharness 启动反思时，不一定把完整历史会话都交给 reflector。

默认情况下，它会把 episode 窗口之前的最近 20 次 exchange 压缩成摘要。摘要主要保留：

- 文本内容；
- 使用过的工具名称。

这是一种上下文压缩，目的是在保留背景信息的同时减少输入长度。

这里有两种携带上下文的方式：

- `bundle`：整理脱敏窗口和摘要，再交给新的子 Agent。
- `fork`：直接恢复并 fork 原来的会话，让 reflector 读取真实会话内容。

因此，`DIGEST_EXCHANGES` 主要影响 `bundle` 模式；使用 `fork` 时不会使用它。

---

## 原文片段：反思内容的携带方式

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_CARRIER` | `bundle` | 携带反思内容的方式。`bundle` 把脱敏窗口和 digest 交给一个新的子 Agent。`fork` 会恢复并 fork 刚刚结束的会话，让 reflector 从父会话的热缓存中读取真实对话。在完成 cache-hit 测量之前保持 `bundle`。 |

### 补充

默认使用 `bundle`，因为它的行为更明确：

1. 提取最近的工作窗口；
2. 对内容进行脱敏；
3. 生成必要的摘要；
4. 把这些内容交给新的 reflector 子 Agent。

`fork` 会尝试复用刚刚结束的会话缓存。它可能更接近真实上下文，但依赖缓存命中情况，因此项目默认建议先保持：

```text
AUTOHARNESS_CARRIER=bundle
```

这一节的核心关系是：

```text
工具调用次数达到阈值
        ↓
触发后台反思
        ↓
选择 bundle 或 fork 携带上下文
        ↓
reflector 分析并提出 skill 变化
```

到这里，我们已经看完了配置部分的前半段：配置方式、项目层和全局层、反思节奏、合并节奏，以及反思上下文如何传递。

---

## 原文片段：召回——模型能看到什么

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_INDEX_SUSPENDED` | `0` | 设为 `1` 后完全停止注入索引。其他部分仍继续运行——生命周期流程、use/view 计数和上次运行摘要都保留；因此它既可用于测量索引的实际价值，也适用于不愿为索引消耗上下文的用户。 |

### 补充

autoharness 会在会话开始时生成一个 skill 索引，让模型知道当前有哪些可用 skill。

设置：

```powershell
$env:AUTOHARNESS_INDEX_SUSPENDED="1"
```

之后，只会停止这部分索引注入，其他功能仍然继续：

- skill 生命周期仍然运行；
- `use/view` 统计仍然记录；
- 上次运行摘要仍然保留；
- skill 本身不会被删除。

所以它适合用来比较：

```text
开启索引时，模型是否更容易使用 skill？
关闭索引后，效果有什么变化？
```

---

## 原文片段：索引和 skill 描述的长度

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_INDEX_DESC_MAX_CHARS` | `60` | 会话开始索引中每行 description 的预算。索引是扫描界面，不是完整触发文本；提高它可以容纳更长的行，但每个会话都会增加上下文消耗。 |
| `AUTOHARNESS_SKILL_DESC_MAX_CHARS` | `1024` | skill 自身 description 的硬上限，与宿主记录的限制一致；超长内容会被拒绝，而不会在加载时静默截断。 |
| `AUTOHARNESS_SKILL_BODY_MAX_LINES` | `25` | 高度上限：非空行超过此数量的 `SKILL.md` 正文会被视为 transcript 而不是规则，并被拒绝。支持细节应该放在 skill 的 `references/` 中。 |

### 补充

这里有三个不同的长度限制。

#### 1. 索引中显示的 description 长度

`AUTOHARNESS_INDEX_DESC_MAX_CHARS=60` 控制会话开始时索引每一行最多显示多少字符。

索引的作用只是让模型快速扫描：

```text
有哪些 skill？
每个 skill 大概解决什么问题？
```

它不是完整的触发说明，所以不应该写得过长。

#### 2. skill 自身 description 的长度

`AUTOHARNESS_SKILL_DESC_MAX_CHARS=1024` 是 skill description 的硬限制。

超过限制时，skill 会被拒绝，而不是被系统悄悄截断。这样可以避免 description 被截断后改变原意。

#### 3. `SKILL.md` 正文的行数

`AUTOHARNESS_SKILL_BODY_MAX_LINES=25` 限制正文高度。

正文应该主要放：

- 什么时候使用；
- 使用时遵循哪些规则；
- 最核心的操作步骤。

更长的说明、示例和参考资料，应放进：

```text
references/
```

这样可以把“触发规则”和“详细资料”分开。

---

## 原文片段：生命周期——什么能够保留下来

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_MATURITY_PROJECT` | `100` | 项目层的 probation 门槛：skill 落地后，该层再收到这么多请求，就会进入毕业检查。在此之前它照常被召回，但不能被归档。 |
| `AUTOHARNESS_MATURITY_GLOBAL` | `300` | 全局层的相同门槛——因为全局 skill 会加载到每个项目，所以数值更高。 |

### 补充

新创建的 skill 不会马上进入“成熟”状态，而是先处于 probation，也就是观察期。

项目层默认需要经过：

```text
skill 落地后，再收到 100 次请求
```

才会进入毕业检查。

全局层默认需要：

```text
skill 落地后，再收到 300 次请求
```

全局层门槛更高，是因为全局 skill 会影响多个项目，需要更多使用数据才能判断它是否真的有价值。

在 probation 阶段：

- skill 可以被正常召回；
- skill 的使用情况会被统计；
- skill 不会因为暂时没被使用而归档。

---

## 原文片段：容量和归档

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_CAPACITY_PROJECT` | `50` | 项目层**成熟** skill 的容量上限。对于已毕业的 skill，容量竞争是唯一的死亡原因：成熟池超过上限之前不会归档；超过后，使用率最低的 skill 先被归档。它不限制会话开始索引：probation 成员同样会被列入索引，而且不计入这个容量，因此索引大小取决于创建速度，而不是两个容量上限。 |
| `AUTOHARNESS_CAPACITY_GLOBAL` | `20` | 全局层的相同上限——因为影响所有项目，所以更小。 |

### 补充

这里要区分：

- **probation skill**：还在观察期；
- **成熟 skill**：已经通过毕业检查。

容量上限只限制成熟 skill。

项目层默认最多保留 50 个成熟 skill，全局层默认最多保留 20 个成熟 skill。

当成熟 skill 超过容量时，系统会优先归档使用率最低的 skill。

但 probation skill 不计入这个容量，因此：

```text
成熟 skill 数量受容量控制；
观察期 skill 仍然可以继续出现在索引中。
```

这意味着索引可能会变大，即使成熟 skill 数量没有超过限制。

---

## 原文片段：暂停毕业和保留快照

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_GRADUATION_SUSPENDED` | `0` | 设为 `1` 后完全暂停毕业检查，因此 skill 不会因为未被使用而归档。适用于你有理由怀疑召回界面有问题的情况：此时依据零使用归档，会惩罚从未被提供给模型的 skill。容量竞争仍然生效。 |
| `AUTOHARNESS_SNAPSHOT_KEEP` | `5` | curator 合并前为每棵 skill 树保留的预运行快照数量。合并是单次原子 rename 无法撤销的操作。 |

### 补充

如果怀疑“skill 没有被使用”不是因为 skill 没价值，而是因为模型根本没有看到它，可以暂时设置：

```powershell
$env:AUTOHARNESS_GRADUATION_SUSPENDED="1"
```

这样会暂停毕业检查，避免系统根据错误的零使用数据归档 skill。

但这不会暂停容量竞争。成熟 skill 过多时，容量限制仍然会生效。

`AUTOHARNESS_SNAPSHOT_KEEP=5` 则与 curator 的合并操作有关。

因为合并 skill 可能改变原来的目录结构，系统会在合并前保留快照。默认每棵 skill 树保留 5 个快照，用于出现问题时检查合并前的状态。

这里可以先记住：

```text
毕业检查：判断 skill 是否值得继续保留
容量竞争：成熟 skill 太多时进行淘汰
快照：合并前留下可追溯的历史状态
```

到这里，配置部分已经覆盖了：

- 召回索引是否启用；
- description 和正文的长度限制；
- skill 的观察期；
- 成熟 skill 的容量；
- 归档条件；
- curator 合并前的快照。

---

## 原文片段：通知——及时知道发生了什么

> 默认关闭。会话开始摘要会延迟一个会话报告上次运行，只包含计数，不包含名称；下面的通知会在 drain 完成后立即发送同一份运行记录。Fail-open：通知器只有在运行记录写入且 intent queue 清空后才运行，因此通知器缺失、失败或挂起只会延迟 drain，不会让它失败或重复执行。

### 补充

通知功能默认关闭。

系统运行完成后，会生成一份运行记录，其中包含：

- 有多少内容成功落地；
- 有多少内容被拒绝；
- 运行是否完成。

会话开始时显示的摘要可能会延迟到下一次会话，而且默认只显示数量，不显示具体名称。

通知器采用 **fail-open** 方式：

- 通知失败，不会让学习流程失败；
- 通知命令挂起，只会延迟 drain；
- 不会因为通知失败而重复执行学习结果。

因此，通知属于辅助功能，不会成为主流程的依赖。

---

## 原文片段：桌面通知

| 变量 | 默认值 | 作用 |
|---|---|---|
| `AUTOHARNESS_NOTIFY` | _（未设置）_ | 设为 `desktop` 后，每次运行发送系统通知——macOS 使用 `osascript`，Linux 在安装 `notify-send` 时使用它（否则静默不执行）。通知会列出落地和拒绝的内容，例如 `create foo, patch bar · rejected: baz`。macOS 中通知归属于 Script Editor；如果没有出现，请在系统设置 → 通知中允许它。 |

### 补充

设置：

```powershell
$env:AUTOHARNESS_NOTIFY="desktop"
```

后，autoharness 会尝试发送桌面系统通知。

不同系统使用不同的通知机制：

- macOS：使用 `osascript`；
- Linux：使用 `notify-send`；
- Windows：README 这一段没有提供专门的 Windows 通知实现说明。

通知内容类似：

```text
create foo, patch bar · rejected: baz
```

也就是告诉你：

- 哪些 skill 被创建或修改；
- 哪些提议被拒绝。

---

## 原文片段：自定义通知命令

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_NOTIFY_CMD` | _（未设置）_ | 一个命令（按 shell argv 拆分，但绝不通过 shell 执行），从 stdin 接收运行记录 JSON——格式与 `runs/<run-id>.json` 相同；单行摘要放在 `AUTOHARNESS_NOTIFY_SUMMARY` 中。这是对接 Slack、webhook 或其他服务的入口。skill 名称会先脱敏，并且命令运行时会设置子会话保护，因此即使命令启动 `claude`，它本身也不会被捕获。可以与 `desktop` 同时使用。 |

### 补充

这个配置允许接入自定义通知程序。

通知程序会得到：

- 标准输入中的运行记录 JSON；
- `AUTOHARNESS_NOTIFY_SUMMARY` 环境变量中的单行摘要。

运行记录格式与：

```text
runs/<run-id>.json
```

相同。

它可以用来连接：

- Slack；
- webhook；
- 自己写的日志程序；
- 其他消息服务。

这里有两个安全和执行方面的细节：

1. 命令会被拆成参数执行，不会通过 shell 再解析一次。
2. skill 名称在发送前会脱敏。

因此不要把通知命令理解成“把一段字符串直接交给 shell 执行”。

---

## 原文片段：通知超时

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_NOTIFY_TIMEOUT_S` | `5` | 每个通知渠道允许阻塞 drain 的总秒数，最小为 1。`/learn` 的 drain 在宿主的 Stop Hook 中运行，因此这也是它可能延迟一个回合的最长时间。 |

### 补充

默认每个通知渠道最多阻塞 5 秒。

如果通知服务响应很慢，autoharness 不会无限等待。超时后会继续处理主流程。

例如：

```powershell
$env:AUTOHARNESS_NOTIFY_TIMEOUT_S="10"
```

可以把超时时间提高到 10 秒，但通知越慢，当前回合结束时可能等待越久。

---

## 原文片段：如何设置配置

> 在 Claude Code 启动时设置这些环境变量——可以设置在 shell 中（`export AUTOHARNESS_REFLECT_EVERY_N=10`），也可以设置在 `.claude/settings.json` 的 `env` 映射中：

```json
{ "env": { "AUTOHARNESS_REFLECT_EVERY_N": "10" } }
```

### 补充

README 给出了两种设置方式。

#### 方式一：在 shell 中设置

Linux/macOS 示例：

```bash
export AUTOHARNESS_REFLECT_EVERY_N=10
```

Windows PowerShell 对应写法：

```powershell
$env:AUTOHARNESS_REFLECT_EVERY_N="10"
```

#### 方式二：写入 `.claude/settings.json`

```json
{
  "env": {
    "AUTOHARNESS_REFLECT_EVERY_N": "10"
  }
}
```

这种方式更适合项目级配置，因为可以和项目一起保存。

---

## 原文片段：配置何时生效

> Hook 会在每个事件上读取环境变量，因此修改会从下一个会话开始生效。默认值是等待实证校准的有意占位值；捕获窗口和 staged 文件的字节上限是固定常量，不是环境变量配置项。

### 补充

这里有三个重点：

1. Hook 会读取环境变量。
2. 修改配置后，不需要修改源码。
3. 新配置通常从下一个会话开始生效。

另外，并不是所有限制都能通过环境变量修改。

以下内容是固定常量：

- 捕获窗口的字节上限；
- staged 文件的字节上限。

因此，环境变量主要控制运行策略和节奏，不能覆盖所有底层安全限制。

---

至此，README 的“配置”部分已经完整看完。下一部分是 **“工作方式”**，会开始解释一条学习流水线如何和 Claude Code 并行运行，以及 skill 如何被宿主召回。

---

# 工作方式

## 原文片段：整体结构

> 一条学习流水线运行在宿主旁边。Skill 是普通的原生文件，宿主通过自己的名称和 description 机制召回它们，就像它们是人手写的一样——这条路径保持不变。在此之上，每个会话都会打开一个由 autoharness 写入的 skill 索引，因此自己的库是否被提供给模型，是这个插件的属性，而不是对宿主行为的期待。

### 补充

这里的“宿主”就是 Claude Code。

autoharness 不会替换 Claude Code 原本的 skill 机制：

```text
Claude Code 原有的 skill 召回机制
                 +
autoharness 额外生成的 skill 索引
```

Skill 仍然是普通目录和普通的 `SKILL.md` 文件。Claude Code 通过 skill 的名称和 description 判断是否召回它们。

autoharness 额外做了一件事：每次会话开始时，把自己管理的 skill 整理成一个索引注入给模型。

这样可以让模型明确知道：

- 当前有哪些 autoharness skill；
- 每个 skill 大概解决什么问题；
- 哪些 skill 属于项目层；
- 哪些 skill 属于全局层。

---

## 原文片段：CAP——捕获

> **CAP** · capture  
> 由 Hook 驱动的简单管道：捕获每个回合（用户输入、Agent 输出、工具 I/O），在出口处脱敏，并指回宿主日志而不是复制日志。它还负责触发器；触发器是确定性的，只统计一种东西——工具调用。跨过阈值的回合结束时进行反思；这里不判断内容。

### 补充

CAP 是捕获阶段，主要负责两件事：

1. 收集会话过程；
2. 判断什么时候触发反思。

它会观察：

- 用户输入；
- Agent 输出；
- 工具调用；
- 工具返回结果。

但它不会把所有日志复制一份到自己的目录，而是尽量引用宿主已有的日志。

CAP 的触发判断是确定性的，只看：

```text
工具调用次数
```

它不判断这次对话内容是否有价值，也不负责决定应该创建什么 skill。

因此：

```text
CAP 负责收集和计数；
REF 负责理解和提出提案。
```

---

## 原文片段：REF——反思

> **REF** · reflect  
> 读取 episode，与现有 skill 索引比较，然后决定新增 / 合并 / patch / 丢弃 support file / 删除——输出一个 intent（包含正文、delta 或路径，以及原因和证据）。如果新经验与旧 skill 冲突，它必须在同一轮重写过时的 skill，不能让库里同时存在互相争论的规则。它只负责提案，没有写入工具；fork carrier 继承的写入工具会在 Hook 层被拒绝。

### 补充

REF 是 reflector，负责分析最近发生的工作。

它会把新 episode 和现有 skill 库进行比较，然后提出一种结果：

- 创建新的 skill；
- 合并相近的 skill；
- 修改已有 skill；
- 丢弃不需要的 support file；
- 删除过时的内容。

它输出的不是直接写入磁盘的命令，而是一个 **intent**，其中包括：

- 要做什么；
- 要写入的正文或差异；
- 相关文件路径；
- 为什么要这样做；
- 哪些证据支持这个判断。

一个重要规则是：如果新经验和旧 skill 冲突，不能让两个互相矛盾的 skill 同时存在。

正确做法是：

```text
发现新规则
    ↓
识别旧规则已经过时
    ↓
同一轮修改旧 skill
```

REF 只有提案能力，没有写入能力。这样可以把“模型的判断”和“实际落盘”分开，避免 reflector 直接修改 skill 库。

---

## 原文片段：Promoter——验证和存储

> **promoter** · validate·store  
> 唯一写入者。在内存中 lint intent（安全性、结构、ledger、完整性、只允许自创建内容），通过后原子地 rename 到活动 skill 目录。新 skill 的 description 必须尽早包含触发词，以便在索引截断前保留下来——如果线索落在截断位置之后，skill 在本来用于召回它的界面上就只剩半句话。合并时必须写明被删除 skill 被哪个 skill 吸收，而且 umbrella 必须是 autoharness 管理的活动 skill——虚构的名称会使整个 intent 失败，而不会丢掉内容。每次运行都会记录落地和拒绝的内容。

### 补充

Promoter 是唯一可以真正写入 skill 目录的组件。

它会先在内存中检查 intent，包括：

- 安全性；
- 文件结构；
- ledger 是否完整；
- 证据是否存在；
- 内容是否确实由 autoharness 自己创建；
- 创建、修改和删除关系是否一致。

只有检查通过，才会把内容原子地写入活动 skill 目录。

这里的“原子地 rename”意味着：写入过程完成后，整个目录一次性切换到正式位置，避免留下半成品。

### 为什么 description 要尽早出现触发词？

会话开始的 skill 索引会截断 description。

如果真正有用的关键词放在后面：

```text
这是一个很长的介绍……很多背景……很多细节……如何处理插件更新
```

索引被截断后，模型可能只能看到前半段，不知道这个 skill 和“插件更新”有关。

因此触发词要尽量放在 description 的前面。

### 合并为什么必须写明 umbrella？

合并时必须明确：

```text
被删除的 skill → 被哪个现有 skill 吸收
```

被吸收的目标 skill 不能是虚构名称，必须是 autoharness 当前管理的活动 skill。

如果目标不存在，整个 intent 会失败，系统不会只执行其中一部分。

每次运行还会记录：

- 哪些提案成功落地；
- 哪些提案被拒绝；
- 拒绝的原因。

---

## 这三个组件的关系

```text
CAP
捕获会话、记录工具调用
        ↓
REF
分析 episode、提出 intent
        ↓
Promoter
验证 intent、真正写入 skill
```

可以先记住它们的职责边界：

| 组件 | 能做什么 |
|---|---|
| CAP | 收集、脱敏、计数、触发 |
| REF | 分析、比较、提出修改方案 |
| Promoter | 验证并写入磁盘 |

后面继续看 IDX、MNG、curator 和 LED 时，会把“索引、生命周期、合并、证据记录”这些部分补完整。

---

## 原文片段：IDX——展示索引

> **IDX** · surface  
> 构建会话开始索引：列出 autoharness 写入的 skill，按类别分组，每行使用截断后的 description，并标记层级。归档和手写 skill 会被排除；空库不会注入任何内容；上次运行的落地/拒绝摘要会一起带入，因此被拒绝的提案不会悄无声息地消失。

### 补充

IDX 的作用是生成会话开始时展示给模型的 skill 索引。

它会：

- 列出 autoharness 创建的 skill；
- 按类别分组；
- 显示截断后的 description；
- 标记项目层或全局层；
- 加入上一次运行的结果摘要。

它不会列出：

- 已归档的 skill；
- 手工编写的 skill；
- 空库内容。

上一次运行中被拒绝的提案也会显示在摘要里，这样拒绝结果不会悄悄消失。

可以把 IDX 理解成：

```text
skill 库目录 = 实际文件
IDX 索引 = 会话开始时给模型看的目录
```

---

## 原文片段：MNG——生命周期管理

> **MNG** · lifecycle  
> 无 daemon：每个会话开始时懒计算一次。按使用率为符号排序——使用次数除以符号创建后收到的请求数，因此这个指标相对于机会计算，合上电脑不会让任何 skill 变老（取代墙上时钟）。

### 补充

MNG 不会在后台长期运行 daemon。

它在每个会话开始时计算一次生命周期状态，这种方式称为“懒计算”。

skill 的使用率大致是：

```text
使用次数 ÷ skill 创建后收到的请求数
```

这是相对于“实际使用机会”的统计，而不是单纯按时间计算。

因此：

- 电脑关机不会让 skill 自动变老；
- 很久没有打开项目，不会直接导致 skill 被淘汰；
- 只有在实际发生请求时，生命周期数据才会继续变化。

---

## 原文片段：load、view 和 patch

> 三个信号彼此分开：**load**（模型调用了 skill）是唯一计入使用率的信号；**view**（会话读取了 skill 目录）说明它有召回价值，但不代表模型遵循了它；**patch** 表示 skill 正在改进，因此 patch 后的一次 load 可以被视为改进后的再次使用。

### 补充

autoharness 不把所有“看到过 skill”的行为都当成使用，而是区分三种信号。

| 信号 | 含义 | 是否计入使用率 |
|---|---|---|
| `load` | 模型真正调用或加载了 skill | 是 |
| `view` | 会话读取了 skill 目录 | 否 |
| `patch` | Promoter 改进了 skill | 否，但会记录改进 |

例如：

- 模型只是看到了 skill 目录，算 `view`；
- 模型真正使用了其中的规则，算 `load`；
- skill 被修改完善，算 `patch`。

这样可以避免把“浏览过”误认为“真正遵循过”。

---

## 原文片段：probation 和毕业检查

> 新符号在收到足够请求前处于 probation：照常召回，但不计入容量，也不可被淘汰。成熟时，毕业检查只会归档从未 load **且**从未 view 的符号——没有使用证据不等于有不使用证据。

### 补充

新 skill 会先进入 probation，也就是观察期。

观察期内：

- skill 仍然可以被召回；
- 不计入成熟 skill 容量；
- 不会因为暂时没有使用而被淘汰。

毕业检查的条件很谨慎：

```text
整个观察期内既没有 load，也没有 view
```

才可能被归档。

仅仅没有 `load` 并不够，因为模型可能只是看到了 skill，但没有真正调用它。

所以：

```text
没有使用证据 ≠ 证明它没有价值
```

---

## 原文片段：成熟 skill 的容量竞争

> 对于已毕业的符号，容量竞争是唯一的死亡原因——层级的成熟池超过容量后，使用率最低的先被归档。归档而不是删除：归档符号只是被移出召回范围的目录，移回来就能复活。

### 补充

skill 毕业后，如果成熟 skill 数量超过该层的容量上限，才会开始竞争。

淘汰顺序是：

```text
使用率最低的成熟 skill 优先归档
```

归档不是物理删除。

归档后的 skill：

- 从正常召回范围中移出；
- ledger 和证据仍然保留；
- 可以把目录移回来恢复；
- 历史记录不会丢失。

因此生命周期管理更像是：

```text
活动 → 归档 → 必要时恢复
```

而不是：

```text
活动 → 永久删除
```

---

## 原文片段：curator——全库合并

> **curator** · consolidate  
> 更少发生的全库流程：把整个库作为一个整体读取，并把近似副本合并到 umbrella 下；这是单个 episode 无法完成的判断。它在开始前为两层 skill 树都创建快照，因为合并是单次原子 rename 无法撤销的操作。

### 补充

curator 处理的是整个 skill 库，而不是某一次 episode。

它负责发现：

- 近似重复的 skill；
- 可以合并的 skill；
- 应该由哪个 umbrella skill 统一承载的内容。

这类判断需要观察整个库，单个 reflector episode 通常无法完成。

因为合并操作可能无法直接撤销，所以 curator 开始前会为：

- 项目层 skill 树；
- 全局层 skill 树；

分别创建快照。

---

## 原文片段：LED——证据账本

> **LED** · ledger  
> 每个符号的追加式 sidecar：记录符号为什么产生或改变，以及证据和反思水位。它不放进 skill 正文，因此不会污染召回内容。

### 补充

LED 是每个 skill 旁边的追加式记录文件。

它记录：

- skill 为什么创建；
- skill 为什么修改；
- 哪些证据支持这次变化；
- 反思处理到了哪个位置。

这些内容不会放进 `SKILL.md` 正文，而是放在 sidecar 中。

因此模型召回 skill 时，主要看到规则本身；证据和维护历史则单独保存。

典型结构是：

```text
.claude/skills/<name>/
├── SKILL.md
├── .ledger.jsonl
├── .sidecar.json
└── references/
```

可以这样理解：

```text
SKILL.md       给模型使用的规则
.ledger.jsonl  记录规则为什么存在
.sidecar.json  记录生命周期计数
references/    保存支持规则的证据
```

---

## 工作方式的完整链路

```text
CAP
捕获会话并统计工具调用
        ↓
REF
分析 episode，提出 intent
        ↓
Promoter
检查并写入 skill
        ↓
IDX
在下一次会话开始时展示索引
        ↓
MNG
统计使用情况并管理生命周期
        ↓
LED
记录创建、修改和证据
        ↓
curator
定期检查整个 skill 库并合并重复内容
```

到这里，“工作方式”这一节已经完整看完。下一节是“演示：观察它学习”，会通过实际目录、文件和计数，展示这条流水线在磁盘上留下什么。

---

# 演示：观察它学习

## 原文片段：演示目的

> AutoHarness 的所有操作最终都会落到磁盘上的普通文件中——演示只是按正确顺序打开这些文件。要进行快速运行，先加快循环。

### 补充

这一节不再只解释概念，而是通过磁盘上的真实文件观察整个流程。

autoharness 不会把学习结果藏在不可见的内部状态里，最终都会体现为：

- `.claude/skills/` 中的 skill 文件；
- `.claude/autoharness/` 中的运行记录；
- ledger 和 sidecar 文件；
- 快照和证据文件。

为了快速看到结果，演示会把反思和成熟阈值调低。

---

## 原文片段：演示配置

```json
{
  "env": {
    "AUTOHARNESS_REFLECT_EVERY_N": "3",
    "AUTOHARNESS_MATURITY_PROJECT": "5",
    "AUTOHARNESS_CAPACITY_PROJECT": "2"
  }
}
```

### 补充

这里把默认值改小，是为了不用等待很长时间。

| 配置 | 演示值 | 作用 |
|---|---:|---|
| `AUTOHARNESS_REFLECT_EVERY_N` | `3` | 工具调用超过 3 次后触发反思 |
| `AUTOHARNESS_MATURITY_PROJECT` | `5` | 项目层 skill 收到 5 次请求后进入毕业检查 |
| `AUTOHARNESS_CAPACITY_PROJECT` | `2` | 项目层最多保留 2 个成熟 skill |

实际学习时不一定要使用这些值，它们主要用于快速观察流程。

---

## 原文片段：第一步——流水线运行

> 在任意非琐碎任务上正常工作几轮（调试问题、研究工作流等）。当某个回合把工具调用计数推过 N 时，该回合结束时会触发后台反思——不会阻塞会话。

### 补充

首先要进行真实工作，而不是单纯聊天。

例如：

- 调试一个问题；
- 阅读项目代码；
- 完成一个研究任务；
- 修改配置并验证结果。

当工具调用次数超过 `AUTOHARNESS_REFLECT_EVERY_N` 时：

```text
当前回合结束
        ↓
后台启动反思
        ↓
主会话继续运行
```

反思不会阻塞当前会话，所以你不需要等待 reflector 完成后才能继续工作。

---

## 原文片段：状态目录

```text
.claude/autoharness/        # 项目层；全局层为 ~/.claude/autoharness/
  requests                     # 层级请求计数（MNG · lifecycle manager，生命周期管理器的分母）
  session-<id>                 # 计入下一次反思的工具调用数
  offset-<id>                  # 上次捕获窗口结束位置的字节水位
  intents/                     # 等待 Promoter · promoter（提案落地器）处理的 skill 提案
  runs/<run-id>.json           # 该次运行提议、落地和拒绝的内容及原因
  last_run.json                # 等待下一个会话开始读取的摘要
  snapshots/                   # curator · curator（整理者）合并前生成的 skill 树 tar 包
```

### 补充

这里是项目层的运行状态目录。全局层对应：

```text
~/.claude/autoharness/
```

各个文件的作用如下：

- `requests`：记录该层收到过多少请求，供 `MNG · lifecycle manager（生命周期管理器）` 计算使用率。
- `session-<id>`：记录当前会话中已经积累的工具调用数。
- `offset-<id>`：记录上次读取捕获窗口的位置，避免重复处理。
- `intents/`：存放等待 `Promoter · promoter（提案落地器）` 验证的提案。
- `runs/<run-id>.json`：记录一次运行提出、落地和拒绝的内容及原因。
- `last_run.json`：保存给下一次会话开始时读取的摘要。
- `snapshots/`：保存 `curator · curator（整理者）` 合并前的 skill 树快照。

这里可以看出，autoharness 的学习流程不是直接把内容写进 skill 目录，而是先经过：

```text
捕获 → 提案 → 验证 → 记录 → 落地
```

---

## 原文片段：第二步——Skill 诞生

> 反思落地后，`.claude/skills/`（项目层）或 `~/.claude/skills/`（全局层——不依赖具体仓库的技术）下会出现新目录。使用 `ls -la`，因为感兴趣的文件是隐藏文件：

```text
.claude/skills/<name>/
  SKILL.md                     # skill 本身——普通原生格式，没有私有格式
  .ledger.jsonl                # LED · ledger（账本）：它为什么诞生 / 改变（追加式）
  .sidecar.json                # MNG · lifecycle manager（生命周期管理器）读取的生命周期计数
  references/evidence-*.md     # 支持每条 ledger · ledger（账本）记录的 transcript · transcript（会话记录）片段
  scripts/ templates/ ...      # reflector · reflector（反思器）附带的可选 support file · support file（支持文件）
```

### 补充

一个新 skill 落地后，会成为普通目录。

最核心的文件是：

- `SKILL.md`：模型实际使用的规则；
- `.ledger.jsonl`：记录规则为什么产生或改变；
- `.sidecar.json`：保存生命周期计数；
- `references/evidence-*.md`：保存支持规则的脱敏会话片段；
- `scripts/`、`templates/`：可选的辅助文件。

其中以 `.` 开头的文件是隐藏文件，所以查看目录时需要使用：

```bash
ls -la
```

Windows PowerShell 中可以使用：

```powershell
Get-ChildItem -Force
```

这里尤其要注意：

```text
SKILL.md 是给模型使用的内容；
ledger 和 evidence 是解释它为什么存在的记录。
```

它们分别承担“使用”和“追溯”两种职责。

---

## 原文片段：第三步——LED · ledger（账本）

> 执行 `cat .ledger.jsonl`，每个生命周期事件占一行 JSON：

```json
{
  "action": "create",
  "reason": "User asked about the correct command to update a plugin ...",
  "evidence": "references/evidence-21cd22cc.md"
}
{
  "action": "patch",
  "reason": "User discovered /reload-plugins is required in-session ...",
  "evidence": "references/evidence-1a4ec51d.md"
}
```

> `action` + `reason` + `evidence`——证据文件是教会它这条规则的真实脱敏会话片段，由 Promoter · promoter（提案落地器）生成（内容寻址，因此模型不会命名文件）。这就是上表中“保留证据供以后使用”的含义。

### 补充

`.ledger.jsonl` 是追加式账本，每个事件占一行 JSON。

这里有三个关键字段：

| 字段 | 中文含义 |
|---|---|
| `action` | 这次做了什么，例如创建或修改 |
| `reason` | 为什么做这次改变 |
| `evidence` | 哪个证据文件支持这次改变 |

例如：

```json
{
  "action": "create",
  "reason": "用户询问更新插件的正确命令",
  "evidence": "references/evidence-21cd22cc.md"
}
```

这表示这个 skill 是因为一次真实工作场景而产生的。

如果后来发现规则需要修正：

```json
{
  "action": "patch",
  "reason": "用户发现当前会话还需要执行 /reload-plugins",
  "evidence": "references/evidence-1a4ec51d.md"
}
```

就会追加一条 `patch · patch（修补、修改）` 记录，而不是覆盖原来的创建记录。

`evidence · evidence（证据）` 文件保存的是经过脱敏的真实会话片段，用来说明这条规则是如何被总结出来的。

---

## 原文片段：第四步——更新，而不是重复

> 再次遇到同一场景并提出修正（“这里少了一步”），让下一次反思运行。Skill 层不会增长一个近似副本：现有 skill 的 `SKILL.md` 会发生变化，ledger · ledger（账本）会追加一行 `patch · patch（修改）`/`update · update（更新）`——上面的两行 ledger 就是真实示例。对项目层 skill 执行 `git diff` 可以看到编辑结果。

### 补充

当同一个问题再次出现时，autoharness 不应该重新创建一个几乎重复的 skill。

正确流程是：

```text
再次遇到相同场景
        ↓
发现原 skill 少了一步或存在问题
        ↓
修改原来的 SKILL.md
        ↓
在 ledger 中追加 patch 或 update 记录
```

这样可以避免 skill 库不断产生近似副本。

对于项目层 skill，可以执行：

```bash
git diff
```

查看 `SKILL.md` 的实际变化。

这也体现了 autoharness 的核心目标：

```text
重复出现的问题 → 改进原 skill
```

而不是：

```text
重复出现的问题 → 再创建一个相似 skill
```

---

## 原文片段：第五步——下一个会话开始时已经知道

> 开启新会话，第一项输入就是这些 skill 的分组索引，加上一行上次运行报告，因此被拒绝的提案会明确显示，而不是消失。宿主自己的召回机制仍然在底层保持不变；索引只是确保库一定出现在模型面前。

### 补充

下一次开启会话时，autoharness 会先生成 skill 的分组索引。

模型可以看到：

- 当前有哪些 skill；
- skill 属于哪个层级；
- 每个 skill 的简短描述；
- 上一次运行有哪些内容成功落地；
- 哪些提案被拒绝。

被拒绝的提案不会被静默丢弃，而是会出现在运行摘要中。

同时，Claude Code 原来的 skill 召回机制仍然存在。

因此这里有两层关系：

```text
Claude Code 原有召回机制：负责实际加载 skill
autoharness 索引：确保模型知道自己的 skill 库存在
```

索引不是替代宿主机制，而是补充它。

---

## 目前这条演示链路

```text
真实工作
   ↓
CAP · capture（捕获）
   ↓
REF · reflect（反思）
   ↓
生成 intent · intent（提案）
   ↓
Promoter · promoter（提案落地器）验证
   ↓
写入 SKILL.md
   ↓
追加 LED · ledger（账本）记录
   ↓
下一次会话注入索引
```

这样，skill 的产生和变化都有两个结果：

1. `SKILL.md` 改变了模型将来使用的规则；
2. `.ledger.jsonl` 记录了这次改变为什么发生。

---

## 原文片段：第六步——使用有三种计数

> 执行 `cat .sidecar.json`：模型真正加载 skill 时 `use · use（使用）` 增加，这是生存率唯一统计的字段；会话读取 skill 目录时 `view · view（查看）` 增加，表示召回有价值但不代表遵循；Promoter · promoter（提案落地器）落地改进时 `patch · patch（修改）` 增加，因此 patch 后的一次 use 表示改进后再次使用。把这些信号分开，才能防止一个只是被浏览过的 skill 看起来像是被遵循过。

### 补充

`.sidecar.json` 保存 skill 的生命周期计数。

三个计数分别表示：

| 计数 | 中文含义 | 作用 |
|---|---|---|
| `use` | 使用 | 模型真正加载或调用了 skill |
| `view` | 查看 | 会话读取了 skill 目录 |
| `patch` | 修改 | Promoter 改进了 skill |

其中只有 `use` 会进入使用率计算。

例如：

```text
模型看到 skill 目录       → view +1
Promoter 修改 skill       → patch +1
模型真正调用 skill         → use +1
```

如果一个 skill 只是经常被查看，但从来没有被真正使用，那么它不会被错误地算成“高使用率”。

`patch` 也有特殊意义：如果 skill 被改进后再次被使用，这次 `use` 可以说明改进后的版本确实被使用了。

---

## 原文片段：第七步——退役是归档，不是删除

> 有两条退出路径，都是把目录移动到 `.claude/skills/.archive/<name>/`——ledger · ledger（账本）、证据和其他内容全部离开召回范围。毕业检查只会归档在整个 probation · probation（观察期）阶段既没有 use · use（使用）**也没有** view · view（查看）的 skill；毕业后，层级成熟池超过容量时，使用率最低的 skill 会被归档。把目录移回来就能恢复，历史保持不变。

### 补充

skill 退出活动状态有两种情况：

### 情况一：观察期内没有任何信号

如果一个 skill 在整个 probation 期间：

```text
use = 0
view = 0
```

说明它既没有被使用，也没有被查看，毕业检查可能会将它归档。

### 情况二：成熟池超过容量

如果 skill 已经毕业，但同一层的成熟 skill 数量超过容量限制：

```text
使用率最低的成熟 skill → 优先归档
```

归档目录是：

```text
.claude/skills/.archive/<name>/
```

归档时不会删除：

- `SKILL.md`；
- `.ledger.jsonl`；
- `.sidecar.json`；
- `references/`；
- 其他支持文件。

它只是离开正常召回范围。

需要恢复时，把目录移回活动目录即可，历史记录仍然保留。

---

## 原文片段：合并后的归档

> 被合并进另一个 skill 的 skill 也以同样方式归档，但 ledger · ledger（账本）会写明吸收它的 umbrella · umbrella（伞形 skill、统一承载 skill）——因此合并和清理仍然可以区分。

### 补充

当两个相近 skill 被合并时，被吸收的 skill 也会进入归档目录。

但它的 ledger 会记录：

```text
这个 skill 被哪个 umbrella skill 吸收
```

这样以后仍然可以区分：

- 这个 skill 是因为长期没有使用而被清理；
- 还是因为内容已经合并到另一个 skill 中。

这也是为什么归档不是简单删除：归档目录保留了整个历史关系。

---

# 演示部分的完整链路

```text
1. 进行真实工作
        ↓
2. 工具调用达到阈值
        ↓
3. 后台触发反思
        ↓
4. 产生 skill intent
        ↓
5. Promoter 验证并写入
        ↓
6. 生成 SKILL.md、ledger、sidecar、evidence
        ↓
7. 下一次会话注入 skill 索引
        ↓
8. use / view / patch 持续记录
        ↓
9. skill 毕业、归档或被合并
```

到这里，README 的“工作方式”和“演示：观察它学习”两部分已经学习完成。下一部分将看 README 最后的比较、限制、致谢和许可证内容。

---

## 原文片段：第八步——不会触碰你的 skill

> 每个 autoharness 创建的 skill 都带有 ledger · ledger（账本）标记；没有该标记的内容——无论是你写的还是安装的——对 Promoter · promoter（提案落地器）和 MNG · lifecycle manager（生命周期管理器）都不可见。

### 补充

这是一个保护机制。

Promoter 和 MNG 只处理带有 autoharness ledger 标记的 skill。

因此以下内容不会被自动修改、归档或删除：

- 你手工创建的 skill；
- 从其他项目安装的 skill；
- 没有 autoharness ledger 的目录。

可以理解为：

```text
autoharness 自己创建的 skill → 可以管理
没有 autoharness 标记的 skill → 不会触碰
```

这保证了项目不会因为自学习机制而修改用户原本维护的内容。

---

# 对比

## 原文片段：验证方式

> 自学习 skill 层可以通过留出的基准数据验证，也可以根据自己的使用情况验证。autoharness 选择后者——成本更低，并且适用于没有现成基准的开放式真实主机。

### 补充

自学习系统通常有两种验证方式：

1. 使用提前准备好的基准数据；
2. 根据真实使用情况验证。

autoharness 选择第二种方式。

它关注的问题是：

```text
模型实际使用这个 skill 时，是否遵循了它？
```

这样做不需要为每个开放式任务提前准备标准答案，也不需要额外维护 oracle · oracle（标准答案判断器）。

---

## 原文片段：项目对比表

| 能力 | 无限增长 | 离线门控的自编辑 | 计时器 + daemon | autoharness |
|---|---|---|---|---|
| 限制 skill 层大小 | 否 | 是 | 是 | 是 |
| 验证信号 | 无 | 留出基准分数 | 墙上时钟上的不活动时间 | 使用时是否遵循 |
| 什么启动学习流程 | — | 离线批处理 | 空闲时间和经过的天数 | 会话中的实际工作 |
| 把自己的库放到模型面前 | 否 | 否 | 是 | 是 |
| 需要基准 / oracle | 否 | 是 | 否 | 否 |
| 需要常驻 daemon | 否 | 否 | 是 | 否 |

### 补充

这张表强调 autoharness 的几个定位。

### 1. 它限制 skill 库大小

skill 不会无限增长，而是通过：

- probation；
- 毕业检查；
- 容量竞争；
- 归档；
- 合并；

控制库的规模。

### 2. 它根据真实使用验证

autoharness 不依赖预先准备的基准分数，而是观察 skill 在真实工作中是否被遵循。

### 3. 真实工作触发学习

学习流程由实际会话中的工具调用触发，而不是：

- 固定时间；
- 电脑空闲；
- 后台 daemon；
- 离线批处理。

### 4. 它主动把自己的库展示给模型

这是 autoharness 和一些只负责后台维护 skill 的系统的区别。

它不仅维护 skill，还会在会话开始时生成索引，让模型明确知道自己的库存在。

### 5. 它不需要常驻 daemon

autoharness 通过 Hook 和会话事件工作，不需要一直运行一个后台服务。

---

# 致谢

## 原文片段

> [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)——研究它的自动 skill 创建和记忆 consolidation · consolidation（合并整理）设计，帮助 autoharness 形成了基于遵循情况、无需 daemon · daemon（后台常驻服务）的方案。  
>
> [AI Coding Tools (Tigerless Labs Workflow 2026)](https://www.youtube.com/watch?v=TM6tGpug1Hc)——AI Insider 频道制作的第三方演示；并非本项目制作，也未经本项目审核。  
>
> 由 Tigerless Labs 构建。

### 补充

这里说明了项目参考的设计来源：

- `hermes-agent`：参考自动创建 skill 和记忆合并设计；
- AI Insider 视频：第三方演示，不代表项目官方内容；
- 项目作者：Tigerless Labs。

---

# 许可证

## 原文片段

> [MIT](LICENSE)

### 补充

项目使用 MIT License · MIT License（MIT 许可证）。

通常意味着：

- 可以阅读和使用代码；
- 可以修改；
- 可以再分发；
- 可以用于商业项目；

但需要保留原许可证和版权声明。

具体权利和条件应以项目中的 [`LICENSE`](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\repo2-中文\LICENSE) 文件为准。

---

# README 第一阶段总结

我们已经完整看完 README：

```text
项目定位
    ↓
安装、更新和卸载
    ↓
配置
    ↓
工作方式
    ↓
演示：观察它学习
    ↓
保护机制、项目对比、致谢和许可证
```

README 给出的整体模型是：

```text
真实工作
  → 捕获会话
  → 反思经验
  → 生成提案
  → 验证并写入 skill
  → 建立索引
  → 观察使用情况
  → 合并、毕业或归档
```

这意味着 README 阶段现在已经完成。下一步可以把本阶段所有“原文片段 + 对应补充”一次性整理进：

[`学习记录/01-README-项目总览.md`](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\学习记录\01-README-项目总览.md)

---

已完成，文件已写入：

[学习记录/01-README-项目总览.md](C:\Users\dummy\PycharmProjects\agent-\自己项目\autoharness\学习记录\01-README-项目总览.md)

内容包括：

- 我们这阶段实际看过的 README 原文片段；
- 每段紧跟对应补充；
- 英文术语后的中文释义；
- 安装、配置、工作方式、演示、对比和许可证；
- 第一阶段完整流程总结。

原项目文件没有修改。
