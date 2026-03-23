export interface Tab {
  id: string
  url: string
  type: string
  title: string
  favicon?: string //空或null不显示图标
  hideAddress?: boolean
  lastAccessed: number // 最后一次激活的时间戳，lastAccessed和createdAt两个属性给后续最大tab页管理备用
  createdAt: number // 创建时间戳
}
