"""把 HelloAgents 原生文件工具限制在项目配置目录内使用。

主 Agent 需要修改 .env（例如写入用户提供的密钥），
但通用文件工具不应具备改写代码或读取任意路径的能力。
"""

from pathlib import Path

from hello_agents.tools.builtin import EditTool, ReadTool


def _restrict(tool, allowed: Path):
    """包装原生工具：只允许访问指定的单个文件。"""

    original_run = tool.run

    def guarded_run(parameters):
        raw = str(parameters.get("path", "")).strip()
        if not raw:
            # 缺少 path 时交给原生工具返回标准参数错误。
            return original_run(parameters)

        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (tool.project_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if candidate != allowed.resolve():
            return tool._error_for_path(raw)

        return original_run(parameters)

    tool.run = guarded_run
    return tool


class EnvEditTool(EditTool):
    """只能编辑项目 .env 的 Edit 工具。"""

    def __init__(self, env_file: Path):
        super().__init__(project_root=env_file.parent)
        self.env_file = env_file.resolve()
        self.description = "精确替换项目 .env 中的内容（仅允许编辑 .env）"

    def _error_for_path(self, raw: str):
        from hello_agents.tools import ToolResponse

        return ToolResponse.error(
            "INVALID_PARAM", f"该工具只能编辑配置文件 .env，不能访问 {raw}"
        )

    def run(self, parameters):
        raw = str(parameters.get("path", "")).strip()
        if not raw:
            return super().run(parameters)

        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (self.project_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if candidate != self.env_file:
            return self._error_for_path(raw)
        return super().run(parameters)


class EnvReadTool(ReadTool):
    """只能读取项目 .env 的 Read 工具。"""

    def __init__(self, env_file: Path):
        super().__init__(project_root=env_file.parent)
        self.env_file = env_file.resolve()
        self.description = "读取项目 .env 配置内容（仅允许读取 .env）"

    def _error_for_path(self, raw: str):
        from hello_agents.tools import ToolResponse

        return ToolResponse.error(
            "INVALID_PARAM", f"该工具只能读取配置文件 .env，不能访问 {raw}"
        )

    def run(self, parameters):
        raw = str(parameters.get("path", "")).strip()
        if not raw:
            return super().run(parameters)

        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (self.project_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if candidate != self.env_file:
            return self._error_for_path(raw)
        return super().run(parameters)
