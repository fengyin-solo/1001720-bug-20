<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <div class="stat-row" v-if="elevatorStats">
      <article class="stat-card">
        <span class="stat-label">电梯总台数</span>
        <strong class="stat-value">{{ elevatorStats.total ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">待检电梯</span>
        <strong class="stat-value">{{ elevatorStats['待检'] ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">在用电梯</span>
        <strong class="stat-value">{{ elevatorStats['在用'] ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">停用电梯</span>
        <strong class="stat-value">{{ elevatorStats['停用'] ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">临近检验</span>
        <strong class="stat-value">{{ elevatorStats['临近检验'] ?? 0 }}</strong>
      </article>
    </div>
    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
  elevator?: { total: number; 待检: number; 在用: number; 停用: number; 临近检验: number }
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const elevatorStats = ref<Overview['elevator'] | null>(null)

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
    elevatorStats.value = payload.elevator ?? null
  } catch {
    cards.value = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
    moduleRows.value = [{"name": "锅炉设备", "created": 0, "pending": 0, "abnormal": 0}, {"name": "压力容器", "created": 0, "pending": 0, "abnormal": 0}, {"name": "压力管道", "created": 0, "pending": 0, "abnormal": 0}, {"name": "起重机械", "created": 0, "pending": 0, "abnormal": 0}, {"name": "电梯设备", "created": 0, "pending": 0, "abnormal": 0}, {"name": "场内机动车辆", "created": 0, "pending": 0, "abnormal": 0}, {"name": "点检计划", "created": 0, "pending": 0, "abnormal": 0}, {"name": "点检记录", "created": 0, "pending": 0, "abnormal": 0}, {"name": "润滑保养", "created": 0, "pending": 0, "abnormal": 0}, {"name": "定期检验", "created": 0, "pending": 0, "abnormal": 0}, {"name": "检验报告", "created": 0, "pending": 0, "abnormal": 0}, {"name": "隐患登记", "created": 0, "pending": 0, "abnormal": 0}, {"name": "整改闭环", "created": 0, "pending": 0, "abnormal": 0}, {"name": "使用登记", "created": 0, "pending": 0, "abnormal": 0}, {"name": "作业人员", "created": 0, "pending": 0, "abnormal": 0}, {"name": "备件器材", "created": 0, "pending": 0, "abnormal": 0}, {"name": "维保合同", "created": 0, "pending": 0, "abnormal": 0}, {"name": "费用结算", "created": 0, "pending": 0, "abnormal": 0}]
  }
})
</script>
