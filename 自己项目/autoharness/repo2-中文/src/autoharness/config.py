"""每个旋钮的单一主页 + 指向两个合约数据文件的指针（架构§config 单点）。

校准值（节奏/成熟阈值/容量）是占位符；经验校准
生活在实验中/。测试仅断言关系（两层都存在，>0），从不绝对
价值观。可通过 AUTOHARNESS_* env 覆盖 — 用于 e2e Runbook 缩小旋钮（因此毕业/
短时间内发生容量争用）；默认值回退到占位符。"""
import os
import warnings
from pathlib import Path

from autoharness.lib import layer


def _int_env(name, default):
    try:
        return int(os.environ[name])
    except KeyError:
        return default
    except ValueError:
        warnings.warn(f"{name}={os.environ[name]!r} is not a valid integer; using default {default}", stacklevel=2)
        return default


# 触发节奏，计入活动量（主会话工具调用，方向 H），而不是轮次。
# 用分子重新校准：旧的回合制 10 接近 30-50 个工具调用，而站立
# 裁决是错误稀疏（沉淀是维护，SessionEnd 冲洗尾部）。
REFLECT_EVERY_N = _int_env("AUTOHARNESS_REFLECT_EVERY_N", 50)  # 窗口本身是水印分隔的（捕获）
CONSOLIDATE_EVERY_N = _int_env("AUTOHARNESS_CONSOLIDATE_EVERY_N", 250)  # 马尾辫：占位符，在实验中校准/； curator（内容级合并）节拍，与 REFLECT_EVERY_N 相同的量程并且比它更稀疏

# 原始捕获字节上限（马尾辫：占位符，在实验/中校准）：每个转录记录，
# 和每个切换窗口（保留尾部）- 远离子上下文的绑定工具转储/base64。
CAPTURE_MAX_RECORD_BYTES = 4_000
CAPTURE_MAX_WINDOW_BYTES = 200_000
DIGEST_EXCHANGES = _int_env("AUTOHARNESS_DIGEST_EXCHANGES", 20)  # 先验上下文摘要：窗口前的交换
DIGEST_MAX_RECORD_CHARS = 200
DIGEST_MAX_BYTES = 20_000

STAGE_MAX_BODY_BYTES = 100_000  # 马尾辫：占位符，SKILL.md 身体帽；有关 stage_skill 参数的即时反馈
# 海拔门：SKILL.md 正文通常必须阅读，而不是文字记录。确定性代理
# 反射器（循环中唯一的法学硕士）实际上提炼-非空白的身体线条（ex-frontmatter）
# 在此拒绝创建/更新；详细信息属于参考文献/。马尾辫：粗略代理，在实验/中校准。
SKILL_BODY_MAX_LINES = _int_env("AUTOHARNESS_SKILL_BODY_MAX_LINES", 25)
# 描述是触发器：主机预加载名称+描述并匹配其上的回忆，因此是一项技能
# 在这里生或死。 Cap = Anthropic 记录的 1024 个字符主机限制（超过该限制主机将截断）。
SKILL_DESC_MAX_CHARS = _int_env("AUTOHARNESS_SKILL_DESC_MAX_CHARS", 1024)
# 自注入回忆索引（SessionStartadditionalContext）：每行描述截断，
# 反映了 Hermes 的 0 级索引规则——索引是一个扫描表面，而不是完整的触发文本。
INDEX_DESC_MAX_CHARS = _int_env("AUTOHARNESS_INDEX_DESC_MAX_CHARS", 60)
# 自注入关闭开关：索引停止发出，其他一切（生命周期传递，
# 使用/查看计数器，上次运行摘要）保持不变。需要，因为唯一的其他运行方式
# 没有索引就是在没有插件的情况下运行——这也删除了测量索引的计数器
# 结果。对于那些不愿意在每次会话中都花费上下文的人来说，这也是一个合法的操作员旋钮。
def _bool_env(name, default):
    val = _int_env(name, int(default))
    if val not in (0, 1):
        warnings.warn(
            f"{name}={val} should be 0 or 1; using default {int(default)}",
            stacklevel=2,
        )
        return bool(default)
    return bool(val)


INDEX_SUSPENDED = _bool_env("AUTOHARNESS_INDEX_SUSPENDED", False)
DISABLE_GLOBAL = _bool_env("AUTOHARNESS_DISABLE_GLOBAL", False)


def active_layers():
    """此部署可以检查和管理的层。"""
    return (layer.PROJECT,) if DISABLE_GLOBAL else layer.LAYERS


