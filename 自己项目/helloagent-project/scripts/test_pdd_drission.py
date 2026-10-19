import time
from pathlib import Path
from urllib.parse import quote
from DrissionPage import ChromiumOptions, ChromiumPage

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".edge-profile"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
QUERY = "iPhone 17 Pro 256GB"
URL = "https://mobile.yangkeduo.com/search_result.html?search_key=" + quote(QUERY)

co = ChromiumOptions()
co.set_browser_path(str(EDGE))
co.set_user_data_path(str(PROFILE))
co.set_local_port(9225)
co.headless(False)
co.set_argument("--start-maximized")
page = ChromiumPage(co)
try:
    page.get(URL)
    time.sleep(12)
    body = page.ele("tag:body").text
    print(f"拼多多已打开：{page.url}")
    print("页面摘要：" + body[:1800].encode("unicode_escape").decode("ascii"))
    markers = ("滑块", "安全验证", "访问异常", "captcha", "登录")
    if any(x.lower() in body.lower() for x in markers):
        input("如出现登录或验证，请在浏览器中手动完成，完成后回终端按回车重试：")
        page.refresh()
        time.sleep(12)
        body = page.ele("tag:body").text
    print("重试/最终摘要：" + body[:2500].encode("unicode_escape").decode("ascii"))
    input("查看结果后按回车退出：")
finally:
    page.quit()
