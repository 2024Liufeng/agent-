from hello_agents import ToolRegistry

from backend.agents.common import create_agent
from backend.tools.product_search import TavilySearchTool
from backend.tools.progress_tool import ProgressTool


SYSTEM_PROMPT = """
你是 ProductDiscoveryAgent，负责商品发现。

根据用户的预算、用途和偏好，通过真实 Tavily 搜索商品。

执行规则（必须遵守）：
1. 只要任务需要搜索商品资料，第一步必须调用已注册的 product_search 工具；不得只根据记忆回答。
2. product_search 已经注册。不得在没有实际调用并核实工具结果前，声称工具未挂载、工具列表为空或缺少 HTTP 工具。
3. 返回商品名称、型号、规格及信息来源；不编造价格或搜索结果。
4. 如果 product_search 返回 status=error，必须把工具返回的真实错误传回主 Agent；尤其 MISSING_API_KEY 必须明确报告“Tavily API Key 未配置”，不得猜测为工具未注册。
5. Tavily 配额不足、认证失败或 Key 缺失时，如实传递对应错误，不伪造搜索结果。
6. 不替主 Agent 决定是否询问用户。
"""


def build_discovery_agent(settings, on_progress=None):
    registry = ToolRegistry()

    tool = TavilySearchTool(settings)  # 原来的真实 Tavily 工具
    if on_progress is not None:
        tool = ProgressTool(tool, "ProductDiscoveryAgent", on_progress)
    registry.register_tool(tool)

    return create_agent(
        settings=settings,
        name="ProductDiscoveryAgent",
        system_prompt=SYSTEM_PROMPT,
        tool_registry=registry,
    )
