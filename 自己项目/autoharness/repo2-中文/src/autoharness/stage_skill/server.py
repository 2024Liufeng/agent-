"""stage_skill：反射器的唯一写入表面（发射意图提议工具）。

该模型是改变技能的唯一途径——而不是通用的写入/编辑。该工具**仅附加到
每次运行意图队列，永远不会触及任何技能树**：塑造/内容交叉引用/安全/
登陆全部生活在确定性启动子中（准入模型，模型无法触及）。仅工具
预先检查“结构”；发起人涵盖“塑造+内容+安全+落地”（纵深防御——
确定性方面并不完全信任工具表面）。

- 模式执行：操作枚举；每个动作 body|delta|path 必需且互斥； LED
  所需的理由/证据；创建的级别枚举（默认项目；更新/补丁/的层
  remove_file/delete 由发起者通过两层查找来解析）。
- 对参数的即时反馈：创建/更新运行结构检查（frontmatter + 名称/描述，重用
  validate.struct) + 身体尺寸，因此模型可以在子代理会话中当场修复它
  而不是重做一整圈。
- 附加意图的形状与promote.promote消耗的内容相匹配（补丁使用顶级
  旧字符串/新字符串）。

马尾辫：MCP stdio 进程 shell（服务）+ .mcp.json 注册推迟到第 7 阶段 — 零依赖规则禁止拉入 mcp SDK，而线形式取决于第 0 阶段 MCP 范围峰值的结论。该模块当前提供确定性处理程序：TOOL_SCHEMA（广告表面）+ stage（强制权限；条件 body|delta 结构位于此处，在 JSON 模式中无法清晰表达）。 run_id/root 由spawn 通过env 注入（第5 阶段），并在此处作为args 接收。"""
import json
import os
import sys

from autoharness import config
from autoharness.lib import intent_queue, layer, validate

_ACTIONS = ("create", "update", "patch", "remove_file", "delete")
_BODY_ACTIONS = ("create", "update")
TOOL_NAME = "stage_skill"
_PROTOCOL_VERSION = "2024-11-05"

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(_ACTIONS),
                   "description": "create=new (with level) / update=replace whole file / patch=small edit (delta) / "
                                  "remove_file=drop one subfile / delete=remove the whole skill"},
        "name": {"type": "string", "description": "skill symbol name"},
        "level": {"type": "string", "enum": list(layer.LAYERS),
                  "description": "create only; defaults to project, global has a high bar"},
        "body": {"type": "string", "description": "create/update: full SKILL.md text"},
        "old_string": {"type": "string", "description": "patch: text to replace (must match the live copy uniquely)"},
        "new_string": {"type": "string", "description": "patch: replacement text"},
        "reason": {"type": "string", "description": "LED: why the change (required)"},
        "evidence": {"type": "string", "description": "LED: triggering evidence slice (required)"},
        "files": {"type": "object", "additionalProperties": {"type": "string"},
                  "description": "create/update only: subfiles as relative path -> content, under "
                                 "scripts/|templates/|assets/|references/; each must be referenced "
                                 "by its relative path in the SKILL.md body"},
        "path": {"type": "string",
                 "description": "remove_file only: relative path of the subfile to remove; the live "
                                "SKILL.md must no longer reference it (patch the pointer out first)"},
        "absorbed_into": {"type": "string",
                          "description": "delete only: the umbrella skill that absorbed this one's "
                                         "content (empty/omitted = pure retirement). The promoter "
                                         "verifies the umbrella actually exists — a hallucinated "
                                         "name rejects the whole intent"},
    },
    "required": ["action", "name", "reason", "evidence"],
}


def _nonempty(params, key):
    v = params.get(key)
    return isinstance(v, str) and bool(v.strip())


