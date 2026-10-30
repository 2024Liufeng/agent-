"""回归：digest() 必须仅读取 end_offset 字节，而不是整个记录。"""
from unittest.mock import mock_open, patch

from autoharness.hook.capture import digest


def test_digest_bounded_read(tmp_path):
    """摘要通过有界 f.read() 只读取 end_offset 字节，而不是 path.read_bytes()。"""
    # 创建包含一些内容的转录文件
    transcript = tmp_path / "transcript.jsonl"
    lines = [
        '{"type": "user", "message": {"content": "hello"}}\n',
        '{"type": "assistant", "message": {"content": "hi there"}}\n',
    ]
    content = "".join(lines).encode("utf-8")
    transcript.write_bytes(content)

    # 使用 end_offset 读取仅覆盖第一行
    first_line_end = len(lines[0].encode("utf-8"))
    bounded_open = mock_open(read_data=content)
    with patch("builtins.open", bounded_open):
        result = digest(str(transcript), first_line_end)

    bounded_open.return_value.read.assert_called_once_with(first_line_end)
    assert "hello" in result
    assert "hi there" not in result


def test_digest_full_when_offset_exceeds_file(tmp_path):
    """当 end_offset 超过文件大小时， f.read(end_offset) 读取整个文件（没有错误）。"""
    transcript = tmp_path / "transcript.jsonl"
    content = '{"type": "user", "message": {"content": "test"}}\n'
    transcript.write_bytes(content.encode("utf-8"))

    result = digest(str(transcript), 999999)
    assert "test" in result
