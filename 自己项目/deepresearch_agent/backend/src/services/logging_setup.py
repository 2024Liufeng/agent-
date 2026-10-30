"""统一记录服务日志：控制台方便观察，文件方便事后排查。"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_research_configured", False):
        return
    log_dir = Path(__file__).resolve().parents[3] / ".runtime" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    # 框架导入时可能已调用 basicConfig，替换默认处理器以免同一条日志重复输出。
    root.handlers.clear()
    console = logging.StreamHandler()
    file = RotatingFileHandler(
        log_dir / "research.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    for handler in (console, file):
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    # 第三方 HTTP 日志不参与研究进度，避免输出无关请求细节。
    for name in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    root._research_configured = True
