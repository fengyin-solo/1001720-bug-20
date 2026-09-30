import { defineStore } from 'pinia'

// 平台登记的使用单位：只有归属本单位的账号能改自己名下电梯的状态。
export const USE_UNITS = ['江北分公司', '江南分公司']

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '特种设备点检运维平台',
    useUnit: USE_UNITS[0],
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setUseUnit(unit: string) {
      this.useUnit = unit
    },
  },
})
