import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright


PROFILE_DIR = Path(__file__).resolve().parents[1] / ".playwright-profile"
QUERY = "iPhone 18 Pro 256GB"
URLS = {
    "京东": "https://search.jd.com/Search?keyword=iPhone%2018%20Pro%20256GB",
    "淘宝": "https://s.taobao.com/search?q=iPhone%2018%20Pro%20256GB",
}


def main() -> None:
    proxy_url = os.environ.get("PLAYWRIGHT_PROXY", "socks5://127.0.0.1:1080")
    with sync_playwright() as p:
        device = p.devices["iPhone 15 Pro"]
        context = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            proxy={"server": proxy_url},
            locale="zh-CN",
            user_agent=device["user_agent"],
            viewport=device["viewport"],
            device_scale_factor=device["device_scale_factor"],
            is_mobile=device["is_mobile"],
            has_touch=device["has_touch"],
        )
        try:
            for name, url in URLS.items():
                page = context.new_page()
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(8000)
                    body = page.locator("body").inner_text(timeout=10000)
                    prices = sorted(set(re.findall(r"[¥￥]\s*[0-9][0-9,]*(?:\.[0-9]{1,2})?", body)))
                    print(f"\n===== {name} =====")
                    print(f"status={response.status if response else 'n/a'}")
                    print(f"title={page.title()}")
                    print(f"url={page.url}")
                    print(f"prices={prices[:30]}")
                    print(body[:5000].replace("\x00", " "))
                except Exception as exc:
                    print(f"\n===== {name} ERROR =====\n{type(exc).__name__}: {exc}")
                finally:
                    page.close()
        finally:
            context.close()


if __name__ == "__main__":
    main()
