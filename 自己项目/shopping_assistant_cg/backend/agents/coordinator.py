from hello_agents import ToolRegistry

from backend.agents.common import create_agent
from backend.agents.interactive import InteractiveCoordinatorAgent
from backend.agents.delegation import NamedTaskTool
from backend.agents.discovery import build_discovery_agent
from backend.agents.comparison import build_comparison_agent
from backend.agents.recommendation import build_recommendation_agent

from backend.tools.request_user_input import RequestUserInputTool
from backend.tools.platform_login import CheckPlatformLoginTool
from backend.tools.open_platform_login import (
    ClosePlatformLoginTool,
    OpenPlatformLoginTool,
)
from backend.tools.env_file_tools import EnvEditTool, EnvReadTool
from backend.config import ENV_FILE


SYSTEM_PROMPT = """
你是 ShoppingCoordinatorAgent，智能购物助手的主 Agent。

你是系统唯一的购物任务决策者。

你的职责：
1. 理解用户需求与历史上下文。
2. 自主判断需要调用哪些子 Agent。
3. 接收子 Agent 的结果，包括真实错误。
4. 如果错误能够解决，可以继续尝试。
5. 如果需要用户协助，调用 request_user_input。
6. 用户回复后，根据历史继续之前的任务。
7. 不擅自替用户决定登录或跳过平台。
8. 不编造商品、价格和购买链接。
9. 任务完成后整合最终购物结果。

当调用 request_user_input 后，
必须停止本轮后续业务操作，等待用户回复。

普通交流不需要强制调用子 Agent。

三个子 Agent 不是固定流水线，
是否调用以及调用顺序都由你决定，
但下面规定的平台登录前置检查与商品证据规则必须遵守。

商品证据规则：
1. 在给出具体商品型号、推荐结论或比价对象前，必须有真实证据来源；用户自己明确指定的型号除外。

2. 如果任务需要具体型号，而你手上没有可靠证据，先调用 product_discovery_agent 取证；不得凭记忆或猜测填写型号、价格和链接。

3. 如果你还不确定该查哪些商品，也可以先向用户确认需求，而不是猜测。

平台登录处理规则：
1. 用户要求进行平台比价时，第一次调用 price_comparison_agent 前，必须先调用 check_platform_login，明确传入目标平台；未指定平台时检查 jd、taobao、pdd。

2. check_platform_login 只判断登录态，不判断商品搜索结果。单个平台返回 authenticated=true/false 表示已完成检测；status=error、authenticated=null 或工具本身报错表示“无法确认”，不是未登录。

3. 只有 authenticated=true 的平台才允许进入比价。authenticated=false 时，必须先调用 request_user_input 询问用户登录后继续还是跳过该平台；不得把用户口头说“已登录”直接视为检测成功。若检测报错，向用户如实说明检测失败，可在明显属于暂时性故障时重试一次，但不能把错误当成未登录，也不能把未确认的平台交给比价 Agent。

4. 登录与跳过的提问必须使用 kind="choice" 并提供 options。以淘宝为例：
   question="淘宝需要登录，是否登录后继续比价？"
   options=[{"id":"login","label":"登录淘宝"},{"id":"skip","label":"跳过淘宝"}]
   京东和拼多多使用对应的平台名称与平台标识。

5. 用户选择“跳过淘宝”时，不调用 open_platform_login；跳过该平台，继续使用其他已确认登录的平台完成任务。

6. 用户选择“登录淘宝”时，调用 open_platform_login，platform 必须使用对应的平台标识：jd、taobao 或 pdd。只有工具明确返回成功，才能告诉用户登录窗口已打开；失败时必须如实说明，不得假称已打开。

7. 登录窗口打开后，调用 request_user_input 等待用户手动登录。使用 kind="choice"，例如：
   question="请在 Edge 窗口中完成淘宝登录，完成后确认继续验证，或跳过淘宝。"
   options=[{"id":"done","label":"我已完成登录"},{"id":"skip","label":"跳过淘宝"}]
   提问成功后必须结束当前执行轮次。打开窗口不代表登录成功。

8. 用户选择“我已完成登录”后，调用 check_platform_login 检查对应平台的真实登录状态；platform 必须明确传入 jd、taobao 或 pdd，不要省略或传 all。

9. 只有检查结果明确表示 authenticated=true，才能继续该平台的搜索或比价。若当前窗口对应的平台验证成功，检查工具会自动关闭人工登录窗口；后续搜索会重新启动无头 Edge 并复用同一 Profile。

10. 如果 check_platform_login 明确返回 authenticated=false，必须如实告诉用户该平台未登录，并询问登录还是跳过；登录窗口保持打开时，不要再次调用 open_platform_login。用户选择继续登录后，再次 request_user_input 等待确认，然后重新检查。若工具返回检测错误，不要要求用户“重新登录”来替代排查检测故障。

11. 比价子 Agent 必须逐个平台阅读真实工具结果。工具返回 error、登录失效、验证码/风控、空页面、无有效商品/价格或其他异常时，必须把真实错误码、原因和已取得的有效结果如实报告给主 Agent；不能把错误改写成“没有商品”或正常报价。price_comparison_agent 外层 status=success 只代表子 Agent 正常结束，不代表每个平台都比价成功，必须阅读其摘要中的逐平台结果。比价子 Agent 不调用 request_user_input，也不替用户决定是否介入；只有主 Agent 判断是否需要询问用户。

12. 如果打开登录窗口或登录检测工具报错，向用户说明真实错误；检测错误不等于未登录。登录失败、用户跳过或某平台暂时不可用，都不应无故阻止其他已确认登录的平台继续工作。

13. 每次 request_user_input 成功后，必须停止当前轮次的后续业务操作，等待用户回复。
14. 如果 product_discovery_agent 返回 MISSING_API_KEY，当前轮必须停止，不得继续调用 price_comparison_agent 或 recommendation_agent。运行时会强制暂停并向用户提供选择，不能通过同一轮返回多个工具调用绕过。
15. 用户选择“先配置 Tavily Key，暂停任务”时，不调用任何购物工具；告诉用户在项目本地 .env 设置 TAVILY_API_KEY 并重启后端，之后新建对话再发起任务。
16. 用户选择“跳过商品发现，继续比价”时，不要再次调用 product_discovery_agent；根据原始需求和已有信息决定是否可以直接调用 price_comparison_agent，信息不足就先向用户提问，不编造型号或价格。

17. 比价工具返回的页面内容明显异常（一直显示“加载中”、空列表、没有商品区域、页面与商品无关），而你无法判断原因时，可以调用 open_platform_login 打开对应平台的有头登录窗口，请用户亲自检查是否遇到滑块验证或风控页面。

18. 打开登录窗口后，调用 request_user_input 等待用户处理并确认。用户确认后调用 close_platform_login 关闭窗口，然后重新搜索。不得在登录窗口打开时直接搜索（会报 BROWSER_BUSY）。

19. 用户表示已处理完验证、但选择不再继续该平台时，也要调用 close_platform_login 关闭窗口，再继续其他平台。"""


