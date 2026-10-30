import asyncio
import json
import sys

from bs4 import BeautifulSoup
from playwright.async_api import Browser, Page, async_playwright

from scraper.utils import clean_soup, extract_title, get_text_from_soup


async def extract_url_content(
    browser: Browser,
    url: str,
) -> dict:
    # page 先设为 None，避免浏览器连 Page 都没创建成功时，
    # finally 中访问不存在的变量。
    page: Page | None = None

    try:
        # 同一个 Browser 可以创建多个 Page；
        # 每个 URL 都有自己的 Page，从而实现并发。
        page = await browser.new_page()

        # 本地 Playwright 打开网页，不使用 AgentQL 查询。
        await page.goto(url)

        # page.content() 获取 JavaScript 渲染后的 HTML。
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        # 复用 GPT Researcher 的 HTML 清洗流程。
        title = extract_title(soup)
        cleaned_soup = clean_soup(soup)
        raw_content = get_text_from_soup(cleaned_soup)

        return {
            "url": url,
            "raw_content": raw_content,
            "title": title,
        }
    except Exception as error:
        # 单个 URL 失败时返回 raw_content=None，
        # 不让异常中断同一批中的其他 URL。
        print(
            f"Error processing {url}: {error}",
            file=sys.stderr,
        )

        return {
            "url": url,
            "raw_content": None,
            "title": "",
        }
    finally:
        # 只有成功创建 Page 后才需要关闭。
        if page is not None:
            await page.close()


async def extract_urls_content(
    urls: list[str],
) -> list[dict]:
    # async with 自动启动和停止 Playwright 驱动。
    async with async_playwright() as playwright:
        # 所有 URL 共用一个本地 Chromium Browser。
        browser = await playwright.chromium.launch(
            headless=True,
        )

        try:
            # 为每个 URL 创建一个协程；asyncio.gather() 让它们并发执行，
            # 并按照 urls 的原顺序返回结果。
            results = await asyncio.gather(
                *(
                    extract_url_content(browser, url)
                    for url in urls
                )
            )

            # 只把成功取得正文的来源返回给 BrowserManager。
            return [
                result
                for result in results
                if result["raw_content"] is not None
            ]
        finally:
            # 所有 Page 完成后，再关闭共享 Browser。
            await browser.close()


async def main() -> None:
    if len(sys.argv) < 2:
        print(
            json.dumps(
                {"error": "missing urls"},
                ensure_ascii=False,
            )
        )
        return

    # sys.argv[0] 是 browser_worker.py；后面的参数都是等待抓取的 URL。
    urls = sys.argv[1:]
    result = await extract_urls_content(urls)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
