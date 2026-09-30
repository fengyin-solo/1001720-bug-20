<template>
  <section class="page" data-module="elevator">
    <header class="page-head">
      <div>
        <h2>电梯设备管理</h2>
        <p class="page-desc">维护电梯设备，围绕电梯编号、电梯名称、载重规格、层站数量做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记电梯设备</button>
        <button class="btn" type="button" :disabled="exporting" @click="exportRows">导出电梯设备清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="search">
      <label class="filter-item">
        <span>电梯编号</span>
        <input v-model="keyword" placeholder="按电梯编号检索" />
      </label>
      <label class="filter-item">
        <span>电梯状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <span class="unit-hint">当前使用单位：{{ store.useUnit }}</span>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <router-link v-if="column === '电梯编号'" class="link" :to="`/elevator/${row.id}`">
              {{ row[column] ?? '—' }}
            </router-link>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <template v-if="nextAction(row.status)">
              <button
                class="link"
                type="button"
                :disabled="!canOperate(row) || busyId === row.id"
                :title="canOperate(row) ? '' : `该电梯归属${row['使用单位']}，当前单位不能操作`"
                @click="runAction(nextAction(row.status) as string, row)"
              >
                {{ nextAction(row.status) }}
              </button>
            </template>
            <span v-else class="muted-text">状态已终结</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的电梯设备，可调整筛选条件或登记新设备</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条电梯设备记录，第 {{ page }} / {{ pages }} 页</span>
      <span class="pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="goPage(1)">首页</button>
        <button class="btn" type="button" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <button class="btn" type="button" :disabled="page >= pages" @click="goPage(page + 1)">下一页</button>
        <button class="btn" type="button" :disabled="page >= pages" @click="goPage(pages)">末页</button>
        <label>
          每页
          <select v-model.number="size" @change="onSizeChange">
            <option :value="5">5</option>
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="50">50</option>
          </select>
          条
        </label>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>
type Stat = { label: string; value: number }

const ENDPOINT = '/api/elevator'
const store = useSessionStore()
const columns = ['电梯编号', '电梯名称', '载重规格', '层站数量', '使用单位', '使用场所', '投用日期', '下次检验日', '电梯状态']
const statuses = ['待投用', '正常运行', '停梯检修', '已停用']
// 每个状态只允许推进到相邻的下一档，回退/跳档由后端继续兜底拦截。
const NEXT_ACTION: Record<string, string> = {
  待投用: '办理投用',
  正常运行: '安排检修',
  停梯检修: '停用电梯',
}

const rows = ref<Row[]>([])
const stats = ref<Stat[]>([
  { label: '电梯总数', value: 0 },
  { label: '待检电梯', value: 0 },
  { label: '在用电梯', value: 0 },
  { label: '停梯检修', value: 0 },
  { label: '已停用', value: 0 },
])
const total = ref(0)
const page = ref(1)
const pages = ref(1)
const size = ref(10)
const keyword = ref('')
const statusFilter = ref('')
const errorMessage = ref('')
const busyId = ref<number | null>(null)
const exporting = ref(false)

function nextAction(status: unknown): string | null {
  return NEXT_ACTION[String(status)] ?? null
}

function canOperate(row: Row): boolean {
  return String(row['使用单位'] ?? '') === store.useUnit
}

function buildQuery(extra: Record<string, string | number> = {}): string {
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
  if (statusFilter.value) params.set('status', statusFilter.value)
  for (const [key, value] of Object.entries(extra)) {
    params.set(key, String(value))
  }
  return params.toString()
}

function search() {
  page.value = 1
  void reload()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  page.value = 1
  void reload()
}

function goPage(target: number) {
  page.value = target
  void reload()
}

function onSizeChange() {
  page.value = 1
  void reload()
}

function openCreate() {
  errorMessage.value = '电梯设备登记入口尚未接入审批流'
}

async function reload() {
  errorMessage.value = ''
  try {
    // 条件、页码、每页条数都随请求下发，偏移与总数以后端返回为准。
    const response = await request(`${ENDPOINT}?${buildQuery({ page: page.value, size: size.value })}`)
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(String(payload.detail ?? '电梯设备列表读取失败'))
    }
    rows.value = payload.items ?? []
    total.value = payload.total ?? 0
    pages.value = payload.pages ?? 1
    // 后端会把越界页码回收为最后一页，这里以后端口径为准。
    page.value = payload.page ?? page.value
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电梯设备列表读取失败'
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats?${buildQuery()}`)
    const payload = await response.json()
    if (response.ok && Array.isArray(payload.cards)) {
      stats.value = payload.cards.map((card: { label: string; value: number }) => ({
        label: card.label,
        value: card.value,
      }))
    }
  } catch {
    // 卡片读不到不阻塞列表，保留上一次的统计值。
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  busyId.value = Number(row.id)
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      headers: { 'X-Use-Unit': encodeURIComponent(store.useUnit) },
      body: JSON.stringify({ values: { action, 使用单位: store.useUnit } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      throw new Error(String(payload.message ?? payload.detail ?? '电梯设备动作未生效，请稍后重试'))
    }
    await Promise.all([reload(), reloadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电梯设备操作失败'
  } finally {
    busyId.value = null
  }
}

async function exportRows() {
  errorMessage.value = ''
  exporting.value = true
  try {
    // 清单与列表当前筛选范围一致，条数以后端同一份结果为准。
    const response = await request(`${ENDPOINT}/export?${buildQuery()}`)
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(String(payload.detail ?? '电梯设备清单导出失败'))
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `电梯设备清单-${payload.total}条.json`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电梯设备清单导出失败'
  } finally {
    exporting.value = false
  }
}

// 切换使用单位后刷新一次，保证可操作按钮与归属一致。
watch(
  () => store.useUnit,
  () => {
    void reload()
  },
)

onMounted(() => {
  void Promise.all([reload(), reloadStats()])
})
</script>

<style scoped>
.unit-hint {
  margin-left: auto;
  color: var(--muted);
  font-size: 12px;
}
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.pager {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}
.pager select {
  padding: 2px 4px;
}
</style>
