"""主 Agent 主动查询平台登录状态，实际检测由 BrowserManager 执行。"""

import logging
from typing import Any

from hello_agents.tools import Tool, ToolParameter, ToolResponse
from backend.browser.browser_manager import BrowserBusyError, LoginCheckError

logger = logging.getLogger(__name__)


class CheckPlatformLoginTool(Tool):
    def __init__(self, browser):
        super().__init__(
            "check_platform_login",
            "检查平台当前登录态；明确未登录与检测失败分开返回",
        )
        self.browser = browser

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="platform",
                type="string",
                description="jd / taobao / pdd / all；用户完成某个平台登录后，必须传入该平台的具体标识。",
                required=False,
                default="all",
            ),
        ]

    def run(self, parameters: dict[str, Any]) -> ToolResponse:
        """返回已确认的 true/false；检测异常作为 error，不伪装成未登录。"""
        platform = str(parameters.get("platform", "all")).strip().lower()
        if platform not in {"jd", "taobao", "pdd", "all"}:
            return ToolResponse.error("INVALID_PARAM", "不支持的平台")

        platforms = ("jd", "taobao", "pdd") if platform == "all" else (platform,)
        results: dict[str, dict[str, Any]] = {}
        login_window_closed = False

        for name in platforms:
            try:
                result = self.browser.check_login(name)
                if not isinstance(result, dict) or type(result.get("authenticated")) is not bool:
                    raise RuntimeError("检测工具没有返回明确的 authenticated 布尔值")
                results[name] = {"status": "checked", **result}
            except BrowserBusyError as exc:
                results[name] = {
                    "status": "error",
                    "authenticated": None,
                    "error_code": "BROWSER_BUSY",
                    "detail": str(exc),
                }
            except Exception as exc:
                # LoginCheckError 的内容是我们生成的安全诊断；其他异常只暴露类型。
                detail = (
                    str(exc)
                    if isinstance(exc, LoginCheckError)
                    else f"登录状态无法确认：{type(exc).__name__}"
                )
                results[name] = {
                    "status": "error",
                    "authenticated": None,
                    "error_code": "LOGIN_CHECK_ERROR",
                    "detail": detail,
                }
                logger.warning(
                    "平台登录态无法确认：%s %s：%s",
                    name, type(exc).__name__, detail,
                )

            # 只有明确验证成功的当前平台，才自动关闭对应人工登录窗口。
            if (
                results[name].get("status") == "checked"
                and platform != "all"
                and name == platform
                and results[name].get("authenticated") is True
                and self.browser.login_platform == name
            ):
                try:
                    self.browser.close_login()
                    login_window_closed = True
                except Exception as exc:
                    return ToolResponse.error(
                        "LOGIN_VERIFIED_BUT_CLOSE_FAILED",
                        "已验证登录，但关闭登录窗口失败："
                        f"{type(exc).__name__}。请先关闭登录窗口后再继续。",
                    )

        errors = {
            name: result for name, result in results.items()
            if result.get("status") == "error"
        }

        # 单平台检测失败时直接返回标准工具错误，避免被误认为未登录。
        if platform != "all" and errors:
            result = errors[platform]
            return ToolResponse.error(result["error_code"], result["detail"])

        # 全部平台都无法检测时仍返回错误，并保留逐平台原因。
        if errors and len(errors) == len(results):
            response = ToolResponse.error(
                "LOGIN_CHECK_ERROR", "所有目标平台的登录态都无法确认，请查看逐平台错误详情。"
            )
            response.data = {"platforms": results}
            return response

        message = "平台登录状态检查完成"
        if errors:
            message = "部分平台登录态无法确认；请区分 status=error 与 authenticated=false。"
        if login_window_closed:
            message += "；已验证登录并关闭登录窗口，后续搜索可以继续。"

        payload = {
            "platforms": results,
            "login_window_closed": login_window_closed,
        }
        if errors:
            return ToolResponse.partial(message, data=payload)
        return ToolResponse.success(message, data=payload)

