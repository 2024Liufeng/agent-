"""端到端实时占位符：在真实主机上安装插件并手动运行完整循环。

CI 中已经涵盖了确定性接缝（调度路由/MCP 服务/清单/跨进程生成）
（test_dispatch / test_stage_skill / test_plugin_manifest / test_spawn）。该存根仅标记实时边界并表示
如何运行它； `pytest -m "not live"` 排除了它，因此它不会阻止 CI。维护人员的完整操作手册位于
他们的实验/树，这不是公开发布的一部分，因此跳过消息本身携带步骤。"""
import pytest

pytestmark = pytest.mark.live


def test_plugin_end_to_end_on_real_host():
    pytest.skip(
        "Manual/live: on a real Claude Code host with an isolated HOME, install the plugin, shrink the "
        "AUTOHARNESS_* knobs as in README 'Walkthrough: watching it learn', work a few turns, then check "
        ".claude/autoharness/runs/ and .claude/skills/ for what landed and why."
    )
