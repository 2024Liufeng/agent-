<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';
import { watchChatEvents, type ChatEvent } from './composables/useChatEvents';
import { sendChatMessage } from './services/api';
import ChatPanel from './components/ChatPanel.vue';
import ProgressPanel from './components/ProgressPanel.vue';

type ChatMessage = { role: 'user' | 'assistant'; text: string };
type ChatOption = { id: string; label: string };

// 对应设计：App 管理聊天历史、进度、对话 ID；子组件只负责展示。
const messages = ref<ChatMessage[]>([]);
const progressEvents = ref<ChatEvent[]>([]);
const input = ref('');
const choiceOptions = ref<ChatOption[]>([]);
const conversationId = ref<string | null>(null);
const running = ref(false);
const waitingForUser = ref(false);
const connectionLost = ref(false);
const errorMessage = ref('');
let closeEvents: (() => void) | null = null;

function closeEventSource() {
  closeEvents?.();
  closeEvents = null;
}

// 后端公开事件：进度显示在右侧，提问/结果/错误显示在左侧。
function handleAgentEvent(event: ChatEvent) {
  if (['agent_started', 'tool_started', 'tool_completed'].includes(event.type)) {
    progressEvents.value.push(event);
    return;
  }

  if (event.type === 'ask_user' && event.question) {
    messages.value.push({ role: 'assistant', text: event.question });

    // 只有 Agent 提供了可选答案才显示选项按钮。
    choiceOptions.value =
      ['choice', 'confirmation'].includes(event.kind ?? '') && Array.isArray(event.options)
        ? event.options
        : [];
    waitingForUser.value = true;
    running.value = false;
    connectionLost.value = false;
    errorMessage.value = '';
  } else if (event.type === 'final') {
    messages.value.push({
      role: 'assistant',
      text: event.text || 'Agent 本轮结束，但没有返回可展示的文字。',
    });
    choiceOptions.value = [];
    waitingForUser.value = false;
    running.value = false;
    connectionLost.value = false;
    errorMessage.value = '';
  } else if (event.type === 'error') {
    errorMessage.value = event.text || 'Agent 运行失败';
    choiceOptions.value = [];
    waitingForUser.value = false;
    running.value = false;
    connectionLost.value = false;
  }
}

// 对应设计：订阅 SSE，不自动重复提交购物任务。
function listenToAgent(id: string) {
  closeEventSource();
  connectionLost.value = false;
  closeEvents = watchChatEvents(id, handleAgentEvent, () => {
    connectionLost.value = true;
    errorMessage.value = '实时连接已中断，可以点击“重新连接进度”，不会重复启动任务。';
    // 连接断开不等于 Agent 已结束，所以不把 running 改成 false。
  });
}

// 重连时只重新 GET 同一轮 SSE，不发送 POST，避免重复执行。
function reconnectEvents() {
  if (!conversationId.value || !connectionLost.value) return;
  errorMessage.value = '';
  listenToAgent(conversationId.value);
}

// 用户点击 Agent 的选择按钮后仍走同一个聊天接口，主 Agent 自己决定调用登录工具。
function selectOption(label: string) {
  input.value = label;
  void sendMessage();
}

async function sendMessage() {
  const message = input.value.trim();
  if (!message || running.value || connectionLost.value) return;

  running.value = true;
  errorMessage.value = '';
  progressEvents.value = []; // 每轮进度单独显示，不混入上一轮。

  try {
    const data = await sendChatMessage(message, conversationId.value);
    conversationId.value = data.conversation_id;

    // 请求被后端接受后才记录消息、清空输入框；失败则保留文字供重试。
    messages.value.push({ role: 'user', text: message });
    input.value = '';
    choiceOptions.value = [];
    waitingForUser.value = false;
    listenToAgent(data.conversation_id);
  } catch (error) {
    errorMessage.value =
      error instanceof Error ? error.message : '消息发送失败，请检查后端服务';
    running.value = false;
  }
}

