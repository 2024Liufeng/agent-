from hello_agents.tools import TaskTool, ToolResponse


class NamedTaskTool(TaskTool):
    """给不同子 Agent 提供明确的工具名称，并支持必需配置预检。

    preflight_error 可以是 (code, message) 元组，也可以是无参函数。
    传入函数时会**每次调用前重新求值**，这样主 Agent 运行中改写 .env
    之后，下一次委托就能立即通过预检，不必重启后端。
    """

    def __init__(self, name, description, agent_factory, preflight_error=None):
        # 使用 HelloAgents 原生 TaskTool。
        super().__init__(
            agent_factory=lambda agent_type: agent_factory(),
        )

        self.name = name
        self.description = description
        self._preflight_error = preflight_error

    def _current_error(self):
        """返回当前的预检错误；callable 表示需要动态判断。"""
        source = self._preflight_error
        if callable(source):
            try:
                source = source()
            except Exception:
                # 预检自身异常时放行，由子 Agent 暴露真实错误。
                return None
        return source

    def run(self, parameters):
        # 确定性的配置缺失不应交给模型猜测，也不应启动注定无法工作的子 Agent。
        error = self._current_error()
        if error is not None:
            code, message = error
            response = ToolResponse.error(code=code, message=message)
            # Preserve machine-readable error metadata for the coordinator and UI.
            response.data = {"code": code, "message": message, "fatal": True}
            return response
        return super().run(parameters)
