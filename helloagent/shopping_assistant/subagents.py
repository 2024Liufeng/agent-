"""购物助手的专业子 Agent 和主 Agent 委托工具。"""

from __future__ import annotations

from typing import Any, Callable

from hello_agents import HelloAgentsLLM, ReActAgent, ToolRegistry
from hello_agents.core.config import Config as HelloAgentsConfig
from hello_agents.tools import TaskTool
from hello_agents.tools.builtin.calculator import CalculatorTool

from .config import AppConfig, PROJECT_ROOT
from .rag import ProductKnowledgeBase
from .tools import JDProductTool, PDDProductTool, ProductSearchTool, TaobaoProductTool
from .tools.drission_platform import ComparisonBrowserSession


def _agent_config(config: AppConfig, max_concurrent_tools: int = 1) -> HelloAgentsConfig:
    return HelloAgentsConfig(
        tool_async_timeout=90,
        llm_async_timeout=180,
        max_concurrent_tools=max_concurrent_tools,
        trace_enabled=True,
        trace_dir=str(PROJECT_ROOT / "data" / "traces"),
        trace_sanitize=True,
    )


class ComparisonReActAgent(ReActAgent):
    """Native HelloAgents sub-agent with a task-scoped browser session."""

    def run_as_subagent(self, task: str, tool_filter=None, return_summary: bool = True,
                        max_steps_override: int | None = None):
        with ComparisonBrowserSession(self._app_config) as session:
            for tool in self._comparison_tools:
                tool.session = session
            try:
                return super().run_as_subagent(task, tool_filter, return_summary, max_steps_override)
            finally:
                for tool in self._comparison_tools:
                    tool.session = None


class NamedTaskTool(TaskTool):
    """HelloAgents native TaskTool with a role-specific registry name."""

    def __init__(self, name: str, description: str, worker: ReActAgent):
        super().__init__(agent_factory=lambda _agent_type: worker)
        self.name = name
        self.description = description

    def run(self, parameters: dict[str, Any]):
        # The framework readonly filter only knows its built-in tool names.
        # These child agents are deliberately limited to their own registered
        # business tools, so do not let the parent filter them out.
        parameters = dict(parameters)
        parameters["tool_filter"] = "none"
        return super().run(parameters)


def _worker(config: AppConfig, name: str, prompt: str, registry: ToolRegistry, concurrency: int = 1, max_steps: int = 6, agent_cls=ReActAgent) -> ReActAgent:
    llm = HelloAgentsLLM(model=config.llm_model_id, api_key=config.llm_api_key, base_url=config.llm_base_url)
    worker = agent_cls(
        name=name,
        llm=llm,
        tool_registry=registry,
        system_prompt=prompt,
        max_steps=max_steps,
        config=_agent_config(config, concurrency),
    )
    worker._app_config = config
    return worker


def build_discovery_agent(config: AppConfig) -> ReActAgent:
    knowledge = ProductKnowledgeBase(config)
    registry = ToolRegistry()
    registry.register_tool(ProductSearchTool(config, knowledge))
    registry.register_tool(knowledge.tool)
    return _worker(
        config,
        "ProductDiscoveryAgent",
        """你是商品发现 Agent。根据主 Agent 给出的预算、用途、类别、品牌偏好和数量，调用 product_search 找到合适候选商品。需要稳定参数时使用 rag。输出候选型号、关键规格、适用理由和来源，不查询电商平台实时价格，也不要编造价格。多件商品需求要逐项列出候选。""",
        registry,
    )


def build_comparison_agent(config: AppConfig) -> ReActAgent:
    registry = ToolRegistry()
    platform_tools = [JDProductTool(config), TaobaoProductTool(config), PDDProductTool(config)]
    for tool in platform_tools:
        registry.register_tool(tool)
    worker = _worker(
        config,
        "PriceComparisonAgent",
        """你是平台比价 Agent。根据主 Agent 给出的明确商品型号和规格，必须对该商品调用京东、淘宝、拼多多三个搜索工具各一次。三个工具共享一个 Edge 浏览器但使用不同标签页，可以并行请求；不要自行扩展到其他容量、版本或多个搜索词，除非主 Agent 明确要求。任何平台失败都要标明原因并继续处理其他平台。平台工具返回 raw_page_text，你要从正文中提取商品标题、明确价格、规格、店铺、补贴、激活和购买条件。输出每个平台的报价证据，严禁猜测隐藏价格或链接。""",
        registry,
        concurrency=3,
        max_steps=3,
        agent_cls=ComparisonReActAgent,
    )
    worker._comparison_tools = platform_tools
    return worker


def build_recommendation_agent(config: AppConfig) -> ReActAgent:
    registry = ToolRegistry()
    registry.register_tool(CalculatorTool())
    return _worker(
        config,
        "RecommendationAgent",
        """你是推荐与购物清单 Agent。综合商品发现结果和三平台报价证据，先按相同型号、容量、版本和购买条件进行公平比较，再给出推荐。明确区分普通价、补贴价、到手价和需要激活的价格。多件商品需求要生成包含商品、数量、单价、平台、条件和小计的清单，并使用计算器核算总预算。只使用输入中明确提供的证据，无法确认的内容标记为未确认。""",
        registry,
    )


def build_delegation_tools(config: AppConfig) -> list[TaskTool]:
    # Use the framework's native TaskTool/run_as_subagent mechanism. Each role
    # gets a named TaskTool, while the child session remains isolated.
    discovery = build_discovery_agent(config)
    comparison = build_comparison_agent(config)
    recommendation = build_recommendation_agent(config)
    return [
        NamedTaskTool("product_discovery_agent", "??????? Agent??????????????", discovery),
        NamedTaskTool("price_comparison_agent", "????? Agent??????????????", comparison),
        NamedTaskTool("recommendation_agent", "????? Agent???????????????", recommendation),
    ]
