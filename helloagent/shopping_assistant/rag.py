"""商品知识库 RAG 的应用层装配。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from hello_agents.retrieval import RAGStore
from hello_agents.tools import RAGTool

from .config import AppConfig


class ProductKnowledgeBase:
    """加载本地商品知识文档，并暴露 HelloAgents 原生 RAGTool。

    第一版使用 HelloAgents 自带的 SQLite + BM25 检索，不额外依赖向量数据库。
    文档是可版本化的：文件内容变化后会以新的 mtime 版本重新导入，旧版本仍可按
    chunk_id 回读，但不会参与当前检索。
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.store = RAGStore(str(config.rag_db))
        self.sync()

    def sync(self) -> int:
        directory = self.config.rag_knowledge_dir
        directory.mkdir(parents=True, exist_ok=True)
        imported = 0
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                continue
            relative_source = path.relative_to(directory).as_posix()
            self.store.add_document(
                text=text,
                source=f"product-knowledge/{relative_source}",
                version=str(path.stat().st_mtime_ns),
            )
            imported += 1
        return imported

    def ingest_web_document(self, content: str, source: str) -> str | None:
        """把搜索 API 返回的网页正文写入知识库，返回文档标识。"""
        content = str(content or "").strip()
        source = str(source or "").strip()
        if len(content) < 80 or not source.startswith(("http://", "https://")):
            return None
        # 控制单个网页的入库大小，避免广告、导航和超长页面污染上下文。
        content = content[:50000]
        version = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return self.store.add_document(
            text=content,
            source=source,
            version=version,
        )

    @property
    def tool(self) -> RAGTool:
        return RAGTool(self.store)
