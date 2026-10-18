import time
from pathlib import Path
from urllib.parse import quote
from DrissionPage import ChromiumOptions, ChromiumPage
root=Path(__file__).resolve().parents[1]
co=ChromiumOptions().set_browser_path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe").set_user_data_path(str(root/'.edge-profile')).set_local_port(9224)
co.headless(True)
page=ChromiumPage(co)
try:
    url='https://s.taobao.com/search?q='+quote('iPhone 17 Pro 256GB')
    page.get(url); time.sleep(10)
    body=page.ele('tag:body').text
    cards=page.eles('css:a[class*="itemCard"]')
    print('url=',page.url)
    print('cards=',len(cards))
    print('captcha=',any(x in body.lower() for x in ('滑块','验证','captcha','访问异常')))
    print('excerpt=',body[:1200].encode('unicode_escape').decode('ascii'))
finally:
    page.quit()
