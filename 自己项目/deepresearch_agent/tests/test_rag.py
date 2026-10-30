import json
from threading import Lock
from types import SimpleNamespace

import pytest

import agent as agent_module
from agent import DeepResearchAgent
from config import Configuration
from models import SummaryState, TodoItem
from services.evidence import prepare_evidence, append_source_index, validate_citations
from services.knowledge_base import KnowledgeBaseService, KnowledgeBaseError
from conftest import make_pdf


class TestEmbedder:
    """测试中使用固定向量；真实模型联调单独进行，不混同效果验证。"""
    __test__ = False

    def encode(self, texts):
        return [[float("nebula" in text.lower()), float("orchid" in text.lower()), 0.1] for text in texts]


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.setenv("EMBED_API_KEY", "test-key")
    monkeypatch.setenv("EMBED_MODEL_TYPE", "dashscope")
    monkeypatch.setenv("EMBED_MODEL_NAME", "test-model")
    service = KnowledgeBaseService(tmp_path)
    monkeypatch.setattr(service, "_get_embedder", lambda: TestEmbedder())
    yield service
    service.close()


def test_pdf_parse_index_retrieve_and_persist(service, monkeypatch):
    first = service.import_pdf("nebula.pdf", make_pdf("Nebula retention is 37 days."))
    other = service.import_pdf("orchid.pdf", make_pdf("Orchid retention is 91 days."))
    assert first["status"] == "ready" and first["chunk_count"] > 0
    hits = service.search(first["id"], "nebula retention")
    assert "37 days" in hits[0]["content"]
    assert all(hit["knowledge_base_id"] == first["id"] for hit in hits)
    assert all("91 days" not in hit["content"] for hit in hits)
    assert other["id"] != first["id"]
    service.close()
    # 重建服务后，清单和本地 Qdrant 索引仍可读取。
    reopened = KnowledgeBaseService(service.root)
    monkeypatch.setattr(reopened, "_get_embedder", lambda: TestEmbedder())
    try:
        assert reopened.get(first["id"], ready=True)["name"] == "nebula.pdf"
        assert "37 days" in reopened.search(first["id"], "nebula")[0]["content"]
    finally:
        reopened.close()


@pytest.mark.parametrize("filename,data", [("x.txt", b"text"), ("x.pdf", b"not a pdf")])
def test_invalid_pdf_is_rejected(service, filename, data):
    with pytest.raises(KnowledgeBaseError):
        service.import_pdf(filename, data)
    assert service.list_knowledge_bases() == []


def test_empty_pdf_is_not_ready(service):
    with pytest.raises(KnowledgeBaseError, match="没有可提取"):
        service.import_pdf("blank.pdf", make_pdf(""))
    assert service.list_knowledge_bases()[0]["status"] == "failed"


def test_zero_vectors_are_not_saved_as_success(service, monkeypatch):
    monkeypatch.setattr(service, "_get_embedder", lambda: SimpleNamespace(encode=lambda texts: [[0, 0] for _ in texts]))
    with pytest.raises(KnowledgeBaseError, match="有效向量"):
        service.import_pdf("zero.pdf", make_pdf("Nebula retention is 37 days."))
    assert service.list_knowledge_bases()[0]["status"] == "failed"


def test_embedding_change_requires_reimport(service, monkeypatch):
    record = service.import_pdf("a.pdf", make_pdf("Nebula retention is 37 days."))
    monkeypatch.setenv("EMBED_MODEL_NAME", "different-model")
    with pytest.raises(KnowledgeBaseError, match="配置已变化"):
        service.search(record["id"], "nebula")


@pytest.mark.parametrize("identifier", ["../private", "kb_invalid", "/etc/passwd"])
def test_invalid_knowledge_base_id(service, identifier):
    with pytest.raises(KnowledgeBaseError, match="ID 无效"):
        service.get(identifier)


def test_evidence_preserves_both_sources_and_deduplicates():
    document = {"knowledge_base_id": "kb_test", "filename": "paper.pdf", "chunk_id": "abc",
                "content": "d" * 20000, "start": 0, "end": 20000}
    web = {"url": "https://example.com", "title": "Web", "content": "w" * 20000}
    sources, references, context = prepare_evidence(2, [document, document], {"results": [web, web]})
    assert len(sources) == 2
    assert {source["type"] for source in sources} == {"document", "web"}
    assert "paper.pdf" in references and "https://example.com" in references
    assert "片段 abc" in references and "w" * 100 in context
    assert all(source["id"].startswith("T2-") for source in sources)


def make_agent(monkeypatch, *, document=True, web="success"):
    instance = object.__new__(DeepResearchAgent)
    instance.config = Configuration(enable_notes=False)
    instance.research_id = "test-research"
    instance.knowledge_base_id = "kb_test" if document else None
    instance._state_lock = Lock()
    instance._citation_numbers = {}
    instance._citation_keys = {}
    instance._drain_tool_events = lambda *args, **kwargs: []
    instance._persist_final_report = lambda *args: None
    instance._set_tool_event_sink = lambda *args: None
    hits = [{"knowledge_base_id": "kb_test", "filename": "a.pdf", "chunk_id": "abc",
             "content": "Nebula retention is 37 days.", "start": 0, "end": 28}] if document is True else []
    monkeypatch.setattr(agent_module.knowledge_bases, "search", lambda *args: hits)

    def search(*args):
        if web == "error":
            raise RuntimeError("network failure")
        results = [{"url": "https://example.com", "title": "Public", "content": "Public background."}] if web == "success" else []
        return {"results": results}, [], None, "test"
    monkeypatch.setattr(agent_module, "dispatch_search", search)
    contexts = []

    def summarize(state, task, context):
        contexts.append(context)
        return "Evidence-based summary."

    def stream_summary(state, task, context):
        text = summarize(state, task, context)
        return iter([text]), lambda: text

    instance.summarizer = SimpleNamespace(summarize_task=summarize, stream_task_summary=stream_summary)
    instance.reporting = SimpleNamespace(generate_report=lambda state: "Research report")
    return instance, contexts


