"""平台登录态检测的轻量单元测试，不启动真实 Edge 或访问真实电商网站。"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.browser.browser_manager import BrowserManager, LoginCheckError
from backend.tools.platform_login import CheckPlatformLoginTool


class FakePage:
    def __init__(
        self,
        *,
        home_body="",
        home_url=None,
        js_result=False,
        security_body="账号安全 " + "资料信息" * 20,
        security_url=None,
        error=None,
    ):
        self.body = home_body
        self.home_body = home_body
        self.url = home_url or ""
        self.home_url = home_url
        self.js_result = js_result
        self.security_body = security_body
        self.security_url = security_url
        self.error = error
        self.visited_urls = []

    def get(self, url, timeout=25):
        self.visited_urls.append(url)
        if self.error is not None:
            raise self.error
        if "account_security" in url:
            self.url = self.security_url or url
            self.body = self.security_body
        else:
            self.url = self.home_url or url
            self.body = self.home_body

    def ele(self, *_args, **_kwargs):
        return SimpleNamespace(text=self.body)

    def run_js(self, _script):
        return self.js_result

    def close(self):
        pass


def _manager_with_page(monkeypatch, page):
    manager = BrowserManager.__new__(BrowserManager)

    @contextmanager
    def temporary_page(allow_login=False):
        yield page

    monkeypatch.setattr(manager, "_temporary_page", temporary_page)
    monkeypatch.setattr(
        "backend.browser.browser_manager._wait_ready",
        lambda *_args, **_kwargs: None,
    )
    return manager


def test_jd_login_requires_account_dom_evidence(monkeypatch):
    page = FakePage(home_body="我的订单", js_result=True)
    manager = _manager_with_page(monkeypatch, page)

    result = manager.check_login("jd")

    assert result["authenticated"] is True


def test_pdd_login_requires_protected_personal_page(monkeypatch):
    page = FakePage(home_body="我的订单 收货地址 设置")
    manager = _manager_with_page(monkeypatch, page)

    result = manager.check_login("pdd")

    assert result["authenticated"] is True


def test_captcha_is_detection_error_not_logged_out(monkeypatch):
    page = FakePage(home_body="安全验证 请完成验证")
    manager = _manager_with_page(monkeypatch, page)

    with pytest.raises(LoginCheckError, match="验证码或风控"):
        manager.check_login("jd")


def test_redirect_to_login_is_confirmed_not_logged_in(monkeypatch):
    page = FakePage(
        home_body="扫码登录",
        home_url="https://passport.jd.com/new/login.aspx",
    )
    manager = _manager_with_page(monkeypatch, page)

    result = manager.check_login("jd")

    assert result["authenticated"] is False


def test_explicit_login_prompt_returns_false(monkeypatch):
    page = FakePage(home_body="你好，请登录")
    manager = _manager_with_page(monkeypatch, page)

    result = manager.check_login("jd")

    assert result["authenticated"] is False


def test_missing_identity_evidence_is_not_guessed_as_logged_out(monkeypatch):
    page = FakePage(home_body="京东首页", js_result=False)
    manager = _manager_with_page(monkeypatch, page)

    with pytest.raises(LoginCheckError, match="无法确认"):
        manager.check_login("jd")


def test_taobao_only_checks_homepage_account_dom(monkeypatch):
    # 即使账号安全页不可用，也不应该影响首页已经确认的登录态。
    page = FakePage(
        home_body="我的淘宝 购物车",
        js_result=True,
        security_body="请登录",
    )
    manager = _manager_with_page(monkeypatch, page)

    result = manager.check_login("taobao")

    assert result["authenticated"] is True
    assert "账号专属" in result["detail"]
    assert page.visited_urls == ["https://www.taobao.com/"]


def test_browser_failure_is_not_returned_as_authenticated_false(monkeypatch):
    page = FakePage(error=TimeoutError("network timeout"))
    manager = _manager_with_page(monkeypatch, page)

    with pytest.raises(LoginCheckError, match="登录检查失败"):
        manager.check_login("jd")


def test_login_tool_returns_error_when_single_platform_cannot_be_checked():
    class BrokenBrowser:
        login_platform = None

        def check_login(self, _platform):
            raise LoginCheckError("页面证据不足")

    response = CheckPlatformLoginTool(BrokenBrowser()).run({"platform": "jd"})

    assert response.status.value == "error"
    assert response.to_dict()["error"]["code"] == "LOGIN_CHECK_ERROR"
    assert response.to_dict()["error"]["message"] == "页面证据不足"


def test_all_platforms_preserves_partial_results_and_detection_error():
    class MixedBrowser:
        login_platform = None

        def check_login(self, platform):
            if platform == "jd":
                return {"authenticated": True, "detail": "京东账号 DOM 已确认"}
            if platform == "taobao":
                raise LoginCheckError("淘宝页面证据不足")
            return {"authenticated": False, "detail": "已跳转拼多多登录页"}

    response = CheckPlatformLoginTool(MixedBrowser()).run({"platform": "all"})
    payload = response.to_dict()

    assert response.status.value == "partial"
    assert payload["data"]["platforms"]["jd"]["authenticated"] is True
    assert payload["data"]["platforms"]["taobao"]["status"] == "error"
    assert payload["data"]["platforms"]["taobao"]["authenticated"] is None
    assert payload["data"]["platforms"]["pdd"]["authenticated"] is False
