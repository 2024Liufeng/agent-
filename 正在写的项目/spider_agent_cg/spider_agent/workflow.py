"""显式的单一编排流程与人工审核门。"""
import html
import json
import time
from pathlib import Path
from urllib.parse import urlparse

from . import storage
from .advisor import advise
from .sites.elink import ElinkAdapter
from .validation import validate

SOURCE_FILES = [Path(__file__), Path(__file__).parent / "sites" / "elink.py", Path(__file__).parent / "validation.py"]


def code_hashes():
    return {p.name: storage.digest(p) for p in SOURCE_FILES}


def check_config(config):
    if not isinstance(config, dict) or config.get("adapter") != "elink" or config.get("site_id") != "elink":
        raise ValueError("目前只支持 elink 适配器")
    columns = config.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("columns 不能为空")
    ids = set()
    for c in columns:
        if not isinstance(c, dict) or not all(isinstance(c.get(k), str) and c[k].strip() for k in ("id", "name", "group", "url")):
            raise ValueError("每个栏目必须有 id、name、group 和 url")
        if c["id"] in ids:
            raise ValueError("栏目 id 不能重复")
        ids.add(c["id"])
        url = urlparse(c["url"])
        if url.scheme != "https" or url.netloc != "elink.chinasatnet.com.cn":
            raise ValueError("栏目 URL 必须属于易联 HTTPS 域名")


def _sample_column(adapter, column, limit, pages=1):
    result = {"id": column["id"], "name": column["name"], "group": column["group"], "url": column["url"], "status": "unverified", "samples": [], "errors": [], "pages_read": 0}
    if not column.get("list_api"):
        result["errors"].append("未配置候选列表接口")
        return result
    seen = set()
    for page in range(1, pages + 1):
        try:
            records = adapter.list_page(column, page, limit)
            result["pages_read"] += 1
        except Exception as exc:
            result["errors"].append(f"列表第 {page} 页失败：{type(exc).__name__}")
            break
        if not records:
            break
        for raw in records[:limit]:
            try:
                item = adapter.detail(column, raw)
                if item["source_id"] in seen:
                    continue
                seen.add(item["source_id"])
                item["validation_errors"] = validate(item)
                result["samples"].append(item)
            except Exception as exc:
                result["errors"].append(f"详情获取失败：{type(exc).__name__}")
        if len(records) < limit:
            break
    result["status"] = "failed" if result["errors"] else ("sampled" if result["samples"] else "empty")
    return result


def _report_text(report):
    lines = [f"# 试采审核报告：{report['site_name']}", "", f"任务：{report['run_id']}", f"状态：{report['status']}", "", "## 栏目覆盖", "", "| 大栏目 | 子栏目 | 状态 | 样本数 | 问题 |", "| --- | --- | --- | ---: | --- |"]
    for c in report["columns"]:
        problems = c["errors"] + [e for s in c["samples"] for e in s["validation_errors"]]
        text = "；".join(problems) or "基础校验通过，仍需人工核对"
        safe = lambda x: str(x).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {safe(c['group'])} | {safe(c['name'])} | {c['status']} | {len(c['samples'])} | {safe(text)} |")
    lines += ["", "## 样本", "", "分类、地区未实现；来源栏目可能是大栏目，必须对照页面确认。"]
    for c in report["columns"]:
        lines += ["", f"### {c['group']} / {c['name']}"]
        for item in c["samples"]:
            preview = " ".join(html.unescape(item['content']).split())[:300]
            lines += ["", f"- 标题：{item['title']}", f"  - 发布时间：{item['release_time']}", f"  - 详情：{item['collect_id']}", f"  - 栏目入口：{item['from_site']}", f"  - 正文 HTML 预览：`{preview.replace('`', '')}`", f"  - 校验问题：{'；'.join(item['validation_errors']) or '无'}"]
    lines += ["", "## 人工审核", "", "核对每个子栏目、详情链接、正文、字段来源。当前分类、地区、附件和数据库写入尚未实现。", "继续采集只会导出本地 JSON，页数由命令指定。"]
    if report.get("advisor"):
        lines += ["", "## 模型建议（仅供参考）", "", report["advisor"]]
    return "\n".join(lines) + "\n"