# 文件夹技能子文件上限（马尾辫：占位符，如 STAGE_MAX_BODY_BYTES，在实验/中校准）
STAGE_MAX_FILES = 8
STAGE_MAX_FILE_BYTES = 64_000
STAGE_MAX_FILES_TOTAL_BYTES = 256_000

# 成熟度阈值（从试用期毕业的分母门）/容量上限，每层设置，独立可调。 global 的爆炸半径更大 -> 更保守（容量更小）。
MATURITY_THRESHOLD = {layer.GLOBAL: _int_env("AUTOHARNESS_MATURITY_GLOBAL", 300),
                      layer.PROJECT: _int_env("AUTOHARNESS_MATURITY_PROJECT", 100)}
CAPACITY = {layer.GLOBAL: _int_env("AUTOHARNESS_CAPACITY_GLOBAL", 20),
            layer.PROJECT: _int_env("AUTOHARNESS_CAPACITY_PROJECT", 50)}
# 毕业审核暂停门（C方向）：当召回面已知损坏时，归档
# 对于零使用埋葬表面的失败 - 翻转以停止审查，容量争夺不受影响。
GRADUATION_REVIEW_SUSPENDED = _bool_env("AUTOHARNESS_GRADUATION_SUSPENDED", False)
SNAPSHOT_KEEP = _int_env("AUTOHARNESS_SNAPSHOT_KEEP", 5)  # curator 每层预运行库快照（镜像 Hermes）

# 运行帐户通知 (lib/notify)，选择加入：SessionStart 摘要是一个会话迟到且
# 带有计数，而不是名称。 “桌面”=本机通知； NOTIFY_CMD = argv 馈送运行记录
# 在标准输入上。失败打开，队列清空后触发；超时（整秒，每个通道，
# 楼层 1) 限制了通知程序可以保留排水管的时间——交互式通知程序在 Stop 内运行。
NOTIFY = os.environ.get("AUTOHARNESS_NOTIFY", "").strip().lower()
NOTIFY_CMD = os.environ.get("AUTOHARNESS_NOTIFY_CMD", "")
NOTIFY_TIMEOUT_S = max(1, _int_env("AUTOHARNESS_NOTIFY_TIMEOUT_S", 5))

_LIB = Path(__file__).parent / "lib"
REDACTION_RULES = _LIB / "redaction_rules.toml"  # 秘密/PII 规则集，CAP 出口 + LED 单一来源
FORMAT_SPEC = _LIB / "format_spec.md"            # #416 用于创作 + lint 的单一来源

CHILD_SESSION_ENV = "AUTOHARNESS_CHILD_SESSION"  # 递归保护信号：仅由spawn 设置，由CAP hooks 读取（单一源）。必须是 autoharness 拥有的：主机在每个钩子子进程上设置 CLAUDE_CODE_CHILD_SESSION，因此重用它会控制每个顶级回合。

# 反射载体（G方向）：“分叉”恢复+分叉刚刚完成的会话 — 相同型号，
# 父母的温暖前缀缓存、完整转录本重播、无物化窗口。保持“捆绑”
# （窗口+通过标准输入摘要到注册的子代理）直到分叉缓存命中峰值通过。
REFLECTOR_CARRIER = os.environ.get("AUTOHARNESS_CARRIER", "bundle")

REFLECTOR_AGENT = "autoharness:reflector"  # 生成的 --agent 参考（插件命名空间，第 0 阶段解析待实时测试）
CURATOR_AGENT = "autoharness:curator"      # 定期合并过程的 --agent 参考（与反射器相同的生成链）
CLAUDE_BIN = "claude"                       # 用于生成的子会话可执行文件；路径解析，在测试中可覆盖
RUN_ID_ENV = "AUTOHARNESS_RUN_ID"           # spawn 通过 env 将意图队列 run_id 注入到子会话中（由 stage_skill 读取）
# 从实时用户会话（/learn，或单独运行的模型）中暂存的意图队列。
# spawn 将运行 ID 注入到它启动的每个子进程中，并在子进程退出时耗尽运行的进程；一个
# 用户自己的会话两者都没有，因此在此之前存在 stage_skill 以“不安全的运行 ID”拒绝
# 而且传送的学习技能永远无法落地。主会话的 Stop 会耗尽此队列。
INTERACTIVE_RUN_ID = "interactive"
PROJECT_ROOT_ENV = "AUTOHARNESS_PROJECT_ROOT"  # 相同：存储库根（队列被持久化的地方）
