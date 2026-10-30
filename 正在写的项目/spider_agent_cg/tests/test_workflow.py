import json
import tempfile
import unittest
from pathlib import Path

from spider_agent import storage, workflow


class FakeAdapter:
    def __init__(self, fail=False, invalid=False):
        self.fail = fail
        self.invalid = invalid

    def list_page(self, column, page, page_size):
        if self.fail:
            raise TimeoutError("private request details")
        return [{"id": f"{column['id']}-{page}"}] if page == 1 else []

    def detail(self, column, raw):
        return {"site_id": "elink", "column_id": column["id"], "source_id": raw["id"], "title": "公告", "release_time": "2026-10-30 10:00:00", "collect_id": "https://elink.chinasatnet.com.cn/notice/1", "from_site": column["url"], "content": "" if self.invalid else "<p>正文</p>"}


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_runs = storage.RUNS
        storage.RUNS = Path(self.tmp.name) / "runs"
        self.config = Path(self.tmp.name) / "config.json"
        self.config.write_text(json.dumps({"adapter": "elink", "site_id": "elink", "site_name": "易联", "columns": [{"id": "a", "name": "公告", "group": "招标", "url": "https://elink.chinasatnet.com.cn/x", "list_api": "/test"}]}), encoding="utf-8")

    def tearDown(self):
        storage.RUNS = self.old_runs
        self.tmp.cleanup()

    def trial(self, adapter=None):
        return workflow.trial(self.config, adapter=adapter or FakeAdapter())

    def test_requires_review_and_approved_run_can_collect(self):
        run_id, path = self.trial()
        with self.assertRaisesRegex(ValueError, "尚未审核"):
            workflow.collect(run_id, 1, FakeAdapter())
        workflow.review(run_id, True, "测试人", "已核对")
        target, result = workflow.collect(run_id, 2, FakeAdapter())
        self.assertTrue(target.exists())
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(result["records"]), 1)
        trace = (path / "trace.jsonl").read_text(encoding="utf-8")
        self.assertIn('"collect_column"', trace)

    def test_failure_and_missing_content_block_approval(self):
        for fake in (FakeAdapter(fail=True), FakeAdapter(invalid=True)):
            run_id, path = self.trial(fake)
            with self.assertRaisesRegex(ValueError, "不能批准"):
                workflow.review(run_id, True, "测试人", "检查")
            self.assertNotIn("private request details", (path / "trace.jsonl").read_text(encoding="utf-8"))

    def test_tampered_config_is_rejected(self):
        run_id, path = self.trial()
        workflow.review(run_id, True, "测试人", "已核对")
        (path / "config.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "已变化"):
            workflow.collect(run_id, 1, FakeAdapter())

    def test_tampering_before_review_is_rejected(self):
        run_id, path = self.trial()
        (path / "config.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "试采后已变化"):
            workflow.review(run_id, True, "测试人", "已核对")

    def test_tampered_report_markdown_cannot_be_approved(self):
        run_id, path = self.trial()
        (path / "report.md").write_text("伪造的报告", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "不一致"):
            workflow.review(run_id, True, "测试人", "已核对")

    def test_reject_and_invalid_run_id(self):
        run_id, _ = self.trial()
        workflow.review(run_id, False, "测试人", "样本错误")
        with self.assertRaisesRegex(ValueError, "没有通过"):
            workflow.collect(run_id, 1, FakeAdapter())
        with self.assertRaises(ValueError):
            storage.run_path("../outside")

    def test_partial_collection_is_reported(self):
        run_id, _ = self.trial()
        workflow.review(run_id, True, "测试人", "已核对")
        _, result = workflow.collect(run_id, 1, FakeAdapter(fail=True))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["columns"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
