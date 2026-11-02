// Called by Codex from a shell. The backend retains the long-lived ACP process.
const [action, sessionId, ...words] = process.argv.slice(2);
const routes = {
  new: "/api/dsh/new",
  resume: "/api/dsh/new",
  prompt: "/api/dsh/prompt",
  status: `/api/dsh/jobs/${sessionId}`,
  details: `/api/dsh/jobs/${sessionId}?details=1`,
  cancel: "/api/dsh/cancel",
};
if (!routes[action]) {
  console.error(
    "Usage: node worker-client.mjs new | resume ID | prompt ID TASK | status JOB_ID | cancel ID",
  );
  process.exit(1);
}
const response = await fetch(
  (process.env.WORKBENCH_URL || "http://127.0.0.1:3088") + routes[action],
  {
    method: ["status", "details"].includes(action) ? "GET" : "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.WORKBENCH_TOKEN || ""}`,
      "X-Workbench-Session": process.env.WORKBENCH_SESSION_ID || "",
    },
    body: ["status", "details"].includes(action)
      ? undefined
      : JSON.stringify({ sessionId, text: words.join(" ") }),
  },
);
console.log(JSON.stringify(await response.json(), null, 2));
if (!response.ok) process.exitCode = 1;
