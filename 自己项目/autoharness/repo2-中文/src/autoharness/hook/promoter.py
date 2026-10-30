"""启动者：主机技能树的唯一确定性编写者（入场门、★安全瓶颈）。

阅读意图（反射器通过 stage_skill 发送的提案）→ 在内存中形成最终的全文→
验证内存中的六个类 → 仅在以原子方式写入磁盘时验证（在任何写入之前验证）。
模型只提出，不涉及磁盘；着陆和验证都发生在这里。以 K8s 为模型
验证准入（在飞行中验证，仅在允许时保留）+ POSIX 原子写入。

- 塑造：创建/更新=意图体；补丁 = 实时读取 + 应用增量；删除=无（删除）。
- 层分辨率：create 采用意图“level”；更新/补丁/删除通过skill_store.find
  （跨层同名错误，缺失则拒绝）。
- 验证：重用lib.validate的六个类，馈送{**意图，级别：已解析层}（全局门
  也适用于更新）。
- 着陆（通过后）：首先着陆意图子文件（路径重新门控；每个着陆父母都解决并
  在任何写入之前进行转义检查 - 预先植入的符号链接拒绝零写入）→具体化
  证据切片到引用/证据-<hash>.md（在此出口处再次编辑，内容寻址→
  幂等；模型从不命名或写入它）→ 最后写入 SKILL.md （原子替换 = 提交
  点：召回仅读取SKILL.md，因此读者永远不会看到它指向未登陆的子文件）→创建
  标记 sidecar created_by:agent → 附加意图自己的 LED 和证据作为切片的 LED
  相对路径。删除 = 物化证据 + LED 报废 + 档案移出（整个目录
  os.replace 携带切片）。 remove_file = 删除一个子文件（路径重新门控 + 转义检查；
  被拒绝，而实时 SKILL.md 仍然引用它；缺少目标=无操作，因此崩溃重播会保留
  幂等）+证据+已删除路径的LED。拒绝=零写入，没有邮票，没有分类账。
- Drain：读队列→逐一提升→最后清除（至少一次+原子地=有效
  恰好一次）；启动时扫描孤儿.tmp。崩溃时，未处理的意图保留在持久队列中
  并在下次重试；在从不运行的极端→零着陆（故障安全）。

马尾辫：每个项目根目录的一个排水管现在通过 lib.lock 进行序列化（请参阅排水管）。 LED 水印仍以 CAP 的真实值为准；创建锚点在着陆时读取层请求计数器（试用期是虚构的，没有真正的锚点）。整体运行清晰，微小的崩溃窗口（在陆地和清晰之间）可能会重新附加 LED - 每个项目幂等水印，等待意图队列粒度最终确定（验证存储打开）。"""
import hashlib
import json

from autoharness import config
from autoharness.lib import (
    atomic,
    counters,
    intent_queue,
    layer,
    ledger,
    lock,
    notify,
    redact,
    sidecar,
    skill_store,
    validate,
)

_MODIFY = ("update", "patch", "remove_file", "delete")


def _reject(action, level, findings):
    return {"ok": False, "action": action, "level": level, "findings": findings}


def _resolve_level(intent, roots):
    if intent.get("action") == "create":
        return intent.get("level")
    return skill_store.find(intent.get("name"), roots)


def _shape(intent, level, root):
    action = intent.get("action")
    if action in ("create", "update"):
        body = intent.get("body")
        if body is None:
            raise ValueError(f"{action} requires body")
        return body
    if action == "patch":
        live = skill_store.read_body(level, intent.get("name"), root)
        if live is None:
            raise ValueError("patch target has no live body")
        return skill_store.apply_delta(live, intent["old_string"], intent["new_string"])
    if action in ("remove_file", "delete"):
        return None
    raise ValueError(f"unknown action: {action!r}")


def _led(intent, evidence_ref):
    entry = {"action": intent.get("action"),
             "reason": intent.get("reason"),
             "evidence": evidence_ref}
    if intent.get("path"):
        entry["path"] = intent["path"]
    if intent.get("absorbed_into"):
        entry["absorbed_into"] = intent["absorbed_into"]  # 合并与修剪，在账户中可区分
    return entry


