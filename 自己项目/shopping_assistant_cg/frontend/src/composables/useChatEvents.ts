// 对应 backend/app/agent_runner.py 的公开 SSE 事件协议。
export interface ChatEvent {
  type: string;
  text?: string;
  question?: string;
  kind?: string;
  options?: Array<{ id: string; label: string }>;
  tool?: string;
  agent?: string;  // 子 Agent 内部工具事件附带 agent
  status?: string;
}

// SSE 仅订阅事件，不 POST、不重新运行 Agent；返回关闭连接的函数。
export function watchChatEvents(
  conversationId: string,
  onEvent: (event: ChatEvent) => void,
  onError?: () => void,
): () => void {
  // Vite 的 /api 代理指向 FastAPI；SSE 数据形如 data: {"type": ...}
  const url = '/api/chat/' + encodeURIComponent(conversationId) + '/events';
  const source = new EventSource(url);

  source.onmessage = (message: MessageEvent<string>) => {
    let event: ChatEvent;
    try {
      event = JSON.parse(message.data) as ChatEvent;
      if (!event || typeof event.type !== 'string') {
        throw new Error('SSE 事件缺少 type');
      }
    } catch {
      source.close();
      onError?.();
      return;
    }

    onEvent(event);

    // 一轮结束时主动关闭连接，避免自动重复连接旧任务。
    if (['ask_user', 'final', 'error'].includes(event.type)) {
      source.close();
    }
  };

  source.onerror = () => {
    // 网络出错不代表 Agent 失败；用户可以通过按钮重新订阅。
    source.close();
    onError?.();
  };

  return () => source.close();
}
