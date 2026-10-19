"""Live shopping search through a dedicated DrissionPage Edge profile.

The profile is intentionally separate from Playwright so platform sessions and
browser fingerprints cannot be mixed between the two drivers.
"""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import quote
from contextlib import contextmanager

from DrissionPage import ChromiumOptions, ChromiumPage
from hello_agents.tools import Tool, ToolErrorCode, ToolParameter, ToolResponse

from ..config import AppConfig

PLATFORMS = {
    "jd": ("京东", "https://search.jd.com/Search?keyword={query}"),
    "taobao": ("淘宝", "https://s.taobao.com/search?q={query}"),
    "pdd": (
        "拼多多",
        "https://mobile.yangkeduo.com/search_result.html?search_key={query}",
    ),
}
class ComparisonBrowserSession:
    """One browser lifetime for one complete comparison-agent run.

    The comparison agent may call each platform tool several times. All those
    calls reuse this browser and its authenticated profile; the browser is
    closed only when the delegating agent returns (or raises).
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.browser: ChromiumPage | None = None

    def __enter__(self) -> "ComparisonBrowserSession":
        profile = Path(self.config.drission_profile)
        profile.mkdir(parents=True, exist_ok=True)
        options = ChromiumOptions()
        options.set_browser_path(str(self.config.edge_path))
        options.set_user_data_path(str(profile))
        options.set_local_port(self.config.drission_port)
        options.headless(self.config.drission_headless)
        options.set_argument("--start-maximized")
        self.browser = ChromiumPage(options)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.browser is not None:
            try:
                self.browser.quit()
            finally:
                self.browser = None


class DrissionProductTool(Tool):
    def __init__(self, config: AppConfig, platform: str):
        if platform not in PLATFORMS:
            raise ValueError(f"不支持的平台: {platform}")
        self.config = config
        self.platform_key = platform
        self.session: ComparisonBrowserSession | None = None
        self.display_name, self.search_template = PLATFORMS[platform]
        super().__init__(
            f"{platform}_product_search",
            f"使用独立 Edge 会话搜索{self.display_name}并返回搜索列表页可见正文",
        )

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="query", type="string", description="商品名称、品牌或型号"),
            ToolParameter(
                name="max_results",
                type="integer",
                description="兼容参数；当前返回完整页面正文，不在工具层截断",
                required=False,
                default=10,
            ),
        ]

    def run(self, parameters: dict[str, Any]) -> ToolResponse:
        query = str(parameters.get("query", "")).strip()
        if not query:
            return ToolResponse.error(ToolErrorCode.INVALID_PARAM, "query 不能为空")
        return self._search(query)

    def _search(self, query: str) -> ToolResponse:
        browser: ChromiumPage | None = self.session.browser if self.session else None
        owns_browser = False
        page = None
        try:
            if browser is None:
                standalone = ComparisonBrowserSession(self.config)
                standalone.__enter__()
                browser = standalone.browser
                owns_browser = True
            page = browser.new_tab()
            url = self.search_template.format(query=quote(query, safe=""))
            page.get(url)
            time.sleep(max(1, self.config.drission_wait_ms // 1000))
            body = page.ele("tag:body").text
            lower = body.lower()
            if "passport.jd.com" in page.url or "登录页面" in body[:500]:
                return ToolResponse.error(
                    "AUTH_REQUIRED",
                    f"{self.display_name}登录会话已失效，请在当前 Edge 页面重新登录后重试",
                    context={"platform": self.platform_key, "url": page.url},
                )
            captcha = any(x in lower for x in ("滑块", "安全验证", "访问异常", "人机验证", "captcha"))
            if captcha:
                return ToolResponse.error(
                    "CAPTCHA_REQUIRED",
                    f"{self.display_name}触发了验证，请在浏览器中手动完成后重试",
                    context={"platform": self.platform_key, "url": page.url},
                )
            # Keep platform parsing out of the driver. The page text is the
            # source of truth; the Agent handles product grouping, prices,
            # links, and duplicate removal.
            items = []
            data = {
                "platform": self.platform_key,
                "query": query,
                "url": page.url,
                "items": items,
                "raw_candidates": items,
                "product_cards_found": len(items),
                "extraction_method": "raw_page_text",
                "raw_page_text": body,
            }
            return ToolResponse.success(
                f"已读取{self.display_name}搜索列表页正文，交由 Agent 分析",
                data=data,
            )
        except Exception as exc:
            return ToolResponse.error(
                ToolErrorCode.EXECUTION_ERROR,
                f"{self.display_name}搜索失败: {type(exc).__name__}: {exc}",
            )
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            if owns_browser:
                standalone.__exit__(None, None, None)

class JDProductTool(DrissionProductTool):
    def __init__(self, config: AppConfig):
        super().__init__(config, "jd")


class TaobaoProductTool(DrissionProductTool):
    def __init__(self, config: AppConfig):
        super().__init__(config, "taobao")


class PDDProductTool(DrissionProductTool):
    def __init__(self, config: AppConfig):
        super().__init__(config, "pdd")
