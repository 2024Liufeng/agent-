from langchain_core.tools import BaseTool

from retrievers.tavily import create_tavily_search_tool


def create_search_tool(
    retriever: str = "tavily",
    max_results: int = 5,
) -> BaseTool:
    if retriever == "tavily":
        return create_tavily_search_tool(
            max_results=max_results,
        )

    raise ValueError(f"不支持的搜索引擎：{retriever}")
