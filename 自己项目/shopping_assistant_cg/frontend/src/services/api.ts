// 对应设计：把普通 HTTP 请求从 App.vue 中抽离。
// App.vue 继续负责聊天状态和业务流程；SSE 继续由 useChatEvents.ts 负责。
// 特别注意：前端不直接调用登录接口；“登录后继续”等选择仍发送给主 Agent。

export interface ChatResponse {
  conversation_id: string;
  status: string;
}

// 统一处理 JSON 请求，并把后端返回的 HTTP 错误转换成可读异常。
async function requestJson<T>(url: string, init: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(url, init);
  } catch {
    // 网络断开或后端未启动时，fetch 会直接抛出异常。
    throw new Error('无法连接后端服务，请确认 FastAPI 已启动。');
  }

  if (!response.ok) {
    let message = '请求失败（HTTP ' + response.status + '）';

    try {
      const body: unknown = await response.json();
      if (body && typeof body === 'object' && 'detail' in body) {
        const detail = (body as { detail?: unknown }).detail;
        if (typeof detail === 'string' && detail.trim()) {
          message = detail;
        }
      }
    } catch {
      // 错误响应不一定是 JSON；保留 HTTP 状态说明即可。
    }

    throw new Error(message);
  }

  try {
    return await response.json() as T;
  } catch {
    throw new Error('后端返回的数据不是有效的 JSON。');
  }
}

// 对应设计：首次发送购物需求时 conversationId 为 null；
// 用户回答 Agent 的提问时，继续携带同一个 conversationId。
export async function sendChatMessage(
  message: string,
  conversationId: string | null,
): Promise<ChatResponse> {
  const data = await requestJson<ChatResponse>('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
    }),
  });

  // HTTP 200 但缺少 ID 时不能启动 SSE，否则页面会一直等待。
  if (!data || typeof data.conversation_id !== 'string' || !data.conversation_id) {
    throw new Error('后端未返回有效的 conversation_id，无法订阅执行进度。');
  }
  return data;
}
