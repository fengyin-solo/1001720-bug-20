<template>
  <section class="page" data-module="elevator">
    <header class="page-head">
      <div>
        <h2>电梯设备管理</h2>
        <p class="page-desc">维护电梯设备，围绕电梯编号、电梯名称、载重规格、使用单位做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记电梯设备</button>
        <button class="btn" type="button" @click="exportRows">导出电梯设备清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="search">
      <label class="filter-item">
        <span>电梯编号</span>
        <input v-model="filters.keyword" placeholder="按电梯编号检索" />
      </label>
      <label class="filter-item">
        <span>电梯状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>当前操作单位</span>
        <select v-model="session.unit">
          <option v-for="u in units" :key="u" :value="u">{{ u }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
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
          <td v-for="column in columns" :key="column">{{ displayValue(row, column) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
            <template v-for="action in allowedActions(row)" :key="action">
              <button class="link" type="button" @click="runAction(action, row)">{{ action }}</button>
            </template>
            <span v-if="!allowedActions(row).length" class="muted-text">已到末态，无可用动作</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">当前条件下暂无电梯设备数据</td>
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
        <label class="filter-item inline">
          <span>每页</span>
          <select v-model.number="size" @change="changeSize">
            <option v-for="s in sizeOptions" :key="s" :value="s">{{ s }} 条</option>
          </select>
        </label>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detailRow" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <h3>电梯设备详情</h3>
        <dl class="detail-grid">
          <template v-for="column in detailColumns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ displayValue(detailRow, column) }}</dd>
          </template>
          <dt>归属使用单位</dt>
          <dd>{{ detailRow['使用单位'] }}</dd>
        </dl>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeDetail">返回列表</button>
        </div>
      </div>
    </div>

    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <div class="modal-card">
        <h3>登记电梯设备</h3>
        <form class="detail-form" @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field" class="filter-item">
            <span>{{ field }}</span>
            <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
          </label>
          <p class="hint-text">新登记电梯初始状态为「待检」，归属使用单位默认取当前操作单位。</p>
          <div class="modal-actions">
            <button class="btn" type="button" @click="creating = false">取消</button>
            <button class="btn primary" type="submit">提交登记</button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onActivated, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { OPERATOR_UNITS, useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/elevator'
const columns = ['电梯编号', '电梯名称', '使用单位', '载重规格', '层站数量', '使用场所', '投用日期', '下次检验日', '电梯状态']
const detailColumns = columns
const createFields = ['电梯编号', '电梯名称', '载重规格']
const statuses = ['待检', '在用', '停用']
const units = OPERATOR_UNITS
const sizeOptions = [10, 20, 50]

// 当前状态 -> 可执行的下一步动作（后端同样按此规则强校验）
const NEXT_ACTIONS: Record<string, string[]> = {
  待检: ['办理投用'],
  在用: ['停用电梯'],
  停用: [],
}

const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const pages = computed(() => Math.max(1, Math.ceil(total.value / size.value)))
const stats = ref<Record<string, number>>({ 待检: 0, 在用: 0, 停用: 0, 临近检验: 0 })
const statCards = computed(() => [
  { label: '电梯总台数', value: stats.value.total ?? 0 },
  { label: '待检', value: stats.value.待检 ?? 0 },
  { label: '在用', value: stats.value.在用 ?? 0 },
  { label: '停用', value: stats.value.停用 ?? 0 },
  { label: '临近检验', value: stats.value.临近检验 ?? 0 },
])

const filters = reactive<{ keyword: string; status: string }>({ keyword: '', status: '' })
const errorMessage = ref('')
const detailRow = ref<Row | null>(null)
const creating = ref(false)
const createForm = reactive<Record<string, string>>({})

// 丢弃过期请求，避免翻页快了把旧页数据盖到新页上
let requestSeq = 0

function buildQuery(extra?: Record<string, number>): string {
  const params = new URLSearchParams()
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.status) params.set('status', filters.status)
  params.set('page', String(extra?.page ?? page.value))
  params.set('size', String(extra?.size ?? size.value))
  return params.toString()
}

function displayValue(row: Row, column: string): string | number {
  const value = column === '电梯状态' ? (row.status ?? row[column]) : row[column]
  if (value === null || value === undefined || value === '') return '—'
  return value as string | number
}

function allowedActions(row: Row): string[] {
  return NEXT_ACTIONS[String(row.status ?? '')] ?? []
}

function search() {
  page.value = 1
  void reload()
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  page.value = 1
  void reload()
}

function goPage(target: number) {
  if (target < 1 || target > pages.value || target === page.value) return
  page.value = target
  void reload()
}

function changeSize() {
  // 改每页条数后回到第一页，由后端重新计算偏移与总数，避免落在最后一页时漏条
  page.value = 1
  void reload()
}

async function reload() {
  errorMessage.value = ''
  const seq = ++requestSeq
  try {
    const [listResp, statResp] = await Promise.all([
      request(`${ENDPOINT}?${buildQuery()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResp.ok) throw new Error('电梯设备列表读取失败')
    if (!statResp.ok) throw new Error('电梯台数概览读取失败')
    const payload = (await listResp.json()) as { items?: Row[]; total?: number; page?: number; size?: number }
    const statPayload = (await statResp.json()) as Record<string, number>
    if (seq !== requestSeq) return
    rows.value = payload.items ?? []
    total.value = payload.total ?? 0
    page.value = payload.page ?? page.value
    if (payload.size) size.value = payload.size
    stats.value = statPayload
  } catch (error) {
    if (seq === requestSeq) {
      errorMessage.value = error instanceof Error ? error.message : '电梯设备列表读取失败'
    }
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const query = new URLSearchParams({ operatorUnit: session.unit }).toString()
    const response = await request(`${ENDPOINT}/${row.id}/actions?${query}`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message || '电梯设备动作未生效，请稍后重试'
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电梯设备操作失败'
  }
}

function openDetail(row: Row) {
  detailRow.value = row
}

async function closeDetail() {
  detailRow.value = null
  // 从详情返回列表时重新拉取，保证看到的是最新状态
  await reload()
}

function openCreate() {
  for (const field of createFields) createForm[field] = ''
  creating.value = true
}

async function submitCreate() {
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({
        values: { ...createForm, 使用单位: session.unit },
      }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message || '电梯设备登记失败'
      return
    }
    creating.value = false
    page.value = 1
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电梯设备登记失败'
  }
}

async function exportRows() {
  // 清单条数与列表当前筛选范围一致：条件随请求一起下发，后端返回全量匹配结果
  const params = new URLSearchParams()
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.status) params.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}/export?${params.toString()}`)
    if (!response.ok) throw new Error('电梯设备清单导出失败')
    const payload = (await response.json()) as { total: number; items: Row[] }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `elevator-list-${Date.now()}.json`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电梯设备清单导出失败'
  }
}

onMounted(reload)
onActivated(reload)
</script>

<style scoped>
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.pager {
  display: flex;
  gap: 6px;
  align-items: center;
}
.filter-item.inline {
  display: flex;
  align-items: center;
  gap: 4px;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  background: #fff;
  border-radius: 8px;
  padding: 18px 22px;
  width: 560px;
  max-width: 90vw;
  max-height: 80vh;
  overflow: auto;
}
.detail-grid {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 6px 12px;
  margin: 12px 0;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
.detail-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hint-text {
  color: var(--muted);
  font-size: 12px;
  margin: 4px 0;
}
</style>
