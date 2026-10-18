"""ShoppingAssistantAgent 的构建。"""

from __future__ import annotations

from hello_agents import HelloAgentsLLM, ReActAgent, ToolRegistry
from hello_agents.core.config import Config as HelloAgentsConfig

from .config import AppConfig, PROJECT_ROOT
from .memory import ShoppingMemoryService
from .subagents import build_delegation_tools


SYSTEM_PROMPT = """你是 ShoppingCoordinatorAgent，负责协调一个智能购物助手系统。

你的目标是帮助用户完成：
1. 模糊需求的商品发现和推荐；
2. 指定商品在京东、淘宝和拼多多的真实报价比较；
3. 多商品购物清单、数量和预算计算。

工作流程：
- 用户已经给出型号时，调用 price_comparison_agent 比较同一商品在三个平台的实际条件。
- 用户只有预算、用途或类别时，先调用 product_discovery_agent，再把候选商品交给 price_comparison_agent。
- 用户需要多件商品时，为每个类别组织发现和比价结果，再调用 recommendation_agent 生成清单并计算总预算。
- 最后必须调用 recommendation_agent 综合候选和报价，输出推荐、价格条件或购物清单。
- 子 Agent 的结果是证据和中间结论；你负责检查任务是否完整、补充缺失步骤并面向用户回答。
- 不能编造任何子 Agent 没有提供的价格、店铺、规格、链接或优惠。

输出应包含：需求理解、候选或报价、推荐理由、价格和购买条件、预算/清单，以及需要用户确认的事项。
"""


def build_agent(config: AppConfig, memory: ShoppingMemoryService) -> ReActAgent:
    llm = HelloAgentsLLM(
        model=config.llm_model_id,
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
    )
    registry = ToolRegistry()
    for tool in build_delegation_tools(config):
        registry.register_tool(tool)
    registry.register_tool(memory.semantic_tool)
    return ReActAgent(
        name="ShoppingAssistantAgent",
        llm=llm,
        tool_registry=registry,
        system_prompt=SYSTEM_PROMPT
        + "\nThe specialist agents are responsible for discovery, platform evidence, and recommendation. Preserve their evidence boundaries and never infer hidden prices or URLs.",
        max_steps=8,
        config=HelloAgentsConfig(
            tool_async_timeout=240,
            llm_async_timeout=240,
            max_concurrent_tools=3,
            trace_enabled=True,
            trace_dir=str(PROJECT_ROOT / "data" / "traces"),
            trace_sanitize=True,
        ),
    )
