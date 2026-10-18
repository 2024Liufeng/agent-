from pathlib import Path
from playwright.sync_api import sync_playwright
profile=Path("C:/Users/小敏/PycharmProjects/SpiderAgent/helloagent/.edge-profile")
with sync_playwright() as p:
    c=p.chromium.launch_persistent_context(str(profile), channel="msedge", headless=True, locale="zh-CN")
    for url in ["https://taobao.com", "https://jd.com", "https://yangkeduo.com"]:
        cs=c.cookies(url)
        print(url, len(cs), sorted({x["name"] for x in cs})[:30])
    c.close()
