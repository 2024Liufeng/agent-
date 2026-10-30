"""PDF 知识库：文档解析、分块、向量入库和相关片段检索。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from threading import RLock

logger = logging.getLogger(__name__)
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / ".runtime" / "knowledge_bases"


class KnowledgeBaseError(ValueError):
    """可直接向用户说明的配置或文档问题。"""


class KnowledgeBaseService:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or os.getenv("KNOWLEDGE_BASE_DIR") or DEFAULT_ROOT).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._client = None
        self._embedder = None
        self._embedder_signature = None

    def _path(self, knowledge_base_id: str) -> Path:
        # ID 由服务生成，拒绝将用户传入的任意路径作为知识库目录。
        if not re.fullmatch(r"kb_[0-9a-f]{32}", knowledge_base_id):
            raise KnowledgeBaseError("知识库 ID 无效")
        return self.root / knowledge_base_id

    def _save(self, record: dict) -> None:
        path = self._path(record["id"]) / "manifest.json"
        with self._lock:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)

    def list_knowledge_bases(self) -> list[dict]:
        records = []
        for path in self.root.glob("kb_*/manifest.json"):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                logger.warning("stage=knowledge_base_list status=unreadable file=%s", path.name)
        return sorted(records, key=lambda item: item.get("created_at", 0), reverse=True)

    def get(self, knowledge_base_id: str, *, ready: bool = False) -> dict:
        path = self._path(knowledge_base_id) / "manifest.json"
        if not path.is_file():
            raise KnowledgeBaseError("知识库不存在")
        record = json.loads(path.read_text(encoding="utf-8"))
        if ready and record["status"] != "ready":
            raise KnowledgeBaseError("知识库尚未成功入库，请重新导入资料")
        return record

    def document_path(self, knowledge_base_id: str) -> Path:
        self.get(knowledge_base_id)
        return self._path(knowledge_base_id) / "document.pdf"

    def _embedding_config(self) -> dict:
        model_type = os.getenv("EMBED_MODEL_TYPE", "dashscope").strip()
        if model_type not in {"dashscope", "local"}:
            raise KnowledgeBaseError("EMBED_MODEL_TYPE 请配置为 dashscope 或 local")
        config = {
            "type": model_type,
            "name": os.getenv("EMBED_MODEL_NAME") or (
                "text-embedding-v3" if model_type == "dashscope"
                else "sentence-transformers/all-MiniLM-L6-v2"
            ),
            "base_url": os.getenv("EMBED_BASE_URL", ""),
        }
        if model_type == "dashscope" and not (os.getenv("EMBED_API_KEY") or os.getenv("DASHSCOPE_API_KEY")):
            raise KnowledgeBaseError("请先配置 EMBED_API_KEY；聊天模型的密钥不会自动用于 Embedding")
        return config

    def _signature(self) -> str:
        # 模型变化后不能用新向量查询旧索引；签名不包含密钥。
        config = json.dumps(self._embedding_config(), sort_keys=True)
        return hashlib.sha256(config.encode()).hexdigest()

    def _get_embedder(self):
        with self._lock:
            signature = self._signature()
            if self._embedder is None or self._embedder_signature != signature:
                from hello_agents.memory.embedding import create_embedding_model
                config = self._embedding_config()
                kwargs = {"model_name": config["name"]}
                if config["type"] == "dashscope":
                    kwargs.update(
                        api_key=os.getenv("EMBED_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
                        base_url=config["base_url"] or None,
                    )
                # 使用明确配置的模型；不静默回退到另一种模型或零向量。
                if config["type"] == "dashscope":
                    from services.embedding import ResearchDashScopeEmbedding
                    self._embedder = ResearchDashScopeEmbedding(**kwargs)
                else:
                    self._embedder = create_embedding_model(config["type"], **kwargs)
                self._embedder_signature = signature
                logger.info("stage=embedding_init status=ready model=%s", config["name"])
            return self._embedder

    def _vectors(self, texts: list[str]) -> list[list[float]]:
        import numpy as np
        vectors = np.asarray(self._get_embedder().encode(texts), dtype=float)
        if vectors.ndim == 1 and len(texts) == 1:
            vectors = vectors.reshape(1, -1)
        if (vectors.ndim != 2 or len(vectors) != len(texts)
                or vectors.shape[1] == 0 or not np.isfinite(vectors).all()
                or (np.linalg.norm(vectors, axis=1) == 0).any()):
            raise KnowledgeBaseError("Embedding 未返回有效向量，知识库未就绪")
        return vectors.tolist()

    def _get_client(self):
        with self._lock:
            if self._client is None:
                from qdrant_client import QdrantClient
                url = os.getenv("QDRANT_URL")
                self._client = (
                    QdrantClient(url=url, api_key=os.getenv("QDRANT_API_KEY"), timeout=30)
                    if url else QdrantClient(path=str(self.root / "vectors"))
                )
                logger.info("stage=vector_store status=ready mode=%s", "server" if url else "local")
            return self._client

    def import_pdf(self, filename: str, content: bytes) -> dict:
        from qdrant_client import models
        from hello_agents.memory.rag.pipeline import load_and_chunk_texts

        if not filename.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
            raise KnowledgeBaseError("请上传有效的 PDF 文件")
        knowledge_base_id = "kb_" + uuid.uuid4().hex
        directory = self._path(knowledge_base_id)
        directory.mkdir()
        record = {
            "id": knowledge_base_id, "name": Path(filename.replace("\\", "/")).name,
            "status": "indexing", "chunk_count": 0, "created_at": time.time(),
        }
        self._save(record)
        started = time.perf_counter()
        logger.info("stage=document_upload kb=%s status=received bytes=%d", knowledge_base_id, len(content))
        try:
            signature = self._signature()
            pdf_path = directory / "document.pdf"
            pdf_path.write_bytes(content)
            logger.info("stage=document_parse kb=%s status=started", knowledge_base_id)
            chunks = load_and_chunk_texts([str(pdf_path)], chunk_size=800, chunk_overlap=100,
                                         namespace=knowledge_base_id)
            if not chunks:
                raise KnowledgeBaseError("PDF 没有可提取的文本，首版暂不支持扫描件 OCR")
            logger.info("stage=document_chunk kb=%s status=completed chunks=%d", knowledge_base_id, len(chunks))
            points = []
            # 按批调用 Embedding，避免一次提交整本文档。
            for start in range(0, len(chunks), 32):
                batch = chunks[start:start + 32]
                vectors = self._vectors([chunk["content"] for chunk in batch])
                for chunk, vector in zip(batch, vectors):
                    metadata = chunk.get("metadata", {})
                    points.append(models.PointStruct(
                        id=str(uuid.UUID(chunk["id"])), vector=vector,
                        payload={
                            "namespace": knowledge_base_id, "content": chunk["content"],
                            "filename": record["name"], "chunk_id": chunk["id"],
                            "heading": metadata.get("heading_path"),
                            "start": metadata.get("start"), "end": metadata.get("end"),
                        },
                    ))
                logger.info("stage=embedding kb=%s status=progress count=%d total=%d",
                            knowledge_base_id, len(points), len(chunks))
            with self._lock:
                client = self._get_client()
                client.create_collection(knowledge_base_id, vectors_config=models.VectorParams(
                    size=len(points[0].vector), distance=models.Distance.COSINE))
                client.upsert(knowledge_base_id, points=points, wait=True)
                # 实际存储数量一致后才能对外宣告入库成功。
                count = client.count(knowledge_base_id, exact=True).count
                if count != len(points):
                    raise KnowledgeBaseError("向量存储不完整，请重新导入")
            record.update(status="ready", chunk_count=count, embedding_signature=signature)
            self._save(record)
            logger.info("stage=vector_index kb=%s status=ready chunks=%d elapsed=%.2fs",
                        knowledge_base_id, count, time.perf_counter() - started)
            return record
        except Exception:
            record.update(status="failed", error="文档入库失败，请检查配置和服务日志")
            self._save(record)
            logger.exception("stage=document_import kb=%s status=failed elapsed=%.2fs",
                             knowledge_base_id, time.perf_counter() - started)
            raise

    def search(self, knowledge_base_id: str, query: str, limit: int = 5) -> list[dict]:
        from qdrant_client import models
        record = self.get(knowledge_base_id, ready=True)
        if record.get("embedding_signature") != self._signature():
            raise KnowledgeBaseError("Embedding 配置已变化，请使用原配置或重新导入知识库")
        started = time.perf_counter()
        logger.info("stage=document_search kb=%s status=started", knowledge_base_id)
        try:
            vector = self._vectors([query])[0]
            with self._lock:
                hits = self._get_client().query_points(
                    collection_name=knowledge_base_id, query=vector, limit=limit,
                    query_filter=models.Filter(must=[models.FieldCondition(
                        key="namespace", match=models.MatchValue(value=knowledge_base_id))]),
                    score_threshold=0.2,
                ).points
            results = []
            for hit in hits:
                payload = hit.payload or {}
                if payload.get("namespace") != knowledge_base_id or not payload.get("content"):
                    continue
                results.append({**payload, "score": hit.score, "knowledge_base_id": knowledge_base_id})
            logger.info("stage=document_search kb=%s status=completed hits=%d elapsed=%.2fs",
                        knowledge_base_id, len(results), time.perf_counter() - started)
            return results
        except Exception:
            logger.exception("stage=document_search kb=%s status=failed", knowledge_base_id)
            raise

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None


knowledge_bases = KnowledgeBaseService()
