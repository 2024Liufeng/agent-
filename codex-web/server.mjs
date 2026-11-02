import http from "node:http";
import path from "node:path";
import os from "node:os";
import { readFile, realpath, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { randomUUID, timingSafeEqual } from "node:crypto";
import { fileURLToPath } from "node:url";
import { Storage } from "./storage.mjs";
import { CodexRuntime } from "./codex.mjs";
import { DshWorker } from "./dsh.mjs";
import { listDirectories } from "./directories.mjs";

const root = path.dirname(fileURLToPath(import.meta.url));
if (existsSync(path.join(root, ".data/provider.env")))
  process.loadEnvFile(path.join(root, ".data/provider.env"));
const storage = new Storage(
  process.env.WORKBENCH_DATA_DIR || path.join(root, ".data"),
);
const defaultPath = await realpath(
  process.env.WORKSPACE || path.join(root, "../正在写的项目/spider_agent_cg"),
);
const registry = await storage.read("workspaces.json", {
  workspaces: [
    {
      id: "default",
      name: "SpiderAgent",
      path: defaultPath,
      preferences:
        "优先使用试采和实际运行验收。不要默认运行或新增单元测试，除非用户明确要求。",
    },
  ],
  defaults: {},
});
const sessions = await storage.sessions("default");
const streams = new Map(),
  workers = new Map(),
  chatRuntimes = new Map(),
  sending = new Set();
const token = process.env.WORKBENCH_TOKEN || "";
const host = process.env.HOST || "127.0.0.1";
if (host !== "127.0.0.1" && !token)
  throw new Error("外部访问必须设置 WORKBENCH_TOKEN");
process.env.WORKBENCH_URL ||= `http://127.0.0.1:${process.env.PORT || 3088}`;
let capabilities,
  shuttingDown = false;
const runtime = new CodexRuntime(
  defaultPath,
  () => {},
  () => {
    capabilities = null;
  },
);
function runtimeFor(session) {
  if (!chatRuntimes.has(session.id)) {
    const chat = new CodexRuntime(
      workspaceFor(session).path,
      handleEvent,
      (error) => {
        if (chatRuntimes.get(session.id) !== chat) return;
        session.resumed = false;
        if (session.turnId) {
          session.turnId = null;
          session.items.push({ kind: "error", text: error.message });
          publish(session);
        }
      },
    );
    chatRuntimes.set(session.id, chat);
  }
  return chatRuntimes.get(session.id);
}
function releaseRuntime(session) {
  const chat = chatRuntimes.get(session.id);
  chatRuntimes.delete(session.id);
  chat?.close();
  session.resumed = false;
}
const workspaceFor = (session) =>
  registry.workspaces.find((w) => w.id === session.workspaceId);
const preferences = (session) => ({
  model: null,
  effort: null,
  fast: null,
  dshEnabled: true,
  yolo: true,
  contextLimit: null,
  compactLimit: null,
  ...session.settings,
});
for (const session of sessions.values())
  session.settings = preferences({
    settings: { ...registry.defaults, ...session.settings },
  });
function publish(session) {
  session.updatedAt = new Date().toISOString();
  for (const response of streams.get(session.id) || [])
    response.write(`data: ${JSON.stringify(session)}\n\n`);
  storage
    .write(session.id + ".json", session)
    .catch((error) => console.error("会话保存失败", error.code));
}
function itemFor(session, id, values) {
  let item = session.items.find((i) => i.id === id);
  if (!item) {
    item = { id, ...values };
    session.items.push(item);
  }
  return item;
}
function handleEvent(message) {
  const p = message.params || {};
  const session = [...sessions.values()].find((s) => s.threadId === p.threadId);
  if (!session) return;
  if (message.method === "turn/started") {
    session.turnId = p.turn.id;
    session.lastCompletedTurn = null;
  }
  if (message.method === "item/agentMessage/delta")
    itemFor(session, p.itemId, { kind: "assistant", text: "" }).text += p.delta;
  if (message.method === "thread/tokenUsage/updated")
    session.usage = p.tokenUsage;
  if (
    message.method === "item/started" &&
    ["commandExecution", "fileChange", "mcpToolCall"].includes(p.item.type)
  ) {
    itemFor(session, p.item.id, {
      kind: "tool",
      source: "codex",
      title: p.item.command || p.item.tool || "修改文件",
      text: "",
      status: "running",
      startedAt: Date.now(),
    });
  }
  if (message.method === "item/commandExecution/outputDelta") {
    const item = session.items.find((i) => i.id === p.itemId);
    if (item) item.text += p.delta;
  }
  if (message.method === "item/completed") {
    const item = session.items.find((i) => i.id === p.item.id);
    if (item?.kind === "tool") {
      item.text =
        p.item.aggregatedOutput ||
        JSON.stringify(p.item.changes || p.item.result || item.text);
      item.status =
        (p.item.exitCode && p.item.exitCode !== 0) || p.item.status === "failed"
          ? "failed"
          : "completed";
      item.endedAt = Date.now();
    }
  }
  if (message.method === "turn/completed") {
    session.turnId = null;
    session.lastCompletedTurn = p.turn.id;
    for (const item of session.items)
      if (item.status === "running" && item.source === "codex") {
        item.status = "interrupted";
        item.endedAt = Date.now();
      }
    if (p.turn.status === "failed")
      session.items.push({
        kind: "error",
        text: p.turn.error?.message || "执行失败",
      });
  }
  if (message.method === "error")
    session.items.push({
      kind: "error",
      text: p.error?.message || "Codex 返回错误",
    });
  publish(session);
}
async function catalogue(cwd = defaultPath) {
  await runtime.start();
  if (!capabilities) {
    const models = [];
    let cursor;
    do {
      const page = await runtime.call("model/list", {
        includeHidden: false,
        cursor,
      });
      models.push(...page.data);
      cursor = page.nextCursor;
    } while (cursor);
    let metadata = [];
    try {
      metadata =
        JSON.parse(
          await readFile(
            path.join(
              process.env.CODEX_HOME || path.join(os.homedir(), ".codex"),
              "models_cache.json",
            ),
            "utf8",
          ),
        ).models || [];
    } catch {}
    capabilities = models.map((model) => ({
      ...model,
      contextWindow:
        metadata.find((m) => m.slug === model.model)?.context_window || null,
    }));
  }
  const config = (
    await runtime.call("config/read", { cwd, includeLayers: false })
  ).config;
  return {
    models: capabilities,
    defaults: {
      model: config.model,
      effort: config.model_reasoning_effort,
      serviceTier: config.service_tier,
      contextLimit: config.model_context_window,
      compactLimit: config.model_auto_compact_token_limit,
    },
  };
}
async function validateSettings(value, current, cwd) {
  const allowed = [
    "model",
    "effort",
    "fast",
    "dshEnabled",
    "yolo",
    "contextLimit",
    "compactLimit",
  ];
  if (Object.keys(value).some((key) => !allowed.includes(key)))
    throw new Error("未知设置");
  const next = { ...current, ...value };
  for (const key of ["fast", "dshEnabled", "yolo"])
    if (next[key] !== null && typeof next[key] !== "boolean")
      throw new Error("开关设置无效");
  const info = await catalogue(cwd);
  const model = info.models.find(
    (m) => m.model === (next.model || info.defaults.model),
  );
  if (!model) throw new Error("模型不在当前服务端目录中");
  if (
    next.effort &&
    !model.supportedReasoningEfforts.some(
      (e) => e.reasoningEffort === next.effort,
    )
  )
    throw new Error("当前模型不支持该思考强度");
  if (
    next.fast &&
    !model.serviceTiers?.some((t) => ["priority", "fast"].includes(t.id))
  )
    throw new Error("当前模型未提供 Fast");
  for (const key of ["contextLimit", "compactLimit"]) {
    if (
      next[key] !== null &&
      (!Number.isSafeInteger(next[key]) || next[key] < 1024)
    )
      throw new Error("上下文设置需为至少 1024 的整数");
  }
  if (
    next.contextLimit &&
    (!model.contextWindow || next.contextLimit > model.contextWindow)
  )
    throw new Error("上下文限制不能超过模型目录上限");
  if (
    next.compactLimit &&
    next.compactLimit >= (next.contextLimit || model.contextWindow || Infinity)
  )
    throw new Error("压缩阈值应小于上下文上限");
  return next;
}
function workerFor(session) {
  const settings = preferences(session);
  if (!settings.dshEnabled) throw new Error("此会话已关闭 DSH 协作");
  const key = session.workspaceId + ":" + settings.yolo;
  if (!workers.has(key))
    workers.set(
      key,
      new DshWorker(workspaceFor(session).path, updateDshActivity, {
        yolo: settings.yolo,
      }),
    );
  return workers.get(key);
}
function updateDshActivity(job) {
  const session = sessions.get(job.ownerId);
  if (!session) return;
  const item = itemFor(session, job.id, {
    kind: "tool",
    source: "dsh",
    startedAt: Date.now(),
    text: "",
  });
  item.title = "DSH 协作";
  item.status = job.status;
  item.steps = job.steps || [];
  const stopNote = job.result?.stopReason === "max_tokens"
    ? "本轮达到输出上限，可在同一协作会话中继续。"
    : job.status === "stopped" ? "本轮已停止，可以继续补充要求。" : "";
  item.text = [job.summary, job.error, stopNote].filter(Boolean).join("\n\n");
  if (job.status !== "running") item.endedAt = Date.now();
  publish(session);
}
function instructions(session) {
  const w = workspaceFor(session),
    settings = preferences(session);
  return `Project preferences (apply to this and future turns): ${w.preferences || "无额外项目偏好"}\n${settings.dshEnabled ? `Use the delegation skill at ${path.resolve(root, "../.agents/skills/dsh-delegation/SKILL.md")}. Its helper is ${path.join(root, "worker-client.mjs")}. Set WORKBENCH_SESSION_ID=${session.id} on every helper call. Reuse worker session ids in this conversation. Choose execution based on total handoff and review cost.` : "DSH is disabled for this conversation. Complete tasks directly; do not invoke DSH."}\nUser chose ${settings.yolo ? "YOLO full access" : "workspace-only access with no escalation"}.`;
}
async function bindThread(session) {
  const settings = preferences(session),
    w = workspaceFor(session);
  const info = await catalogue(w.path);
  const model = info.models.find(
    (m) => m.model === (settings.model || info.defaults.model),
  );
  const contextWindow =
    settings.contextLimit || info.defaults.contextLimit || model?.contextWindow;
  const config = {
    model_reasoning_effort:
      settings.effort || model?.defaultReasoningEffort || info.defaults.effort,
    model_context_window: contextWindow,
    model_auto_compact_token_limit:
      settings.compactLimit ||
      info.defaults.compactLimit ||
      (contextWindow ? Math.floor(contextWindow * 0.8) : null),
  };
  for (const key of Object.keys(config))
    if (config[key] == null) delete config[key];
  const params = {
    cwd: w.path,
    approvalPolicy: "never",
    sandbox: settings.yolo ? "danger-full-access" : "workspace-write",
    developerInstructions: instructions(session),
    config,
  };
  if (settings.model) params.model = settings.model;
  if (settings.fast !== null)
    params.serviceTier = settings.fast ? "priority" : "default";
  const response = await runtimeFor(session).call(
    session.threadId ? "thread/resume" : "thread/start",
    { ...params, ...(session.threadId ? { threadId: session.threadId } : {}) },
  );
  session.threadId = response.thread.id;
  session.resumed = true;
  session.effective = {
    model: response.model,
    effort: response.reasoningEffort,
    serviceTier: response.serviceTier,
    cwd: response.cwd,
    yolo: response.sandbox.type === "dangerFullAccess",
    contextLimit: contextWindow,
    compactLimit: config.model_auto_compact_token_limit,
    updatedAt: new Date().toISOString(),
  };
}
async function submit(session, text) {
  if (sending.has(session.id)) throw new Error("上一条消息正在提交");
  sending.add(session.id);
  try {
    const chat = runtimeFor(session);
    await chat.start();
    if (!session.resumed) await bindThread(session);
    const item = { id: randomUUID(), kind: "user", text };
    session.items.push(item);
    publish(session);
    try {
      const params = {
        threadId: session.threadId,
        input: [{ type: "text", text, text_elements: [] }],
      };
      if (session.turnId)
        await chat.call("turn/steer", {
          ...params,
          expectedTurnId: session.turnId,
        });
      else {
        const result = await chat.call("turn/start", params);
        if (session.lastCompletedTurn !== result.turn.id)
          session.turnId = result.turn.id;
      }
      if (session.title === "新会话") session.title = text.slice(0, 32);
    } catch (error) {
      session.items = session.items.filter((i) => i !== item);
      throw error;
    } finally {
      publish(session);
    }
  } finally {
    sending.delete(session.id);
  }
}
function json(response, status, value) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  response.end(JSON.stringify(value));
}
async function body(request) {
  let text = "";
  for await (const chunk of request) {
    text += chunk;
    if (Buffer.byteLength(text) > 65536) throw new Error("请求过长");
  }
  return JSON.parse(text || "{}");
}
function authorized(request) {
  if (!token) return true;
  const actual = Buffer.from(request.headers.authorization || ""),
    expected = Buffer.from("Bearer " + token);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url, "http://localhost");
    if (url.pathname.startsWith("/api/")) {
      if (!authorized(request))
        return json(response, 401, { error: "访问令牌无效" });
      if (
        request.headers.origin &&
        new URL(request.headers.origin).host !== request.headers.host
      )
        return json(response, 403, { error: "来源不匹配" });
      const post = request.method === "POST";
      if (url.pathname === "/api/status")
        return json(response, 200, {
          project: registry.workspaces[0].name,
          version: 3,
        });
      if (url.pathname === "/api/directories" && request.method === "GET")
        return json(
          response,
          200,
          await listDirectories(url.searchParams.get("path"), defaultPath),
        );
      if (url.pathname === "/api/models")
        return json(
          response,
          200,
          await catalogue(
            registry.workspaces.find(
              (w) => w.id === url.searchParams.get("workspaceId"),
            )?.path,
          ),
        );
      if (url.pathname === "/api/workspaces") {
        if (!post)
          return json(response, 200, {
            ...registry,
            workspaces: registry.workspaces.map((w) => ({
              ...w,
              active: [...sessions.values()].filter(
                (s) => s.workspaceId === w.id && s.turnId,
              ).length,
            })),
          });
        const input = await body(request);
        if (typeof input.path !== "string" || !path.isAbsolute(input.path))
          throw new Error("请先选择服务器目录");
        const target = await realpath(input.path);
        if (!(await stat(target)).isDirectory())
          throw new Error("请选择服务器上的目录");
        let workspace = registry.workspaces.find((w) => w.path === target);
        if (!workspace) {
          workspace = {
            id: randomUUID(),
            name: String(input.name || path.basename(target)).slice(0, 80),
            path: target,
            preferences: "",
          };
          registry.workspaces.push(workspace);
        }
        await storage.write("workspaces.json", registry);
        return json(response, 201, workspace);
      }
      const wm = url.pathname.match(
        /^\/api\/workspaces\/([\w-]+)\/preferences$/,
      );
      if (wm && post) {
        const workspace = registry.workspaces.find((w) => w.id === wm[1]);
        if (!workspace) throw new Error("工作区不存在");
        if (
          [...sessions.values()].some(
            (s) =>
              s.workspaceId === workspace.id && (s.turnId || sending.has(s.id)),
          )
        )
          return json(response, 409, {
            error: "请在此工作区的任务结束后修改项目偏好",
          });
        const input = await body(request);
        if (typeof input.text !== "string" || input.text.length > 8000)
          throw new Error("项目偏好过长");
        workspace.preferences = input.text;
        for (const s of sessions.values())
          if (s.workspaceId === workspace.id) releaseRuntime(s);
        await storage.write("workspaces.json", registry);
        return json(response, 200, workspace);
      }
      if (url.pathname === "/api/defaults" && post) {
        registry.defaults = await validateSettings(
          await body(request),
          preferences({ settings: registry.defaults }),
          defaultPath,
        );
        await storage.write("workspaces.json", registry);
        return json(response, 200, registry.defaults);
      }
      if (url.pathname === "/api/sessions") {
        if (!post)
          return json(
            response,
            200,
            [...sessions.values()]
              .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
              .map((s) => ({
                id: s.id,
                title: s.title,
                workspaceId: s.workspaceId,
                active: !!s.turnId,
                updatedAt: s.updatedAt,
              })),
          );
        const input = await body(request),
          workspaceId = input.workspaceId || "default";
        if (!registry.workspaces.some((w) => w.id === workspaceId))
          throw new Error("工作区不存在");
        const session = {
          id: randomUUID(),
          title: "新会话",
          workspaceId,
          items: [],
          settings: preferences({ settings: registry.defaults }),
          threadId: null,
          turnId: null,
          dshSessions: [],
          createdAt: new Date().toISOString(),
        };
        sessions.set(session.id, session);
        publish(session);
        await storage.queue;
        return json(response, 201, session);
      }
      if (url.pathname.startsWith("/api/dsh/")) {
        const owner = sessions.get(request.headers["x-workbench-session"]);
        if (!owner) throw new Error("请设置 WORKBENCH_SESSION_ID 后调用 DSH");
        const worker = workerFor(owner);
        if (!post && url.pathname.startsWith("/api/dsh/jobs/")) {
          const job = worker.jobs.get(url.pathname.split("/").at(-1));
          if (!job || job.ownerId !== owner.id)
            return json(response, 404, {
              error: "任务不存在或服务已重启，请恢复 DSH 会话后继续",
            });
          return json(
            response,
            200,
            url.searchParams.get("details") === "1" ? job : worker.report(job),
          );
        }
        if (!post) return json(response, 405, { error: "不支持此操作" });
        const input = await body(request);
        if (url.pathname === "/api/dsh/new") {
          if (input.sessionId && !owner.dshSessions.includes(input.sessionId))
            throw new Error("DSH 会话不属于当前聊天");
          const result = await worker.create(input.sessionId);
          if (!owner.dshSessions.includes(result.sessionId))
            owner.dshSessions.push(result.sessionId);
          publish(owner);
          return json(response, 201, { sessionId: result.sessionId });
        }
        if (!owner.dshSessions.includes(input.sessionId))
          throw new Error("DSH 会话不属于当前聊天");
        if (url.pathname === "/api/dsh/cancel")
          return json(response, 200, await worker.cancel(input.sessionId));
        if (
          url.pathname === "/api/dsh/prompt" &&
          typeof input.text === "string" &&
          input.text.trim()
        )
          return json(
            response,
            202,
            worker.report(
              await worker.prompt(
                input.sessionId,
                `项目偏好：${workspaceFor(owner).preferences || "无额外要求"}\n\n${input.text}`,
                owner.id,
              ),
            ),
          );
        throw new Error("无效 DSH 请求");
      }
      const match = url.pathname.match(
        /^\/api\/sessions\/([a-f0-9-]+)(?:\/(events|messages|stop|settings))?$/,
      );
      const session = match && sessions.get(match[1]);
      if (!session) return json(response, 404, { error: "找不到会话" });
      if (!post && !match[2])
        return json(response, 200, {
          ...session,
          settings: preferences(session),
        });
      if (!post && match[2] === "events") {
        response.writeHead(200, {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "X-Accel-Buffering": "no",
        });
        if (!streams.has(session.id)) streams.set(session.id, new Set());
        streams.get(session.id).add(response);
        response.write(`data: ${JSON.stringify(session)}\n\n`);
        const heartbeat = setInterval(
          () => response.write(": keepalive\n\n"),
          15000,
        );
        request.on("close", () => {
          clearInterval(heartbeat);
          streams.get(session.id).delete(response);
        });
        return;
      }
      if (post && match[2] === "settings") {
        if (
          session.turnId ||
          sending.has(session.id) ||
          [...workers.values()].some((w) =>
            [...w.jobs.values()].some(
              (j) => j.ownerId === session.id && j.status === "running",
            ),
          )
        )
          return json(response, 409, { error: "请在当前任务结束后修改设置" });
        const previous = preferences(session);
        session.settings = await validateSettings(
          await body(request),
          previous,
          workspaceFor(session).path,
        );
        if (previous.yolo !== session.settings.yolo) session.dshSessions = [];
        // Loaded native threads ignore config overrides on resume. Restart only
        // this chat's process, then resume its persisted thread with new settings.
        releaseRuntime(session);
        publish(session);
        return json(response, 200, session);
      }
      if (post && match[2] === "stop") {
        for (const worker of workers.values())
          for (const job of worker.jobs.values())
            if (job.ownerId === session.id && job.status === "running")
              await worker.cancel(job.sessionId);
        if (session.turnId)
          await runtimeFor(session).call("turn/interrupt", {
            threadId: session.threadId,
            turnId: session.turnId,
          });
        return json(response, 200, { ok: true });
      }
      if (post && match[2] === "messages") {
        const input = await body(request);
        if (
          typeof input.text !== "string" ||
          !input.text.trim() ||
          input.text.length > 50000
        )
          throw new Error("请输入有效消息");
        await submit(session, input.text);
        return json(response, 202, { ok: true });
      }
      return json(response, 405, { error: "不支持此操作" });
    }
    const filename = {
      "/": "public/index.html",
      "/app.js": "public/app.js",
      "/style.css": "public/style.css",
      "/vendor/marked.umd.js": "node_modules/marked/lib/marked.umd.js",
      "/vendor/purify.min.js": "node_modules/dompurify/dist/purify.min.js",
    }[url.pathname];
    if (url.pathname === "/favicon.ico") {
      response.writeHead(204);
      return response.end();
    }
    if (!filename) return json(response, 404, { error: "找不到页面" });
    response.writeHead(200, {
      "Content-Type": filename.endsWith(".js")
        ? "text/javascript"
        : filename.endsWith(".css")
          ? "text/css"
          : "text/html; charset=utf-8",
      "Cache-Control": "no-cache",
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    });
    response.end(await readFile(path.join(root, filename)));
  } catch (error) {
    json(response, 400, { error: error.message });
  }
});
server.listen(Number(process.env.PORT || 3088), host, () =>
  console.log(`Codex 工作台 http://${host}:${server.address().port}`),
);
async function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  runtime.close();
  for (const session of sessions.values()) releaseRuntime(session);
  for (const worker of workers.values()) worker.close();
  for (const clients of streams.values())
    for (const client of clients) client.end();
  await storage.queue;
  server.close(() => process.exit(0));
  server.closeIdleConnections();
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
