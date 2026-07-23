<script setup lang="ts">
// MemoryDashboard：记忆管理总览（Wave 6.1 WT-J4）
// 顶部：MemoryList（带过滤）+ 右侧 MemoryDetail / MemoryEditForm（tab 切换）
// 下方：MemorySearchBar + MemoryAuditTimeline
import { computed, onMounted, ref } from 'vue'
import {
  createMemoryDashboardApi,
  type CreateMemoryItemRequest,
  type UpdateMemoryItemRequest
} from '@/api/memory'
import type {
  MemoryAuditEvent,
  MemoryItem,
  MemorySearchResult,
  MemoryStatus,
  MemoryType
} from '@/types/api'
import MemoryList from '@/components/memory/MemoryList.vue'
import MemoryDetail from '@/components/memory/MemoryDetail.vue'
import MemoryEditForm from '@/components/memory/MemoryEditForm.vue'
import MemorySearchBar from '@/components/memory/MemorySearchBar.vue'
import MemoryAuditTimeline from '@/components/memory/MemoryAuditTimeline.vue'

const api = createMemoryDashboardApi()

const items = ref<MemoryItem[]>([])
const loading = ref<boolean>(false)
const error = ref<string | null>(null)

const selectedId = ref<string | null>(null)
const selectedItem = ref<MemoryItem | null>(null)
const detailLoading = ref<boolean>(false)

/** 列表过滤（v-model via update:emit） */
const filterStatus = ref<MemoryStatus | ''>('')
const filterType = ref<MemoryType | ''>('')
const filterSource = ref<string>('')

/** 右侧模式：view / edit / create */
const rightMode = ref<'view' | 'edit' | 'create'>('view')
const submitting = ref<boolean>(false)

/** 搜索 */
const searchResults = ref<MemorySearchResult[]>([])
const searchLoading = ref<boolean>(false)
const lastQuery = ref<string>('')
const lastTopK = ref<number>(5)

/** 审计 */
const auditLoading = ref<boolean>(false)
const auditEvents = ref<MemoryAuditEvent[]>([])

/** 当前编辑表单对应的 item（null = 创建模式） */
const editingItem = computed<MemoryItem | null>(() => {
  if (rightMode.value !== 'edit') return null
  return selectedItem.value
})

/** 简单 debounce 句柄（避免污染 window 全局） */
let sourceTimer: ReturnType<typeof setTimeout> | null = null

