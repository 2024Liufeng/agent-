"""主 Agent 调用此工具，打开平台的有头浏览器供用户手动登录。"""

from typing import Any

from hello_agents.tools import Tool, ToolParameter, ToolResponse
from backend.browser.browser_manager import BrowserBusyError


class OpenPlatformLoginTool(Tool):
    """打开指定电商平台的登录窗口；不负责判断用户是否已登录。"""

    def __init__(self, browser):
        super().__init__(
            "open_platform_login",
            "用户明确选择登录平台时，打开有头浏览器窗口，供用户手动登录。",
        )
        self.browser = browser

    def get_parameters(self) -> list[ToolParameter]:
        # 告诉主 Agent 这个工具需要指定平台。
        return [
            ToolParameter(
                name="platform",
                type="string",
                description="平台标识：jd / taobao / pdd",
            ),
        ]

    def run(self, parameters: dict[str, Any]) -> ToolResponse:
        # ① 获取主 Agent 传入的平台名称。
        platform = str(parameters.get("platform", "")).strip().lower()

        # ② 只允许我们支持的三个平台。
        if platform not in {"jd", "taobao", "pdd"}:
            return ToolResponse.error("INVALID_PARAM", "不支持的平台")

        try:
            # ③ 复用已有 BrowserManager，不通过 HTTP 调用自己的后端。
            result = self.browser.open_login(platform)

            # 注意：窗口打开成功，不代表用户已经登录。
            return ToolResponse.success(
                "登录窗口已打开，请用户手动完成登录。",
                data=result,
            )
        except BrowserBusyError as exc:
            # 例如其他平台还在搜索，浏览器暂时不能切换到登录模式。
            return ToolResponse.error("BROWSER_BUSY", str(exc))
        except Exception as exc:
            # 不将底层异常细节直接暴露给用户。
            return ToolResponse.error(
                "LOGIN_WINDOW_ERROR",
                f"打开登录窗口失败：{type(exc).__name__}",
            )


class ClosePlatformLoginTool(Tool):
    """关闭有头登录窗口，让后续搜索可以重新使用 Profile。

    用户完成登录或验证后，必须先关闭窗口；窗口打开期间搜索会报
    BROWSER_BUSY，因此这个工具是继续比价的前置步骤。
    """

    def __init__(self, browser):
        super().__init__(
            "close_platform_login",
            "关闭当前打开的有头登录窗口，释放浏览器以便继续搜索或比价",
        )
        self.browser = browser

    def get_parameters(self) -> list[ToolParameter]:
        return []

    def run(self, parameters: dict[str, Any]) -> ToolResponse:
        try:
            self.browser.close_login()
            return ToolResponse.success(
                "登录窗口已关闭，可以继续搜索。",
                data={"closed": True},
            )
        except BrowserBusyError as exc:
            return ToolResponse.error("BROWSER_BUSY", str(exc))
        except Exception as exc:
            return ToolResponse.error(
                "LOGIN_WINDOW_ERROR",
                f"关闭登录窗口失败：{type(exc).__name__}",
            )
