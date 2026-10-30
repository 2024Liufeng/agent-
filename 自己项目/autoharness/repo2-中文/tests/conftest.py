import os

import pytest

from autoharness import config


@pytest.fixture
def dir_link():
    """链接目录：符号链接或 Windows 保留符号链接的 NTFS 连接
    特权（无开发人员模式/未提升）。两者后面都是 Path.resolve()。"""
    def link(alias, target):
        try:
            alias.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            import _winapi
            _winapi.CreateJunction(str(target), str(alias))
    return link


@pytest.fixture(autouse=True)
def _no_real_notifier(monkeypatch):
    # 配置在导入时读取 AUTOHARNESS_NOTIFY*：如果没有这个，贡献者自己的通知程序（团队
    # Slack hook、桌面弹出窗口）将在套件运行的每个排水管中触发
    monkeypatch.setattr(config, "NOTIFY", "")
    monkeypatch.setattr(config, "NOTIFY_CMD", "")