/** 加载列表 */
async function loadList(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const r = await api.listMemoryItems({
      status: filterStatus.value || undefined,
      memory_type: filterType.value || undefined,
      source: filterSource.value || undefined,
      limit: 100
    })
    items.value = r.items
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

/** 加载单条记忆详情 */
async function loadDetail(id: string): Promise<void> {
  selectedId.value = id
  detailLoading.value = true
  error.value = null
  rightMode.value = 'view'
  try {
    const r = await api.getMemoryItem(id)
    selectedItem.value = r.item
    void loadAudit(id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    selectedItem.value = null
  } finally {
    detailLoading.value = false
  }
}

async function loadAudit(id: string): Promise<void> {
  auditLoading.value = true
  try {
    const r = await api.getMemoryAudit(id)
    auditEvents.value = r.events
  } catch {
    auditEvents.value = []
  } finally {
    auditLoading.value = false
  }
}

function onSelectItem(id: string): void {
  void loadDetail(id)
}

function onFilterStatusChange(v: MemoryStatus | ''): void {
  filterStatus.value = v
  void loadList()
}

function onFilterTypeChange(v: MemoryType | ''): void {
  filterType.value = v
  void loadList()
}

function onFilterSourceChange(v: string): void {
  filterSource.value = v
  // 简单 debounce：300ms 内只触发一次
  if (sourceTimer) {
    clearTimeout(sourceTimer)
  }
  sourceTimer = setTimeout(() => {
    void loadList()
  }, 300)
}

function onStartCreate(): void {
  selectedId.value = null
  selectedItem.value = null
  rightMode.value = 'create'
}

function onStartEdit(id: string): void {
  if (selectedItem.value && selectedItem.value.id === id) {
    rightMode.value = 'edit'
  } else {
    void loadDetail(id).then(() => {
      rightMode.value = 'edit'
    })
  }
}

async function onSubmitForm(
  payload: CreateMemoryItemRequest | UpdateMemoryItemRequest,
  isEdit: boolean
): Promise<void> {
  submitting.value = true
  error.value = null
  try {
    if (isEdit && selectedItem.value) {
      const r = await api.updateMemoryItem(selectedItem.value.id, payload)
      selectedItem.value = r.item
      rightMode.value = 'view'
    } else {
      const r = await api.createMemoryItem(
        payload as CreateMemoryItemRequest
      )
      selectedItem.value = r.item
      selectedId.value = r.item.id
      rightMode.value = 'view'
      void loadAudit(r.item.id)
    }
    await loadList()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    submitting.value = false
  }
}

function onCancelForm(): void {
  if (selectedItem.value) {
    rightMode.value = 'view'
  } else {
    rightMode.value = 'view'
  }
}

async function onArchive(id: string): Promise<void> {
  if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
    const ok = window.confirm(`确认归档记忆 ${id}?`)
    if (!ok) return
  }
  try {
    const r = await api.archiveMemoryItem(id)
    selectedItem.value = r.item
    await loadList()
    void loadAudit(id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function onDelete(id: string): Promise<void> {
  if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
    const ok = window.confirm(`确认删除记忆 ${id}? 不可恢复。`)
    if (!ok) return
  }
  try {
    await api.deleteMemoryItem(id)
    selectedItem.value = null
    selectedId.value = null
    rightMode.value = 'view'
    await loadList()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function onSearch(payload: { q: string; topK: number }): Promise<void> {
  searchLoading.value = true
  lastQuery.value = payload.q
  lastTopK.value = payload.topK
  try {
    const r = await api.searchMemory(payload.q, payload.topK)
    searchResults.value = r.results
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    searchResults.value = []
  } finally {
    searchLoading.value = false
  }
}

function onSelectSearchResult(id: string): void {
  void loadDetail(id)
}

onMounted(() => {
  void loadList()
})
</script>

<template>
  <div
    class="memory-dashboard"
    data-testid="memory-dashboard"
  >
    <header class="md-header">
      <div>
        <h1 class="md-title">
          Memory Dashboard
        </h1>
        <p class="md-sub">
          长期记忆管理（Wave 6.1）
        </p>
      </div>
      <div class="md-header-actions">
        <button
          type="button"
          class="md-btn md-btn-create"
          data-testid="memory-create-btn"
          @click="onStartCreate"
        >
          + 新建记忆
        </button>
      </div>
    </header>

    <div
      v-if="error"
      class="md-error"
      data-testid="memory-dashboard-error"
    >
      {{ error }}
    </div>

    <div class="md-grid">
      <div class="md-col md-col-list">
        <MemoryList
          :items="items"
          :loading="loading"
          :filter-status="filterStatus"
          :filter-type="filterType"
          :filter-source="filterSource"
          @select="onSelectItem"
          @update:filter-status="onFilterStatusChange"
          @update:filter-type="onFilterTypeChange"
          @update:filter-source="onFilterSourceChange"
        />
      </div>

      <div class="md-col md-col-detail">
        <MemoryEditForm
          v-if="rightMode === 'create' || rightMode === 'edit'"
          :item="editingItem"
          :submitting="submitting"
          @submit="onSubmitForm"
          @cancel="onCancelForm"
        />
        <MemoryDetail
          v-else
          :item="selectedItem"
          @edit="onStartEdit"
          @archive="onArchive"
          @delete="onDelete"
        />
      </div>
    </div>

    <div class="md-bottom">
      <MemorySearchBar
        :results="searchResults"
        :loading="searchLoading"
        :last-query="lastQuery"
        :last-top-k="lastTopK"
        @search="onSearch"
        @select="onSelectSearchResult"
      />
      <MemoryAuditTimeline
        :events="auditEvents"
        :loading="auditLoading"
        :memory-id="selectedId ?? ''"
      />
    </div>
  </div>
</template>

<style scoped>
.memory-dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
}

.md-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
}

.md-title {
  font-size: 22px;
  font-weight: 700;
  color: #c9d1d9;
  margin: 0;
}

.md-sub {
  font-size: 13px;
  color: var(--muted-color);
  margin: 4px 0 0 0;
}

.md-header-actions {
  display: flex;
  gap: 8px;
}

.md-btn {
  background: #0a0e14;
  color: #c9d1d9;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
}

.md-btn:hover {
  background: #1e242e;
}

.md-btn-create {
  background: #4338ca;
  color: #fff;
  border-color: #6366f1;
}

.md-btn-create:hover {
  background: #6366f1;
}

.md-error {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}

.md-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 16px;
}

.md-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.md-bottom {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 960px) {
  .md-grid {
    grid-template-columns: 1fr;
  }
  .md-bottom {
    grid-template-columns: 1fr;
  }
}
</style>
