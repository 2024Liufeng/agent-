from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    d = p.devices["iPhone 15 Pro"]
    c = p.chromium.launch_persistent_context(
        str(Path(__file__).resolve().parents[1] / ".playwright-profile"),
        headless=False,
        proxy={"server": "socks5://127.0.0.1:1080"},
        locale="zh-CN",
        user_agent=d["user_agent"],
        viewport=d["viewport"],
        device_scale_factor=d["device_scale_factor"],
        is_mobile=d["is_mobile"],
        has_touch=d["has_touch"],
    )
    page = c.new_page()
    try:
        page.goto("https://m.taobao.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(8000)
        print("home", page.url, page.title())
        print(page.locator("body").inner_text(timeout=15000)[:5000])
        search_text = page.get_by_text("搜索", exact=True).first
        print("search_text_count", search_text.count())
        if search_text.count():
            search_text.click(force=True)
            page.wait_for_timeout(3000)
            print("after_click", page.url, page.title())
            print(page.locator("body").inner_text(timeout=15000)[:4000])
        inputs = page.locator("input")
        print("inputs", inputs.count())
        for i in range(inputs.count()):
            el = inputs.nth(i)
            print(i, el.get_attribute("placeholder"), el.get_attribute("type"))
        target = page.locator("input").first
        if target.count():
            target.fill("iPhone 18 Pro 256GB")
            target.press("Enter")
            page.wait_for_timeout(12000)
            print("search", page.url, page.title())
            print(page.locator("body").inner_text(timeout=15000)[:12000])
    except Exception as e:
        print(type(e).__name__, e)
    finally:
        c.close()