def _schema_errors(params):
    action = params.get("action")
    if action not in _ACTIONS:
        return [("schema", f"action must be one of {_ACTIONS}, got {action!r}")]
    errors = []
    if not _nonempty(params, "name"):
        errors.append(("schema", "name required (non-empty)"))
    else:
        try:  # 活动结束后发起人会拒绝
            (layer.check_new_name if action == "create" else layer._check_name)(params["name"])
        except ValueError as exc:
            errors.append(("schema", str(exc)))
    if not _nonempty(params, "reason") or not _nonempty(params, "evidence"):
        errors.append(("schema", "LED reason+evidence required"))

    has_body = params.get("body") is not None
    has_delta = params.get("old_string") is not None or params.get("new_string") is not None
    has_files = params.get("files") is not None
    if action != "remove_file" and params.get("path") is not None:
        errors.append(("schema", f"{action} takes no path (path is remove_file only)"))
    if action != "delete" and params.get("absorbed_into") is not None:
        errors.append(("schema", f"{action} takes no absorbed_into (delete only)"))
    if action in _BODY_ACTIONS:
        if not has_body:
            errors.append(("schema", f"{action} requires body"))
        if has_delta:
            errors.append(("schema", f"{action} takes body, not old_string/new_string"))
        if has_files and not isinstance(params["files"], dict):
            errors.append(("schema", "files must be an object of relative path -> content"))
        if action == "create":
            level = params.get("level", layer.PROJECT)
            if level not in layer.LAYERS:
                errors.append(("schema", f"level must be one of {layer.LAYERS}, got {level!r}"))
            elif level == layer.GLOBAL and config.DISABLE_GLOBAL:
                errors.append(("routing", "global layer is disabled by AUTOHARNESS_DISABLE_GLOBAL"))
    elif action == "patch":
        if has_body:
            errors.append(("schema", "patch takes old_string/new_string, not body"))
        if params.get("old_string") is None or params.get("new_string") is None:
            errors.append(("schema", "patch requires both old_string and new_string"))
        if has_files:
            errors.append(("schema", "patch takes no files (use update to change subfiles)"))
    elif action == "remove_file":
        if not _nonempty(params, "path"):
            errors.append(("schema", "remove_file requires path"))
        if has_body or has_delta or has_files:
            errors.append(("schema", "remove_file takes only path, no body/delta/files"))
    elif action == "delete":
        if has_body or has_delta:
            errors.append(("schema", "delete takes no body/delta"))
        if has_files:
            errors.append(("schema", "delete takes no files"))
    return errors


def _content_errors(params):
    if params["action"] == "remove_file":
        return validate.check_remove_path(params["path"])
    body = params.get("body")
    if body is None:
        return []
    errors = []
    if len(body.encode("utf-8")) > config.STAGE_MAX_BODY_BYTES:
        errors.append(("size", f"body exceeds {config.STAGE_MAX_BODY_BYTES} bytes"))
    files = params.get("files")
    errors += validate.check_files(files, creating=params["action"] == "create")
    errors += validate.structure(body, files)
    if params.get("action") in ("create", "update"):
        # 发起者是权威，但它在本次会话消失后运行：描述门
        # 只有一个模型永远无法学习的地方才被强制执行——它会进入、退出，然后
        # 判决结果保存在一个文件中，没有人读回它。检查这里将错误传递给
        # 作者，同时它仍然可以重写（出于同样的原因，hermes 在 Skill_manage 中进行验证）。
        desc = (validate._frontmatter(body) or {}).get("description")
        if desc:
            errors += validate.description_findings(desc)
    return errors


def _intent(params):
    action = params["action"]
    intent = {"action": action, "name": params["name"],
              "reason": params["reason"], "evidence": params["evidence"]}
    if action == "create":
        intent["level"] = params.get("level", layer.PROJECT)
    if action in _BODY_ACTIONS:
        intent["body"] = params["body"]
        if params.get("files"):
            intent["files"] = params["files"]
    elif action == "patch":
        intent["old_string"] = params["old_string"]
        intent["new_string"] = params["new_string"]
    elif action == "remove_file":
        intent["path"] = params["path"]
    if action == "delete" and params.get("absorbed_into"):
        intent["absorbed_into"] = params["absorbed_into"]
    return intent


def stage(params, *, run_id, root=None):
    errors = _schema_errors(params)
    if not errors:
        errors += _content_errors(params)
    if errors:
        return {"ok": False, "errors": errors, "intent": None}
    intent = _intent(params)
    try:
        intent_queue.append(run_id, intent, root)
    except ValueError as exc:
        return {"ok": False, "errors": [("queue", str(exc))], "intent": None}
    return {"ok": True, "errors": [], "intent": intent}


def _ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(request, *, run_id, root=None):
    method = request.get("method")
    req_id = request.get("id")
    if method == "initialize":
        return _ok(req_id, {"protocolVersion": _PROTOCOL_VERSION,
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": TOOL_NAME, "version": "0.2.0"}})
    if method == "tools/list":
        return _ok(req_id, {"tools": [{"name": TOOL_NAME,
                                       "description": "the reflector's sole write surface: emit-intent, only appends "
                                                      "to the per-run intent queue, never touches the skill tree",
                                       "inputSchema": TOOL_SCHEMA}]})
    if method == "tools/call":
        params = request.get("params") or {}
        if params.get("name") != TOOL_NAME:
            return _err(req_id, -32602, f"unknown tool: {params.get('name')}")
        out = stage(params.get("arguments") or {}, run_id=run_id, root=root)
        return _ok(req_id, {"content": [{"type": "text",
                                         "text": json.dumps(out, ensure_ascii=False, default=list)}],
                            "isError": not out["ok"]})
    if req_id is None:
        return None
    return _err(req_id, -32601, f"method not found: {method}")


def serve(stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    run_id = os.environ.get(config.RUN_ID_ENV) or config.INTERACTIVE_RUN_ID
    root = os.environ.get(config.PROJECT_ROOT_ENV) or None
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        response = handle(json.loads(line), run_id=run_id, root=root)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


if __name__ == "__main__":
    serve()
