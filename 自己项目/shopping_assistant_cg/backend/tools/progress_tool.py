"""通用工具进度包装：只报告开始/结束，不修改真实工具结果。"""

from typing import Callable

from hello_agents.tools import Tool, ToolResponse


class ProgressTool(Tool):
    """保留原工具名称和参数，将真实执行状态发送给指定对话。"""

    def __init__(self, tool: Tool, agent_name: str, on_progress: Callable[[dict], None]):
        super().__init__(tool.name, tool.description)
        self.tool = tool                     # 例如真正的 jd_product_search 工具
        self.agent_name = agent_name         # 例如 PriceComparisonAgent
        self.on_progress = on_progress       # 来自该对话 ProgressReporter.emit

    def get_parameters(self):
        return self.tool.get_parameters()  # LLM 工具参数完全不变

    def run(self, parameters: dict) -> ToolResponse:
        self.on_progress({
            "type": "tool_started",
            "agent": self.agent_name,
            "tool": self.name,
            "text": f"{self.name} 开始执行",
        })

        try:
            response = self.tool.run(parameters)  # 调用原有真实工具
        except Exception:
            # 保持原异常语义，让 HelloAgents 的工具层按原协议处理。
            self.on_progress({
                "type": "tool_completed",
                "agent": self.agent_name,
                "tool": self.name,
                "status": "error",
                "text": f"{self.name} 执行异常",
            })
            raise

        self.on_progress({
            "type": "tool_completed",
            "agent": self.agent_name,
            "tool": self.name,
            "status": response.status.value,  # success / partial / error
            "text": f"{self.name} 执行结束：{response.status.value}",
        })
        return response  # 结果原封不动交给子 Agent，由框架负责截断
