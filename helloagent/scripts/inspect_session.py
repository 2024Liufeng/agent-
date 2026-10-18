from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(Path(__file__).resolve().parents[1] / ".playwright-profile"),
        headless=True,
    )
    cookies = ctx.cookies()
    for c in cookies:
        if any(x in c["domain"] for x in ("jd.com", "taobao.com", "tmall.com")):
            print(c["domain"], c["name"], c.get("expires"))
    ctx.close()
