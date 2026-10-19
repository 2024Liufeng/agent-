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
        url = "https://so.m.jd.com/ware/search.action?keyword=iPhone%2018%20Pro%20256GB"
        r = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(12000)
        print("status", r.status if r else None)
        print("title", page.title())
        print("url", page.url)
        print(page.locator("body").inner_text(timeout=15000)[:10000])
    except Exception as e:
        print(type(e).__name__, e)
    finally:
        c.close()
