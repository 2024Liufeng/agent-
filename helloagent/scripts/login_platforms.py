import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")
PROFILE_DIR = Path(os.environ.get("PLAYWRIGHT_PROFILE_DIR", PROJECT_DIR / ".playwright-profile"))


def main() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        launch_options = {
            "headless": False,
            "no_viewport": True,
                        "chromium_sandbox": True,
            "locale": "zh-CN",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "args": ["--start-maximized", "--new-window"],
        }
        context = p.chromium.launch_persistent_context(str(PROFILE_DIR), channel="msedge", **launch_options)
        try:
            urls = {
                "京东": "https://www.jd.com/",
                "淘宝": "https://www.taobao.com/",
                "拼多多": "https://mobile.yangkeduo.com/",
            }
            for name, url in urls.items():
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                print(f"已打开{name}：{page.url}")
            print(f"请在浏览器中完成三个平台的登录。会话目录：{PROFILE_DIR}")
            input("全部登录完成后，回到终端按回车保存会话并退出：")
        finally:
            context.close()


if __name__ == "__main__":
    main()