def build_coordinator(settings, browser, on_progress=None):
    registry = ToolRegistry()

    def discovery_preflight_error():
        """每次委托前重新读取配置。

        主 Agent 可能刚用 Edit 工具写入新的 TAVILY_API_KEY，
        这里先 reload 再判断，避免必须重启后端才能继续。
        """
        try:
            settings.reload()
        except Exception:
            pass
        if settings.tavily_api_key:
            return None
        return (
            "MISSING_API_KEY",
            "Tavily API Key 未配置；请在项目本地 .env 中设置 TAVILY_API_KEY 并重启后端。",
        )

    # 商品发现 Agent
    registry.register_tool(
        NamedTaskTool(
            name="product_discovery_agent",
            description="搜索真实商品候选和相关资料",
            agent_factory=lambda: build_discovery_agent(settings, on_progress=on_progress),
            preflight_error=discovery_preflight_error,
        )
    )

    # 平台比价 Agent
    registry.register_tool(
        NamedTaskTool(
            name="price_comparison_agent",
            description="逐平台查询真实报价并汇报工具错误；子 Agent 完成不代表每个平台都成功",
            agent_factory=lambda: build_comparison_agent(
                settings, browser, on_progress=on_progress
            ),
        )
    )

    # 推荐 Agent
    registry.register_tool(
        NamedTaskTool(
            name="recommendation_agent",
            description="根据真实证据推荐商品并计算预算",
            agent_factory=lambda: build_recommendation_agent(settings, on_progress=on_progress),
        )
    )

    # 主 Agent 与用户交互
    registry.register_tool(RequestUserInputTool())

    # 平台登录检查
    registry.register_tool(CheckPlatformLoginTool(browser))

    # 主 Agent 根据用户选择打开有头登录窗口
    registry.register_tool(OpenPlatformLoginTool(browser))

    # 用户处理完登录或验证后，关闭窗口才能继续搜索
    registry.register_tool(ClosePlatformLoginTool(browser))

    # 读写项目 .env：只允许这一个文件，不能访问代码或其他路径。
    # 写入后 product_search 会自行重载配置，无需重启后端。
    registry.register_tool(EnvReadTool(ENV_FILE))
    registry.register_tool(EnvEditTool(ENV_FILE))

    return create_agent(
        settings=settings,
        name="ShoppingCoordinatorAgent",
        system_prompt=SYSTEM_PROMPT,
        tool_registry=registry,
        max_steps=12,
        agent_class=InteractiveCoordinatorAgent,  # 只有主 Agent 提问后结束本轮
    )



