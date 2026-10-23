"""主 Agent 通用结构化提问工具；不做购物决策。"""

from typing import Any

from hello_agents.tools import Tool, ToolParameter, ToolResponse


class RequestUserInputTool(Tool):
    def __init__(self):
        super().__init__(
            "request_user_input",
            "向用户提出问题；调用后本轮应结束并等待回复",
        )

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="question", type="string",
                          description="需要用户回答的问题"),
            ToolParameter(name="kind", type="string",
                          description="choice / text / confirmation",
                          required=False, default="text"),
            ToolParameter(
                name="options", type="array",
                description="选项列表，每项包含 id 和 label",
                required=False,
                json_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "label": {"type": "string"},
                        },
                        "required": ["id", "label"],
                    },
                },
            ),
        ]

    def run(self, parameters: dict[str, Any]) -> ToolResponse:
        question = str(parameters.get("question", "")).strip()
        kind = str(parameters.get("kind", "text")).strip().lower()
        options = parameters.get("options") or []

        if not question or len(question) > 800:
            return ToolResponse.error(
                "INVALID_PARAM", "question 必须在 1～800 字以内"
            )
        if kind not in {"choice", "text", "confirmation"}:
            return ToolResponse.error("INVALID_PARAM", "不支持的输入类型")
        if not isinstance(options, list) or len(options) > 8:
            return ToolResponse.error(
                "INVALID_PARAM", "选项必须是不超过 8 项的列表"
            )
        if any(
            not isinstance(item, dict)
            or not str(item.get("id", "")).strip()
            or not str(item.get("label", "")).strip()
            for item in options
        ):
            return ToolResponse.error(
                "INVALID_PARAM", "选项必须包含 id 和 label"
            )
        if kind == "choice" and not options:
            return ToolResponse.error(
                "INVALID_PARAM", "选择题必须提供选项"
            )

        return ToolResponse.success(
            "已向用户请求输入，请结束本轮等待用户回复",
            data={
                "question": question,  # 一个对话同时只保存一个待回答的问题

                "kind": kind,
                "options": [
                    {"id": str(item["id"]).strip(),
                     "label": str(item["label"]).strip()}
                    for item in options
                ],
            },
        )
