import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

const root = path.dirname(fileURLToPath(import.meta.url));

function launcher() {
  if (process.env.DSH_ENTRY) {
    return {
      command: process.env.DSH_BIN || process.execPath,
      args: [process.env.DSH_ENTRY],
    };
  }
  if (process.env.DSH_BIN || process.platform !== "win32") {
    return { command: process.env.DSH_BIN || "dsh", args: [] };
  }
  for (const directory of (process.env.PATH || "").split(path.delimiter)) {
    const entry = path.join(
      directory,
      "node_modules",
      "@deepseek-ai",
      "dsh",
      "lib",
      "bin.js",
    );
    if (existsSync(entry)) return { command: process.execPath, args: [entry] };
  }
  throw new Error("找不到 DSH，请安装 DSH 或配置 DSH_BIN / DSH_ENTRY。");
}

// ACP keeps sessions alive between prompts. The web service owns the process.
export class DshWorker {
  constructor(cwd, onUpdate = () => {}, options = {}) {
    this.cwd = cwd;
    this.onUpdate = onUpdate;
    this.pending = new Map();
    this.jobs = new Map();
    this.sessions = new Set();
    this.counter = 0;
    this.state = "idle";
    this.yolo = options.yolo ?? true;
  }
  async start() {
    if (this.ready) return this.ready;
    this.ready = (async () => {
      this.state = "starting";
      const launch = launcher();
      const args = [
        ...launch.args,
        "--profile",
        "acp",
        "--patch",
        path.join(root, "acp.patch.yml"),
      ];
      this.child = spawn(launch.command, args, {
        cwd: this.cwd,
        windowsHide: true,
        env: {
          ...process.env,
          DSH_HOME:
            process.env.DSH_WORKER_HOME || path.join(root, ".data", "dsh"),
          DSH_PERMISSION_MODE: this.yolo
            ? "danger-full-access"
            : "workspace-write",
        },
        stdio: ["pipe", "pipe", "pipe"],
      });
      const child = this.child;
      this.child.stderr.on("data", (chunk) => {
        let diagnostic = String(chunk);
        for (const secret of [
          process.env.ARK_API_KEY,
          process.env.WORKBENCH_TOKEN,
        ]) {
          if (secret) diagnostic = diagnostic.replaceAll(secret, "[redacted]");
        }
        console.error("DSH:", diagnostic);
      });
      const fail = (error) => {
        if (child !== this.child) return;
        this.state = "failed";
        this.error = error.message;
        for (const p of this.pending.values()) p.reject(error);
        this.pending.clear();
        this.ready = undefined;
        this.sessions.clear();
      };
      this.child.on("error", fail);
      this.child.on("exit", (code) =>
        fail(new Error(`DSH 进程退出 (${code})`)),
      );
      this.child.stdin.on("error", fail);
      createInterface({ input: this.child.stdout }).on("line", (line) => {
        if (child !== this.child) return;
        let message;
        try {
          message = JSON.parse(line);
        } catch {
          return;
        }
        if (message.method === "session/update") {
          if (message.params.update.sessionUpdate === "agent_thought_chunk")
            return;
          const job = [...this.jobs.values()].find(
            (j) =>
              j.sessionId === message.params.sessionId &&
              j.status === "running",
          );
          if (job) {
            job.updates.push(message.params.update);
            if (job.updates.length > 1000) job.updates.shift();
            this.projectUpdate(job, message.params.update);
            this.onUpdate(job);
          }
        } else if (message.id !== undefined && message.method) {
          if (message.method === "session/request_permission") {
            const option =
              this.yolo &&
              message.params.options?.find((o) => o.kind === "allow_once");
            this.send({
              jsonrpc: "2.0",
              id: message.id,
              result: {
                outcome: option
                  ? { outcome: "selected", optionId: option.optionId }
                  : { outcome: "cancelled" },
              },
            });
          } else
            this.send({
              jsonrpc: "2.0",
              id: message.id,
              error: { code: -32601, message: "Unsupported client request" },
            });
        } else if (message.id !== undefined) {
          const request = this.pending.get(message.id);
          this.pending.delete(message.id);
          if (message.error) request?.reject(new Error(message.error.message));
          else request?.resolve(message.result);
        }
      });
      try {
        const result = await this.call("initialize", {
          protocolVersion: 1,
          clientCapabilities: {},
          clientInfo: { name: "codex-dsh-worker", version: "0.1.0" },
        });
        this.state = "ready";
        return result;
      } catch (error) {
        fail(error);
        child.kill();
        this.ready = undefined;
        throw error;
      }
    })().catch((error) => {
      this.ready = undefined;
      this.state = "failed";
      this.error = error.message;
      throw error;
    });
    return this.ready;
  }
  send(message) {
    if (!this.child || this.child.stdin.destroyed)
      throw new Error("DSH 连接已关闭");
    this.child.stdin.write(JSON.stringify(message) + "\n");
  }
  call(method, params) {
    const id = ++this.counter;
    return new Promise((resolve, reject) => {
      const timeout =
        method === "session/prompt"
          ? Number(process.env.DSH_TASK_TIMEOUT_MS || 1800000)
          : Number(process.env.DSH_STARTUP_TIMEOUT_MS || 180000);
      const timer = setTimeout(() => {
        this.close();
        reject(new Error(`DSH ${method} 超时`));
      }, timeout);
      this.pending.set(id, {
        resolve: (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
      });
      try {
        this.send({ jsonrpc: "2.0", id, method, params });
      } catch (error) {
        this.pending.get(id)?.reject(error);
        this.pending.delete(id);
      }
    });
  }
  async create(sessionId) {
    await this.start();
    if (sessionId && this.sessions.has(sessionId)) return { sessionId };
    const result = sessionId
      ? await this.call("session/resume", {
          sessionId,
          cwd: this.cwd,
          mcpServers: [],
        })
      : await this.call("session/new", { cwd: this.cwd, mcpServers: [] });
    this.sessions.add(result.sessionId || sessionId);
    return { ...result, sessionId: result.sessionId || sessionId };
  }
  async prompt(sessionId, text, ownerId) {
    if (
      [...this.jobs.values()].some(
        (j) => j.sessionId === sessionId && j.status === "running",
      )
    )
      throw new Error("该 DSH 会话仍在执行");
    const id = randomUUID(),
      job = {
        id,
        sessionId,
        ownerId,
        status: "running",
        updates: [],
        steps: [],
        summary: "",
        startedAt: Date.now(),
      };
    this.jobs.set(id, job);
    try {
      await this.create(sessionId);
    } catch (error) {
      job.status = "failed";
      job.error = error.message;
      this.onUpdate(job);
      throw error;
    }
    this.onUpdate(job);
    this.call("session/prompt", { sessionId, prompt: [{ type: "text", text }] })
      .then((result) => {
        job.status = result.stopReason === "end_turn" ? "completed" : "stopped";
        job.result = result;
      })
      .catch((error) => {
        job.status = "failed";
        job.error = error.message;
      })
      .finally(() => {
        job.endedAt = Date.now();
        this.onUpdate(job);
      });
    return job;
  }
  async cancel(sessionId) {
    this.send({
      jsonrpc: "2.0",
      method: "session/cancel",
      params: { sessionId },
    });
    return { ok: true };
  }
  projectUpdate(job, update) {
    if (
      update.sessionUpdate === "agent_message_chunk" &&
      update.content?.text
    ) {
      job.summary = (job.summary + update.content.text).slice(-12000);
    }
    if (update.sessionUpdate === "usage_update") job.usage = update;
    if (!["tool_call", "tool_call_update"].includes(update.sessionUpdate))
      return;
    let step = job.steps.find((item) => item.id === update.toolCallId);
    if (!step) {
      step = {
        id: update.toolCallId,
        title: update.title || update.kind || "工具调用",
        status: "running",
      };
      job.steps.push(step);
    }
    if (update.title) step.title = update.title;
    if (update.status) step.status = update.status;
    const input = update.rawInput;
    if (input)
      step.detail = String(
        input.file_path ||
          input.path ||
          input.command ||
          input.cmd ||
          JSON.stringify(input),
      ).slice(0, 1500);
    if (update.locations?.length)
      step.detail = update.locations
        .map((location) => location.path)
        .join(", ");
  }
  report(job) {
    return {
      id: job.id,
      sessionId: job.sessionId,
      status: job.status,
      summary: job.summary?.slice(-6000),
      steps: job.steps?.slice(-20),
      result: job.result,
      error: job.error,
      usage: job.usage,
      elapsedMs: (job.endedAt || Date.now()) - job.startedAt,
      detailsCommand: `node worker-client.mjs details ${job.id}`,
    };
  }
  close() {
    const child = this.child;
    for (const request of this.pending.values())
      request.reject(new Error("DSH 连接已关闭"));
    this.pending.clear();
    this.sessions.clear();
    this.ready = undefined;
    this.child = null;
    this.state = "idle";
    child?.kill();
  }
}
