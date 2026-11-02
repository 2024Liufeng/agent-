/* Codex mobile workbench — front end core (part 1 of 2).
 * API auth, state, icons, secure Markdown, merged tool timelines, SSE-safe
 * rendering, session/workspace lifecycle, history drawer, overlay manager.
 * Settings, workspace sheet and folder picker logic is appended in part 2. */

const $ = (id) => document.getElementById(id);
const BASE = "";
let token = sessionStorage.getItem("workbench-token") || "";

const shared = {
  registry: null,
  modelInfo: null,
  state: null,
  sessionId: localStorage.getItem("workbench-session") || null,
  workspaceId: localStorage.getItem("workbench-workspace") || "default",
  sessions: [],
  historyQuery: "",
  draft: null,
  settingsTargetId: null,
  currentFolder: null,
  stream: null,
  selection: 0,
  follow: true,
  pendingMessages: new Map(),
  busy: { send: false, save: false, folder: false, preferences: false },
};
const { busy, pendingMessages } = shared;
Object.assign(globalThis, shared);

const EFFORT_LABELS = {
  minimal: "极简",
  low: "轻量",
  medium: "标准",
  high: "深入",
  xhigh: "更深入",
  max: "最高",
  ultra: "Ultra",
};

/* ---------------------------------------------------------------- helpers */

function icon(name, className = "icon") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function setIcon(button, name) {
  button.replaceChildren(icon(name));
}
function formatTokens(value) {
  return Number.isFinite(value) ? Number(value).toLocaleString() : "未知";
}
function elapsed(item) {
  if (!item.startedAt) return null;
  if (item.status === "running") return Math.round((Date.now() - item.startedAt) / 1000);
  return item.endedAt ? Math.round((item.endedAt - item.startedAt) / 1000) : null;
}
let toastTimer = 0;
function toast(message, kind = "info") {
  const node = $("toast");
  if (!node) return;
  node.textContent = message;
  node.dataset.kind = kind;
  node.hidden = false;
  requestAnimationFrame(() => node.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    node.classList.remove("show");
    setTimeout(() => (node.hidden = true), 200);
  }, kind === "error" ? 4200 : 2400);
}
function showActivity(message) {
  const node = $("activity");
  if (!node) return;
  if (message !== undefined) node.textContent = message;
  node.hidden = !node.textContent;
}
function workspace() {
  return shared.registry?.workspaces.find((w) => w.id === shared.workspaceId);
}
function workspaceById(id) {
  return shared.registry?.workspaces.find((w) => w.id === id);
}
function chosenSettings() {
  return {
    model: null,
    effort: null,
    fast: null,
    dshEnabled: true,
    yolo: true,
    contextLimit: null,
    compactLimit: null,
    ...shared.registry?.defaults,
    ...shared.state?.settings,
  };
}
function currentModel() {
  const settings = chosenSettings();
  const info = shared.modelInfo;
  const id = settings.model || shared.state?.effective?.model || info?.defaults?.model;
  const list = info?.models || [];
  return list.find((m) => m.model === id) || list.find((m) => m.isDefault) || null;
}
function modelLabel() {
  if (!shared.modelInfo) return "模型";
  const model = currentModel();
  return model?.displayName || chosenSettings().model || shared.state?.effective?.model || "默认模型";
}
function localDate(iso) {
  const date = iso ? new Date(iso) : new Date();
  return Number.isNaN(date.getTime()) ? null : date;
}
function dayKey(date) {
  return date ? `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}` : "";
}
function historyGroup(iso) {
  const date = localDate(iso);
  if (!date) return "更早";
  const now = new Date();
  if (dayKey(date) === dayKey(now)) return "今天";
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (dayKey(date) === dayKey(yesterday)) return "昨天";
  return "更早";
}
function timeLabel(iso) {
  const date = localDate(iso);
  return date ? date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "";
}

/* -------------------------------------------------------------------- api */

class AuthError extends Error {}
async function api(url, body) {
  let response;
  try {
    response = await fetch(BASE + url, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("网络连接失败，请检查服务器");
  }
  let result = null;
  try {
    result = await response.json();
  } catch {}
  if (response.status === 401) {
    openLogin("访问令牌无效，请重新连接");
    throw new AuthError("请先连接工作台");
  }
  if (!response.ok) throw new Error(result?.error || `请求失败（${response.status}）`);
  return result;
}
function reportError(error) {
  if (error instanceof AuthError) return error.message;
  const message = error?.message || "操作失败";
  toast(message, "error");
  showActivity("");
  return message;
}

/* ---------------------------------------------------------------- overlays */

const overlay = { stack: [], lastFocus: null };
const SHEET_IDS = ["workspace-sheet", "folder-sheet", "model-sheet", "advanced-sheet", "settings-sheet"];
const DRAWER_ID = "history";
const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

function topOverlay() {
  return overlay.stack[overlay.stack.length - 1] || null;
}
function isOpen(id) {
  return overlay.stack.some((entry) => entry.id === id);
}
function anySheetOpen() {
  return SHEET_IDS.some(isOpen);
}
function focusables(container) {
  return [...container.querySelectorAll(FOCUSABLE)].filter(
    (node) => node.getClientRects().length && !node.closest("[hidden]"),
  );
}
function syncBackdrops() {
  for (const [id, visible] of [
    ["drawer-backdrop", isOpen(DRAWER_ID)],
    ["sheet-backdrop", anySheetOpen()],
  ]) {
    const node = $(id);
    if (!node) continue;
    if (visible) {
      node.hidden = false;
      requestAnimationFrame(() => node.classList.add("open"));
    } else {
      node.classList.remove("open");
      setTimeout(() => {
        if (!isOpen(DRAWER_ID) && !anySheetOpen()) node.hidden = true;
      }, 220);
    }
  }
  $("menu")?.setAttribute("aria-expanded", String(isOpen(DRAWER_ID)));
}
/**
 * Open one overlay layer. options: { initialFocus, returnTo, onClose }.
 * Opening a sheet closes the drawer first so only one layer holds focus.
 */
function openOverlay(id, options = {}) {
  const node = $(id);
  if (!node) return false;
  const existing = overlay.stack.findIndex((entry) => entry.id === id);
  if (existing >= 0) overlay.stack.splice(existing, 1);
  else if (id !== DRAWER_ID && isOpen(DRAWER_ID)) closeOverlay(DRAWER_ID, { keepFocus: true });
  if (!overlay.lastFocus) overlay.lastFocus = document.activeElement;
  if (!node.hasAttribute("tabindex")) node.setAttribute("tabindex", "-1");
  overlay.stack.push({ id, node, options });
  node.hidden = false;
  if (node.tagName === "ASIDE") node.setAttribute("aria-hidden", "false");
  requestAnimationFrame(() => node.classList.add("open"));
  document.body.style.overflow = "hidden";
  syncBackdrops();
  const target = options.initialFocus ? node.querySelector(options.initialFocus) : null;
  (target || focusables(node)[0] || node).focus({ preventScroll: true });
  return true;
}
function closeOverlay(id, { keepFocus = false } = {}) {
  const index = overlay.stack.findIndex((entry) => entry.id === id);
  if (index < 0) return true;
  const entry = overlay.stack[index];
  if (entry.options.onClose?.(entry.node) === false) return false;
  overlay.stack.splice(index, 1);
  entry.node.classList.remove("open");
  if (entry.node.tagName === "ASIDE") entry.node.setAttribute("aria-hidden", "true");
  const delay = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 260;
  setTimeout(() => {
    if (!isOpen(entry.id)) {
      entry.node.hidden = true;
      entry.node.removeAttribute("tabindex");
    }
  }, delay);
  const stillOpen = overlay.stack.length > 0;
  document.body.style.overflow = stillOpen ? "hidden" : "";
  syncBackdrops();
  if (keepFocus) return true;
  if (stillOpen) {
    const top = topOverlay();
    (focusables(top.node)[0] || top.node).focus({ preventScroll: true });
  } else {
    const back = entry.options.returnTo || overlay.lastFocus;
    overlay.lastFocus = null;
    if (back?.isConnected && !back.closest("[hidden]")) back.focus({ preventScroll: true });
  }
  return true;
}
function closeTop() {
  const top = topOverlay();
  return top ? closeOverlay(top.id) : false;
}
function openDrawer() {
  if (anySheetOpen()) closeOverlay(SHEET_IDS.find(isOpen));
  openOverlay(DRAWER_ID, { returnTo: $("menu") });
  $("history-search")?.focus({ preventScroll: true });
  return true;
}
function closeDrawer() {
  return closeOverlay(DRAWER_ID);
}

function onKeydown(event) {
  if (event.key === "Escape" && isOpen(DRAWER_ID) && !anySheetOpen()) {
    if (closeDrawer()) {
      event.preventDefault();
      event.stopPropagation();
    }
    return;
  }
  if (event.key !== "Tab") return;
  const top = topOverlay();
  if (!top) return;
  const items = focusables(top.node);
  if (!items.length) {
    event.preventDefault();
    return;
  }
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  } else if (!top.node.contains(document.activeElement)) {
    event.preventDefault();
    first.focus();
  }
}

