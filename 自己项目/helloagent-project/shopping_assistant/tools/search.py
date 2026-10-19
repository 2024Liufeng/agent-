"""商品发现工具。

搜索 API 只用于发现候选商品，不作为京东或淘宝的最终报价来源。
"""

from __future__ import annotations

import json
from typing import Any

import requests
from hello_agents.tools import Tool, ToolErrorCode, ToolParameter, ToolResponse

from ..config import AppConfig
from ..rag import ProductKnowledgeBase
from ..schemas import SearchCandidate


class ProductSearchTool(Tool):
    """通过 Tavily 兼容 API 发现候选商品。"""

    def __init__(
        self, config: AppConfig, knowledge_base: ProductKnowledgeBase | None = None
    ):
        super().__init__(
            "product_search",
            "搜索互联网中的商品资料，发现候选商品；不用于读取京东和淘宝最终报价。",
        )
        self.config = config
        self.knowledge_base = knowledge_base

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="商品类别、使用场景、预算或型号等搜索条件",
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="最多返回的候选数量",
                required=False,
                default=5,
            ),
        ]

    def run(self, parameters: dict[str, Any]) -> ToolResponse:
        query = str(parameters.get("query", "")).strip()
        if not query:
            return ToolResponse.error(ToolErrorCode.INVALID_PARAM, "query 不能为空")

        try:
            max_results = max(1, min(int(parameters.get("max_results", 5)), 10))
        except (TypeError, ValueError):
            return ToolResponse.error(
                ToolErrorCode.INVALID_PARAM, "max_results 必须是整数"
            )

        if self.config.search_provider.lower() != "tavily":
            return ToolResponse.error(
                ToolErrorCode.INVALID_PARAM,
                f"暂不支持搜索提供商: {self.config.search_provider}",
            )
        if not self.config.tavily_api_key:
            return ToolResponse.error(
                ToolErrorCode.API_ERROR,
                "未配置 TAVILY_API_KEY，无法执行商品发现搜索",
            )

        payload = {
            "api_key": self.config.tavily_api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            # 搜索结果用于发现候选商品，正文用于写入 RAG 知识库。
            "include_raw_content": True,
        }
        try:
            response = requests.post(
                self.config.tavily_endpoint,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            return ToolResponse.error(
                ToolErrorCode.NETWORK_ERROR, f"商品搜索请求失败: {exc}"
            )
        except (ValueError, json.JSONDecodeError) as exc:
            return ToolResponse.error(
                ToolErrorCode.INVALID_FORMAT, f"商品搜索返回格式无效: {exc}"
            )

        candidates = [
            SearchCandidate(
                title=str(item.get("title", "")).strip(),
                url=str(item.get("url", "")).strip(),
                snippet=str(item.get("content", "")).strip(),
                source="search_api",
            ).to_dict()
            for item in body.get("results", [])
            if item.get("title") and item.get("url")
        ]
        ingested_sources = []
        if self.knowledge_base is not None:
            for item in body.get("results", []):
                source = str(item.get("url", "")).strip()
                raw_content = str(item.get("raw_content", "")).strip()
                document_id = self.knowledge_base.ingest_web_document(
                    raw_content, source
                )
                if document_id:
                    ingested_sources.append(source)
        return ToolResponse.success(
            text=f"搜索到 {len(candidates)} 个候选商品或资料页面。",
            data={
                "query": query,
                "candidates": candidates,
                "rag_ingested_sources": ingested_sources,
            },
        )
