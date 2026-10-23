"""项目 Edge 资源管理：无头 Edge 多标签并行查询，人工登录时独占 Profile。"""

from __future__ import annotations

import logging
import socket
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit

import psutil
from DrissionPage import ChromiumOptions, ChromiumPage

logger = logging.getLogger(__name__)


class BrowserBusyError(RuntimeError):
    """当前 Profile 正被用户登录窗口占用。"""


LOGIN_URLS = {
    "jd": "https://passport.jd.com/new/login.aspx",
    "taobao": "https://login.taobao.com/",
    "pdd": "https://mobile.yangkeduo.com/login.html",
}
LOGIN_PROBE_URLS = {
    "jd": "https://www.jd.com/",
    "taobao": "https://www.taobao.com/",
    "pdd": "https://mobile.yangkeduo.com/personal.html",
}
LOGIN_HOST_MARKERS = (
    "passport.jd.com",
    "login.taobao.com",
    "login.m.taobao.com",
)
CAPTCHA_MARKERS = (
    "滑动验证", "拖动滑块", "请完成验证", "安全验证",
    "人机验证", "异常流量", "nc_1_n1z", "验证码登录",
)
LOGIN_REQUIRED_TEXT_MARKERS = ("请先登录", "请登录", "你好，请登录", "亲，请登录", "扫码登录", "登录后查看", "手机登录")
LOGIN_READY_MARKERS = (
    "我的订单", "我的京东", "退出登录", "京东会员",
    "退出", "账号管理", "已买到的宝贝", "我的淘宝", "购物车",
    "个人中心", "我的拼小圈",
    *LOGIN_REQUIRED_TEXT_MARKERS,
    *CAPTCHA_MARKERS,
)


class LoginCheckError(RuntimeError):
    """页面无法提供足够证据确认登录状态。"""


