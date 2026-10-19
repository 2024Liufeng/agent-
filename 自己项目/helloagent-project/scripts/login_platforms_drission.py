import time
from pathlib import Path

from DrissionPage import ChromiumOptions, ChromiumPage

ROOT = Path(__file__).resolve().parents[1]
# Dedicated DrissionPage profile. Do not share it with Playwright's profile.
PROFILE = ROOT / '.drission-edge-profile'
EDGE = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
PLATFORMS = [
    ('淘宝', 'https://www.taobao.com/'),
    ('京东', 'https://www.jd.com/'),
    ('拼多多', 'https://mobile.yangkeduo.com/'),
]


def main():
    co = ChromiumOptions()
    co.set_browser_path(str(EDGE))
    co.set_user_data_path(str(PROFILE))
    co.set_local_port(9232)
    co.headless(False)
    co.set_argument('--start-maximized')
    browser = ChromiumPage(co)
    pages = []
    try:
        for name, url in PLATFORMS:
            page = browser if not pages else browser.new_tab()
            page.get(url)
            pages.append(page)
            print(f'{name}已打开：{page.url}，共享 profile={PROFILE}')
            time.sleep(2)
        print(f'会话目录：{PROFILE}（三个标签页共享）')
        input('请在三个页面完成登录；完成后回终端按回车保存并退出：')
    finally:
        browser.quit()


if __name__ == '__main__':
    main()
