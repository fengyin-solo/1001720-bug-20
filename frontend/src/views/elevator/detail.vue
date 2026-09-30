<template>
  <section class="page" data-module="elevator-detail">
    <header class="page-head">
      <div>
        <h2>电梯设备详情</h2>
        <p class="page-desc">查看电梯设备台账信息，并按单向状态流程处置设备。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <div v-if="entry" class="detail-card">
      <table class="data-table">
        <tbody>
          <tr v-for="field in detailFields" :key="field">
            <th>{{ field }}</th>
            <td>{{ entry[field] ?? '—' }}</td>
          </tr>
          <tr>
            <th>当前状态</th>
            <td>{{ entry.status }}</td>
          </tr>
        </tbody>
      </table>

      <div class="detail-actions">
        <template v-if="nextAction">
          <button
            class="btn primary"
            type="button"
            :disabled="!ownerMatched || busy"
            @click="runAction(nextAction)"
          >
            {{ nextAction }}
          </button>
          <span v-if="!ownerMatched" class="error-text">
            该电梯归属{{ entry['使用单位'] }}，当前单位为{{ store.useUnit }}，不能变更状态
          </span>
        </template>
        <span v-else class="muted-text">状态已到「{{ entry.status }}」，没有可继续执行的动作</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </div>
    </div>

    <div v-else class="empty-state">{{ errorMessage || '设备加载中…' }}</div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/elevator'
const route = useRoute()
const router = useRouter()
const store = useSessionStore()

const detailFields = ['电梯编号', '电梯名称', '载重规格', '层站数量', '使用单位', '使用场所', '投用日期', '下次检验日']
const NEXT_ACTION: Record<string, string> = {
  待投用: '办理投用',
  正常运行: '安排检修',
  停梯检修: '停用电梯',
}

const entry = ref<Row | null>(null)
const errorMessage = ref('')
const busy = ref(false)

const entryId = computed(() => Number(route.params.id))
const nextAction = computed(() => (entry.value ? NEXT_ACTION[String(entry.value.status)] ?? null : null))
const ownerMatched = computed(() =>
  entry.value ? String(entry.value['使用单位'] ?? '') === store.useUnit : false,
)

async function load() {
  errorMessage.value = ''
  try {
    // 每次进详情都向后端取最新数据，从列表操作后再进来看到的就是最新状态。
    const response = await request(`${ENDPOINT}/${entryId.value}`)
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(String(payload.detail ?? '电梯设备详情读取失败'))
    }
    entry.value = payload
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电梯设备详情读取失败'
  }
}

async function runAction(action: string) {
  errorMessage.value = ''
  busy.value = true
  try {
    const response = await request(`${ENDPOINT}/${entryId.value}/actions`, {
      method: 'POST',
      headers: { 'X-Use-Unit': encodeURIComponent(store.useUnit) },
      body: JSON.stringify({ values: { action, 使用单位: store.useUnit } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      throw new Error(String(payload.message ?? payload.detail ?? '电梯设备动作未生效，请稍后重试'))
    }
    await load()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电梯设备操作失败'
  } finally {
    busy.value = false
  }
}

function goBack() {
  void router.push({ name: 'elevator' })
}

watch(entryId, () => {
  void load()
})

onMounted(load)
</script>

<style scoped>
.detail-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  max-width: 720px;
}
.detail-card th {
  width: 140px;
  color: var(--muted);
}
.detail-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 16px;
}
.muted-text {
  color: var(--muted);
  font-size: 13px;
}
</style>
