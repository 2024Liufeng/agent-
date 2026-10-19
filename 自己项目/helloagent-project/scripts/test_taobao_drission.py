import time
from pathlib import Path
from urllib.parse import quote
from DrissionPage import ChromiumOptions, ChromiumPage

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".edge-profile"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
QUERY = "iPhone 17 Pro 256GB"
URL = "https://s.taobao.com/search?q=" + quote(QUERY)

co = ChromiumOptions()
co.set_browser_path(str(EDGE))
co.set_user_data_path(str(PROFILE))
co.set_local_port(9223)
co.headless(False)
co.set_argument("--start-maximized")
page = ChromiumPage(co)
try:
    page.get("https://www.taobao.com/")
    time.sleep(5)
    print(f"淘宝已打开：{page.url}")
    input("如果需要登录，请在这个 Edge 窗口完成；完成后回终端按回车：")
    page.get(URL)
    time.sleep(12)
    body = page.ele("tag:body").text
    cards = page.eles('css:a[class*="itemCard"]')
    markers = ("滑块", "安全验证", "访问异常", "captcha")
    has_captcha = any(x.lower() in body.lower() for x in markers)
    print(f"搜索地址：{page.url}")
    print(f"商品卡片数量：{len(cards)}")
    print(f"检测到验证页面：{has_captcha}")
    print("页面摘要：" + body[:1500].encode("unicode_escape").decode("ascii"))
    if has_captcha or not cards:
        input("请在浏览器中手动完成验证，完成后回终端按回车重试：")
        page.refresh()
        time.sleep(12)
        body = page.ele("tag:body").text
        cards = page.eles('css:a[class*="itemCard"]')
        print(f"重试后商品卡片数量：{len(cards)}")
        print("重试摘要：" + body[:1500].encode("unicode_escape").decode("ascii"))
    input("查看结果后按回车退出：")
finally:
    page.quit()
