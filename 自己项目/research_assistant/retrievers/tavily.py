import os

from langchain_tavily import TavilySearch


os.environ["TAVILY_API_KEY"] = os.environ.get("TAVILY_API_KEY", "")


def create_tavily_search_tool(max_results: int = 5) -> TavilySearch:
    return TavilySearch(
        max_results=max_results,
        topic="general",
    )