/* --------------------------------------------------------------- markdown */

let purify = null;
function sanitizer() {
  if (purify) return purify;
  const factory = globalThis.DOMPurify;
  if (typeof factory?.sanitize === "function") purify = factory;
  else if (typeof factory === "function") purify = factory(globalThis);
  if (!purify || typeof purify.sanitize !== "function") throw new Error("Markdown 安全过滤不可用");
  purify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      node.setAttribute("rel", "noopener noreferrer");
      node.setAttribute("target", "_blank");
    }
  });
  return purify;
}
function renderMarkdown(text) {
  const box = el("div", "md");
  let html;
  try {
    const marked = globalThis.marked;
    if (!marked || typeof marked.parse !== "function") throw new Error("Markdown 解析器不可用");
    const parsed = marked.parse(text || "", { gfm: true, breaks: true });
    html = sanitizer().sanitize(parsed, { USE_PROFILES: { html: true } });
  } catch (error) {
    box.textContent = text || "";
    return box;
  }
  box.innerHTML = html;
  for (const link of box.querySelectorAll("a")) {
    if (!/^https?:/i.test(link.getAttribute("href") || "")) link.removeAttribute("href");
    link.setAttribute("rel", "noopener noreferrer");
    link.setAttribute("target", "_blank");
  }
  for (const table of box.querySelectorAll("table")) {
    if (table.closest(".table-wrap")) continue;
    const wrap = el("div", "table-wrap");
    table.replaceWith(wrap);
    wrap.append(table);
  }
  return box;
}

/* ------------------------------------------------------------ item labels */

const SOURCE_LABELS = { codex: "Codex", dsh: "DSH" };
const STATUS_LABELS = {
  running: "执行中",
  pending: "等待中",
  in_progress: "执行中",
  completed: "已完成",
  failed: "失败",
  stopped: "已停止",
  interrupted: "已中断",
  canceled: "已取消",
  cancelled: "已取消",
};
function statusLabel(status) {
  return STATUS_LABELS[status] || status || "已记录";
}
function isRunning(status) {
  return ["running", "pending", "in_progress"].includes(status);
}
function toolName(item) {
  if (item.source === "dsh") return "DSH 协作";
  const title = (item.title || "").trim();
  if (!title) return "工具调用";
  if (/Get-Content|cat |read_file/i.test(title)) return "读取文件";
  if (/\brg |grep|Select-String/i.test(title)) return "搜索内容";
  if (/git diff/i.test(title)) return "检查代码差异";
  if (/git (status|log)/i.test(title)) return "查看 Git 状态";
  if (/apply_patch|write|edit/i.test(title)) return "修改文件";
  return title.length > 80 ? "执行命令" : title;
}
function stepName(title) {
  return (
    {
      read: "读取文件",
      grep: "搜索内容",
      pwsh: "执行 PowerShell",
      bash: "执行命令",
      write: "写入文件",
      edit: "修改文件",
      todo_write: "更新任务清单",
      glob: "查找文件",
      web_search: "搜索网页",
      web_fetch: "读取网页",
    }[title] || title || "步骤"
  );
}
function itemSignature(items) {
  return items
    .map((item) => [item.kind, item.source, item.status, item.startedAt, item.endedAt, (item.steps || []).length, (item.text || "").length].join(":"))
    .join("|");
}

/* -------------------------------------------------------------- rendering */

