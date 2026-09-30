import { defineStore } from 'pinia'

// 平台内预置的使用单位：电梯状态变更只允许归属本单位的操作人发起
export const OPERATOR_UNITS = ['华辰制药厂', '江南纺织有限公司', '临港物流园']

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '特种设备点检运维平台',
    unit: OPERATOR_UNITS[0],
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setUnit(unit: string) {
      this.unit = unit
    },
  },
})
