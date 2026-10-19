"""Continue an Agent answer from an existing trace without rerunning browsers."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shopping_assistant.agent import build_agent
from shopping_assistant.config import AppConfig
from shopping_assistant.memory import ShoppingMemoryService


def main():
    root = Path(__file__).resolve().parents[1]
    traces = sorted((root / "data" / "traces").glob("trace-*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not traces:
        raise SystemExit("没有找到已有 trace")
    trace = traces[-1]
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    evidence = []
    for event in events:
        if event.get("event") != "tool_result":
            continue
        payload = event.get("payload", {})
        if payload.get("name") in {"jd_product_search", "taobao_product_search", "pdd_product_search"}:
            evidence.append({
                "step": event.get("step"),
                "tool": payload.get("name"),
                "result": payload.get("result", ""),
            })
    prompt = """这是一次续接任务。不要调用任何工具，也不要重新搜索平台。
请严格使用下面已有的用户需求和工具结果，继续完成同一套购物比价分析。
淘宝结果已经可以使用；京东和拼多多结果包含标题及页面正文提取结果，但字段可能不完整。
只报告证据中明确出现的价格、商品名和链接；缺失就写‘未提取到’，不要猜测。
请输出清晰的三平台对比，并说明哪些结果需要人工打开页面核对。

用户原始需求：搜索苹果18promax并比较淘宝、京东、拼多多价格。

已有工具结果：
""" + json.dumps(evidence, ensure_ascii=False, indent=2)
    config = AppConfig.from_env()
    memory = ShoppingMemoryService(config.memory_db, config.user_id)
    agent = build_agent(config, memory)
    print(agent.run(prompt))


if __name__ == "__main__":
    main()