function captureUiState() {
  const conversation = $("conversation");
  const active = document.activeElement;
  const open = new Set();
  for (const details of document.querySelectorAll("#messages details[data-id][open]")) open.add(details.dataset.id);
  for (const details of document.querySelectorAll("#messages details.raw[open]")) open.add(details.dataset.id);
  return {
    open,
    scrollTop: conversation.scrollTop,
    focusId: active && $("messages").contains(active) && active.id ? active.id : null,
  };
}
function restoreUiState(snapshot) {
  const conversation = $("conversation");
  conversation.scrollTop = snapshot.scrollTop;
  if (snapshot.focusId) $(snapshot.focusId)?.focus({ preventScroll: true });
}
function groupItems(items) {
  const groups = [];
  for (const item of items) {
    const previous = groups[groups.length - 1];
    if (item.kind === "tool" && previous?.tools) previous.tools.push(item);
    else if (item.kind === "tool") groups.push({ tools: [item] });
    else groups.push({ item });
  }
  return groups;
}
function renderMessage(item) {
  if (item.kind === "error") return el("div", "message error", item.text || "执行出错");
  if (item.kind === "user") {
    const node = el("div", "message user");
    node.append(el("div", "message-body", item.text || ""));
    return node;
  }
  const node = el("div", "message assistant");
  const avatar = el("div", "assistant-avatar");
  avatar.append(icon("sparkle"));
  const body = el("div", "message-body");
  body.append(item.text ? renderMarkdown(item.text) : el("span", "typing", "正在思考…"));
  node.append(avatar, body);
  return node;
}
function renderToolItem(item, index, openSet) {
  const id = item.id || `anon-${index}-${item.startedAt || ""}`;
  const row = el("div", "tool-item");
  row.dataset.id = id;
  const head = el("div", "tool-item-head");
  const seconds = elapsed(item);
  head.append(
    el("span", "tool-source", SOURCE_LABELS[item.source] || "工具"),
    el("span", "tool-name", toolName(item)),
    el("span", "tool-status", statusLabel(item.status)),
    el("span", "tool-time", seconds === null ? "" : `${seconds} 秒`),
  );
  row.append(head);
  const steps = Array.isArray(item.steps) ? item.steps : [];
  if (steps.length) {
    const list = el("ol", "step-list");
    for (const step of steps) {
      const line = el("li", "step");
      const lineHead = el("div", "step-head");
      lineHead.append(el("span", "step-name", stepName(step.title)), el("span", "step-status", statusLabel(step.status)));
      line.append(lineHead);
      if (step.detail) line.append(el("p", "step-detail", String(step.detail).slice(0, 400)));
      list.append(line);
    }
    row.append(list);
  }
  if (item.source === "dsh" && !steps.length && item.text) row.append(el("p", "tool-summary-text", item.text.slice(0, 1200)));
  if (item.title && item.source !== "dsh") row.append(el("code", "tool-detail", item.title));
  if (item.text) {
    const raw = el("details", "raw");
    raw.dataset.id = id + ":raw";
    raw.open = openSet.has(raw.dataset.id);
    raw.append(el("summary", "", "原始输出"), el("pre", "", item.text));
    row.append(raw);
  }
  return row;
}
function renderToolGroup(tools, openSet) {
  const details = el("details", "tool-group");
  details.dataset.id = "tools:" + tools.map((t) => t.id || t.startedAt || "").join(",");
  details.open = openSet.has(details.dataset.id);
  const summary = el("summary", "tool-summary");
  const badge = el("span", "tool-icon");
  badge.append(icon("sparkle", "icon icon-sm"));
  summary.append(badge, el("span", "tool-label", "执行过程"), el("span", "tool-count", `${tools.length} 项`));
  const running = tools.some((t) => isRunning(t.status));
  const failed = tools.some((t) => ["failed", "interrupted", "stopped", "canceled", "cancelled"].includes(t.status));
  const stateText = running ? "执行中" : failed ? "有失败项" : tools.every((t) => t.status === "completed") ? "已完成" : "已结束";
  summary.append(el("span", "tool-state " + (running ? "running" : failed ? "failed" : "completed"), stateText));
  const chevron = el("span", "tool-chevron");
  chevron.append(icon("chevron-right"));
  summary.append(chevron);
  details.append(summary);
  const body = el("div", "tool-body");
  tools.forEach((item, index) => body.append(renderToolItem(item, index, openSet)));
  details.append(body);
  return details;
}
function renderMessages() {
  const state = shared.state;
  const container = $("messages");
  const welcome = $("welcome");
  if (!state) {
    container.replaceChildren();
    if (welcome) {
      welcome.hidden = false;
      const name = $("welcome-workspace");
      if (name) name.textContent = "当前工作区 · " + (workspace()?.name || "未选择");
    }
    return;
  }
  const items = Array.isArray(state.items) ? state.items : [];
  const snapshot = captureUiState();
  if (welcome) welcome.hidden = items.length > 0;
  if (!items.length) {
    container.replaceChildren();
    restoreUiState(snapshot);
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const group of groupItems(items)) {
    if (group.tools) fragment.append(renderToolGroup(group.tools, snapshot.open));
    else fragment.append(renderMessage(group.item));
  }
  if (state.turnId && !isRunning(items[items.length - 1]?.status) && items[items.length - 1]?.kind !== "tool") {
    const typing = el("div", "message assistant");
    const avatar = el("div", "assistant-avatar");
    avatar.append(icon("sparkle"));
    typing.append(avatar, el("div", "message-body typing", "Codex 正在工作…"));
    fragment.append(typing);
  }
  container.replaceChildren(fragment);
  restoreUiState(snapshot);
  if (shared.follow) $("conversation").scrollTop = $("conversation").scrollHeight;
}
function syncComposer() {
  const running = !!shared.state?.turnId;
  const typing = !!$("prompt")?.value.trim();
  $("stop").hidden = !running;
  $("composer")?.classList.toggle("is-send", !running || typing);
  $("composer")?.classList.toggle("is-stop", running && !typing);
  showActivity(running ? "Codex 正在工作，可继续补充要求" : "");
}
function renderHeader() {
  const name = $("workspace-name");
  if (name) name.textContent = workspace()?.name || "工作区";
  $("model-chip-name").textContent = modelLabel();
  $("model-button")?.setAttribute("aria-label", `当前模型 ${modelLabel()}，打开模型设置`);
  syncComposer();
}
function buildHistory() {
  const query = shared.historyQuery.trim().toLowerCase();
  const container = $("sessions");
  if (!container) return;
  const list = shared.sessions
    .filter((s) => s.workspaceId === shared.workspaceId)
    .filter((s) => !query || (s.title || "").toLowerCase().includes(query))
    .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
  container.replaceChildren();
  if (!list.length) {
    container.append(el("p", "list-empty", query ? "没有匹配的对话" : "当前工作区还没有对话"));
    return;
  }
  let groupNode = null;
  let currentGroup = null;
  for (const session of list) {
    const group = historyGroup(session.updatedAt);
    if (group !== currentGroup) {
      currentGroup = group;
      groupNode = el("section", "history-group");
      groupNode.append(el("p", "history-group-title", group));
      container.append(groupNode);
    }
    const button = el("button", "history-item");
    button.type = "button";
    button.dataset.id = session.id;
    button.append(el("span", "history-title", session.title || "新会话"));
    if (session.active) button.append(el("span", "running-dot"));
    button.append(el("span", "history-time", group === "更早" ? "" : timeLabel(session.updatedAt)));
    button.classList.toggle("selected", session.id === shared.sessionId);
    if (session.id === shared.sessionId) button.setAttribute("aria-current", "true");
    button.onclick = () => selectSession(session.id).catch(reportError);
    groupNode.append(button);
  }
}
function render() {
  renderHeader();
  renderMessages();
}

