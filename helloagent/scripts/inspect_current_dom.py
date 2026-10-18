from DrissionPage import ChromiumPage

p = ChromiumPage('127.0.0.1:9232')
selectors = [
    'li.gl-item',
    'div.search_prolist_item',
    'a[href*="item.jd.com"]',
    'a[href*="goods.html"]',
    '[data-goods-id]',
    'span.price',
    'div.p-price',
]
for tab in p.get_tabs():
    if 'jd.com' not in tab.url and 'yangkeduo.com' not in tab.url:
        continue
    print('URL', tab.url)
    for selector in selectors:
        try:
            print(selector, len(tab.eles('css:' + selector)))
        except Exception as exc:
            print(selector, 'ERR', type(exc).__name__)
    body = tab.ele('tag:body').text
    print('BODY_LEN', len(body))
    print('BODY_HEAD', body[:1200].replace('\n', ' | '))
