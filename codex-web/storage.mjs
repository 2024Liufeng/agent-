import {
  mkdir,
  readFile,
  readdir,
  rename,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";

export class Storage {
  constructor(directory) {
    this.directory = directory;
    this.queue = Promise.resolve();
  }

  async read(filename, fallback) {
    try {
      return JSON.parse(
        await readFile(path.join(this.directory, filename), "utf8"),
      );
    } catch (error) {
      if (error.code === "ENOENT") return fallback;
      throw error;
    }
  }

  write(filename, value) {
    const encoded = JSON.stringify(value, null, 2);
    const operation = this.queue.then(async () => {
      const target = path.join(this.directory, filename);
      await writeFile(target + ".tmp", encoded, { mode: 0o600 });
      for (let attempt = 0; ; attempt++) {
        try {
          await rename(target + ".tmp", target);
          return;
        } catch (error) {
          if (
            !["EPERM", "EACCES", "EBUSY"].includes(error.code) ||
            attempt === 5
          )
            throw error;
          await delay(50 * 2 ** attempt);
        }
      }
    });
    this.queue = operation.catch(() => {});
    return operation;
  }

  async sessions(defaultWorkspaceId) {
    await mkdir(this.directory, { recursive: true });
    const files = [
      ...new Set(
        (await readdir(this.directory))
          .filter((file) => /^[a-f0-9-]{36}\.json(?:\.tmp)?$/.test(file))
          .map((file) => file.replace(/\.tmp$/, "")),
      ),
    ];
    const sessions = new Map();
    for (const file of files) {
      const candidates = [];
      for (const candidate of [file, file + ".tmp"]) {
        try {
          const filename = path.join(this.directory, candidate);
          const value = JSON.parse(await readFile(filename, "utf8"));
          if (value.id + ".json" === file && Array.isArray(value.items)) {
            candidates.push({
              value,
              modified: (await stat(filename)).mtimeMs,
            });
          }
        } catch (error) {
          if (error.code !== "ENOENT" && !(error instanceof SyntaxError))
            throw error;
        }
      }
      candidates.sort((a, b) => b.modified - a.modified);
      if (!candidates.length) throw new Error(`会话文件无法恢复：${file}`);
      const session = candidates[0].value;
      session.workspaceId ||= defaultWorkspaceId;
      session.createdAt ||= new Date(candidates[0].modified).toISOString();
      session.updatedAt ||= session.createdAt;
      session.settings ||= {};
      if (!Array.isArray(session.dshSessions)) {
        const previous = session.items
          .map((item) => item.text || "")
          .join("\n");
        session.dshSessions = [
          ...new Set(
            [...previous.matchAll(/"sessionId"\s*:\s*"([a-f0-9-]{36})"/g)].map(
              (match) => match[1],
            ),
          ),
        ];
      }
      session.title ||=
        session.items.find((item) => item.kind === "user")?.text.slice(0, 32) ||
        "新会话";
      if (session.turnId)
        session.items.push({
          kind: "error",
          text: "服务曾重启，请发送消息继续。",
        });
      session.turnId = null;
      session.sending = false;
      session.resumed = false;
      for (const item of session.items) {
        if (item.kind !== "tool") continue;
        item.status ||= "completed";
        if (item.status === "running") item.status = "interrupted";
        // Older DSH cards contained an unstructured mixture of diagnostics and text.
        if (item.title?.startsWith("DSH ·") && !item.source) {
          item.source = "dsh";
          item.text = "旧版协作记录。新任务将显示文件、操作状态和结果摘要。";
        }
      }
      sessions.set(session.id, session);
    }
    return sessions;
  }
}