def _wait_ready(page, seconds: float = 6.0) -> None:
    """等待页面出现可用于判断的关键内容；这些标记本身不代表已登录。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            body = page.ele("tag:body", timeout=2).text or ""
        except Exception:
            body = ""
        if any(marker.lower() in body.lower() for marker in LOGIN_READY_MARKERS):
            time.sleep(0.8)
            return
        time.sleep(0.5)


def _account_evidence(platform: str, page, url: str, body: str) -> str | None:
    """只检查账号专属 DOM；普通导航文字不能证明用户已登录。"""
    if platform == "pdd":
        parts = urlsplit(url)
        if (
            parts.hostname == "mobile.yangkeduo.com"
            and parts.path == "/personal.html"
            and all(marker in body for marker in ("我的订单", "收货地址", "设置"))
        ):
            return "拼多多受保护个人中心可访问，且账号功能区已渲染"
        return None

    if platform == "jd":
        script = """return !!(
            document.querySelector('.nickname') &&
            [...document.querySelectorAll('a.user_logout')].some(
                link => /退出/.test(link.textContent || '')
            )
        );"""
    elif platform == "taobao":
        script = """return !!(
            document.querySelector('a[href*="login.taobao.com/member/logout.jhtml"]') &&
            document.querySelector('a[href*="member1.taobao.com/member/fresh/account_security.htm"]')
        );"""
    else:
        return None

    try:
        if page.run_js(script) is True:
            return f"{platform} 已渲染账号专属入口和退出链接"
    except Exception:
        # DOM 查询失败不等于未登录；上层会将其作为无法确认处理。
        return None
    return None


def _is_login_redirect(platform: str, url: str) -> bool:
    lowered = (url or "").lower()
    parts = urlsplit(lowered)
    if any(marker in lowered for marker in LOGIN_HOST_MARKERS):
        return True
    return platform == "pdd" and parts.hostname == "mobile.yangkeduo.com" and "/login" in parts.path


class BrowserManager:
    def __init__(self, settings):
        self.settings = settings
        self._lock = RLock()
        self._login_browser: ChromiumPage | None = None
        self._login_platform: str | None = None
        self._search_browser: ChromiumPage | None = None  # 三个平台共用的无头浏览器
        self._active_tabs = 0  # 正在使用的临时标签页数量（搜索或登录检查）

    def _create_browser(self, *, headless: bool) -> ChromiumPage:
        profile = Path(self.settings.edge_profile)
        profile.mkdir(parents=True, exist_ok=True)

        options = ChromiumOptions()
        options.set_browser_path(str(self.settings.edge_path))
        options.set_user_data_path(str(profile))
        options.headless(headless)
        # 单实例在同一时刻持有该 Profile。端口只用于当前项目浏览器。
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        options.set_local_port(port)

        browser = ChromiumPage(options)
        logger.info("项目 Edge 已启动：pid=%s headless=%s",
                    browser.process_id, headless)
        return browser

    @staticmethod
    def _close_browser(browser: ChromiumPage) -> None:
        pid = browser.process_id
        try:
            browser.quit(timeout=5, force=True)
            logger.info("项目 Edge 已关闭：pid=%s", pid)
        except Exception:
            logger.exception("项目 Edge 关闭异常：pid=%s", pid)
            raise

    def _clear_closed_login(self) -> None:
        """用户手动关掉登录窗口后，回收本进程的失效引用。"""
        browser = self._login_browser
        if browser is None:
            return
        pid = browser.process_id
        if not pid or not psutil.pid_exists(pid):
            self._login_browser = None
            self._login_platform = None

    @property
    def login_platform(self) -> str | None:
        """当前人工登录窗口对应的平台；窗口关闭后返回 None。"""
        with self._lock:
            self._clear_closed_login()
            return self._login_platform

    def _get_search_browser(self) -> ChromiumPage:
        """必须在 self._lock 内调用：首次启动无头 Edge，后续直接复用。"""
        browser = self._search_browser
        if browser is not None:
            pid = browser.process_id
            if pid and psutil.pid_exists(pid):
                return browser  # 同一个 Edge，后续只创建新标签页

            if self._active_tabs:
                raise BrowserBusyError("浏览器异常退出，等待其他搜索结束")
            self._search_browser = None  # 无头 Edge 已退出，下次重新启动

        browser = self._create_browser(headless=True)
        self._search_browser = browser
        return browser

    @contextmanager
    def _temporary_page(self, *, allow_login: bool = False):
        """新建临时标签页；登录状态检查可选择复用有头登录窗口。"""
        with self._lock:
            self._clear_closed_login()

            if self._login_browser is not None:
                if not allow_login:
                    # 普通搜索仍不与用户手动登录争用同一个 Profile。
                    raise BrowserBusyError("正在人工登录，请先完成登录状态检查")
                # 检查在同一个 Edge 的新标签页中执行，共享刚登录的 Cookie。
                browser = self._login_browser
            else:
                # 没有人工登录窗口时，继续复用三个平台共用的无头 Edge。
                browser = self._get_search_browser()

            page = browser.new_tab()
            self._active_tabs += 1

        try:
            yield page
        finally:
            with self._lock:
                try:
                    page.close()  # 只关闭本次临时标签页
                except Exception:
                    logger.exception("关闭临时标签页失败")
                finally:
                    self._active_tabs -= 1

    @staticmethod
    def _body(page) -> str:
        element = page.ele("tag:body", timeout=12)
        return element.text if element else ""

    def read_page(self, url: str) -> dict[str, str]:
        """读取完整网页正文；不在工具层做截断。"""
        with self._temporary_page() as page:
            page.get(url, timeout=25)
            return {"url": str(page.url or ""), "text": self._body(page)}

    def open_login(self, platform: str) -> dict:
        """有头窗口由用户手动登录；后端 API 负责调用此方法。"""
        if platform not in LOGIN_URLS:
            raise ValueError("不支持的平台")
        with self._lock:
            self._clear_closed_login()
            if self._login_browser is not None:
                raise BrowserBusyError("已有登录窗口，请先关闭")
            if self._active_tabs:
                # 人工登录和正在搜索的标签页不能争用同一个 Profile。
                raise BrowserBusyError("仍有平台正在搜索，请搜索结束后再登录")

            if self._search_browser is not None:
                # 切换成有头登录前，先关闭本项目持有的无头 Edge。
                self._close_browser(self._search_browser)
                self._search_browser = None

            browser = self._create_browser(headless=False)
            try:
                browser.latest_tab.get(LOGIN_URLS[platform], timeout=25)
                self._login_browser = browser
                self._login_platform = platform
                return {"status": "login_window_open", "platform": platform,
                        "pid": browser.process_id}
            except Exception:
                self._close_browser(browser)
                raise

    def close_login(self) -> None:
        with self._lock:
            browser = self._login_browser
            # 先关闭成功，再清理引用；关闭失败时保留引用便于恢复。
            if browser is not None and psutil.pid_exists(browser.process_id):
                self._close_browser(browser)
            self._login_browser = None
            self._login_platform = None

    def close(self) -> None:
        """服务关闭时清理本项目打开的浏览器，不能关闭其他 Edge。"""
        with self._lock:
            if self._active_tabs:
                raise BrowserBusyError("仍有临时标签页正在使用，不能关闭浏览器")
            self.close_login()
            if self._search_browser is not None:
                try:
                    self._close_browser(self._search_browser)
                finally:
                    self._search_browser = None

    def check_login(self, platform: str) -> dict:
        """借鉴已验证的账号 DOM 检测；不确定时抛出错误，不冒充未登录。"""
        if platform not in LOGIN_PROBE_URLS:
            raise ValueError("不支持的平台")

        try:
            with self._temporary_page(allow_login=True) as page:
                page.get(LOGIN_PROBE_URLS[platform], timeout=25)
                _wait_ready(page)

                url = str(page.url or "")
                body = self._body(page)
                lowered_body = body.lower()

                # 验证/风控不是“未登录”的同义词，交给工具层如实报告。
                if any(marker.lower() in lowered_body for marker in CAPTCHA_MARKERS):
                    raise LoginCheckError(f"{platform} 页面出现验证码或风控提示，无法确认登录态")

                # 明确跳转登录页，可以确认当前未登录或会话已失效。
                if _is_login_redirect(platform, url):
                    return {"authenticated": False, "detail": f"已跳转登录页：{url[:160]}"}

                evidence = _account_evidence(platform, page, url, body)
                if evidence:
                    # 淘宝首页账号专属 DOM 已提供明确证据，无需再次进入账号安全页。
                    return {"authenticated": True, "detail": evidence}

                # 明确登录提示可以判未登录；普通导航文字不算登录证据。
                if any(marker in body for marker in LOGIN_REQUIRED_TEXT_MARKERS):
                    return {"authenticated": False, "detail": "页面显示需要登录"}

                # 页面可访问但没有可靠身份信号，不能猜成 true 或 false。
                raise LoginCheckError("页面未提供明确的账号身份信号，无法确认是否已登录")

        except (BrowserBusyError, ValueError, LoginCheckError):
            raise
        except Exception as exc:
            # 记录真实原因（例如 BrowserConnectError 的详细提示），
            # 否则只剩异常类名，无法判断是 Profile 被占用还是网络问题。
            logger.warning(
                "登录检查失败：%s %s: %s",
                platform, type(exc).__name__, exc,
            )
            raise LoginCheckError(f"登录检查失败：{type(exc).__name__}") from exc




