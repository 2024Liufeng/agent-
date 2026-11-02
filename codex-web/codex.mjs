import { spawn } from "node:child_process";
import { createInterface } from "node:readline";

export class CodexRuntime {
  constructor(cwd, onEvent, onFailure) {
    this.cwd = cwd;
    this.onEvent = onEvent;
    this.onFailure = onFailure;
    this.pending = new Map();
    this.sequence = 0;
  }

  async start() {
    if (this.ready) return this.ready;
    this.ready = this.boot().catch((error) => {
      this.ready = undefined;
      throw error;
    });
    return this.ready;
  }

  async boot() {
    const child = spawn(
      process.env.CODEX_BIN || "codex",
      ["app-server", "--listen", "stdio://"],
      {
        cwd: this.cwd,
        windowsHide: true,
        stdio: ["pipe", "pipe", "pipe"],
      },
    );
    this.child = child;
    child.stderr.on("data", (chunk) => {
      let text = String(chunk);
      for (const secret of [
        process.env.ARK_API_KEY,
        process.env.WORKBENCH_TOKEN,
      ]) {
        if (secret) text = text.replaceAll(secret, "[redacted]");
      }
      console.error(text);
    });
    const fail = (error) => {
      if (child !== this.child) return;
      this.child = null;
      this.ready = undefined;
      for (const request of this.pending.values()) request.reject(error);
      this.pending.clear();
      this.onFailure(error);
    };
    child.on("error", fail);
    child.stdin.on("error", fail);
    child.on("exit", (code) => fail(new Error(`Codex 进程退出 (${code})`)));
    createInterface({ input: child.stdout }).on("line", (line) => {
      if (child !== this.child) return;
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        return;
      }
      if (message.id !== undefined && !message.method) {
        const request = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) request?.reject(new Error(message.error.message));
        else request?.resolve(message.result);
      } else if (message.id !== undefined) {
        this.send({
          id: message.id,
          error: {
            code: -32601,
            message: "此界面不支持该交互。可调整工作区权限后重试。",
          },
        });
      } else {
        this.onEvent(message);
      }
    });
    try {
      await this.call("initialize", {
        clientInfo: {
          name: "codex_mobile_workspace",
          title: "Codex Mobile",
          version: "0.2.0",
        },
      });
      this.send({ method: "initialized", params: {} });
    } catch (error) {
      fail(error);
      child.kill();
      throw error;
    }
  }

  send(message) {
    if (!this.child || this.child.stdin.destroyed)
      throw new Error("Codex 服务未连接");
    this.child.stdin.write(JSON.stringify(message) + "\n");
  }

  call(method, params) {
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} 请求超时`));
      }, 30000);
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
        this.send({ id, method, params });
      } catch (error) {
        this.pending.get(id)?.reject(error);
        this.pending.delete(id);
      }
    });
  }

  close() {
    this.child?.kill();
  }
}
