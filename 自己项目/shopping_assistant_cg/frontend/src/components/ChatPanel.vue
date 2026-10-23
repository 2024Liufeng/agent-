<script setup lang="ts">
// 对应设计：ChatPanel 只负责聊天显示和上报用户操作，不直接发 HTTP 请求。
import { nextTick, ref, watch } from 'vue';

type ChatMessage = { role: 'user' | 'assistant'; text: string };
type ChatOption = { id: string; label: string };

const props = defineProps<{
  messages: ChatMessage[]; // App.vue 保存的聊天历史
  options: ChatOption[];   // Agent 的 ask_user 选项
  running: boolean;       // Agent 执行期间不能发送下一条消息
  error: string;          // 后端可公开的错误或 SSE 中断提示
  modelValue: string;     // App.vue 的 input；通过 v-model 保持同步
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string]; // 把新输入的文字通知给 App
  send: [];                            // 用户点击发送
  'select-option': [label: string];    // 用户点击 Agent 的选项
}>();

const messagesElement = ref<HTMLElement | null>(null);

function onInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLInputElement).value);
}

// 当 App.vue 在 messages 中加入新消息时，聊天窗口自动滚动到底部。
watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    const el = messagesElement.value;
    if (el) el.scrollTop = el.scrollHeight;
  },
);
</script>

<template>
  <section class="chat-panel" aria-label="购物对话">
    <header class="panel-header">
      <h2>对话</h2>
      <p>主 Agent 的提问、回复和最终推荐都在这里</p>
    </header>

    <div ref="messagesElement" class="messages" role="log" aria-label="聊天消息" aria-live="polite">
      <p v-if="messages.length === 0" class="empty-chat">
        描述你的购物需求，主 Agent 会按需调用商品发现、比价和推荐子 Agent。
      </p>

      <article v-for="(msg, index) in messages" :key="index"
               class="message" :class="msg.role">
        <strong>{{ msg.role === 'user' ? '你' : 'Agent' }}</strong>
        <!-- Agent 文本自动转义，不作为 HTML 运行。 -->
        <p>{{ msg.text }}</p>
      </article>
    </div>

    <!-- 只有 Agent 真的提供可选答案时，才生成按钮。 -->
    <div v-if="options.length > 0" class="choice-actions" aria-label="回答选项">
      <button v-for="option in options" :key="option.id"
              type="button" :disabled="running"
              @click="emit('select-option', option.label)">
        {{ option.label }}
      </button>
    </div>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>

    <!-- 不刷新页面；提交事件由 App.vue 的 sendMessage 处理。 -->
    <form class="composer" @submit.prevent="emit('send')">
      <input :value="modelValue" :disabled="running"
             placeholder="输入购物需求或回答 Agent 的问题"
             aria-label="购物需求" @input="onInput" />
      <button type="submit" :disabled="running || !modelValue.trim()">
        {{ running ? '处理中…' : '发送' }}
      </button>
    </form>
  </section>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 420px;
  padding: 20px;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: #ffffff;
}
.panel-header { padding-bottom: 16px; border-bottom: 1px solid #e8edf3; }
.panel-header h2 { margin: 0; font-size: 18px; }
.panel-header p { margin: 6px 0 0; color: #64748b; font-size: 13px; }
.messages {
  flex: 1 1 auto;
  min-height: 260px;
  max-height: calc(100vh - 260px);
  overflow-y: auto;
  padding: 14px 3px;
}
.empty-chat {
  margin: 30px 5px;
  color: #94a3b8;
  text-align: center;
  font-size: 13px;
  line-height: 1.8;
}
.message { max-width: 92%; margin: 10px 0; }
.message strong { display: block; margin-bottom: 5px; color: #64748b; font-size: 12px; }
.message p {
  margin: 0;
  padding: 12px 14px;
  border-radius: 12px;
  background: #f1f5f9;
  line-height: 1.7;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  font-size: 14px;
}
.message.user { margin-left: auto; }
.message.user strong { text-align: right; }
.message.user p { background: #dbeafe; }
.choice-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 6px 0 14px; }
.choice-actions button {
  border: 1px solid #93c5fd;
  border-radius: 9px;
  padding: 9px 13px;
  background: #eff6ff;
  color: #1d4ed8;
}
.choice-actions button:hover:not(:disabled) { background: #dbeafe; }
.error-message {
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px solid #fecaca;
  border-radius: 9px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 13px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.composer { display: flex; gap: 8px; padding-top: 14px; border-top: 1px solid #e8edf3; }
.composer input {
  flex: 1;
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  outline-color: #93c5fd;
  color: #172033;
}
.composer button {
  min-width: 74px;
  border: 0;
  border-radius: 10px;
  background: #2563eb;
  color: white;
  padding: 11px 14px;
}
@media (max-width: 480px) { .chat-panel { padding: 14px; } }
</style>