def trial(config_path, limit=3, use_advisor=False, adapter=None):
    if not 1 <= limit <= 10:
        raise ValueError("试采数量必须为 1 到 10")
    config = storage.read(Path(config_path))
    check_config(config)
    run_id, path = storage.new_run()
    storage.save(path / "config.json", config)
    storage.event(path, run_id, "trial", "started", columns=len(config["columns"]), limit=limit)
    adapter = adapter or ElinkAdapter()
    columns = []
    for column in config["columns"]:
        started = time.monotonic()
        result = _sample_column(adapter, column, limit)
        columns.append(result)
        storage.event(path, run_id, "trial_column", result["status"], column_id=column["id"], duration_ms=round((time.monotonic()-started)*1000), sample_count=len(result["samples"]), errors=result["errors"])
    storage.save(path / "samples.json", [s for c in columns for s in c["samples"]])
    report = {"run_id": run_id, "site_name": config.get("site_name", ""), "status": "awaiting_review", "limit": limit, "columns": columns, "config_sha256": storage.digest(path / "config.json"), "samples_sha256": storage.digest(path / "samples.json"), "code_hashes": code_hashes(), "warnings": ["分类、地区和附件尚未实现；请逐条核对来源", "历史候选接口不保证覆盖正确的子栏目"]}
    if use_advisor:
        summary = [{"name": c["name"], "status": c["status"], "sample_count": len(c["samples"]), "errors": c["errors"], "validation_errors": [e for s in c["samples"] for e in s["validation_errors"]]} for c in columns]
        try:
            report["advisor"] = advise(summary, lambda step, status, **details: storage.event(path, run_id, step, status, **details))
            storage.event(path, run_id, "advisor", "success")
        except Exception as exc:
            report["advisor_error"] = type(exc).__name__
            storage.event(path, run_id, "advisor", "failed", error=type(exc).__name__)
    storage.save(path / "report.json", report)
    (path / "report.md").write_text(_report_text(report), encoding="utf-8")
    storage.event(path, run_id, "trial", "awaiting_review")
    return run_id, path


def review(run_id, approve, reviewer, note):
    if not reviewer.strip() or not note.strip():
        raise ValueError("审核人和备注不能为空")
    path = storage.run_path(run_id)
    report = storage.read(path / "report.json")
    if (path / "review.json").exists():
        raise ValueError("该任务已审核；如需重新审核，请创建新的试采任务")
    if report.get("run_id") != run_id or report.get("status") != "awaiting_review":
        raise ValueError("报告状态不允许审核")
    for name in ("config", "samples"):
        if report.get(name + "_sha256") != storage.digest(path / (name + ".json")):
            raise ValueError(f"{name} 在试采后已变化，请重新试采")
    if (path / "report.md").read_text(encoding="utf-8") != _report_text(report):
        raise ValueError("审核报告与试采结果不一致，请重新试采")
    if report.get("code_hashes") != code_hashes():
        raise ValueError("采集或校验代码已变化，请重新试采")
    if approve:
        bad = [c["name"] for c in report["columns"] if c["status"] != "sampled" or any(s["validation_errors"] for s in c["samples"])]
        if bad:
            raise ValueError("以下栏目未通过基础校验，不能批准：" + "、".join(bad))
    decision = {"decision": "approved" if approve else "rejected", "reviewer": reviewer, "note": note, "at": storage.now(), "config_sha256": storage.digest(path / "config.json"), "report_sha256": storage.digest(path / "report.json"), "samples_sha256": storage.digest(path / "samples.json"), "code_hashes": code_hashes()}
    storage.save(path / "review.json", decision)
    storage.event(path, run_id, "review", decision["decision"], reviewer=reviewer)
    return decision


def collect(run_id, pages, adapter=None):
    if not 1 <= pages <= 100:
        raise ValueError("页数必须为 1 到 100")
    path = storage.run_path(run_id)
    if not (path / "review.json").exists():
        raise ValueError("任务尚未审核")
    decision = storage.read(path / "review.json")
    if decision.get("decision") != "approved":
        raise ValueError("任务没有通过审核")
    for name in ("config", "report", "samples"):
        if decision.get(name + "_sha256") != storage.digest(path / (name + ".json")):
            raise ValueError(f"{name} 已变化，请重新试采审核")
    if decision.get("code_hashes") != code_hashes():
        raise ValueError("采集或校验代码已变化，请重新试采审核")
    config = storage.read(path / "config.json")
    check_config(config)
    adapter = adapter or ElinkAdapter()
    collection_id = storage.now().replace(":", "-").replace("+", "_")
    output = []
    summary = []
    seen = set()
    storage.event(path, run_id, "collect", "started", pages=pages, collection_id=collection_id)
    for column in config["columns"]:
        started = time.monotonic()
        result = _sample_column(adapter, column, 10, pages)
        valid_count = 0
        invalid_count = 0
        for item in result["samples"]:
            if item["validation_errors"]:
                invalid_count += 1
                continue
            key = (item["site_id"], item["source_id"])
            if key not in seen:
                output.append(item)
                seen.add(key)
                valid_count += 1
        row = {"column_id": column["id"], "status": result["status"], "pages_read": result["pages_read"], "valid_new": valid_count, "invalid": invalid_count, "errors": result["errors"]}
        summary.append(row)
        storage.event(path, run_id, "collect_column", row["status"], column_id=column["id"], duration_ms=round((time.monotonic()-started)*1000), valid_new=valid_count, invalid=invalid_count, errors=row["errors"])
    incomplete = any(c["status"] in ("failed", "unverified") or c["invalid"] for c in summary)
    result = {"collection_id": collection_id, "run_id": run_id, "status": "partial" if incomplete else "finished", "page_limit": pages, "columns": summary, "records": output, "note": "按页数上限采集，不能证明历史数据完整；未写入数据库。"}
    target = path / ("collection-" + collection_id + ".json")
    storage.save(target, result)
    storage.event(path, run_id, "collect", result["status"], collection_id=collection_id, record_count=len(output))
    return target, result