/* ------------------------------------------------------------ session flow */

function stopStream() {
  shared.stream?.abort();
  shared.stream = null;
}
function setConnection(kind) {
  const text = $("connection-text");
  const dot = $("connection-dot");
  if (text)
    text.textContent =
      kind === "connected" ? (workspace()?.name || "工作区") + " · 已连接" : kind === "reconnecting" ? "断线重连中…" : "未连接";
  if (dot) dot.className = "status-dot" + (kind === "connected" ? " connected" : kind === "reconnecting" ? " reconnecting" : " offline");
}
async function connectEvents(id, signal) {
  while (!signal.aborted) {
    try {
      const response = await fetch(`/api/sessions/${id}/events`, {
        headers: { Authorization: "Bearer " + token },
        signal,
      });
      if (response.status === 401) {
        openLogin("访问令牌无效，请重新连接");
        return;
      }
      if (!response.ok) throw new Error("事件流连接失败");
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      while (!signal.aborted) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += value;
        let end;
        while ((end = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, end);
          buffer = buffer.slice(end + 2);
          if (signal.aborted) break;
          if (!frame.startsWith("data:")) continue;
          try {
            const next = JSON.parse(frame.slice(5).trim());
            if (shared.sessionId === id) applyState(next);
          } catch {}
        }
      }
      if (!signal.aborted) setConnection("reconnecting");
    } catch {
      if (signal.aborted) return;
      setConnection("reconnecting");
    }
    if (signal.aborted) return;
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}
function updateSessionCache(next) {
  if (!next.id) return;
  const cached = shared.sessions.find((s) => s.id === next.id);
  const summary = { id: next.id, title: next.title, workspaceId: next.workspaceId, active: !!next.turnId, updatedAt: next.updatedAt };
  if (cached) Object.assign(cached, summary);
  else shared.sessions.push(summary);
}
function applyState(next) {
  if (!next || next.id !== shared.sessionId) return;
  shared.state = next;
  updateSessionCache(next);
  render();
  setConnection("connected");
  // Refresh history only while the drawer is visible to avoid needless churn.
  if (isOpen(DRAWER_ID)) buildHistory();
}
async function selectSession(id) {
  const generation = ++shared.selection;
  stopStream();
  const next = await api("/api/sessions/" + id);
  if (generation !== shared.selection) throw new AuthError("对话已切换，已忽略旧结果");
  shared.sessionId = id;
  shared.workspaceId = next.workspaceId;
  shared.follow = true;
  shared.state = next;
  updateSessionCache(next);
  // Commit settings or preferences that waited for a session/workspace.
  const revise = shared.pendingRevision;
  if (revise && revise.id === id) {
    shared.pendingRevision = null;
    return revise();
  }
  localStorage.setItem("workbench-session", id);
  localStorage.setItem("workbench-workspace", next.workspaceId);
  const prompt = $("prompt");
  prompt.value = "";
  prompt.style.height = "auto";
  closeDrawer();
  render();
  setConnection("connected");
  const controller = new AbortController();
  shared.stream = controller;
  connectEvents(id, controller.signal);
  return next;
}
async function newSession() {
  const created = await api("/api/sessions", { workspaceId: shared.workspaceId });
  updateSessionCache(created);
  for (const id of [SHEET_IDS.find(isOpen)]) if (id) closeOverlay(id);
  return selectSession(created.id);
}
async function switchWorkspace(id) {
  if (!workspaceById(id)) throw new Error("工作区不存在");
  const generation = ++shared.selection;
  stopStream();
  shared.workspaceId = id;
  shared.sessionId = null;
  shared.state = null;
  shared.modelInfo = null;
  localStorage.setItem("workbench-workspace", id);
  localStorage.removeItem("workbench-session");
  await refreshHistory();
  if (generation !== shared.selection) return;
  render();
  const latest = shared.sessions
    .filter((s) => s.workspaceId === id)
    .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")))[0];
  if (latest) await selectSession(latest.id);
}
async function refreshHistory() {
  const [registry, list] = await Promise.all([api("/api/workspaces"), api("/api/sessions")]);
  shared.registry = registry;
  shared.sessions = Array.isArray(list) ? list : [];
  if (!workspace()) shared.workspaceId = registry.workspaces[0]?.id || "default";
  buildHistory();
  renderHeader();
  return registry;
}

/* --------------------------------------------------------------- composer */

function autosizePrompt() {
  const prompt = $("prompt");
  prompt.style.height = "auto";
  prompt.style.height = Math.min(prompt.scrollHeight, 140) + "px";
}
function renderPending() {
  if (shared.state) return;
  for (const node of document.querySelectorAll("[data-pending]")) node.remove();
  const list = shared.sessionId ? pendingMessages.get(shared.sessionId) || [] : [];
  const container = $("messages");
  for (const message of list) {
    const node = renderMessage({ kind: "user", text: message });
    node.dataset.pending = "1";
    $("welcome").hidden = true;
    container.append(node);
  }
}
async function submitMessage(text) {
  if (busy.send) return false;
  busy.send = true;
  $("send").disabled = true;
  try {
    if (!shared.sessionId || shared.state?.workspaceId !== shared.workspaceId) await newSession();
    const target = shared.sessionId;
    await api(`/api/sessions/${target}/messages`, { text });
    if (!shared.state) {
      const list = pendingMessages.get(target) || [];
      list.push(text);
      pendingMessages.set(target, list);
      renderPending();
    }
    return true;
  } catch (error) {
    reportError(error);
    return false;
  } finally {
    busy.send = false;
    $("send").disabled = false;
  }
}
async function stopTurn() {
  if (!shared.sessionId) return;
  try {
    await api(`/api/sessions/${shared.sessionId}/stop`, {});
    toast("已请求停止，等待服务端确认");
  } catch (error) {
    reportError(error);
  }
}

/* ------------------------------------------------------------------ login */

function openLogin(message) {
  const dialog = $("login");
  const error = $("login-error");
  if (error) error.textContent = message || "";
  if (dialog && !dialog.open) dialog.showModal();
  $("token")?.focus();
}
function closeLogin() {
  const dialog = $("login");
  if (dialog?.open) dialog.close();
}
async function connectWithToken(value) {
  token = value || "";
  sessionStorage.setItem("workbench-token", token);
  await boot();
  closeLogin();
  setConnection("connected");
}

/* ------------------------------------------------ settings, sheets, boot */

