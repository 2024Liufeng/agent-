---
name: dsh-delegation
description: Coordinate persistent DSH ACP workers when coding in this workspace. Delegate implementation when useful, retain architecture decisions and review in Codex, and continue worker conversations through follow-up prompts.
---

# DSH collaboration

Use judgment to choose the executor. Delegate bounded implementation, routine edits, and research to DSH when the expected savings exceed the handoff and review cost. Handle ambiguous architecture, difficult debugging, integration decisions, or work that would be faster directly yourself. DSH is an agent runtime; its actual ability and cost depend on its configured model.

In this workspace, the user prefers conserving their Plus GPT quota. Default to delegating simple and medium-complexity implementation, ordinary debugging, and runtime checks to the configured DeepSeek worker. Codex retains planning, difficult decisions, and final review. Batch related work into a clear assignment and request concise completion reports; choose the executor yourself without asking the user for every handoff.

Keep each implementation turn bounded to a file or a small coherent change. For a full redesign, settle structure, styling, and behavior in successive prompts. If a turn stops with `max_tokens`, inspect what actually landed and continue the same worker session with a smaller next step; do not accept the stopped job as complete or restart the entire investigation.

The mobile workbench owns a long-lived ACP process. Use the repository's `codex-web/worker-client.mjs` with Node. `WORKBENCH_URL` and `WORKBENCH_TOKEN` are inherited from the web server. Never print the token.

Set `WORKBENCH_SESSION_ID` to the web conversation id supplied in your developer instructions so DSH activity appears in the same chat. The current Worker uses the configured Ark Coding DeepSeek model, retaining its ACP session across prompts. If this skill is read by a DSH worker itself, complete your assigned task directly instead of invoking this helper recursively.

- `node <repo>/codex-web/worker-client.mjs new` creates a worker session.
- `node <repo>/codex-web/worker-client.mjs prompt SESSION_ID "task"` starts a prompt and returns a job id.
- `node <repo>/codex-web/worker-client.mjs status JOB_ID` returns updates and settlement.
- `node <repo>/codex-web/worker-client.mjs details JOB_ID` returns full diagnostics only when the compact result is insufficient.
- `node <repo>/codex-web/worker-client.mjs cancel SESSION_ID` cancels current work.
- `node <repo>/codex-web/worker-client.mjs resume SESSION_ID` restores a persisted session after a process restart.

Reuse the session for follow-up instructions, corrections, and questions about the same task. Keep the session id in your working notes. One prompt can run at a time per session. Poll running jobs at reasonable intervals while continuing independent work. A settled job requires inspecting its ACP stop reason and actual artifacts before accepting it. An error requires diagnosis, scoped revision instructions, or taking over the work yourself.

Give DSH the goal, relevant files, allowed editing scope, project preferences, architectural decisions already made, and observable completion criteria. Workers inherit the conversation's runtime permissions. Written editing scope is coordination guidance, not an OS sandbox. Delegate only within the user's authorized task. Use compact status reports by default and ask for focused follow-up details rather than repeatedly loading entire logs.

Coordinate file ownership so Codex and DSH do not edit the same file concurrently. Review the diff and use suitable build or runtime checks before accepting the work. If the worker needs repeated corrections or the task has become complex, take over and explain the result to the user. Show concise delegation progress in the same conversation.
