"""易联历史候选接口适配器；请求失败向调用方报告。"""
import json
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

BASE = "https://elink.chinasatnet.com.cn"
MAX_RESPONSE = 5 * 1024 * 1024


def request(url, payload=None, referer=None):
    headers = {"User-Agent": "SpiderAgentCG/0.1", "Accept": "application/json, text/html, */*"}
    if referer:
        headers["Referer"] = referer
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Origin"] = BASE
    req = Request(url, data=data, headers=headers)
    with urlopen(req, timeout=12) as response:
        content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise ValueError("响应超过大小限制")
        return content.decode("utf-8", errors="replace")


class ElinkAdapter:
    def list_page(self, column, page, page_size):
        api = column.get("list_api")
        if not api:
            raise ValueError("未配置列表接口")
        url = urljoin(BASE, api)
        if urlparse(url).netloc != urlparse(BASE).netloc or urlparse(url).scheme != "https":
            raise ValueError("接口必须属于易联 HTTPS 域名")
        raw = request(url, {"pageNo": page, "pageSize": page_size, "title": "", "projectCode": "", "procurementType": ""}, column["url"])
        result = json.loads(raw)
        if not isinstance(result, dict) or not isinstance(result.get("result"), dict):
            raise ValueError("列表响应不是预期结构；可能需要验证或接口已变化")
        if result.get("success") is False:
            raise ValueError("列表接口报告失败")
        records = result["result"].get("records")
        if not isinstance(records, list):
            raise ValueError("列表响应缺少 records")
        return records

    def detail(self, column, raw):
        if not isinstance(raw, dict):
            raise ValueError("列表记录格式错误")
        notice_id = str(raw.get("noticeMappingId") or "")
        if not notice_id or not notice_id.isalnum():
            raise ValueError("缺少有效 noticeMappingId")
        attachment = raw.get("htmlAttachUrl")
        content = ""
        if attachment:
            content = request(BASE + "/file-eb/previewAttach?" + urlencode({"identify": attachment}), referer=column["url"])
            # 接口错误页不能当正文。
            if not content.strip() or content.lstrip().startswith("{"):
                raise ValueError("正文接口未返回有效 HTML")
        return {
            "site_id": "elink", "column_id": column["id"], "column_name": column["name"],
            "source_id": notice_id, "title": str(raw.get("title") or ""),
            "release_time": str(raw.get("sendTime") or ""),
            "collect_id": BASE + "/ebPortal/notice/" + notice_id,
            "from_site": column["url"], "content": content,
            "announcement_type": None, "type": None, "province": None, "city": None,
            "field_sources": {"title": "list.title", "release_time": "list.sendTime", "collect_id": "noticeMappingId 拼接（需人工核对）", "from_site": "配置的栏目入口（可能为大栏目）", "content": "previewAttach", "announcement_type": "未映射", "province": "未提取"},
        }
