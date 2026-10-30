import subprocess

import pytest

from autoharness.lib import layer


def test_layers_are_the_two_known():
    assert set(layer.LAYERS) == {"global", "project"}


@pytest.mark.parametrize("lyr", layer.LAYERS)
def test_paths_nest_under_root(tmp_path, lyr):
    skills = layer.skills_dir(lyr, tmp_path)
    assert skills == tmp_path / "skills"
    assert layer.archive_dir(lyr, tmp_path) == skills / ".archive"
    assert layer.symbol_dir(lyr, "foo", tmp_path) == skills / "foo"
    assert layer.state_dir(lyr, tmp_path) == tmp_path / "autoharness"
    # 状态区域与实时技能脱节（计数器/队列永远不会进入实时技能树）
    assert layer.state_dir(lyr, tmp_path) != skills
    assert layer.archive_dir(lyr, tmp_path) != layer.symbol_dir(lyr, "foo", tmp_path)


def test_default_roots_differ_between_layers():
    assert layer.default_root("global") != layer.default_root("project")


@pytest.mark.parametrize("fn", [layer.skills_dir, layer.archive_dir, layer.state_dir])
def test_unknown_layer_rejected(fn):
    with pytest.raises(ValueError):
        fn("staging", "/tmp/whatever")


@pytest.mark.parametrize("bad", ["../evil", "a/b", "a\\b", "..", ".", ".archive", ""])
def test_symbol_name_traversal_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        layer.symbol_dir("project", bad, tmp_path)


@pytest.mark.parametrize("bad", ["a" * 101, "notes.", "con", "CON", "aux.md", "com1", "lpt9.txt", "nul"])
def test_new_name_the_filesystem_would_refuse_is_rejected(bad):
    # 一旦 mkstemp 添加后缀，就会过去 NAME_MAX，或者在 Windows 上不可用：创建之前拒绝
    with pytest.raises(ValueError):
        layer.check_new_name(bad)


@pytest.mark.parametrize("existing", ["a" * 101, "con", "notes."])
def test_existing_names_still_resolve(tmp_path, existing):
    # 用户的技能/缺点/或较长的遗留名称不得妨碍阅读库
    assert layer.symbol_dir("project", existing, tmp_path).name == existing


def test_new_subfile_segment_the_filesystem_would_refuse_is_rejected():
    for bad in ["references/" + "b" * 250 + ".md", "references/aux.md", "scripts/run."]:
        with pytest.raises(ValueError):
            layer.check_subfile(bad, new=True)
        layer.check_subfile(bad)  # 仍然可以寻址同名的现有文件


def test_ordinary_new_names_near_the_limit_pass():
    for ok in ["a" * 100, "console", "auxiliary-notes", "com10", "my.skill.v2"]:
        layer.check_new_name(ok)


def test_valid_symbol_name_ok(tmp_path):
    assert layer.symbol_dir("project", "my_skill-2.v1", tmp_path).name == "my_skill-2.v1"


# --- 子文件路径门（文件夹技能）---

@pytest.mark.parametrize("rel", ["scripts/run.sh", "references/notes.md",
                                 "templates/py/starter.py", "assets/logo.svg"])
def test_subfile_path_accepted_and_nests_under_symbol(tmp_path, rel):
    layer.check_subfile(rel)
    p = layer.subfile_path("project", "foo", rel, tmp_path)
    assert p == layer.symbol_dir("project", "foo", tmp_path) / rel


@pytest.mark.parametrize("bad", [
    "../x", "/etc/passwd", "scripts/../SKILL.md",      # 遍历/绝对
    "bin/x.sh",                                         # 非白名单顶级目录
    "notes.md", "SKILL.md", ".sidecar.json", ".ledger.jsonl",  # <2 段：没有顶级文件
    "references/.hidden", "references//x",              # 点段/空段
    "scripts/a\\b", "", None, 7,                        # 反斜杠/空/非字符串
])
def test_subfile_gate_rejects(bad):
    with pytest.raises(ValueError):
        layer.check_subfile(bad)


def test_subfile_dirs_whitelist_is_the_four():
    assert set(layer.SUBFILE_DIRS) == {"scripts", "templates", "assets", "references"}


# --- 项目根：链接工作树重映射 ---

def _git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True,
    )


@pytest.fixture
def main_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.fixture
def linked_worktree(main_repo):
    wt = main_repo / ".claude" / "worktrees" / "br"
    _git(main_repo, "worktree", "add", "-q", "-b", "br", str(wt))
    return wt


def _project_root_at(monkeypatch, cwd):
    monkeypatch.chdir(cwd)
    return layer.default_root(layer.PROJECT)


def test_project_root_non_git_is_cwd(tmp_path, monkeypatch):
    assert _project_root_at(monkeypatch, tmp_path) == tmp_path / ".claude"


def test_project_root_main_repo_is_cwd(main_repo, monkeypatch):
    assert _project_root_at(monkeypatch, main_repo) == main_repo / ".claude"


def test_project_root_repo_subdir_stays_cwd_no_jump_to_repo_root(main_repo, monkeypatch):
    sub = main_repo / "nested_project"
    sub.mkdir()
    assert _project_root_at(monkeypatch, sub) == sub / ".claude"


def test_project_root_linked_worktree_maps_to_main_root(linked_worktree, main_repo, monkeypatch):
    assert _project_root_at(monkeypatch, linked_worktree) == main_repo / ".claude"


def test_project_root_worktree_and_main_resolve_same_path(linked_worktree, main_repo, monkeypatch):
    from_wt = _project_root_at(monkeypatch, linked_worktree)
    from_main = _project_root_at(monkeypatch, main_repo)
    assert from_wt == from_main


def test_project_root_worktree_subdir_maps_to_main_root(linked_worktree, main_repo, monkeypatch):
    sub = linked_worktree / "src"
    sub.mkdir()
    assert _project_root_at(monkeypatch, sub) == main_repo / ".claude"


def test_project_root_worktree_outside_repo_maps_to_main_root(main_repo, tmp_path, monkeypatch):
    wt = tmp_path / "outside-wt"
    _git(main_repo, "worktree", "add", "-q", "-b", "out", str(wt))
    assert _project_root_at(monkeypatch, wt) == main_repo / ".claude"


def test_worktree_root_cache_normalizes_symlink(linked_worktree, main_repo, tmp_path, dir_link):
    alias = tmp_path / "worktree-alias"
    dir_link(alias, linked_worktree)
    layer._main_worktree_root_resolved.cache_clear()

    assert layer._main_worktree_root(str(alias)) == main_repo
    after_alias = layer._main_worktree_root_resolved.cache_info()
    assert layer._main_worktree_root(str(linked_worktree)) == main_repo
    after_real_path = layer._main_worktree_root_resolved.cache_info()

    assert after_alias.misses == 1
    assert after_real_path.hits == after_alias.hits + 1
    assert after_real_path.misses == after_alias.misses


def test_project_root_git_failure_falls_back_to_cwd(linked_worktree, monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("git not installed")
    monkeypatch.setattr(layer.subprocess, "run", boom)
    layer._main_worktree_root_resolved.cache_clear()
    assert _project_root_at(monkeypatch, linked_worktree) == linked_worktree / ".claude"


def test_project_root_global_layer_unaffected(linked_worktree, monkeypatch):
    monkeypatch.chdir(linked_worktree)
    assert layer.default_root(layer.GLOBAL) == layer.default_root(layer.GLOBAL)
    assert ".claude/worktrees" not in str(layer.default_root(layer.GLOBAL))