// 新建对话只清空前端数据，下一条消息带 null ID，后端会创建新的主 Agent。
// Agent 执行中不允许切换，以免丢失进行中的进度订阅。
function newConversation() {
  if (running.value && !connectionLost.value) return;
  closeEventSource();
  messages.value = [];
  progressEvents.value = [];
  choiceOptions.value = [];
  input.value = '';
  conversationId.value = null;
  running.value = false;
  connectionLost.value = false;
  waitingForUser.value = false;
  errorMessage.value = '';
}

onBeforeUnmount(() => closeEventSource());
</script>

<template>
  <main class="app-shell">
    <header class="app-header">
      <div>
        <p class="eyebrow">HELLOAGENTS · SHOPPING</p>
        <h1>智能购物助手</h1>
        <p>左侧和 Agent 对话，右侧查看真实工具执行进度</p>
      </div>

      <div class="header-actions">
        <button class="new-chat" type="button"
                :disabled="running && !connectionLost" @click="newConversation">
          {{ connectionLost ? '放弃并新建对话' : '新建对话' }}
        </button>
        <span class="state-badge" :class="{ working: running, disconnected: connectionLost }">
          {{ connectionLost ? '连接中断' : running ? '执行中' : waitingForUser ? '等待你的回复' : '就绪' }}
        </span>
      </div>
    </header>

    <!-- 网络中断只需要恢复 GET SSE，不能重新发送上一条购物消息。 -->
    <div v-if="connectionLost" class="connection-notice" role="alert">
      <span>实时连接已中断，后台任务可能仍在执行。可重连查看；如果后端已重启，可放弃当前对话并新建。</span>
      <button type="button" @click="reconnectEvents">重新连接进度</button>
    </div>

    <!-- 对应设计：左侧聊天，右侧实时进度；两边的数据统一由 App 管理。 -->
    <div class="workspace">
      <ChatPanel
        v-model="input"
        :messages="messages"
        :options="choiceOptions"
        :running="running || connectionLost"
        :error="errorMessage"
        @send="sendMessage"
        @select-option="selectOption"
      />

      <!-- 右侧只接收执行事件，不处理购物策略，也不调用后端。 -->
      <ProgressPanel
        :events="progressEvents"
        :running="running"
      />
    </div>
  </main>
</template>

<style>
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  background: #f5f7fb;
  font-family: Inter, "Segoe UI", "Microsoft YaHei", sans-serif;
}
button, input {
  font: inherit;
}
</style>

<style scoped>
.app-shell {
  width: min(1440px, 100%);
  margin: 0 auto;
  padding: 28px;
}
.app-header {
  margin-bottom: 20px;
}
.app-header h1 {
  margin: 0;
  color: #172033;
  font-size: 26px;
}
.app-header p {
  margin: 7px 0 0;
  color: #64748b;
  font-size: 14px;
}
.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  align-items: start;
  gap: 20px;
}
@media (max-width: 800px) {
  .app-shell {
    padding: 16px;
  }
  .workspace {
    grid-template-columns: minmax(0, 1fr);
  }
}

.eyebrow { margin: 0 0 7px; color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: 0.09em; }
.app-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.app-header h1 { font-size: 27px; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.new-chat { padding: 9px 14px; border: 1px solid #cbd5e1; border-radius: 9px; background: white; color: #334155; }
.state-badge { padding: 9px 12px; border-radius: 999px; background: #e2e8f0; color: #475569; font-size: 12px; white-space: nowrap; }
.state-badge.working { background: #e0f2fe; color: #075985; }
.state-badge.disconnected { background: #fef3c7; color: #92400e; }
.connection-notice { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 18px; padding: 12px 16px; border: 1px solid #fbbf24; border-radius: 10px; background: #fffbeb; color: #92400e; font-size: 13px; }
.connection-notice button { padding: 7px 12px; border: 1px solid #d97706; border-radius: 8px; color: #92400e; background: white; }
@media (max-width: 800px) { .app-header { flex-direction: column; } }
</style>

