"""购物助手的薄记忆业务入口。

当前 hello_agents 1.0.1 的 MemoryStore 以 user_id + task_id 绑定范围，
因此这里用三个稳定的内部 task_id 表示 working、episodic、semantic 三类记忆。
用户不需要看到这些内部标识。

MemoryStore 默认是关键词检索；启用 vector_enabled 后，三个作用域改用
SemanticMemorySearch 的关键词 + 向量混合检索。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hello_agents.memory import MemoryStore
from hello_agents.tools.builtin.memory_tool import MemoryTool


class _AutoSyncMemorySearch:
    """在 MemoryTool 写入后，下一次查询前同步向量索引。"""

    def __init__(self, backend):
        self.backend = backend

    def search(self, query: str = "", limit: int = 10):
        self.backend.sync()
        return self.backend.search(query, limit)


class ShoppingMemoryService:
    """在明确的购物业务事件上读写三类记忆。"""

    def __init__(
        self,
        db_path: Path,
        user_id: str,
        *,
        vector_enabled: bool = False,
        vector_path: Path | None = None,
        embedding_api_key: str | None = None,
        embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_model: str = "text-embedding-v3",
        embedding_dimension: int = 1024,
    ):
        self.user_id = user_id
        self.working = MemoryStore(str(db_path), user_id, "working")
        self.episodic = MemoryStore(str(db_path), user_id, "episodic")
        self.semantic = MemoryStore(str(db_path), user_id, "semantic")
        self._search_backends: dict[str, Any] = {}
        if vector_enabled:
            if not embedding_api_key:
                raise ValueError(
                    "MEMORY_VECTOR_ENABLED=true 时必须配置 DASHSCOPE_API_KEY"
                )
            self._search_backends = self._build_vector_backends(
                vector_path or db_path.parent / "memory_vectors",
                embedding_api_key,
                embedding_base_url,
                embedding_model,
                embedding_dimension,
            )

    def _build_vector_backends(
        self,
        vector_path: Path,
        api_key: str,
        base_url: str,
        model: str,
        dimension: int,
    ) -> dict[str, Any]:
        try:
            from openai import OpenAI
            from hello_agents.memory import SemanticMemorySearch
            from hello_agents.retrieval import OpenAIEmbeddingProvider
        except ImportError as exc:
            raise RuntimeError(
                "向量记忆需要安装 hello-agents[qdrant]"
            ) from exc

        vector_path.mkdir(parents=True, exist_ok=True)
        client = OpenAI(api_key=api_key, base_url=base_url)
        embedding = OpenAIEmbeddingProvider(
            client,
            model=model,
            dimension=dimension,
            request_dimensions=True,
            model_id=f"{base_url}:{model}:{dimension}",
        )
        stores = {
            "working": self.working,
            "episodic": self.episodic,
            "semantic": self.semantic,
        }
        backends = {}
        for task_id, store in stores.items():
            backend = SemanticMemorySearch(
                store,
                embedding,
                hybrid=True,
                path=str(vector_path / task_id),
                collection=f"shopping_memory_{task_id}",
            )
            backend.sync()
            backends[task_id] = _AutoSyncMemorySearch(backend)
        return backends

    @property
    def semantic_tool(self) -> MemoryTool:
        """给 Agent 暴露显式的记住、回顾、修订、撤回能力。"""
        return MemoryTool(
            self.semantic,
            search_backend=self._search_backends.get("semantic"),
        )

    def relevant_context(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        records = []
        for task_id, store in (
            ("semantic", self.semantic),
            ("episodic", self.episodic),
            ("working", self.working),
        ):
            backend = self._search_backends.get(task_id, store)
            records.extend(record.to_dict() for record in backend.search(query, limit))
        return records[:limit]

    def begin_task(self, query: str, context: dict[str, Any] | None = None) -> None:
        payload = {"query": query, "context": context or {}}
        self.working.add(
            content=f"当前购物任务：{payload}",
            source="user_request",
            kind="fact",
        )
        self.prune_working()

    def finish_task(self, query: str, answer: str) -> None:
        self.episodic.add(
            content=f"购物事件：用户需求={query}；助手结果={answer[:4000]}",
            source="shopping_task_completed",
            kind="episode",
        )

    def save_explicit_preference(self, content: str, source: str) -> None:
        self.semantic.add(content=content, source=source, kind="preference")

    def prune_working(self, max_records: int = 20, ttl_hours: int = 24) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
        records = self.working.search("", 100)
        for record in records[max_records:]:
            self.working.retract(record.memory_id)
        for record in records[:max_records]:
            try:
                updated = datetime.fromisoformat(record.updated_at)
            except ValueError:
                continue
            if updated < cutoff:
                self.working.retract(record.memory_id)