const EMPTY_SETTINGS = { dshEnabled: true, yolo: true, contextLimit: null, compactLimit: null };
let settingsDraft = null; // model/advanced draft; never mixed with composer text
let settingsForSessionId = null;
let folderSeq = 0;
let folderCache = null;

function setSwitch(id, on) {
  $(id)?.setAttribute("aria-checked", String(!!on));
}
function switchValue(id) {
  return $(id)?.getAttribute("aria-checked") === "true";
}
function toggleSwitch(id, rerender = () => {}) {
  setSwitch(id, !switchValue(id));
  rerender();
}
function bindSwitch(id, onChange) {
  const node = $(id);
  if (!node) return;
  node.onclick = () => {
    const next = !switchValue(id);
    setSwitch(id, next);
    onChange?.(next);
  };
}
function baselineSettings() {
  const effective = shared.state?.effective;
  if (shared.registry?.defaults?.model || (shared.sessionId && !shared.state?.settings))
    return { ...EMPTY_SETTINGS, ...shared.registry?.defaults };
  return {
    ...EMPTY_SETTINGS,
    ...(effective ? { model: effective.model, effort: effective.effort, fast: effective.serviceTier === "priority" } : {}),
    ...shared.state?.settings,
  };
}
function draftModel() {
  const info = shared.modelInfo;
  const list = info?.models || [];
  const id = settingsDraft?.model || info?.defaults?.model;
  return list.find((m) => m.model === id) || list.find((m) => m.isDefault) || null;
}
function supportedEfforts(model) {
  return (model?.supportedReasoningEfforts || []).map((e) => e.reasoningEffort);
}
function fastTier(model) {
  return model?.serviceTiers?.find((t) => ["priority", "fast"].includes(t.id)) || null;
}
function setSaveState(button, pending, label) {
  if (!button) return;
  button.disabled = pending;
  if (label) button.textContent = label;
}
function setModelHint(text) {
  const chip = $("model-chip-name");
  if (chip) chip.textContent = text;
}

/* -------- model / advanced sheets (shared settingsDraft) -------- */

function renderModelSheet() {
  const info = shared.modelInfo;
  const list = $("model-list");
  const model = draftModel();
  const efforts = $("effort-options");
  list.replaceChildren();
  efforts.replaceChildren();
  if (!info) return;
  const models = info.models || [];
  if (!models.length) list.append(el("p", "list-empty", "服务端没有可用模型"));
  for (const m of models) {
    const option = el("button", "model-option");
    option.type = "button";
    option.setAttribute("role", "radio");
    option.dataset.model = m.model;
    const selected = model?.model === m.model;
    option.classList.toggle("selected", selected);
    option.setAttribute("aria-checked", String(selected));
    option.setAttribute("aria-label", m.displayName || m.model);
    const radio = el("span", "model-radio");
    if (selected) radio.append(icon("check", "icon"));
    const copy = el("span", "model-copy");
    copy.append(el("span", "model-name", m.displayName || m.model));
    if (m.description) copy.append(el("span", "model-desc", m.description));
    option.append(radio, copy);
    option.onclick = () => {
      settingsDraft.model = m.model;
      settingsDraft.effort = null;
      settingsDraft.fast = null;
      renderModelSheet();
      renderAdvancedSheet();
    };
    list.append(option);
  }
  const defaultEffort = model?.defaultReasoningEffort || null;
  const defaultLabel = "模型默认" + (defaultEffort ? ` · ${EFFORT_LABELS[defaultEffort] || defaultEffort}` : "");
  const choices = [{ value: null, label: defaultLabel, title: `跟随模型默认（${EFFORT_LABELS[defaultEffort] || defaultEffort || "未提供"}）` }];
  for (const effort of supportedEfforts(model))
    choices.push({ value: effort, label: EFFORT_LABELS[effort] || effort, title: EFFORT_LABELS[effort] || effort });
  // Only overwrite an invalid stored effort once this session's draft was loaded;
  // a blank draft (null) keeps "model default" selected.
  if (settingsDraft.effort && !supportedEfforts(model).includes(settingsDraft.effort) && settingsForSessionId === (shared.sessionId || null))
    settingsDraft.effort = null;
  for (const choice of choices) {
    const button = el("button", "effort-option", choice.label);
    button.type = "button";
    button.title = choice.title;
    button.dataset.effort = choice.value ?? "";
    button.setAttribute("aria-pressed", String((settingsDraft.effort || null) === choice.value));
    button.classList.toggle("selected", (settingsDraft.effort || null) === choice.value);
    button.onclick = () => {
      settingsDraft.effort = choice.value;
      renderModelSheet();
    };
    efforts.append(button);
  }
  const tier = fastTier(model);
  const note = $("fast-note");
  if (!note) return;
  note.textContent = tier ? tier.description || tier.name || "Fast 加速（服务端未提供描述）" : "当前模型未提供 Fast";
  setSwitch("fast-toggle", !!tier && settingsDraft.fast === true);
  $("fast-toggle").disabled = !tier;
  const effortNote = $("effort-note");
  if (effortNote)
    effortNote.textContent = settingsDraft.effort
      ? (model?.supportedReasoningEfforts || []).find((e) => e.reasoningEffort === settingsDraft.effort)?.description || ""
      : `未选择时使用 ${EFFORT_LABELS[defaultEffort] || defaultEffort || "模型默认"}`;
  const running = !!shared.state?.turnId;
  setSaveState($("save-model"), busy.save || !shared.modelInfo, "完成");
  $("save-model").disabled = running || busy.save || !shared.modelInfo;
  $("save-model").title = running ? "任务结束后才能保存" : "";
  $("model-error").textContent = running ? "任务运行中，结束后才能保存设置。" : "";
}

function formatUsage() {
  const usage = shared.state?.usage;
  const parts = [];
  if (usage) {
    parts.push(`最近上下文 ${formatTokens(usage.last?.totalTokens)} / ${formatTokens(usage.modelContextWindow)} tokens`);
    parts.push(`累计输入 ${formatTokens(usage.total?.inputTokens)}，输出 ${formatTokens(usage.total?.outputTokens)}`);
  } else parts.push("本会话尚无用量记录");
  const effective = shared.state?.effective;
  if (effective) {
    const at = effective.updatedAt ? new Date(effective.updatedAt) : null;
    parts.push(
      `上次运行确认：${effective.model} · ${effective.effort || "默认思考"} · ${effective.serviceTier || "默认速度"}${effective.contextLimit ? " · 上下文 " + formatTokens(effective.contextLimit) : ""}${at ? " · " + at.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : ""}`,
    );
  }
  return parts.join("；");
}