def _materialize_evidence(level, name, evidence, root):
    text = redact.redact(evidence)
    rel = f"{layer.EVIDENCE_PREFIX}{hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]}.md"
    p = layer.subfile_path(level, name, rel, root)
    if not p.exists():
        atomic.write_text(p, text)
    return rel


def _land_files(level, name, files, root):
    if not files:
        return
    sdir = layer.symbol_dir(level, name, root).resolve()
    paths = {rel: layer.subfile_path(level, name, rel, root) for rel in sorted(files)}
    for rel, p in paths.items():
        if not p.resolve().is_relative_to(sdir):
            raise ValueError(f"subfile escapes the skill dir: {rel}")
    for rel, p in paths.items():
        atomic.write_text(p, files[rel])


def _remove_subfile(level, name, rel, root):
    p = layer.subfile_path(level, name, rel, root)
    sdir = layer.symbol_dir(level, name, root).resolve()
    if not p.resolve().is_relative_to(sdir):
        raise ValueError(f"subfile escapes the skill dir: {rel}")
    live = skill_store.read_body(level, name, root) or ""
    # 使用与准入相同的上下文指针解释。标记
    # 请求的路径已知，即使它已经不存在：它的指针仍然需要修补。
    if rel in validate.subfile_references(live, base_dir=sdir, files={rel: ""}):
        raise ValueError(f"{rel} is still referenced by the live SKILL.md (patch the pointer out first)")
    if p.is_file():
        p.unlink()


def _land(action, intent, body, level, name, root):
    if action == "delete":
        evidence_ref = _materialize_evidence(level, name, intent.get("evidence"), root)
        ledger.append(level, name, _led(intent, evidence_ref), root)
        skill_store.archive(level, name, root)
        return
    if action == "remove_file":
        _remove_subfile(level, name, intent["path"], root)
        evidence_ref = _materialize_evidence(level, name, intent.get("evidence"), root)
        ledger.append(level, name, _led(intent, evidence_ref), root)
        return
    _land_files(level, name, intent.get("files"), root)
    evidence_ref = _materialize_evidence(level, name, intent.get("evidence"), root)
    skill_store.write_body(level, name, body, root)
    if action == "create":
        existing = sidecar.read(level, name, root)
        if not existing:
            sidecar.create(level, name, counters.request_count(level, root), root)
        # 崩溃重播：sidecar 已经存在 — 跳过创建以保留计数器
    else:
        sidecar.bump_patch(level, name, root)  # 更新/补丁：提供改进后重用对
    ledger.append(level, name, _led(intent, evidence_ref), root)


def promote(intent, *, roots=None, repo_name=None):
    roots = roots or {}
    action = intent.get("action")
    name = intent.get("name")
    if action == "create":
        try:  # 在任何文件系统调用之前：超过 NAME_MAX 的名称将引发，而不是拒绝
            layer.check_new_name(name)
        except ValueError as exc:
            return _reject(action, None, [("shape", str(exc))])

    try:
        level = _resolve_level(intent, roots)
    except ValueError as exc:
        return _reject(action, None, [("routing", str(exc))])
    if level not in layer.LAYERS:
        return _reject(action, level, [("routing", f"unresolved/illegal level: {level!r}")])
    if level == layer.GLOBAL and config.DISABLE_GLOBAL:
        return _reject(action, level,
                       [("routing", "global layer is disabled by AUTOHARNESS_DISABLE_GLOBAL")])

    if level == layer.GLOBAL:
        # 每个项目的排水锁无法协调另一个项目的编辑
        # 同一个全球图书馆。保持仅限本地的促销活动的独立性。
        with lock.file_lock(layer.state_dir(level, roots.get(level)) / "promote.lock"):
            return _promote_resolved(intent, action, name, level, roots, repo_name)
    return _promote_resolved(intent, action, name, level, roots, repo_name)


