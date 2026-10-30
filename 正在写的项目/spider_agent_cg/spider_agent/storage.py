"""任务文件与事件追踪。"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"


def now():
    return datetime.now(timezone.utc).isoformat()


def new_run():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:10]
    path = RUNS / run_id
    path.mkdir(parents=True, exist_ok=False)
    return run_id, path


def run_path(run_id):
    if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{10}", run_id):
        raise ValueError("无效 run_id")
    path = RUNS / run_id
    if not path.is_dir():
        raise ValueError("任务不存在")
    return path


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def event(path, run_id, step, status, **details):
    row = {"timestamp": now(), "run_id": run_id, "step": step, "status": status, **details}
    with (path / "trace.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
