"""命令行入口：python -m shopping_assistant"""

from __future__ import annotations

import os
import sys

from .config import AppConfig
from .service import ShoppingAssistantService


def main() -> None:
    # hello-agents prints Unicode status markers during tool registration;
    # keep the Windows console from failing under the legacy GBK code page.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    user_id = os.getenv("SHOPPING_USER_ID", "default-user")
    service = ShoppingAssistantService(AppConfig.from_env(user_id))
    print("智能购物助手已启动，输入 exit 或 quit 退出。")
    while True:
        try:
            user_input = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.lower() in {"exit", "quit", "退出"}:
            break
        if not user_input:
            continue
        try:
            print(f"\n助手：{service.ask(user_input)}")
        except Exception as exc:
            print(f"\n助手：本次任务执行失败：{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
