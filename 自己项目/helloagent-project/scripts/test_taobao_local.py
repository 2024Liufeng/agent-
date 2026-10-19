import re
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
profile = Path("C:/Users/小敏/PycharmProjects/SpiderAgent/helloagent/.edge-profile")
query = "iPhone 17 Pro 256GB"
url = "https://s.taobao.com/search?q=" + query.replace(" ", "%20")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        str(profile), channel="msedge", headless=True,
        locale="zh-CN", viewport={"width": 1440, "height": 1000},
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"),
    )
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)
        body = page.locator("body").inner_text(timeout=20000)
        cards = page.locator('a[class*="itemCard"], a[href*="detail.tmall.com/item"], a[href*="item.taobao.com/item"]')
        print(f"status={response.status if response else 'n/a'}")
        print(f"title={page.title()}")
        print(f"url={page.url}")
        print(f"body_chars={len(body)}")
        print(f"product_card_count={cards.count()}")
        print("body_excerpt=" + body[:3000].encode("unicode_escape").decode("ascii"))
        for i in range(min(cards.count(), 5)):
            card = cards.nth(i)
            print(f"card_{i+1}=" + " ".join(card.inner_text(timeout=5000).split())[:500].encode("unicode_escape").decode("ascii"))
    finally:
        page.close()
        context.close()
