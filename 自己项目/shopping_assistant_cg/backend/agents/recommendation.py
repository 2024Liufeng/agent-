from hello_agents import ToolRegistry
from hello_agents.tools.builtin.calculator import CalculatorTool

from backend.agents.common import create_agent
from backend.tools.progress_tool import ProgressTool


SYSTEM_PROMPT = """
你是 RecommendationAgent，负责购物推荐和清单。

要求：
1. 只根据已有真实证据推荐商品。
2. 比较相同型号和规格。
3. 综合预算、用途、优惠和购买条件。
4. 需要计算价格时使用 Calculator。
5. 不能编造价格、商品和购买链接。
6. 证据不足时明确报告。
"""


def build_recommendation_agent(settings, on_progress=None):
    registry = ToolRegistry()

    tool = CalculatorTool()  # 保留 HelloAgents 原生计算器
    if on_progress is not None:
        tool = ProgressTool(tool, "RecommendationAgent", on_progress)
    registry.register_tool(tool)

    return create_agent(
        settings=settings,
        name="RecommendationAgent",
        system_prompt=SYSTEM_PROMPT,
        tool_registry=registry,
    )
