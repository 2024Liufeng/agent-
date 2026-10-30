import unittest
from spider_agent.database import prepare


def record(column, title):
    return {"column_id": column, "title": title, "release_time": "2026-10-30 12:00:00", "from_site": "https://example.test/list", "collect_id": "https://example.test/detail", "content": '<p>招标人：北京市示例单位</p><p style="font-size: 29px; font-weight: bold">正文</p>', "validation_errors": []}


class DatabaseMappingTest(unittest.TestCase):
    def test_mapping_region_and_html(self):
        item = prepare(record("bid_ann", "示例招标公告"))
        self.assertEqual((item["announcement_type"], item["type"]), (0, 0))
        self.assertEqual((item["province"], item["city"]), ("北京市", "北京市"))
        self.assertEqual(item["region_source"], "招标人名称")
        self.assertIn("font-size: 16px", item["content"])
        self.assertIn("font-weight: normal", item["content"])

    def test_mismatched_candidate_is_not_written(self):
        with self.assertRaisesRegex(ValueError, "不一致"):
            prepare(record("nonbid_bidding", "设备服务谈判公告"))

    def test_unknown_region_is_explicit_fallback(self):
        item = record("bid_change", "示例变更公告")
        item["content"] = "<p>正文</p>"
        self.assertIn("兜底", prepare(item)["region_source"])

    def test_html_separated_fields_and_short_municipality(self):
        item = record("bid_candidate", "结果公示")
        item["content"] = "<span>招标人：</span><span>上海卫星互联网研究院有限公司</span><span>招标代理机构：</span><span>北京公司</span>"
        result = prepare(item)
        self.assertEqual(result["province"], "上海市")
        self.assertEqual(result["region_source"], "招标人名称")


if __name__ == "__main__":
    unittest.main()
