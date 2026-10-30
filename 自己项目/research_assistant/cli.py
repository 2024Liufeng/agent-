import argparse
import asyncio
import json
import sys
import uuid

from agent import DSResearcher
from skills.chat import ChatAgentWithMemory
from skills.groundedness_guard import evaluate_groundedness
from tools.file import save_report


cli = argparse.ArgumentParser(
    description="生成资料研究报告。",
)

cli.add_argument(
    "query",
    type=str,
    help="要研究的主题或问题。",
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def main(args) -> None:
    thread_id = str(uuid.uuid4())

    researcher = DSResearcher(
        query=args.query,
        thread_id=thread_id,
        user_id="1",
    )

    print(f"Thread ID: {thread_id}")

    await researcher.conduct_research()

    if not researcher.research_sources:
        print("没有收集到可用于生成答案的网页正文资料。")
        return

    if not researcher.context:
        print("没有检索到和主题足够相关的资料片段。")
        return

    report = researcher.write_report()

    grounded_grade = evaluate_groundedness(
        report,
        researcher.context,
    )

    if not grounded_grade["grounded"]:
        print("生成答案未通过来源一致性校验，请重新搜索或补充资料。")
        print(f"校验理由：{grounded_grade['explanation']}")
        return

    # 根据用户问题和报告预览生成简短标题。
    title = researcher.generate_report_title(
        report
    )

    # 保存工具会自动处理同名文件。
    report_path = save_report.invoke({
        "title": title,
        "content": report,
    })

    print(f"报告已保存：{report_path}")
    print(report)

    chat_agent = ChatAgentWithMemory(report=report)

    while True:
        message = input("\n继续提问，输入 exit 结束：").strip()

        if message == "exit":
            break

        if not message:
            continue

        ai_message, tool_calls_metadata = await chat_agent.chat(
            messages=[
                {
                    "role": "user",
                    "content": message,
                }
            ],
            thread_id=thread_id,
            user_id=researcher.user_id,
        )

        if tool_calls_metadata:
            print(
                "Tool calls used: "
                f"{json.dumps(tool_calls_metadata, ensure_ascii=False)}"
            )

        print(ai_message)


if __name__ == "__main__":
    args = cli.parse_args()
    asyncio.run(main(args))
