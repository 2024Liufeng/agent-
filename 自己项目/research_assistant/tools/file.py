from pathlib import Path

from langchain.tools import tool


OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "outputs"
)


def resolve_unique_path(
    output_dir: Path,
    title: str,
) -> Path:
    # 第一次保存使用：标题.md。
    report_path = output_dir / f"{title}.md"

    if not report_path.exists():
        return report_path

    # 已存在时依次使用：标题_2.md、标题_3.md……
    index = 2

    while True:
        report_path = (
            output_dir
            / f"{title}_{index}.md"
        )

        if not report_path.exists():
            return report_path

        index += 1


@tool
def save_report(
    title: str,
    content: str,
) -> str:
    """把验证通过的研究报告保存为 Markdown 文件。"""
    # 所有报告只能保存在项目的 outputs 目录中。
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 根据标题寻找一个尚未使用的 Markdown 文件路径。
    report_path = resolve_unique_path(
        OUTPUT_DIR,
        title,
    )
    report_path.write_text(
        content,
        encoding="utf-8",
    )

    return str(report_path)
