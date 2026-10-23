"""京东、淘宝、拼多多真实搜索页面工具；正文不截断，不伪造报价。"""

from typing import Any
from urllib.parse import quote

from hello_agents.tools import Tool, ToolParameter, ToolResponse

from backend.browser.browser_manager import BrowserBusyError, CAPTCHA_MARKERS

SEARCH_URLS = {
    "jd": "https://search.jd.com/Search?keyword={query}",
    "taobao": "https://s.taobao.com/search?q={query}",
    "pdd": "https://mobile.yangkeduo.com/search_result.html?search_key={query}",
}
LOGIN_REDIRECTS = (
    "passport.jd.com",
    "login.taobao.com",
    "login.m.taobao.com",
    "yangkeduo.com/login",
)


class PlatformSearchTool(Tool):
    def __init__(self, platform: str, browser):
        if platform not in SEARCH_URLS:
            raise ValueError(f"不支持的平台：{platform}")
        self.platform = platform
        self.browser = browser
        super().__init__(
            f"{platform}_product_search",
            f"读取 {platform} 真实商品搜索页面",
        )

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query", type="string",
                description="需要搜索的商品型号及规格",
            ),
        ]

    def run(self, parameters: dict[str, Any]) -> ToolResponse:
        query = str(parameters.get("query", "")).strip()
        if not query:
            return ToolResponse.error("INVALID_PARAM", "商品搜索词不能为空")

        url = SEARCH_URLS[self.platform].format(query=quote(query, safe=""))

        try:
            page = self.browser.read_page(url)
            final_url = page["url"]
            body = page["text"]
            if any(marker in final_url.lower() for marker in LOGIN_REDIRECTS):
                return ToolResponse.error(
                    "AUTH_REQUIRED", f"{self.platform} 跳转至登录页面"
                )

            if any(marker.lower() in body.lower() for marker in CAPTCHA_MARKERS):
                return ToolResponse.error(
                    "CAPTCHA_REQUIRED", f"{self.platform} 需要人工验证"
                )

            if not body.strip():
                return ToolResponse.error(
                    "EMPTY_PAGE", f"{self.platform} 未返回可读取的页面内容"
                )

            return ToolResponse.success(
                f"{self.platform} 页面读取成功，报价需要进一步核实",
                data={
                    "platform": self.platform,
                    "query": query,
                    "url": final_url,
                    "raw_page_text": body,  # 不主动截断，保留完整网页正文
                },
            )

        except BrowserBusyError as exc:
            return ToolResponse.error("BROWSER_BUSY", str(exc))
        except Exception as exc:
            return ToolResponse.error(
                "BROWSER_ERROR",
                f"{self.platform} 搜索失败：{type(exc).__name__}",
            )
