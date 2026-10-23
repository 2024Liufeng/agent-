<script setup lang="ts">
// 对应设计：右侧只显示后端真实发来的执行事件，不推测 Agent 的内部思考。
import type { ChatEvent } from '../composables/useChatEvents';

defineProps<{
  events: ChatEvent[]; // App.vue 收集的 agent_started / tool_started / tool_completed
  running: boolean;    // 当前主 Agent 是否正在执行
}>();

// 根据后端事件类型显示简短状态；不根据工具名称猜测执行结果。
function statusLabel(event: ChatEvent): string {
  if (event.type === 'agent_started') return '已启动';
  if (event.type === 'tool_started') return '进行中';

  if (event.type === 'tool_completed') {
    if (event.status === 'success') return '已完成';
    if (event.status === 'partial') return '部分完成';
    if (event.status === 'error') return '失败';
    return '状态未确认';
  }

  return '事件';
}

// 区分主 Agent 直接发起的工具调用和子 Agent 内部的工具。
function ownerLabel(event: ChatEvent): string {
  if (event.type === 'agent_started') return '主 Agent';
  return event.agent || '主 Agent 调用';
}
</script>

<template>
  <section class="progress-panel" aria-label="Agent 实时进度">
    <header class="panel-header">
      <div>
        <h2>实时进度</h2>
        <p>只展示后端报告的真实执行事件</p>
      </div>
      <span class="run-state" :class="{ active: running }">
        {{ running ? '执行中' : events.length ? '本轮已暂停或结束' : '尚未开始' }}
      </span>
    </header>

    <!-- 还没有事件时，明确告诉用户这里会显示什么。 -->
    <div v-if="events.length === 0" class="empty-state">
      <span class="empty-mark">···</span>
      <strong>暂无执行记录</strong>
      <p>发送购物需求后，主 Agent 和工具的实际进度会显示在这里。</p>
    </div>

    <!-- 每收到一条真实进度事件，App.vue 就会把它加入 events。 -->
    <ol v-else class="event-list">
      <li
        v-for="(event, index) in events"
        :key="index"
        class="event-card"
        :class="{
          started: event.type === 'agent_started',
          pending: event.type === 'tool_started',
          failed: event.status === 'error'
        }"
      >
        <div class="event-topline">
          <strong>{{ ownerLabel(event) }}</strong>
          <span class="event-status">{{ statusLabel(event) }}</span>
        </div>

        <!-- text 来自后端，不在前端编造“搜索成功”等业务结论。 -->
        <p class="event-text">{{ event.text || event.type }}</p>

        <!-- 如果后端提供工具名，就额外显示；没有则不补造。 -->
        <p v-if="event.tool" class="event-tool">工具：{{ event.tool }}</p>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.progress-panel {
  min-width: 0;
  min-height: 420px;
  padding: 20px;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: #ffffff;
  color: #172033;
}
.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e8edf3;
}
h2 {
  margin: 0;
  font-size: 18px;
}
.panel-header p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}
.run-state, .event-status {
  flex-shrink: 0;
  border-radius: 999px;
  padding: 4px 9px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 12px;
}
.run-state.active, .pending .event-status {
  background: #e0f2fe;
  color: #075985;
}
.event-list {
  display: grid;
  gap: 10px;
  max-height: calc(100vh - 250px);
  overflow-y: auto;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
}
.event-card {
  padding: 12px 13px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #fbfdff;
}
.event-card.started {
  border-color: #bfdbfe;
}
.event-card.failed {
  border-color: #fecaca;
  background: #fffafa;
}
.event-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.event-topline strong {
  overflow-wrap: anywhere;
  font-size: 13px;
}
.event-text {
  margin: 8px 0 0;
  overflow-wrap: anywhere;
  font-size: 14px;
  line-height: 1.5;
}
.event-tool {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.empty-state {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: 56px 16px;
  text-align: center;
}
.empty-mark {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 50%;
  background: #f1f5f9;
  color: #64748b;
  font-size: 24px;
}
.empty-state strong {
  font-size: 14px;
}
.empty-state p {
  max-width: 260px;
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}
</style>

