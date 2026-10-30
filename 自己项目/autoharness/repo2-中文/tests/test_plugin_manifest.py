import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_plugin_json_has_identity():
    m = _load(".claude-plugin/plugin.json")
    assert m["name"] == "autoharness"
    assert m["version"]


def test_hooks_route_all_events_to_dispatch():
    h = _load("hooks/hooks.json")["hooks"]
    assert set(h) == {"SessionStart", "Stop", "PreToolUse", "SessionEnd"}
    for groups in h.values():
        for group in groups:
            for hook in group["hooks"]:
                assert "autoharness.hook.dispatch" in hook["command"]
    assert (ROOT / "src/autoharness/hook/dispatch.py").exists()


def test_pretooluse_reaches_dispatch_for_every_tool_exactly_once():
    # 方向 H：活动分子是*每个*主会话工具调用，因此工具名称
    # 匹配器会默默地将 Bash/Grep/Task 从计数中删除。一个包罗万象的群体，而不是
    # 几个：两个匹配组将为同一调用和双碰撞调用两次调度。
    pre = _load("hooks/hooks.json")["hooks"]["PreToolUse"]
    assert len(pre) == 1
    assert pre[0].get("matcher", "*") in ("*", "")


def test_pretooluse_backstops_reflector_writes():
    # S1/S3：反射器写入拒绝是顶级 PreToolUse backstop（不是代理 frontmatter），
    # 因此，包罗万象的组必须是进行调度的组——路由是调度的工作。
    pre = _load("hooks/hooks.json")["hooks"]["PreToolUse"]
    assert any("autoharness.hook.dispatch" in hook["command"]
               for group in pre for hook in group["hooks"])


def test_mcp_registers_existing_stage_skill():
    m = _load(".claude-plugin/plugin.json")["mcpServers"]["stage_skill"]
    assert "autoharness.stage_skill.server" in m["args"]
    assert (ROOT / "src/autoharness/stage_skill/server.py").exists()


def test_mcp_ships_only_this_plugin_servers():
    # 插件的 MCP 服务器安装到每个用户的会话中：剩下一个仅用于开发的服务器
    # 这里将在他们的机器上启动第三方代码。船舶边界的最低特权。
    assert set(_load(".claude-plugin/plugin.json")["mcpServers"]) == {"stage_skill"}


def test_no_project_mcp_json_at_repo_root():
    # 插件根目录是存储库根目录：这里的 .mcp.json 也是此签出的项目范围配置，
    # 它的排名高于插件的相同命令服务器，因此存储库内的会话获取该工具为
    # mcp__stage_skill__stage_skill 和 Reflector/curator 允许列表找不到任何可以舞台使用的内容
    assert not (ROOT / ".mcp.json").exists()


def test_marketplace_lists_this_plugin():
    mk = _load(".claude-plugin/marketplace.json")
    assert "autoharness" in [p["name"] for p in mk["plugins"]]


def test_agents_reflector_present():
    assert (ROOT / "agents/reflector.md").exists()


def test_agents_curator_present():
    assert (ROOT / "agents/curator.md").exists()  # 定期合并通行证代理


def test_learn_skill_ships_with_the_plugin():
    # 用户可调用条目（方向 B1）：必须存在于要提供的插件的技能/树中
    assert (ROOT / "skills" / "learn" / "SKILL.md").is_file()