def _promote_resolved(intent, action, name, level, roots, repo_name):
    root = roots.get(level)
    try:
        body = _shape(intent, level, root)
        base_dir = layer.symbol_dir(level, name, root)
    except (ValueError, KeyError) as exc:
        return _reject(action, level, [("shape", str(exc))])

    target_created = sidecar.is_agent_created(level, name, root) if action in _MODIFY else None

    absorbed = intent.get("absorbed_into")
    if action == "delete" and absorbed:
        # 失败关闭吸收声明（D方向，Hermes信任链第1层）：雨伞必须是
        # 一种与目标不同的活生生的、自我产生的技能——一个幻觉的名字拒绝了这个意图。
        try:
            alevel = skill_store.find(absorbed, roots)
        except ValueError as exc:
            return _reject(action, level, [("absorbed_into", str(exc))])
        if alevel is None or absorbed == name \
                or not sidecar.is_agent_created(alevel, absorbed, roots.get(alevel)):
            return _reject(action, level,
                           [("absorbed_into", f"umbrella {absorbed!r} is not a live self-produced skill")])

    verdict = validate.validate(
        {**intent, "level": level}, body,
        target_is_agent_created=target_created, repo_name=repo_name, base_dir=base_dir,
    )
    if not verdict["ok"]:
        return _reject(action, level, verdict["findings"])

    try:
        _land(action, intent, body, level, name, root)
    except ValueError as exc:
        return _reject(action, level, [("landing", str(exc))])
    return {"ok": True, "action": action, "level": level, "findings": [], "notes": _notes(action, body)}


def _notes(action, body):
    """对落地意图的失败开放观察：不是拒绝，也不是沉默。

    缺失的类别只会将技能分组得很差（指数回落到“一般”），因此拒绝
    其上的真实内容是不成比例的——与描述门相反的说法，其中
    无线索的描述根本无法被回忆起来。它仍然必须到达帐户，否则
    图书馆在没有人注意到的情况下融入了一个扁平的群体。"""
    if action not in ("create", "update"):
        return []
    return [] if (validate._frontmatter(body) or {}).get("category") else ["category"]


def sweep(roots=None):
    roots = roots or {}
    removed = []
    for lyr in config.active_layers():
        removed += skill_store.sweep_orphans(lyr, roots.get(lyr))
    return removed


def _account(run_id, intents, verdicts, proot):
    """运行级判决账户（方向B，反静音）：每符号LED记录仅落地
    事实，因此被拒绝的作品将会消失得无影无踪——这个账户就是判决的所在地。
    last_run.json 提供单行 SessionStart 摘要，并在一次注入后被消耗。"""
    rows = [{"action": v.get("action"), "name": i.get("name"), "ok": v["ok"],
             "findings": [f[0] for f in v.get("findings", [])], "notes": v.get("notes", [])}
            for i, v in zip(intents, verdicts, strict=True)]
    landed = sum(1 for r in rows if r["ok"])
    absorbed = sum(1 for i, v in zip(intents, verdicts, strict=True)
                   if v["ok"] and i.get("action") == "delete" and i.get("absorbed_into"))
    families = sorted({f for r in rows if not r["ok"] for f in r["findings"]})
    state = layer.state_dir(layer.PROJECT, proot)
    runs = state / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    record = {"run_id": run_id, "verdicts": rows}
    atomic.write_text(runs / f"{run_id}.json", json.dumps(record, ensure_ascii=False, indent=2))
    atomic.write_text(state / "last_run.json",
                      json.dumps({"run_id": run_id, "landed": landed,
                                  "rejected": len(rows) - landed, "absorbed": absorbed,
                                  "families": families,
                                  "uncategorized": sum(1 for r in rows if "category" in r["notes"])},
                                 ensure_ascii=False))
    return record


def drain(run_id, *, roots=None, repo_name=None):
    roots = roots or {}
    proot = roots.get(layer.PROJECT)
    # 每个项目根一次有一个排水管。钩子是一个短暂的过程，因此两次传递同一个
    # 状态目录（并行工作树重新映射到一个根，或者一个被杀死的会话留下一个分离的
    # 升级运行）在文件级别交错：每次读取库时都不会看到
    # 对方的技能，各自落地。保持读取→着陆→清除，这也会关闭崩溃窗口
    # 下面的帐户评论过去曾向外部作者开放。
    with lock.file_lock(layer.state_dir(layer.PROJECT, proot) / "drain.lock"):
        sweep(roots)
        intents = intent_queue.read(run_id, proot)
        verdicts = [promote(i, roots=roots, repo_name=repo_name) for i in intents]
        record = _account(run_id, intents, verdicts, proot) if intents else None
        intent_queue.clear(run_id, proot)
    if record:
        # 清除后并在锁外：通知是即发即弃的，不得保留
        # 下一次从状态目录传出
        notify.send(record)
    return verdicts
