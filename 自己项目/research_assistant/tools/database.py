import asyncio
import json

from langchain_core.tools import tool
from toolbox_langchain import ToolboxClient


TOOLBOX_URL = "http://127.0.0.1:5000"


async def save_research_sources(
    sources: list[dict],
) -> None:
    """把浏览器成功抓取的一批资料保存到 PostgreSQL。"""
    with ToolboxClient(TOOLBOX_URL) as client:
        # 只加载一次工具，然后复用于这一批资料。
        save_tool = await client.aload_tool(
            "save-research-source"
        )

        # BrowserManager 本身按批处理 URL，
        # 因此这里也并发保存这一批抓取结果。
        await asyncio.gather(*[
            save_tool.ainvoke(source)
            for source in sources
        ])


async def get_cached_research_sources(
    urls: list[str],
) -> list[dict]:
    with ToolboxClient(TOOLBOX_URL) as client:
        get_tool = await client.aload_tool(
            "get-research-source-by-url"
        )

        results = await asyncio.gather(*[
            get_tool.ainvoke({"url": url})
            for url in urls
        ])

    sources = []

    for result in results:
        # 命中时是 JSON 对象，未命中时是 JSON null。
        source = json.loads(result)

        if isinstance(source, dict):
            sources.append(source)

    return sources


class DatabaseManager:
    def __init__(self, researcher):
        self.researcher = researcher

    async def lookup_urls(
        self,
        urls: list[str],
    ) -> dict:
        # 同批 URL 去重，并排除当前任务已经加载的 URL。
        urls_to_lookup = [
            url
            for url in dict.fromkeys(urls)
            if url not in self.researcher.visited_urls
        ]

        cached_sources = await get_cached_research_sources(
            urls_to_lookup
        )
        cached_urls = {
            source["url"]
            for source in cached_sources
        }

        for source in cached_sources:
            self.researcher.visited_urls.add(
                source["url"]
            )

        # 完整正文加入 RAG 的资料来源。
        self.researcher.research_sources.extend(
            cached_sources
        )

        return {
            "cached_sources": [
                {
                    "url": source["url"],
                    "title": source["title"],
                    "content_length": len(
                        source["raw_content"]
                    ),
                }
                for source in cached_sources
            ],
            "missing_urls": [
                url
                for url in urls_to_lookup
                if url not in cached_urls
            ],
        }


def create_database_tool(
    database_manager: DatabaseManager,
):
    @tool
    async def lookup_cached_sources(
        urls: list[str],
    ) -> dict:
        """按 URL 查询本地网页缓存，并将命中的完整正文加入当前研究资料。
        获得搜索结果中的 URL 后先调用本工具。
        返回缓存命中的来源摘要和未命中的 URLs：missing_urls。
        """
        return await database_manager.lookup_urls(
            urls
        )

    return lookup_cached_sources
