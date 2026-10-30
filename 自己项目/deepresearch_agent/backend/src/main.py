"""FastAPI entrypoint exposing the DeepResearchAgent via HTTP."""

from __future__ import annotations

import json
import asyncio
import logging
import sys
from typing import Any, Dict, Iterator, Optional

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from config import Configuration, SearchAPI
from agent import DeepResearchAgent
from services.knowledge_base import knowledge_bases, KnowledgeBaseError
from services.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class ResearchRequest(BaseModel):
    """Payload for triggering a research run."""

    topic: str = Field(..., min_length=1, max_length=2000, description="Research topic supplied by the user")
    knowledge_base_id: str | None = Field(default=None, description="可选的已就绪知识库")
    search_api: SearchAPI | None = Field(
        default=None,
        description="Override the default search backend configured via env",
    )


class ResearchResponse(BaseModel):
    """HTTP response containing the generated report and structured tasks."""

    report_markdown: str = Field(
        ..., description="Markdown-formatted research report including sections"
    )
    todo_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured TODO items with summaries and sources",
    )


def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    """Mask sensitive tokens while keeping leading and trailing characters."""
    if not value:
        return "unset"

    if len(value) <= visible * 2:
        return "*" * len(value)

    return f"{value[:visible]}...{value[-visible:]}"


def public_research_error(exc: Exception) -> str:
    if "429" in str(exc) or "rate limit" in str(exc).lower():
        return "上游模型限流（429），请稍后重试"
    return "研究执行失败，请检查服务日志"


def _build_config(payload: ResearchRequest) -> Configuration:
    if not payload.topic.strip():
        raise ValueError("研究主题不能为空")
    overrides: Dict[str, Any] = {}

    if payload.search_api is not None:
        overrides["search_api"] = payload.search_api

    return Configuration.from_env(overrides=overrides)


def create_app() -> FastAPI:
    app = FastAPI(title="HelloAgents Deep Researcher")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def log_startup_configuration() -> None:
        config = Configuration.from_env()

        if config.llm_provider == "ollama":
            base_url = config.sanitized_ollama_url()
        elif config.llm_provider == "lmstudio":
            base_url = config.lmstudio_base_url
        else:
            base_url = config.llm_base_url or "unset"

        logger.info(
            "DeepResearch configuration loaded: provider=%s model=%s base_url=%s search_api=%s "
            "max_loops=%s fetch_full_page=%s tool_calling=%s strip_thinking=%s api_key=%s",
            config.llm_provider,
            config.resolved_model() or "unset",
            base_url,
            (config.search_api.value if isinstance(config.search_api, SearchAPI) else config.search_api),
            config.max_web_research_loops,
            config.fetch_full_page,
            config.use_tool_calling,
            config.strip_thinking_tokens,
            "configured" if config.llm_api_key else "unset",
        )

    @app.get("/healthz")
    def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    @app.on_event("shutdown")
    def close_knowledge_bases() -> None:
        knowledge_bases.close()

    @app.get("/knowledge-bases")
    def list_knowledge_bases() -> dict:
        return {"items": knowledge_bases.list_knowledge_bases()}

    @app.post("/knowledge-bases")
    async def import_document(file: UploadFile) -> dict:
        # 解析和入库会调用模型，放到工作线程，避免阻塞其他研究的 SSE。
        try:
            content = await file.read(20 * 1024 * 1024 + 1)
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="PDF 请控制在 20 MB 以内")
            return await asyncio.to_thread(knowledge_bases.import_pdf, file.filename or "", content)
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("stage=document_api status=failed")
            raise HTTPException(status_code=503, detail="文档入库失败，请检查 Embedding 配置和服务日志") from exc
        finally:
            await file.close()

    @app.get("/knowledge-bases/{knowledge_base_id}/document")
    def original_document(knowledge_base_id: str):
        try:
            record = knowledge_bases.get(knowledge_base_id, ready=True)
            return FileResponse(knowledge_bases.document_path(knowledge_base_id),
                                media_type="application/pdf", filename=record["name"],
                                content_disposition_type="inline")
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/research", response_model=ResearchResponse)
    def run_research(payload: ResearchRequest) -> ResearchResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config, knowledge_base_id=payload.knowledge_base_id)
            result = agent.run(payload.topic)
        except ValueError as exc:  # Likely due to unsupported configuration
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive guardrail
            logger.exception("stage=research_api status=failed")
            raise HTTPException(status_code=503, detail=public_research_error(exc)) from exc

        # 同步接口与 SSE 使用同一套展示编号。
        todo_payload = [
            {**agent._serialize_task(item), "notices": item.notices}
            for item in result.todo_items
        ]

        return ResearchResponse(
            report_markdown=(result.report_markdown or result.running_summary or ""),
            todo_items=todo_payload,
        )

    @app.post("/research/stream")
    def stream_research(payload: ResearchRequest) -> StreamingResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config, knowledge_base_id=payload.knowledge_base_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        def event_iterator() -> Iterator[str]:
            try:
                for event in agent.run_stream(payload.topic):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:  # pragma: no cover - defensive guardrail
                logger.exception("Streaming research failed")
                error_payload = {"type": "error", "detail": public_research_error(exc)}
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    return app


app = create_app()


if __name__ == "__main__":
    import os

    import uvicorn

    # 端口从 .env 读取，默认 8001，避免与同机其他项目（购物助手用 8000）冲突。
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8001")),
        reload=True,
        log_level="info",
    )
