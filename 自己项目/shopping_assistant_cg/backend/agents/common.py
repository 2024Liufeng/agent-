from hello_agents import HelloAgentsLLM, ReActAgent
from hello_agents.core.config import Config

from backend.config import Settings


def create_agent(
    settings: Settings,
    name: str,
    system_prompt: str,
    tool_registry,
    max_steps: int = 8,
    agent_class=ReActAgent,  # 默认仍使用原生 ReActAgent
) -> ReActAgent:
    # 每个 Agent 拥有自己的 LLM 客户端和工具注册表
    llm = HelloAgentsLLM(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

    return agent_class(
        name=name,
        llm=llm,
        system_prompt=system_prompt,
        tool_registry=tool_registry,
        max_steps=max_steps,
        config=Config(
            tool_async_timeout=180,
            llm_async_timeout=180,
            trace_enabled=True,
        ),
    )
