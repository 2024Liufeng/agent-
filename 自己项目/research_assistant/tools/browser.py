import asyncio
import json
import logging
from pathlib import Path

from langchain_core.tools import tool

from tools.database import save_research_sources


BROWSER_PYTHON = str(
    Path.home()
    / "miniconda3"
    / "envs"
    / "stage2_browser"
    / "python.exe"
)
PROJECT_ROOT = Path(__file__).parents[1]
logger = logging.getLogger(__name__)


async def _extract_urls_content(
    urls: list[str],
) -> list[dict]:
    """调用浏览器 worker，并发抓取一批网页正文。"""
    process = await asyncio.create_subprocess_exec(
        BROWSER_PYTHON,
        "-m",
        "scraper.browser_worker",
        *urls,
        cwd=str(PROJECT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=60,
        )
    except TimeoutError:
        # 超时后终止并回收仍在运行的浏览器 worker。
        process.kill()
        await process.wait()
        raise

    # 子进程失败时先转成异常，之后再由工具错误中间件处理。
    if process.returncode != 0:
        raise RuntimeError(
            stderr.decode(
                "utf-8",
                errors="replace",
            )
        )

    # worker 输出的是 JSON 数组，将它还原为 list[dict]。
    return json.loads(
        stdout.decode("utf-8")
    )


class BrowserManager:
    def __init__(self, researcher):
        # researcher 是 DSResearcher 实例的引用，
        # 因此这里可以访问它的 visited_urls 和 research_sources。
        self.researcher = researcher

    async def browse_urls(
        self,
        urls: list[str],
    ) -> list[dict]:
        # 先删除同一批中的重复 URL，并保留首次出现的顺序。
        unique_urls = list(dict.fromkeys(urls))

        # 再排除本次研究中以前已经成功抓取过的 URL。
        new_urls = [
            url
            for url in unique_urls
            if url not in self.researcher.visited_urls
        ]

        if not new_urls:
            return []

        # 内部子进程函数把去重后的 URL 交给并发 worker。
        scraped_content = await _extract_urls_content(
            new_urls
        )

        # 只有成功返回的来源才标记为已访问；
        # 抓取异常时不会执行到这里，因此仍然允许工具重试。
        for source in scraped_content:
            self.researcher.visited_urls.add(
                source["url"]
            )

        # 与 GPT Researcher 相同，把抓取结果保存在 researcher。
        self.researcher.research_sources.extend(
            scraped_content
        )

        try:
            # 内存保存完成后，再把同一批资料持久化到 PostgreSQL。
            await save_research_sources(
                scraped_content
            )
        except Exception as error:
            # 数据库暂时不可用时保留已经成功抓取的资料，
            # 本次研究仍然可以继续生成报告。
            logger.warning(
                "研究资料保存到 PostgreSQL 失败：%s",
                error,
            )

        return scraped_content


def create_browser_tool(
    browser_manager: BrowserManager,
):
    # 每调用一次工厂，就创建一个绑定指定 BrowserManager 的工具。
    @tool
    async def browse_urls_tool(
        urls: list[str],
    ) -> list[dict]:
        """并发抓取 lookup_cached_sources 返回的 missing_urls。
        不要传入缓存已经命中的 URL。
        保存抓取到的完整正文，并返回来源摘要。
        """
        scraped_content = await browser_manager.browse_urls(
            urls
        )

        # 完整正文已经保存在 researcher.research_sources；
        # ToolMessage 只返回模型判断下一步所需的少量信息。
        return [
            {
                "url": source["url"],
                "title": source["title"],
                "content_length": len(
                    source["raw_content"]
                ),
            }
            for source in scraped_content
        ]

    return browse_urls_tool
