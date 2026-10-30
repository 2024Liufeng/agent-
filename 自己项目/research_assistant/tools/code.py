from langchain.tools import tool
from langchain_experimental.utilities import PythonREPL


python_repl = PythonREPL()


@tool
def code_execution(code: str) -> str:
    """执行 Python 代码，用于精确计算、统计和数据处理。
    使用 print(...) 输出需要返回的结果。
    """
    return python_repl.run(code)
