# Spider Agent CG

面向招采公告的采集接入实验：以易联为例，逐栏目试采、检查样本、人工审核，并在审核通过后导出更多数据。架构和边界见 [架构设计](docs/架构设计.md)。

需要 Python 3.10+；试采和导出使用标准库，试采写库需要 `pip install -r requirements.txt`。在项目目录执行：

```powershell
python -m spider_agent trial --config config/elink.json --limit 3
python -m spider_agent stage-db <run_id>
python -m spider_agent show <run_id>
python -m spider_agent review <run_id> --approve --reviewer "你的名字" --note "已对照网页检查"
python -m spider_agent collect <run_id> --pages 2
```

试采结果在 `runs/<run_id>/`：`report.md` 给人审核，`report.json` 是结构化结果，`samples.json` 是原始样本，`trace.jsonl` 是流程追踪。栏目失败、为空、未配置接口或字段不完整时不能批准；修正配置或问题后重新试采生成新任务。`review --reject` 可记录驳回。批准只解锁本地 JSON 批量采集，不会部署。

试采入库：先设置 `DB_HOST`、`DB_PORT`（默认 3306）、`DB_USER`、`DB_PASSWORD`、`DB_NAME`，再执行 `stage-db <run_id>`；也可在 `trial` 中添加 `--write-db` 一步完成试采和写库。将真实写入指定的 `business_invite_tenders` 表。它按标题和发布时间去重，并在 `database-stage-*.json` 记录插入 ID、跳过原因和地区来源。竞价栏目样本与栏目不符时跳过。地区找不到时按历史业务资料兜底北京市，并在报告标记，须人工核对。数据库未设置对应唯一约束，并发写入时仍有重复风险。

可选单 Agent 审核建议：设置 `LLM_BASE_URL`（OpenAI 兼容 API 根地址，例如以 `/v1` 结尾）、`LLM_MODEL`、`LLM_API_KEY`，给 `trial` 加 `--advisor`。Agent 最多调用 4 轮模型，只能调用只读的试采摘要工具；模型不接收正文或密钥，失败不影响试采和人工审核。当前 Agent 不负责自主发现网站或生成爬虫。

接口源于旧项目的历史证据，仅供验证，站点变化或网络不可达时会如实报告。完整地区规则、附件和通用网站自主接入尚未实现。

运行测试：`python -m unittest discover -s tests -v`。