function renderAdvancedSheet() {
  const model = draftModel();
  if (shared.modelInfo) {
    setSwitch("dsh-enabled", settingsDraft.dshEnabled);
    setSwitch("yolo", settingsDraft.yolo);
  }
  try {
    if (shared.state?.usage) $("usage-text").textContent = formatUsage();
  } catch {} // model info may still be loading; usage text updates next render
  $("context-limit").placeholder = model?.contextWindow ? "自动（目录上限 " + formatTokens(model.contextWindow) + "）" : "自动";
  const running = !!shared.state?.turnId;
  $("save-advanced").disabled = running || busy.save;
  $("save-advanced").title = running ? "任务结束后才能保存" : "";
  $("advanced-error").textContent = running ? "任务运行中，结束后才能保存设置。" : "";
}

function fillDraft(target) {
  settingsDraft = { ...baselineSettings(), ...(target || {}) };
  settingsForSessionId = shared.sessionId || null;
}

/* Re-read the draft fields from the DOM so the model -> advanced -> model
 * round trip never loses unsaved toggles or limit values. */
function captureDraft() {
  if (!settingsDraft) return;
  settingsDraft.dshEnabled = switchValue("dsh-enabled");
  settingsDraft.yolo = switchValue("yolo");
  const context = $("context-limit")?.value.trim();
  const compact = $("compact-limit")?.value.trim();
  if (context !== undefined) settingsDraft.contextLimit = context ? Number(context) : null;
  if (compact !== undefined) settingsDraft.compactLimit = compact ? Number(compact) : null;
}

async function loadModelInfo() {
  if (shared.modelInfo) return shared.modelInfo;
  const info = await api("/api/models?workspaceId=" + encodeURIComponent(shared.workspaceId));
  shared.modelInfo = info;
  renderHeader();
  return info;
}

async function openModelSheet() {
  const opener = document.activeElement;
  openOverlay("model-sheet", {
    initialFocus: ".sheet-head button",
    returnTo: opener,
    onClose: () => {
      if (!busy.save) {
        settingsDraft = null;
        shared.settingsTargetId = null;
      }
    },
  });
  const list = $("model-list");
  if (!settingsDraft || settingsForSessionId !== (shared.sessionId || null)) {
    fillDraft(null);
    list.replaceChildren(el("p", "loading-state", "正在读取模型目录…"));
    $("effort-options").replaceChildren();
    $("save-model").disabled = true;
    try {
      await loadModelInfo();
    } catch (error) {
      list.replaceChildren(el("p", "error-text", error.message));
      $("save-model").disabled = true;
      return;
    }
    settingsDraft.model ||= shared.modelInfo.defaults?.model;
  }
  openOverlay("model-sheet", { initialFocus: ".sheet-head button", returnTo: opener });
  renderModelSheet();
}

async function openAdvancedSheet() {
  captureDraft();
  if (!shared.modelInfo) {
    await loadModelInfo().catch(reportError);
    if (!shared.modelInfo) return;
    renderModelSheet();
  }
  $("context-limit").value = settingsDraft.contextLimit ?? "";
  $("compact-limit").value = settingsDraft.compactLimit ?? "";
  if (!$("save-default").dataset.touched) setSwitch("save-default", false);
  openOverlay("advanced-sheet", { returnTo: $("advanced-open") });
  renderAdvancedSheet();
}

function readLimit(id, label) {
  const raw = $(id).value.trim();
  if (!raw) return null;
  if (!/^\d+$/.test(raw) || Number(raw) < 1024) throw new Error(`${label}需为至少 1024 的整数`);
  return Number(raw);
}

async function saveSettings() {
  if (busy.save) return;
  const error = $("advanced-error") || $("model-error");
  error.textContent = "";
  captureDraft();
  const draft = { ...settingsDraft };
  let contextLimit, compactLimit;
  try {
    contextLimit = readLimit("context-limit", "上下文限制");
    compactLimit = readLimit("compact-limit", "自动压缩阈值");
  } catch (e) {
    error.textContent = e.message;
    if (!isOpen("advanced-sheet")) openOverlay("advanced-sheet", { initialFocus: "#context-limit" });
    return;
  }
  const payload = {
    model: draft.model || null,
    effort: draft.effort || null,
    fast: fastTier(draftModel()) ? draft.fast === true : false,
    dshEnabled: draft.dshEnabled !== false,
    yolo: draft.yolo !== false,
    contextLimit,
    compactLimit,
  };
  const asDefault = switchValue("save-default");
  busy.save = true;
  const primary = $("save-model");
  setSaveState(primary, true, "正在保存…");
  primary.textContent = "正在保存…";
  setSaveState($("save-advanced"), true);
  try {
    let id = shared.sessionId;
    if (!id || shared.state?.workspaceId !== shared.workspaceId) {
      id = await createSessionFor(shared.workspaceId);
      // The new chat starts with registry defaults; apply the draft to it now
      // instead of dropping the user's unsaved settings.
      shared.settingsTargetId = null;
      const applied = await api(`/api/sessions/${id}/settings`, payload);
      if (asDefault) await api("/api/defaults", payload);
      await refreshHistory();
      if (shared.sessionId === id) {
        if (!shared.state) shared.state = applied;
        else await selectSession(id);
      }
      settingsDraft = null;
      closeOverlay("advanced-sheet", { keepFocus: true });
      closeOverlay("model-sheet", { keepFocus: true });
      toast("已为新对话保存设置");
      return;
    }
    await api(`/api/sessions/${id}/settings`, payload);
    if (asDefault && shared.workspaceId === (shared.state?.workspaceId || shared.workspaceId))
      await api("/api/defaults", payload);
    shared.settingsTargetId = null;
    shared.pendingRevision = null;
    settingsDraft = null;
    const next = await api("/api/sessions/" + id);
    if (shared.sessionId === id) {
      shared.state = next;
      updateSessionCache(next);
      render();
      setConnection("connected");
    }
    closeOverlay("advanced-sheet", { keepFocus: true });
    closeOverlay("model-sheet", { keepFocus: true });
    toast(next.settings?.model === payload.model || !payload.model ? "设置已保存，从下一轮生效" : "设置已保存");
  } catch (e) {
    reportError(e);
    error.textContent = "保存失败：" + (e.message || "未知错误");
  } finally {
    busy.save = false;
    primary.textContent = "完成";
    primary.disabled = !!shared.state?.turnId;
    $("save-advanced").disabled = !!shared.state?.turnId;
  }
}

/* -------- workspace sheet + folder picker -------- */

