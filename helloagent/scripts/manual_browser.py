import time
import os
from pathlib import Path
from playwright.sync_api import sync_playwright


def open_with_retry(page, url: str) -> None:
    """代理短暂断开时等待恢复，不让浏览器进程退出导致远程黑屏。"""
    while True:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return
        except Exception as exc:
            print(
                f"页面暂时无法打开，将在 5 秒后重试: {type(exc).__name__}: {exc}",
                flush=True,
            )
            time.sleep(5)


with sync_playwright() as p:
    d = p.devices["iPhone 15 Pro"]
    context = p.chromium.launch_persistent_context(
        str(Path(__file__).resolve().parents[1] / ".playwright-profile"),
        headless=False,
        args=[
            f"--remote-debugging-port={os.getenv('PLAYWRIGHT_CDP_PORT', '19222')}"
        ],
        proxy={"server": "socks5://127.0.0.1:1080"},
        locale="zh-CN",
        user_agent=d["user_agent"],
        viewport=d["viewport"],
        device_scale_factor=d["device_scale_factor"],
        is_mobile=d["is_mobile"],
        has_touch=d["has_touch"],
    )
    taobao = context.pages[0] if context.pages else context.new_page()
    open_with_retry(taobao, "https://main.m.taobao.com/")
    jd = context.new_page()
    open_with_retry(jd, "https://so.m.jd.com/ware/search.action?keyword=iPhone%2018%20Pro%20256GB")
    print("远程浏览器已打开，保持此进程运行。")
    while True:
        time.sleep(60)
