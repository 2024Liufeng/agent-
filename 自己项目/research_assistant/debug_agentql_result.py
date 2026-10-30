import json
import os
import sys

from langchain_agentql.tools import ExtractWebDataTool


os.environ["AGENTQL_API_KEY"] = os.environ.get("AGENTQL_API_KEY", "")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python debug_agentql_result.py <url>")
        raise SystemExit(1)

    tool = ExtractWebDataTool()
    result = tool.invoke(
        {
            "url": sys.argv[1],
            "prompt": "Extract the main title and main readable article content from this page.",
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