function renderWorkspaceSheet() {
  const list = $("workspace-list");
  list.replaceChildren();
  const workspaces = shared.registry?.workspaces || [];
  if (!workspaces.length) list.append(el("p", "list-empty", "还没有工作区"));
  for (const w of workspaces) {
    const row = el("div", "workspace-row");
    row.dataset.workspace = w.id;
    row.classList.toggle("selected", w.id === shared.workspaceId);
    const main = el("button", "workspace-main");
    main.type = "button";
    main.setAttribute("aria-label", `切换到工作区 ${w.name}${w.active ? "，有任务运行中" : ""}`);
    const check = el("span", "workspace-check");
    if (w.id === shared.workspaceId) {
      check.classList.add("checked");
      check.append(icon("check", "icon"));
    }
    const meta = el("span", "workspace-meta");
    meta.append(el("span", "workspace-name", w.name), el("span", "workspace-path", w.path));
    main.append(check, meta);
    main.onclick = () => {
      const same = w.id === shared.workspaceId;
      closeOverlay("workspace-sheet", { keepFocus: true });
      if (same) return;
      switchWorkspace(w.id)
        .then(() => toast(`已切换到 ${w.name}`))
        .catch(reportError);
    };
    const gear = el("button", "icon-button workspace-gear");
    gear.type = "button";
    gear.append(icon("settings", "icon icon-sm"));
    gear.setAttribute("aria-label", `设置 ${w.name}`);
    gear.title = `设置 ${w.name}`;
    gear.onclick = () => openPreferences(w.id);
    row.append(main, gear);
    list.append(row);
  }
}

async function openWorkspaceSheet() {
  openOverlay("workspace-sheet", { initialFocus: ".sheet-head button", returnTo: $("workspace-button") });
  renderWorkspaceSheet();
  try {
    await refreshHistory();
    if (isOpen("workspace-sheet")) renderWorkspaceSheet();
  } catch (error) {
    $("workspace-list").append(el("p", "error-text", "刷新失败：" + error.message));
  }
}

function requestedTarget(id) {
  return shared.registry?.workspaces.find((w) => w.id === id);
}

function openPreferences(workspaceId = null) {
  const targetId = workspaceId || shared.settingsTargetId || shared.workspaceId;
  const target = requestedTarget(targetId);
  if (!target) return reportError(new Error("找不到要设置的工作区"));
  shared.settingsTargetId = target.id;
  closeOverlay("workspace-sheet", { keepFocus: true });
  $("settings-workspace-name").textContent = target.name;
  $("preferences-workspace-name").textContent = target.name;
  $("settings-workspace-path").textContent = target.path;
  $("project-preferences").value = target.preferences || "";
  $("preferences-status").textContent =
    target.id === shared.workspaceId ? "保存后从下一轮生效，会带入本工作区的所有新轮次。" : "这是另一个工作区的项目偏好，不会影响当前对话。";
  $("settings-workspace-path").hidden = !target.path;
  openOverlay("settings-sheet", { returnTo: $("workspace-button"), onClose: () => (shared.settingsTargetId = null) });
}

async function savePreferences() {
  if (busy.preferences) return;
  const targetId = shared.settingsTargetId || shared.workspaceId;
  const button = $("save-preferences");
  const status = $("preferences-status");
  busy.preferences = true;
  button.disabled = true;
  status.textContent = "正在保存…";
  try {
    const saved = await api(`/api/workspaces/${targetId}/preferences`, { text: $("project-preferences").value });
    const w = shared.registry?.workspaces.find((x) => x.id === saved.id);
    if (w) w.preferences = saved.preferences;
    status.textContent = "已保存";
    toast(`${saved.name} 的项目偏好已保存`);
  } catch (error) {
    status.textContent = "保存失败：" + (error.message || "未知错误");
    reportError(error);
  } finally {
    busy.preferences = false;
    button.disabled = false;
  }
}

function renderFolderList() {
  const list = $("folder-list");
  list.replaceChildren();
  const query = $("folder-search").value.trim().toLowerCase();
  const data = shared.currentFolder;
  if (!data) return;
  const entries = (data.entries || []).filter((e) => !query || e.name.toLowerCase().includes(query));
  if (!entries.length)
    list.append(el("p", "list-empty", query ? "当前文件夹没有匹配的子文件夹" : "这个文件夹里没有子文件夹"));
  for (const entry of entries) {
    const row = el("button", "folder-row");
    row.type = "button";
    const badge = el("span", "folder-icon");
    badge.append(icon("folder", "icon icon-sm"));
    const chevron = el("span", "folder-chevron");
    chevron.append(icon("chevron-right"));
    row.append(badge, el("span", "folder-name", entry.name), chevron);
    row.onclick = () => loadFolder(entry.path);
    list.append(row);
  }
}

function renderFolderChrome(data) {
  const crumbs = $("folder-breadcrumbs");
  crumbs.replaceChildren();
  (data.breadcrumbs || []).forEach((crumb, index, all) => {
    const button = el("button", "crumb" + (index === all.length - 1 ? " current" : ""), crumb.name);
    button.type = "button";
    button.title = crumb.path;
    button.onclick = () => loadFolder(crumb.path);
    if (index > 0) crumbs.append(el("span", "crumb-sep", "/"));
    crumbs.append(button);
  });
  requestAnimationFrame(() => (crumbs.scrollLeft = crumbs.scrollWidth));
  const roots = $("folder-roots");
  roots.replaceChildren();
  for (const root of data.roots || []) {
    const chip = el("button", "root-chip" + (root.path === data.path ? " active" : ""), root.name);
    chip.type = "button";
    chip.title = root.path;
    chip.onclick = () => loadFolder(root.path);
    roots.append(chip);
  }
  $("folder-back").disabled = !data.parent;
  $("folder-path").textContent = data.path;
  $("use-folder").disabled = false;
  $("folder-title").textContent = "选择项目目录";
}

/**
 * Load a directory listing. Every request gets a sequence number so a slow,
 * stale response can never overwrite a newer folder.
 */
async function loadFolder(path) {
  const seq = ++folderSeq;
  const list = $("folder-list");
  list.replaceChildren(el("div", "loading-state", "正在读取目录…"));
  $("folder-error").textContent = "";
  $("use-folder").disabled = true;
  try {
    const data = await api("/api/directories" + (path ? "?path=" + encodeURIComponent(path) : ""));
    if (seq !== folderSeq) return null;
    shared.currentFolder = data;
    renderFolderChrome(data);
    renderFolderList();
    return data;
  } catch (error) {
    if (seq !== folderSeq) return null;
    shared.currentFolder = null;
    list.replaceChildren();
    $("folder-error").textContent = error.message || "无法读取目录";
    $("use-folder").disabled = true;
    $("folder-path").textContent = "尚未选择";
    return null;
  }
}

