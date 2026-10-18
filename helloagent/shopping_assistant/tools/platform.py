"""京东、淘宝和拼多多 Playwright 商品查询工具。"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from hello_agents.tools import Tool, ToolErrorCode, ToolParameter, ToolResponse
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from ..config import AppConfig


_BROWSER_LOCK = threading.Lock()
_COOLDOWN_LOCK = threading.Lock()
_PLATFORM_COOLDOWN_UNTIL: dict[str, float] = {}
_CAPTCHA_MARKERS = (
    "滑动验证",
    "拖动滑块",
    "安全验证",
    "人机验证",
    "请完成验证",
    "异常流量",
    "访问异常",
    "captcha",
    "nc_1_n1z",
    "验证码",
)
_BLOCKED_MARKERS = (
    "当前人数过多",
    "更多精彩请前往京东app",
    "网络有点慢哦",
    "请前往京东app",
    "访问频繁",
    "系统繁忙",
    "网络异常",
    "请稍后再试",
)


@dataclass(frozen=True)
class PlatformConfig:
    key: str
    display_name: str
    search_url: str
    login_markers: tuple[str, ...]


PLATFORMS = {
    "jd": PlatformConfig(
        key="jd",
        display_name="京东",
        # 移动设备 UA 访问桌面搜索页会被重定向到京东首页。
        search_url="https://so.m.jd.com/ware/search.action?keyword={query}",
        login_markers=("登录", "请登录"),
    ),
    "taobao": PlatformConfig(
        key="taobao",
        display_name="淘宝",
        search_url="https://s.taobao.com/search?q={query}",
        login_markers=("登录", "请登录", "扫码登录"),
    ),
    "pdd": PlatformConfig(
        key="pdd",
        display_name="拼多多",
        search_url="https://mobile.yangkeduo.com/search_result.html?search_key={query}",
        login_markers=("登录", "手机号登录", "微信登录", "立即登录"),
    ),
}


def _cooldown_remaining(platform: str) -> int:
    with _COOLDOWN_LOCK:
        remaining = _PLATFORM_COOLDOWN_UNTIL.get(platform, 0.0) - time.monotonic()
    return max(0, int(remaining))


def _set_cooldown(platform: str, seconds: int) -> None:
    with _COOLDOWN_LOCK:
        _PLATFORM_COOLDOWN_UNTIL[platform] = time.monotonic() + max(1, seconds)


class PlatformProductTool(Tool):
    """共享实现，分别暴露为京东、淘宝和拼多多工具。"""

    def __init__(self, config: AppConfig, platform: str):
        if platform not in PLATFORMS:
            raise ValueError(f"不支持的平台: {platform}")
        self.config = config
        self.platform = PLATFORMS[platform]
        super().__init__(
            f"{platform}_product_search",
            f"使用 Playwright 读取{self.platform.display_name}商品列表卡片原文和详情链接，具体字段由 Agent 解析。",
        )

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query", type="string", description="商品类别、品牌或型号"
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="最多返回的商品数量",
                required=False,
                default=self.config.max_platform_results,
            ),
        ]

    def run(self, parameters: dict[str, Any]) -> ToolResponse:
        query = str(parameters.get("query", "")).strip()
        if not query:
            return ToolResponse.error(ToolErrorCode.INVALID_PARAM, "query 不能为空")
        try:
            max_results = max(
                1,
                min(
                    int(parameters.get("max_results", self.config.max_platform_results)),
                    10,
                ),
            )
        except (TypeError, ValueError):
            return ToolResponse.error(
                ToolErrorCode.INVALID_PARAM, "max_results 必须是整数"
            )

        remaining = _cooldown_remaining(self.platform.key)
        if remaining:
            return ToolResponse.error(
                "PLATFORM_COOLDOWN",
                f"{self.platform.display_name}刚刚触发了风控，暂缓请求 {remaining} 秒，避免重复触发限流",
                context={
                    "platform": self.platform.key,
                    "query": query,
                    "cooldown_remaining_seconds": remaining,
                },
            )

        # 三个平台复用同一份已登录 profile，持久化浏览器不能并发打开。
        with _BROWSER_LOCK:
            return self._run_browser(query, max_results)

    def _run_browser(self, query: str, max_results: int) -> ToolResponse:
        device_name = os.getenv("PLAYWRIGHT_DEVICE", "iPhone 15 Pro")
        if not self.config.playwright_headless:
            os.environ.setdefault("DISPLAY", os.getenv("PLAYWRIGHT_DISPLAY", ":99"))
        cdp_endpoint = self.config.playwright_cdp_endpoint
        try:
            with sync_playwright() as playwright:
                owns_context = False
                browser = None
                if cdp_endpoint:
                    browser = playwright.chromium.connect_over_cdp(cdp_endpoint)
                    if not browser.contexts:
                        return ToolResponse.error(
                            "BROWSER_UNAVAILABLE",
                            f"{self.platform.display_name}共享浏览器没有可用上下文",
                        )
                    context = browser.contexts[0]
                else:
                    device = playwright.devices.get(
                        device_name, playwright.devices["iPhone 15 Pro"]
                    )
                    launch_kwargs: dict[str, Any] = {
                        "headless": self.config.playwright_headless,
                        "locale": "zh-CN",
                        "user_agent": device["user_agent"],
                        "viewport": device["viewport"],
                        "device_scale_factor": device["device_scale_factor"],
                        "is_mobile": device["is_mobile"],
                        "has_touch": device["has_touch"],
                    }
                    if self.config.playwright_proxy:
                        launch_kwargs["proxy"] = {"server": self.config.playwright_proxy}
                    context = playwright.chromium.launch_persistent_context(
                        str(self.config.playwright_profile), **launch_kwargs
                    )
                    owns_context = True
                page = None
                try:
                    page = context.new_page()
                    # 成功脚本使用 %20 编码空格；不要改成移动站点常见的加号格式。
                    url = self.platform.search_url.format(query=quote(query, safe=""))
                    response = page.goto(
                        url, wait_until="domcontentloaded", timeout=60000
                    )
                    page.wait_for_timeout(self.config.playwright_wait_ms)
                    body = page.locator("body").inner_text(timeout=20000)
                    title = page.title()
                    current_url = page.url
                    raw_items = self._extract_product_cards(page, max_results)
                finally:
                    if page is not None:
                        page.close()
                    if owns_context:
                        context.close()
        except PlaywrightTimeoutError as exc:
            return ToolResponse.error(
                ToolErrorCode.TIMEOUT,
                f"{self.platform.display_name}页面加载超时: {exc}",
            )
        except Exception as exc:
            return ToolResponse.error(
                ToolErrorCode.EXECUTION_ERROR,
                f"{self.platform.display_name}查询失败: {type(exc).__name__}: {exc}",
            )

        if not body.strip():
            return ToolResponse.error(
                ToolErrorCode.NOT_FOUND, f"{self.platform.display_name}没有返回页面内容"
            )

        body_lower = body.lower()
        captcha_detected = any(marker.lower() in body_lower for marker in _CAPTCHA_MARKERS)
        if captcha_detected:
            return ToolResponse.error(
                "CAPTCHA_REQUIRED",
                f"{self.platform.display_name}页面触发了滑动或安全验证，请先在远程浏览器完成验证",
                context={
                    "platform": self.platform.key,
                    "query": query,
                    "url": current_url,
                    "page_title": title,
                    "captcha_detected": True,
                },
            )

        blocked_marker = next(
            (marker for marker in _BLOCKED_MARKERS if marker.lower() in body_lower),
            None,
        )
        if blocked_marker:
            _set_cooldown(
                self.platform.key, self.config.playwright_block_cooldown_seconds
            )
            return ToolResponse.error(
                "PLATFORM_BLOCKED",
                f"{self.platform.display_name}暂时限制了搜索：{blocked_marker}",
                context={
                    "platform": self.platform.key,
                    "query": query,
                    "url": current_url,
                    "page_title": title,
                    "captcha_detected": False,
                    "blocked_marker": blocked_marker,
                },
            )

        login_hint = any(
            marker in body[:1200] for marker in self.platform.login_markers
        )
        data = {
            "platform": self.platform.key,
            "query": query,
            "page_title": title,
            "url": current_url,
            "status_code": response.status if response else None,
            "login_required": login_hint and not raw_items,
            "captcha_detected": False,
            "items": raw_items,
            "raw_candidates": raw_items,
            "extraction_method": "product_cards",
            "product_cards_found": len(raw_items),
        }
        if login_hint and not raw_items:
            return ToolResponse.error(
                "AUTH_REQUIRED",
                f"{self.platform.display_name}登录状态失效，请先重新登录后再查询",
                context=data,
            )
        if not raw_items:
            return ToolResponse.partial(
                f"{self.platform.display_name}页面已打开，但没有解析出明确商品条目。",
                data=data,
            )
        return ToolResponse.success(
            f"已从{self.platform.display_name}页面读取 {len(raw_items)} 条商品卡片，具体字段交给 Agent 解析。",
            data=data,
        )

    def _extract_product_cards(self, page: Any, max_results: int) -> list[dict[str, Any]]:
        """只定位商品卡片并返回原文，字段解释交给 LLM。"""
        if self.platform.key == "jd":
            return self._extract_jd_cards(page, max_results)
        if self.platform.key == "pdd":
            return self._extract_pdd_cards(page, max_results)
        return self._extract_taobao_cards(page, max_results)

    @staticmethod
    def _extract_jd_cards(page: Any, max_results: int) -> list[dict[str, Any]]:
        cards = page.locator("div.search_prolist_item")
        results: list[dict[str, Any]] = []
        for index in range(min(cards.count(), max_results)):
            card = cards.nth(index)
            raw_text = " ".join(card.inner_text(timeout=5000).split())
            inner = card.locator(".search_prolist_item_inner")
            url = inner.get_attribute("pure_item_link") if inner.count() else None
            if not raw_text:
                continue
            results.append(
                {
                    "index": index + 1,
                    "detail_url": url or "",
                    "raw_text": raw_text[:1000],
                }
            )
        return results

    @staticmethod
    def _extract_taobao_cards(page: Any, max_results: int) -> list[dict[str, Any]]:
        # 淘宝当前搜索页把商品卡片渲染为带 itemCard 类名的详情链接；
        # 同时保留详情链接选择器，降低类名哈希变化的影响。
        cards = page.locator(
            'a[class*="itemCard"], a[href*="detail.tmall.com/item"], '
            'a[href*="item.taobao.com/item"]'
        )
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for index in range(min(cards.count(), max_results * 2)):
            card = cards.nth(index)
            raw_text = " ".join(card.inner_text(timeout=5000).split())
            url = card.get_attribute("href") or ""
            if url.startswith("//"):
                url = f"https:{url}"
            if not raw_text or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(
                {
                    "index": index + 1,
                    "detail_url": url,
                    "raw_text": raw_text[:1000],
                }
            )
            if len(results) >= max_results:
                break
        return results

    @staticmethod
    def _extract_pdd_cards(page: Any, max_results: int) -> list[dict[str, Any]]:
        """拼多多页面结构经常变化，只抽取商品卡片原文和详情链接。"""
        cards = page.locator(
            'a[href*="goods.html"], a[href*="goods_detail"], '
            '[data-goods-id]'
        )
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for index in range(min(cards.count(), max_results * 3)):
            card = cards.nth(index)
            raw_text = " ".join(card.inner_text(timeout=5000).split())
            url = card.get_attribute("href") or ""
            if url.startswith("//"):
                url = f"https:{url}"
            if not url:
                goods_id = card.get_attribute("data-goods-id")
                if goods_id:
                    url = f"https://mobile.yangkeduo.com/goods.html?goods_id={goods_id}"
            if url.startswith("/"):
                url = f"https://mobile.yangkeduo.com{url}"
            if not raw_text or (url and url in seen_urls):
                continue
            if url:
                seen_urls.add(url)
            results.append(
                {
                    "index": len(results) + 1,
                    "detail_url": url,
                    "raw_text": raw_text[:1000],
                }
            )
            if len(results) >= max_results:
                break
        return results


class JDProductTool(PlatformProductTool):
    def __init__(self, config: AppConfig):
        super().__init__(config, "jd")


class TaobaoProductTool(PlatformProductTool):
    def __init__(self, config: AppConfig):
        super().__init__(config, "taobao")


class PDDProductTool(PlatformProductTool):
    def __init__(self, config: AppConfig):
        super().__init__(config, "pdd")
