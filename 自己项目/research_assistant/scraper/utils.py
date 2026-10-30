import re

from bs4 import BeautifulSoup


def clean_soup(soup: BeautifulSoup) -> BeautifulSoup:
    # 直接复用 GPT Researcher 的清洗范围：
    # 删除不属于研究正文的脚本、样式和页面公共区域。
    for tag in soup.find_all(
        [
            "script",
            "style",
            "footer",
            "header",
            "nav",
            "menu",
            "sidebar",
            "svg",
        ]
    ):
        tag.decompose()

    # 有些网站使用 <div class="sidebar">，而不是 <sidebar> 标签。
    # class_ 会匹配标签 class 列表中的任意一个禁止名称。
    disallowed_classes = [
        "nav",
        "menu",
        "sidebar",
        "footer",
    ]

    for tag in soup.find_all(class_=disallowed_classes):
        tag.decompose()

    return soup


def get_text_from_soup(soup: BeautifulSoup) -> str:
    # get_text() 删除剩余的 HTML 标签，只保留标签里的文字。
    # separator="\n" 让不同标签的文字用换行分隔。
    # strip=True 删除每段文字首尾的空白。
    text = soup.get_text(
        strip=True,
        separator="\n",
    )

    # 网页中可能有连续空格、换行和制表符，
    # 把连续两个以上的空白压缩成一个空格。
    text = re.sub(r"\s{2,}", " ", text)

    return text


def extract_title(soup: BeautifulSoup) -> str:
    # soup.title 查找网页的 <title> 标签；
    # 如果网页没有 <title>，返回空字符串，避免访问 None.string。
    return soup.title.string if soup.title else ""
