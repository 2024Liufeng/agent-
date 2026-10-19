import time

from fastapi.testclient import TestClient

from app.main import app, task_manager


class FakeService:
    def ask(self, query: str) -> str:
        return f"已收到：{query}"


def wait_for_completed(client: TestClient, task_id: str) -> dict:
    for _ in range(40):
        snapshot = client.get(f"/api/tasks/{task_id}").json()
        if snapshot["status"] in {"completed", "failed"}:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("任务没有在测试时间内结束")


def test_health_and_platform_status():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        response = client.get("/api/platforms/status")
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["platforms"]} == {"jd", "taobao", "pdd"}


def test_task_lifecycle_and_sse_replay():
    old_factory = task_manager.service_factory
    task_manager.service_factory = FakeService
    try:
        with TestClient(app) as client:
            created = client.post("/api/tasks", json={"query": "苹果手机，预算一万元"})
            assert created.status_code == 202
            task_id = created.json()["task_id"]
            snapshot = wait_for_completed(client, task_id)
            assert snapshot["status"] == "completed"
            assert "苹果手机" in snapshot["result"]

            stream = client.get(f"/api/tasks/{task_id}/events")
            assert stream.status_code == 200
            assert "assistant_delta" in stream.text
            assert "completed" in stream.text
    finally:
        task_manager.service_factory = old_factory


def test_message_endpoint_for_existing_task():
    old_factory = task_manager.service_factory
    task_manager.service_factory = FakeService
    try:
        with TestClient(app) as client:
            created = client.post("/api/tasks", json={"query": "测试"})
            task_id = created.json()["task_id"]
            response = client.post(f"/api/tasks/{task_id}/messages", json={"message": "继续"})
            assert response.status_code == 200
    finally:
        task_manager.service_factory = old_factory

