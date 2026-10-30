---
name: learn
description: "Use when /learn, save, remember, or distill."
category: general
---
# Learn：把本次会话提炼进 skill 库

回顾到目前为止的对话，distill 值得保留的内容（remember 这些经验）——通过标准提案链完成，绝不直接写文件。

1. 识别类别级、可复用的经验：被纠正的做法、非平凡技术、持久的用户偏好。跳过一次性叙述和环境专属故障。
2. 先比较：读取注入的 skill 索引；如果已有 skill 覆盖该主题，优先使用 `patch`/`update`，不要创建近似副本。
3. 协调新旧规则：如果新经验取代了旧规则，搜索受管理 skill 树中相互矛盾的陈述，并提交更新，让新版本在所有地方生效。
4. 只通过 `stage_skill` 提交每个变化，每条经验一个 intent，并提供 `reason` 以及来自本次会话的逐字 `evidence` 引用。确定性的 Promoter 会校验并落地；被拒绝的内容会在下次会话开始时报告。

如果没有经验达到标准，就说明这一点，不提交任何内容。
