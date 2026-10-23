"""真实 Tavily 商品资料搜索，不作为实时电商报价来源。"""

from typing import Any

import httpx
from hello_agents.tools import Tool, ToolParameter, ToolResponse


class TavilySearchTool(Tool):
    def __init__(self, settings):
        super().__init__(
            "product_search",
            "通过 Tavily 搜索真实商品资料，不作为最终电商报价",
        )
        self.settings = settings

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query", type="string",
                description="商品型号、预算、用途或搜索关键词",
            ),
            ToolParameter(
                name="max_results", type="integer",
                description="最多返回多少条结果", required=False, default=5,
            ),
        ]

    def run(self, parameters: dict[str, Any]) -> ToolResponse:
        query = str(parameters.get("query", "")).strip()
        if not query:
            return ToolResponse.error("INVALID_PARAM", "搜索词不能为空")

        # 主 Agent 可能刚刚用文件工具把 Key 写进 .env，
        # 这里重新读取一次，避免必须重启后端才能使用。
        try:
            self.settings.reload()
        except Exception:
            pass  # 读取失败时沿用当前内存配置

        if not self.settings.tavily_api_key:
            return ToolResponse.error(
                "MISSING_API_KEY", "Tavily API Key 未配置"
            )

        try:
            limit = max(1, min(int(parameters.get("max_results", 5)), 10))
        except (ValueError, TypeError):
            return ToolResponse.error(
                "INVALID_PARAM", "max_results 必须是整数"
            )

        try:
            response = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.settings.tavily_api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": limit,
                    "include_answer": False,
                },
                timeout=30,
            )

            if response.status_code in (429, 432):
                return ToolResponse.error(
                    "QUOTA_EXCEEDED",
                    f"Tavily 请求受限（HTTP {response.status_code}），请检查额度或速率限制",
                )
            if response.status_code in (401, 403):
                return ToolResponse.error(
                    "AUTH_ERROR", "Tavily API 认证或权限失败"
                )
            if response.status_code >= 400:
                return ToolResponse.error(
                    "API_ERROR",
                    f"Tavily 返回 HTTP {response.status_code}",
                )

            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                return ToolResponse.error(
                    "INVALID_RESPONSE", "Tavily 返回格式无效"
                )
            results = [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                }
                for item in data["results"]
                if isinstance(item, dict)
            ]
            return ToolResponse.success(
                f"Tavily 返回 {len(results)} 条真实搜索结果",
                data={"query": query, "results": results},
            )
        except httpx.RequestError as exc:
            return ToolResponse.error(
                "NETWORK_ERROR",
                f"Tavily 网络请求失败：{type(exc).__name__}",
            )
        except (ValueError, TypeError):
            return ToolResponse.error(
                "INVALID_RESPONSE", "Tavily 返回格式无效"
            )
