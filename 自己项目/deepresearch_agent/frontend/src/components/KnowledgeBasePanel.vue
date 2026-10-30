<template>
  <section class="knowledge-panel">
    <div class="panel-heading">
      <span class="label">参考资料 <span class="optional">（可选）</span></span>
      <button type="button" class="add-button" :disabled="disabled || importing" @click="fileInput?.click()">
        {{ document ? '更换 PDF' : '＋ 添加 PDF' }}
      </button>
      <input ref="fileInput" class="file-input" type="file" accept=".pdf,application/pdf"
        :disabled="disabled || importing" @change="chooseFile" />
    </div>

    <div v-if="importing" class="document-row" role="status">
      <span class="document-name">📄 {{ importingName }}</span>
      <span class="document-status">正在解析并导入…</span>
    </div>
    <div v-else-if="document" class="document-row">
      <span class="document-name">📄 {{ document.name }}</span>
      <span class="document-status ready">已就绪</span>
      <button type="button" class="remove-button" :disabled="disabled" @click="removeDocument">移除</button>
    </div>

    <p class="hint">支持含文本的 PDF，最大 20 MB。不添加资料时将只搜索网页。</p>
    <p v-if="error" class="upload-error" role="alert">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { uploadPDF, type KnowledgeBase } from '../services/api';

defineProps<{ modelValue: string; document: KnowledgeBase | null; disabled: boolean }>();
const emit = defineEmits<{
  (event: 'update:modelValue', value: string): void;
  (event: 'update:document', value: KnowledgeBase | null): void;
  (event: 'busy', value: boolean): void;
}>();

const fileInput = ref<HTMLInputElement | null>(null);
const importing = ref(false);
const importingName = ref('');
const error = ref('');

function removeDocument() {
  // 只解除本次研究的关联，不删除已保存的文档和向量。
  emit('update:modelValue', '');
  emit('update:document', null);
  error.value = '';
}

async function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  // 清空文件控件，允许用户在失败后重新选择同一个文件。
  input.value = '';
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 20 * 1024 * 1024) {
    error.value = '请选择 20 MB 以内的 PDF 文件';
    return;
  }

  // 更换资料时先解除旧关联，避免新文件导入失败后误用旧文档。
  removeDocument();
  importing.value = true;
  importingName.value = file.name;
  emit('busy', true);
  try {
    const result = await uploadPDF(file);
    emit('update:document', result);
    emit('update:modelValue', result.id);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '导入失败，请重新选择 PDF';
  } finally {
    importing.value = false;
    importingName.value = '';
    emit('busy', false);
  }
}
</script>

<style scoped>
.knowledge-panel { display: grid; gap: 12px; padding: 16px 18px; border: 1px solid #ddd; border-radius: 12px; }
.panel-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; }
.label { font-size: 14px; font-weight: 600; color: #25334a; }
.optional { font-weight: 400; color: #667; }
.file-input { display: none; }
.add-button, .remove-button { border: 0; background: transparent; cursor: pointer; }
.add-button { padding: 7px 10px; color: #3558b4; font-weight: 600; border-radius: 8px; background: #edf2ff; }
.document-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 8px; background: #f5f7fb; }
.document-name { flex: 1 1 120px; min-width: 0; overflow-wrap: anywhere; font-size: 13px; color: #25334a; }
.document-status { color: #667; font-size: 12px; }
.ready { color: #288058; }
.remove-button { padding: 4px; color: #667; font-size: 12px; }
button:disabled { cursor: default; opacity: .6; }
p { margin: 0; font-size: 12px; line-height: 1.6; }
.hint { color: #667; }
.upload-error { color: #af2438; }
</style>
