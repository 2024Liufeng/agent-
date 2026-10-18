import re
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE = Path(__file__).resolve().parents[1] / ".playwright-profile"
URLS = {
    "京东": "https://search.jd.com/Search?keyword=iPhone%2018%20Pro%20256GB",
    "淘宝": "https://s.taobao.com/search?q=iPhone%2018%20Pro%20256GB",
}

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        str(PROFILE),
        headless=False,
        proxy={"server": "socks5://127.0.0.1:1080"},
        locale="zh-CN",
        viewport={"width": 1440, "height": 1000},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    )
    try:
        for name, url in URLS.items():
            page = context.new_page()
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(15000)
                body = page.locator("body").inner_text(timeout=15000)
                prices = sorted(set(re.findall(r"[¥￥]\s*[0-9][0-9,]*(?:\.[0-9]{1,2})?", body)))
                print(f"\n===== {name} =====")
                print(f"status={response.status if response else 'n/a'}")
                print(f"title={page.title()}")
                print(f"url={page.url}")
                print(f"prices={prices[:50]}")
                print(body[:8000].replace("\x00", " "))
            except Exception as exc:
                print(f"\n===== {name} ERROR =====\n{type(exc).__name__}: {exc}")
            finally:
                page.close()
    finally:
        context.close()
