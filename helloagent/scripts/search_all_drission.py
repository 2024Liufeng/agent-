import time
from pathlib import Path
from urllib.parse import quote

from DrissionPage import ChromiumOptions, ChromiumPage

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / '.drission-edge-profile'
EDGE = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
QUERY = '苹果18promax'


def main():
    co = ChromiumOptions()
    co.set_browser_path(str(EDGE))
    co.set_user_data_path(str(PROFILE))
    co.set_local_port(9232)
    co.headless(False)
    co.set_argument('--start-maximized')
    page = ChromiumPage(co)
    urls = [
        ('淘宝', 'https://s.taobao.com/search?q=' + quote(QUERY)),
        ('京东', 'https://search.jd.com/Search?keyword=' + quote(QUERY)),
        ('拼多多', 'https://mobile.yangkeduo.com/search_result.html?search_key=' + quote(QUERY)),
    ]
    try:
        tabs = []
        for name, url in urls:
            tab = page if not tabs else page.new_tab(url)
            if not tabs:
                tab.get(url)
            tabs.append((name, tab))
            time.sleep(8)
        for name, tab in tabs:
            tab.set.activate()
            time.sleep(1)
            body = tab.ele('tag:body').text
            low = body.lower()
            markers = ('滑块', '安全验证', '访问异常', '验证码', 'captcha')
            print(f'[{name}] URL: {tab.url}')
            print(f'[{name}] 验证提示: {any(x.lower() in low for x in markers)}')
            print(f'[{name}] 页面摘要: {body[:1800].encode("unicode_escape").decode("ascii")}')
        input('查看结果后按回车退出：')
    finally:
        page.quit()


if __name__ == '__main__':
    main()