@pytest.mark.parametrize("document,web,status,types", [
    (True, "error", "completed", {"document"}),
    (True, "empty", "completed", {"document"}),
    (True, "success", "completed", {"document", "web"}),
    (False, "success", "completed", {"web"}),
    (False, "empty", "skipped", set()),
    (False, "error", "failed", set()),
])
def test_task_uses_available_evidence(monkeypatch, document, web, status, types):
    instance, contexts = make_agent(monkeypatch, document=document, web=web)
    task = TodoItem(id=1, title="Research", intent="Find evidence", query="nebula")
    state = SummaryState(research_topic="test", todo_items=[task])
    list(instance._execute_task(state, task, emit_stream=False))
    assert task.status == status
    assert {source["type"] for source in task.sources} == types
    assert bool(contexts) == bool(types)


def test_document_failure_keeps_web_evidence(monkeypatch):
    instance, contexts = make_agent(monkeypatch)
    def fail(*args):
        raise RuntimeError("document store unavailable")
    monkeypatch.setattr(agent_module.knowledge_bases, "search", fail)
    task = TodoItem(id=1, title="Research", intent="Find evidence", query="nebula")
    list(instance._execute_task(SummaryState(research_topic="test"), task, emit_stream=False))
    assert task.status == "completed" and contexts
    assert {source["type"] for source in task.sources} == {"web"}


def test_sync_run_really_executes_generator(monkeypatch):
    instance, contexts = make_agent(monkeypatch)
    instance.planner = SimpleNamespace(plan_todo_list=lambda state: [TodoItem(id=1, title="t", intent="i", query="nebula")])
    result = instance.run("nebula")
    assert contexts
    assert result.todo_items[0].status == "completed"
    assert "参考来源" in result.report_markdown


def test_stream_has_document_sources_and_final_report(monkeypatch):
    instance, _ = make_agent(monkeypatch, web="error")
    instance.planner = SimpleNamespace(plan_todo_list=lambda state: [TodoItem(id=1, title="t", intent="i", query="nebula")])
    events = list(instance.run_stream("nebula"))
    source_event = next(event for event in events if event["type"] == "sources")
    assert source_event["sources"][0]["type"] == "document"
    assert any(event["type"] == "final_report" and "参考来源" in event["report"] for event in events)
    assert events[-1]["type"] == "done"


def test_no_evidence_does_not_call_report_model():
    assert "资料不足" in append_source_index("", [])


def test_generated_citation_must_exist():
    sources = [{"id": "T1-D1"}]
    validate_citations("A fact [T1-D1]", sources)
    with pytest.raises(ValueError, match="证据编号"):
        validate_citations("A fact [T1-D9]", sources)


def test_qoder_dsml_is_converted_to_framework_tool_protocol():
    from services.llm_compat import normalize_tool_protocol
    from hello_agents import ToolAwareSimpleAgent
    raw = '<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke name="note:{"action":"update","tags":["task_1"],"content":"quoted \\"text\\""}]</｜｜DSML｜｜ parameter></｜｜DSML｜｜ invoke></｜｜DSML｜｜ calls>'
    converted = normalize_tool_protocol(raw)
    parser = object.__new__(ToolAwareSimpleAgent)
    calls = parser._parse_tool_calls(converted)
    assert len(calls) == 1 and calls[0]["tool_name"] == "note"
    assert json.loads(calls[0]["parameters"])["tags"] == ["task_1"]
    assert "DSML" not in converted


def test_unrecognized_dsml_is_not_a_successful_report():
    from services.llm_compat import normalize_tool_protocol
    with pytest.raises(ValueError, match="DSML"):
        normalize_tool_protocol('<｜｜DSML｜｜ calls>broken</｜｜DSML｜｜ calls>')


def test_planner_finds_task_json_among_explanations():
    from services.planner import PlanningService
    service = object.__new__(PlanningService)
    payload = service._extract_json_payload('已保存 {"action":"create"}。\n{"tasks":[{"title":"t","query":"q"}]}\n完成。')
    assert payload["tasks"][0]["query"] == "q"


def test_upload_api_and_original_document(service, monkeypatch):
    import main
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, "knowledge_bases", service)
    with TestClient(main.app) as client:
        response = client.post("/knowledge-bases", files={"file": ("test.pdf", make_pdf("Nebula is 37 days."), "application/pdf")})
        assert response.status_code == 200
        record = response.json()
        assert record["status"] == "ready"
        assert client.get("/knowledge-bases").json()["items"][0]["id"] == record["id"]
        pdf = client.get(f"/knowledge-bases/{record['id']}/document")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
        assert client.post("/knowledge-bases", files={"file": ("x.pdf", b"not pdf")}).status_code == 400
        assert client.post("/research", json={"topic": "  "}).status_code == 400
        assert client.post("/research/stream", json={"topic": "test", "knowledge_base_id": "bad"}).status_code == 400
