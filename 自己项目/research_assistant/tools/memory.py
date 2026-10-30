import uuid

from langchain.tools import ToolRuntime, tool

from memory.long_term.context import Context


@tool
async def save_user_memory(
    memory: str,
    runtime: ToolRuntime[Context],
) -> str:
    """当用户明确要求记住长期有效的信息或研究偏好时，保存这条记忆。"""
    user_id = runtime.context.user_id
    namespace = (user_id, "memories")

    await runtime.store.aput(
        namespace,
        str(uuid.uuid4()),
        {"data": memory},
    )
    return "已保存这条用户长期记忆。"
