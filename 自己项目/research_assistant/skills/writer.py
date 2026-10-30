import os

from langchain_core.documents import Document
from langchain_deepseek import ChatDeepSeek


os.environ["DEEPSEEK_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")

model = ChatDeepSeek(
    model="deepseek-v4-flash",
    temperature=0,
)


def pretty_print_docs(retrieved_docs: list[Document]) -> str:
    return "\n\n".join(
        f"Title: {doc.metadata.get('title', '')}\n"
        f"URL: {doc.metadata.get('source', '未知来源')}\n"
        f"Content: {doc.page_content}"
        for doc in retrieved_docs
    )


class ReportGenerator:
    def __init__(self, researcher):
        self.researcher = researcher

    def generate_title(
        self,
        report: str,
    ) -> str:
        # 只把报告前 600 个字符交给模型，
        # 避免为了生成文件名重复传入整份报告。
        report_preview = (report or "")[:600]
        prompt = (
            "你是图书管理员。请为下面的研究报告生成一个简短标题，"
            "标题最多 20 个字符，并与用户问题使用相同语言。\n"
            "标题将作为文件名，因此：\n"
            "- 不要使用引号、括号或标点包裹标题\n"
            "- 不要添加前缀、后缀或解释\n"
            "- 只用一行输出标题\n\n"
            f"用户问题：\n{self.researcher.query}\n\n"
            f"报告预览：\n{report_preview}\n\n"
            "标题："
        )

        try:
            response = model.invoke([
                {
                    "role": "system",
                    "content": "只输出简短标题，不要输出其他内容。",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ])

            # 去掉模型偶尔添加的引号、书名号和多余换行。
            title = (
                response.content
                .strip()
                .strip('"')
                .strip("'")
                .strip("《》")
                .splitlines()[0]
                .strip()
            )

            return title or self.researcher.query

        except Exception:
            # 标题生成失败不应阻止报告保存，
            # 因此退回使用原始研究问题。
            return self.researcher.query

    def write_report(self) -> str:
        docs_content = pretty_print_docs(self.researcher.context)
        prompt = f"""
你是资料研究助手的写作阶段。

请基于下面的上下文回答用户主题。

要求：
1. 只能使用上下文中的信息，不要编造事实、数据、URL。
2. 正文使用 [1]、[2]、[3] 格式内联引用。
3. 每个唯一 URL 只分配一个引用编号。
4. 引用编号必须连续，不能跳号。
5. 回答末尾必须包含 ### Sources。
6. 来源格式：[编号] 来源标题: URL，每个来源单独一行。
7. 如果上下文不足以回答，请明确说明资料不足。

用户主题：
{self.researcher.query}

上下文：
{docs_content}
"""
        return model.invoke(prompt).content
