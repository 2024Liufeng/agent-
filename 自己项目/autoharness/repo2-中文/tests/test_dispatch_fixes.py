"""调度回归测试：_detached_launch 错误处理 + _run_id 冲突避免。"""
from unittest.mock import patch

from autoharness.hook import dispatch


def test_run_id_empty_session_gets_hash():
    """清理为空的 session_id 应该产生一个唯一的哈希值，而不是纯粹的“运行”。"""
    result = {"session_id": "...", "count": 5}
    rid = dispatch._run_id(result)
    assert rid != "run-5"
    assert rid.endswith("-5")
    # 两个不同的 session_id 都清理为空应该不同
    r1 = dispatch._run_id({"session_id": "...", "count": 0})
    r2 = dispatch._run_id({"session_id": "???", "count": 0})
    assert r1 != r2


def test_run_id_normal_session_unchanged():
    """正常的 session_id 仍应产生预期的格式。"""
    result = {"session_id": "abc-123", "count": 3}
    assert dispatch._run_id(result) == "abc-123-3"


def test_curate_run_id_empty_session_gets_hash():
    """_curate_run_id 具有相同的哈希后备。"""
    r1 = dispatch._curate_run_id({"session_id": "..."}, 10)
    r2 = dispatch._curate_run_id({"session_id": "???"}, 10)
    assert r1 != r2
    assert r1.endswith("-c10")


def test_detached_launch_oserror_returns_error():
    """如果 Popen 引发 OSError，则 _detached_launch 返回错误字典而不是传播。"""
    with patch("autoharness.hook.dispatch.subprocess.Popen", side_effect=OSError("no interpreter")):
        result = dispatch._detached_launch("/tmp/t", "sid", "run-0", {"project": "/p", "global": "/g"})
    assert result is not None
    assert "error" in result
    assert "no interpreter" in result["error"]


def test_detached_launch_success_returns_none():
    """正常Popen成功； _detached_launch 返回 None。"""
    with patch("autoharness.hook.dispatch.subprocess.Popen"):
        result = dispatch._detached_launch("/tmp/t", "sid", "run-0", {"project": "/p", "global": "/g"})
    assert result is None
