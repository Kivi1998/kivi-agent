<script setup lang="ts">
// MemoryEditForm：记忆创建 / 编辑表单（受控）
// 字段：content（必填）/ memory_type / importance（0-1 滑块）/ status / source / expires_at
// 提交 → emit('submit', payload)；取消 → emit('cancel')
import { computed, reactive, watch } from 'vue'
import type {
  MemoryItem,
  MemoryStatus,
  MemoryType
} from '@/types/api'
import type {
  CreateMemoryItemRequest,
  UpdateMemoryItemRequest
} from '@/api/memory'

interface FormState {
  content: string
  memory_type: MemoryType
  importance: number
  status: MemoryStatus
  source: string
  expires_at: string
}

const props = defineProps<{
  /** 已有 item：进入"编辑"模式；null：进入"创建"模式 */
  item: MemoryItem | null
  /** 是否正在提交（禁用按钮） */
  submitting?: boolean
}>()

const emit = defineEmits<{
  (
    e: 'submit',
    payload: CreateMemoryItemRequest | UpdateMemoryItemRequest,
    isEdit: boolean
  ): void
  (e: 'cancel'): void
}>()

const isEdit = computed<boolean>(() => props.item !== null)

const form = reactive<FormState>({
  content: '',
  memory_type: 'user',
  importance: 0.5,
  status: 'active',
  source: '',
  expires_at: ''
})

/** 监听 item 变化：进入编辑模式时回填表单 */
watch(
  () => props.item,
  (next) => {
    if (next) {
      form.content = next.content
      form.memory_type = next.memory_type
      form.importance = next.importance
      form.status = next.status
      form.source = next.source
      form.expires_at = next.expires_at ? toLocalDatetime(next.expires_at) : ''
    } else {
      form.content = ''
      form.memory_type = 'user'
      form.importance = 0.5
      form.status = 'active'
      form.source = ''
      form.expires_at = ''
    }
  },
  { immediate: true }
)

/** ISO8601 → <input type="datetime-local"> 字符串（去掉秒/Z） */
function toLocalDatetime(iso: string): string {
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return ''
    const pad = (n: number) => String(n).padStart(2, '0')
    return (
      d.getFullYear() +
      '-' +
      pad(d.getMonth() + 1) +
      '-' +
      pad(d.getDate()) +
      'T' +
      pad(d.getHours()) +
      ':' +
      pad(d.getMinutes())
    )
  } catch {
    return ''
  }
}

/** datetime-local 字符串 → ISO8601（补 0 秒 + Z） */
function toIso(local: string): string {
  if (!local) return ''
  try {
    const d = new Date(local)
    if (isNaN(d.getTime())) return ''
    return d.toISOString()
  } catch {
    return ''
  }
}

const canSubmit = computed<boolean>(() => {
  return form.content.trim().length > 0 && !props.submitting
})

const importancePct = computed<string>(() => {
  return (form.importance * 100).toFixed(0) + '%'
})

function onSubmit(): void {
  if (!canSubmit.value) return
  const expiresIso = toIso(form.expires_at)
  if (isEdit.value) {
    const payload: UpdateMemoryItemRequest = {
      content: form.content,
      memory_type: form.memory_type,
      importance: form.importance,
      status: form.status,
      source: form.source,
      expires_at: expiresIso || null
    }
    emit('submit', payload, true)
  } else {
    const payload: CreateMemoryItemRequest = {
      content: form.content,
      memory_type: form.memory_type,
      importance: form.importance,
      source: form.source,
      expires_at: expiresIso || null
    }
    emit('submit', payload, false)
  }
}

function onCancel(): void {
  emit('cancel')
}
</script>

<template>
  <section
    class="memory-edit-form"
    data-testid="memory-edit-form"
    :data-mode="isEdit ? 'edit' : 'create'"
  >
    <header class="mef-header">
      <h3 class="mef-title">
        {{ isEdit ? '编辑记忆' : '新建记忆' }}
      </h3>
    </header>

    <form
      class="mef-form"
      data-testid="memory-edit-form-body"
      @submit.prevent="onSubmit"
    >
      <label class="mef-field mef-field-content">
        <span class="mef-label">内容 *</span>
        <textarea
          v-model="form.content"
          rows="5"
          required
          placeholder="记忆内容..."
          data-testid="memory-form-content"
        />
      </label>

      <div class="mef-row">
        <label class="mef-field">
          <span class="mef-label">类型</span>
          <select
            v-model="form.memory_type"
            data-testid="memory-form-type"
          >
            <option value="user">
              用户
            </option>
            <option value="feedback">
              反馈
            </option>
            <option value="project">
              项目
            </option>
            <option value="reference">
              参考
            </option>
            <option value="task">
              任务
            </option>
          </select>
        </label>

        <label
          v-if="isEdit"
          class="mef-field"
        >
          <span class="mef-label">状态</span>
          <select
            v-model="form.status"
            data-testid="memory-form-status"
          >
            <option value="active">
              活跃
            </option>
            <option value="pending">
              待处理
            </option>
            <option value="archived">
              已归档
            </option>
            <option value="expired">
              已过期
            </option>
          </select>
        </label>

        <label class="mef-field">
          <span class="mef-label">来源</span>
          <input
            v-model="form.source"
            type="text"
            placeholder="如 session-abc"
            data-testid="memory-form-source"
          >
        </label>
      </div>

      <label class="mef-field mef-field-importance">
        <span class="mef-label">重要度 ({{ importancePct }})</span>
        <input
          v-model.number="form.importance"
          type="range"
          min="0"
          max="1"
          step="0.05"
          data-testid="memory-form-importance"
        >
      </label>

      <label class="mef-field">
        <span class="mef-label">过期时间（可选）</span>
        <input
          v-model="form.expires_at"
          type="datetime-local"
          data-testid="memory-form-expires-at"
        >
      </label>

      <div class="mef-actions">
        <button
          type="button"
          class="mef-btn mef-btn-cancel"
          data-testid="memory-form-cancel"
          @click="onCancel"
        >
          取消
        </button>
        <button
          type="submit"
          class="mef-btn mef-btn-submit"
          :disabled="!canSubmit"
          data-testid="memory-form-submit"
        >
          {{ submitting ? '提交中...' : (isEdit ? '保存' : '创建') }}
        </button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.memory-edit-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.mef-header {
  border-bottom: 1px solid #1e242e;
  padding-bottom: 8px;
}

.mef-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.mef-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mef-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mef-label {
  font-size: 11px;
  color: var(--muted-color);
  font-weight: 500;
  text-transform: uppercase;
}

.mef-field textarea,
.mef-field input[type='text'],
.mef-field input[type='datetime-local'],
.mef-field select {
  background: #0a0e14;
  color: #c9d1d9;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 6px 8px;
  font-size: 12px;
  font-family: inherit;
}

.mef-field textarea {
  resize: vertical;
  min-height: 80px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.mef-field input[type='range'] {
  width: 100%;
  accent-color: #6366f1;
}

.mef-field-content {
  width: 100%;
}

.mef-field-importance {
  width: 100%;
}

.mef-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.mef-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid #1e242e;
  padding-top: 10px;
}

.mef-btn {
  background: #0a0e14;
  color: #c9d1d9;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
}

.mef-btn:hover:not(:disabled) {
  background: #1e242e;
}

.mef-btn-submit {
  background: #4338ca;
  color: #fff;
  border-color: #6366f1;
}

.mef-btn-submit:hover:not(:disabled) {
  background: #6366f1;
}

.mef-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
