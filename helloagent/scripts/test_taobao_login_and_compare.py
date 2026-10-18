from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".edge-profile"
QUERY = "iPhone 17 Pro 256GB"
URL = "https://s.taobao.com/search?q=" + quote(QUERY)


def inspect_result(page):
    body = page.locator("body").inner_text(timeout=20000)
    cards = page.locator(
        'a[class*="itemCard"], a[href*="detail.tmall.com/item"], '
        'a[href*="item.taobao.com/item"]'
    )
    captcha_markers = ("滑块", "验证", "captcha", "访问异常", "安全验证")
    captcha = any(marker.lower() in body.lower() for marker in captcha_markers)
    print(f"搜索地址：{page.url}")
    print(f"商品卡片数量：{cards.count()}")
    print(f"检测到验证页面：{captcha}")
    print("页面摘要：" + body[:1200].encode("unicode_escape").decode("ascii"))
    return captcha, cards.count()


with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        str(PROFILE), channel="msedge", headless=False, chromium_sandbox=True, no_viewport=True, locale="zh-CN",
        args=["--start-maximized", "--new-window"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://www.taobao.com/", wait_until="domcontentloaded", timeout=60000)
    print("淘宝已打开。请在这个 Edge 窗口中完成登录。")
    input("登录完成后回到终端按回车：")
    cookies = context.cookies("https://taobao.com")
    print(f"淘宝 Cookie 数量：{len(cookies)}")
    if not cookies:
        print("未检测到淘宝 Cookie，本次不进行比价。")
    else:
        search = context.new_page()
        response = search.goto(URL, wait_until="domcontentloaded", timeout=60000)
        search.wait_for_timeout(12000)
        print(f"搜索状态：{response.status if response else 'n/a'}")
        captcha, count = inspect_result(search)
        if captcha or count == 0:
            input("请在浏览器中手动完成滑块/安全验证，完成后回终端按回车重试：")
            search.reload(wait_until="domcontentloaded", timeout=60000)
            search.wait_for_timeout(12000)
            print("重试结果：")
            inspect_result(search)
        input("查看结果后按回车退出：")
        search.close()
    context.close()
