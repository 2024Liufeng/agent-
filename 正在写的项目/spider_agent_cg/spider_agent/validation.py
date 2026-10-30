"""纯函数校验；业务分类、地区不在此处猜测。"""
from urllib.parse import urlparse


def validate(record):
    errors = []
    for field in ("title", "release_time", "collect_id", "from_site", "content"):
        if not str(record.get(field) or "").strip():
            errors.append(f"{field} 为空")
    for field in ("collect_id", "from_site"):
        url = urlparse(str(record.get(field) or ""))
        if url.scheme not in ("http", "https") or not url.netloc:
            errors.append(f"{field} 不是有效 URL")
    return errors
