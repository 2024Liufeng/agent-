import os

from typing_extensions import Annotated, TypedDict

from langchain_core.documents import Document
from langchain_deepseek import ChatDeepSeek


os.environ["DEEPSEEK_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")


class GroundedGrade(TypedDict):
    # 先解释为什么给出这个判断。
    explanation: Annotated[
        str,
        ...,
        "解释评分理由",
    ]

    # 判断回答是否根据文档生成，
    # 是否包含文档之外的幻觉信息。
    grounded: Annotated[
        bool,
        ...,
        "回答是否基于文档，是否存在幻觉",
    ]


grounded_instructions = """
你是一名负责批改测验的老师。

你将收到：
1. FACTS：检索到的事实资料。
2. STUDENT ANSWER：需要检查的回答。

请按照以下标准评分：

1. 确保 STUDENT ANSWER 的内容以 FACTS 为依据。
2. 确保 STUDENT ANSWER 不包含超出 FACTS 范围的幻觉信息。

Grounded 判断：

- grounded 为 True，表示回答符合以上所有标准。
- grounded 为 False，表示回答不符合以上标准。

请逐步解释你的判断理由，确保推理和最终结论正确。
不要一开始就直接给出最终判断。
"""


grounded_llm = ChatDeepSeek(
    model="deepseek-v4-flash",
    temperature=0,
    extra_body={
        "thinking": {
            "type": "disabled",
        }
    },
).with_structured_output(
    GroundedGrade,
    method="json_schema",
    strict=True,
)


def evaluate_groundedness(
    answer: str,
    documents: list[Document],
) -> GroundedGrade:
    """评估 RAG 报告是否以检索文档为依据。"""
    # 取出所有检索文档的正文，
    # 使用两个换行符拼接成完整事实资料。
    doc_string = "\n\n".join(
        doc.page_content
        for doc in documents
    )

    # 把检索资料和待验证报告一起交给评分模型。
    content = (
        f"FACTS: {doc_string}\n"
        f"STUDENT ANSWER: {answer}"
    )

    # 返回完整评分，让调用者同时取得判断和理由。
    return grounded_llm.invoke([
        {
            "role": "system",
            "content": grounded_instructions,
        },
        {
            "role": "user",
            "content": content,
        },
    ])