async function openFolderSheet() {
  openOverlay("folder-sheet", { initialFocus: "#folder-search", returnTo: $("open-folder") });
  $("use-folder").disabled = true;
  for (const id of ["folder-breadcrumbs", "folder-roots"]) $(id).replaceChildren();
  if (folderCache && folderCache.path) return loadFolder(folderCache.path);
  return loadFolder(null);
}

async function useCurrentFolder() {
  const data = shared.currentFolder;
  const button = $("use-folder");
  if (!data || busy.folder) return;
  busy.folder = true;
  button.disabled = true;
  button.textContent = "正在添加…";
  const name = data.path.split(/[\\/]/).filter(Boolean).pop() || data.path;
  try {
    const created = await api("/api/workspaces", { path: data.path, name });
    await refreshHistory();
    closeOverlay("folder-sheet", { keepFocus: true });
    if (created.id !== shared.workspaceId) {
      await switchWorkspace(created.id);
      toast(`已切换到 ${created.name || name}`);
    } else toast("该目录已是当前工作区");
  } catch (error) {
    $("folder-error").textContent = "添加失败：" + (error.message || "未知错误");
  } finally {
    busy.folder = false;
    button.textContent = "使用此目录";
    button.disabled = !shared.currentFolder;
  }
}

async function createSessionFor(workspaceId) {
  const created = await api("/api/sessions", { workspaceId });
  updateSessionCache(created);
  if (created.workspaceId === shared.workspaceId) {
    await selectSession(created.id);
    for (const id of SHEET_IDS) if (isOpen(id)) closeOverlay(id, { keepFocus: true });
  }
  return created.id;
}

/* ------------------------------------------------------------------ boot */

function applyWelcome() {
  const welcome = $("welcome");
  if (!welcome) return;
  welcome.hidden = !!shared.state?.items?.length;
  $("welcome-workspace").textContent = "当前工作区 · " + (workspace()?.name || "未选择");
}

async function boot() {
  document.documentElement.dataset.theme = "light";
  document.body.classList.add("light");
  bindCoreEvents();
  $("model-chip-name").textContent = "正在连接…";
  try {
    await refreshHistory();
  } catch (error) {
    setConnection("offline");
    if (!(error instanceof AuthError)) reportError(error);
    return false;
  }
  setConnection("connected");
  loadModelInfo().catch(() => {});
  const local = shared.sessionId && shared.sessions.find((s) => s.id === shared.sessionId);
  const latest = shared.sessions
    .filter((s) => s.workspaceId === shared.workspaceId)
    .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")))[0];
  try {
    if (local) await selectSession(local.id);
    else if (latest) await selectSession(latest.id);
    else {
      shared.sessionId = null;
      shared.state = null;
      localStorage.removeItem("workbench-session");
      render();
    }
    applyWelcome();
  } catch (error) {
    if (!(error instanceof AuthError)) reportError(error);
    render();
  }
  return true;
}

/* ------------------------------------------------------------------ wiring */

function bindCoreEvents() {
  if (document.body.dataset.bound === "1") return;
  document.body.dataset.bound = "1";
  document.addEventListener("keydown", onKeydown);
  $("menu")?.addEventListener("click", () => (isOpen(DRAWER_ID) ? closeDrawer() : openDrawer()));
  $("close-menu")?.addEventListener("click", () => closeDrawer());
  $("drawer-backdrop")?.addEventListener("click", () => closeDrawer());
  $("sheet-backdrop")?.addEventListener("click", () => closeTop());
  for (const button of document.querySelectorAll("[data-close-sheet]"))
    button.addEventListener("click", () => closeOverlay(button.dataset.closeSheet));
  $("history-search")?.addEventListener("input", (event) => {
    shared.historyQuery = event.target.value;
    buildHistory();
  });
  $("new")?.addEventListener("click", () =>
    newSession()
      .then(() => toast("已新建对话"))
      .catch(reportError),
  );
  $("workspace-button")?.addEventListener("click", openWorkspaceSheet);
  $("model-button")?.addEventListener("click", () => openModelSheet().catch(reportError));
  $("advanced-open")?.addEventListener("click", () => openAdvancedSheet().catch(reportError));
  $("advanced-back")?.addEventListener("click", () => {
    closeOverlay("advanced-sheet", { keepFocus: true });
    openOverlay("model-sheet", { initialFocus: ".sheet-head button", returnTo: $("model-button") });
    renderModelSheet();
  });
  $("settings-button")?.addEventListener("click", () => {
    closeDrawer();
    openPreferences();
  });
  $("save-preferences")?.addEventListener("click", savePreferences);
  $("save-model")?.addEventListener("click", saveSettings);
  $("save-advanced")?.addEventListener("click", saveSettings);
  $("fast-toggle")?.addEventListener("click", () => {
    if ($("fast-toggle").disabled) return;
    toggleSwitch("fast-toggle");
    settingsDraft.fast = switchValue("fast-toggle");
  });
  bindSwitch("dsh-enabled", (value) => (settingsDraft.dshEnabled = value));
  bindSwitch("yolo", (value) => (settingsDraft.yolo = value));
  $("save-default")?.addEventListener("click", () => {
    toggleSwitch("save-default");
    $("save-default").dataset.touched = "1";
  });
  $("open-folder")?.addEventListener("click", () => openFolderSheet());
  $("folder-back")?.addEventListener("click", () => {
    if (shared.currentFolder?.parent) loadFolder(shared.currentFolder.parent);
  });
  $("folder-search")?.addEventListener("input", () => renderFolderList());
  $("use-folder")?.addEventListener("click", useCurrentFolder);
  $("stop")?.addEventListener("click", stopTurn);
  $("composer")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const prompt = $("prompt");
    const text = prompt.value.trim();
    if (!text || busy.send) return;
    shared.draft = { text };
    prompt.value = "";
    prompt.style.height = "auto";
    shared.follow = true;
    syncComposer();
    submitMessage(text)
      .then((ok) => {
        if (ok) shared.draft = null;
        else {
          prompt.value = text;
          autosizePrompt();
          syncComposer();
        }
      })
      .catch(() => {
        prompt.value = text;
        autosizePrompt();
        syncComposer();
      });
  });
  $("prompt")?.addEventListener("input", () => {
    autosizePrompt();
    syncComposer();
  });
  $("prompt")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      $("composer").requestSubmit();
    }
  });
  $("conversation")?.addEventListener("scroll", () => {
    const node = $("conversation");
    shared.follow = node.scrollHeight - node.scrollTop - node.clientHeight < 120;
  });
  $("login-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = $("token")?.value || "";
    $("login-error").textContent = "";
    connectWithToken(value)
      .then(() => toast("已连接"))
      .catch((error) => {
        $("login-error").textContent = error.message || "连接失败";
      });
  });
}

boot().catch((error) => reportError(error));
