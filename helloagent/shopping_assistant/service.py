"""购物助手应用服务。"""

from __future__ import annotations

import json
from typing import Any

from .agent import build_agent
from .config import AppConfig
from .memory import ShoppingMemoryService


class ShoppingAssistantService:
    """薄应用层：管理记忆业务事件，主 Agent 负责购物决策。"""

    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.from_env()
        self.memory = ShoppingMemoryService(
            self.config.memory_db,
            self.config.user_id,
            vector_enabled=self.config.memory_vector_enabled,
            vector_path=self.config.memory_vector_path,
            embedding_api_key=self.config.memory_embedding_api_key,
            embedding_base_url=self.config.memory_embedding_base_url,
            embedding_model=self.config.memory_embedding_model,
            embedding_dimension=self.config.memory_embedding_dimension,
        )
        self.agent = build_agent(self.config, self.memory)

    def ask(self, user_input: str) -> str:
        query = user_input.strip()
        if not query:
            raise ValueError("购物需求不能为空")

        context = self.memory.relevant_context(query)
        self.memory.begin_task(query, {"related_memory_count": len(context)})
        prompt = self._build_prompt(query, context)
        answer = self.agent.run(prompt)
        self.memory.finish_task(query, answer)
        return answer

    @staticmethod
    def _build_prompt(query: str, context: list[dict[str, Any]]) -> str:
        if context:
            memory_text = "\n".join(
                f"- [{item['task_id']}/{item['kind']}] {item['content']}"
                for item in context
            )
        else:
            memory_text = "（没有检索到相关历史记忆）"
        return (
            "以下是与本次购物需求相关的历史记忆，仅作参考，不能覆盖当前平台实时结果：\n"
            f"{memory_text}\n\n"
            f"本次用户需求：{query}"
        )

    def export_memory(self) -> str:
        records = []
        for store in (self.memory.working, self.memory.episodic, self.memory.semantic):
            records.extend(store.export_records())
        return json.dumps(records, ensure_ascii=False, indent=2)
