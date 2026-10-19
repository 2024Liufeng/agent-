<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type Message = { role: 'user' | 'assistant' | 'system'; content: string }
type Platform = { id: string; name: string; status: string }
type EventPayload = { type: string; data: any }

const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const input = ref('')
const messages = ref<Message[]>([{ role: 'assistant', content: '你好，我可以帮你发现商品、比较平台价格，也可以整理购物清单。请直接描述你的需求。' }])
const progress = ref<string[]>([])
const platforms = ref<Platform[]>([])
const taskId = ref('')
const status = ref('idle')
const result = ref('')
const pendingPrompt = ref('')
let source: EventSource | null = null

const busy = computed(() => status.value === 'running' || status.value === 'queued')
const statusText = computed(() => ({ idle: '等待输入', queued: '排队中', running: '执行中', waiting_user: '等待你的回复', completed: '已完成', failed: '执行失败' } as Record<string, string>)[status.value] || status.value)

async function loadPlatforms() {
  const res = await fetch(`${apiBase}/api/platforms/status`)
  const data = await res.json()
  platforms.value = data.platforms || []
}

function addProgress(message: string) {
  if (message) progress.value.push(message)
}

function handleEvent(event: EventPayload) {
  const data = event.data || {}
  if (event.type === 'progress' || event.type === 'tool_started' || event.type === 'tool_completed') addProgress(data.message || data.name || '')
  if (event.type === 'assistant_delta') {
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'assistant' && status.value !== 'completed') last.content += data.content || ''
    else messages.value.push({ role: 'assistant', content: data.content || '' })
  }
  if (event.type === 'user_input_required' || event.type === 'auth_required') {
    pendingPrompt.value = data.message || data.prompt || '请补充信息后继续。'
    status.value = 'waiting_user'
    messages.value.push({ role: 'system', content: pendingPrompt.value })
  }
  if (event.type === 'completed') { result.value = data.result || ''; status.value = 'completed' }
  if (event.type === 'failed') { result.value = data.error || '任务执行失败'; status.value = 'failed'; messages.value.push({ role: 'system', content: result.value }) }
}

function connectEvents(id: string) {
  source?.close()
  source = new EventSource(`${apiBase}/api/tasks/${id}/events`)
  const types = ['progress', 'tool_started', 'tool_completed', 'assistant_delta', 'user_input_required', 'auth_required', 'completed', 'failed']
  for (const type of types) source.addEventListener(type, (raw) => handleEvent({ type, data: JSON.parse((raw as MessageEvent).data).data }))
  source.onerror = () => { if (status.value === 'running') addProgress('事件连接暂时中断，页面会继续保留任务状态') }
}

async function send() {
  const text = input.value.trim()
  if (!text) return
  input.value = ''
  messages.value.push({ role: 'user', content: text })
  pendingPrompt.value = ''
  if (!taskId.value || status.value === 'completed' || status.value === 'failed') {
    progress.value = []
    result.value = ''
    messages.value.push({ role: 'assistant', content: '' })
    const res = await fetch(`${apiBase}/api/tasks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: text }) })
    const data = await res.json()
    taskId.value = data.task_id
    status.value = data.status
    connectEvents(taskId.value)
  } else {
    status.value = 'running'
    await fetch(`${apiBase}/api/tasks/${taskId.value}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text }) })
  }
}

async function login(platform: string) {
  const res = await fetch(`${apiBase}/api/platforms/${platform}/login`, { method: 'POST' })
  const data = await res.json()
  messages.value.push({ role: 'system', content: data.message })
}

onMounted(loadPlatforms)
onUnmounted(() => source?.close())
</script>

<template>
  <main class="shell">
    <header class="topbar"><div><p class="eyebrow">LOCAL AGENT WORKSPACE</p><h1>智能购物助手</h1></div><span class="state" :class="status">{{ statusText }}</span></header>
    <section class="platforms"><span class="label">平台会话</span><button v-for="platform in platforms" :key="platform.id" class="platform" @click="login(platform.id)"><i :class="platform.status"></i>{{ platform.name }} · {{ platform.status === 'profile_ready' ? '已配置' : '需登录' }}</button></section>
    <div class="grid">
      <section class="panel conversation"><div class="panel-title"><span>对话</span><small>主 Agent 会在这里继续提问</small></div><div class="messages"><article v-for="(message, index) in messages" :key="index" :class="['message', message.role]"><b>{{ message.role === 'user' ? '你' : message.role === 'assistant' ? 'Agent' : '提示' }}</b><p>{{ message.content }}</p></article></div><div class="composer"><textarea v-model="input" :placeholder="pendingPrompt || '例如：我想买一台苹果 18，预算 1 万元'" @keydown.enter.exact.prevent="send"></textarea><button class="send" :disabled="busy && !pendingPrompt" @click="send">{{ pendingPrompt ? '继续' : '发送' }}</button></div></section>
      <aside class="panel progress-panel"><div class="panel-title"><span>实时进度</span><small>{{ taskId ? `任务 ${taskId.slice(0, 8)}` : '等待任务' }}</small></div><ol class="progress-list"><li v-for="(item, index) in progress" :key="index">{{ item }}</li><li v-if="!progress.length" class="muted">发送需求后，这里会显示 Agent、工具和平台的执行过程。</li></ol><div v-if="result" class="result"><h3>结果</h3><pre>{{ result }}</pre></div></aside>
    </div>
  </main>
</template>
