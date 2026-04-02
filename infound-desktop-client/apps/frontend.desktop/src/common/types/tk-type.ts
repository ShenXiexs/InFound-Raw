export interface TkShopSetting {
  id: string
  name: string
  region: string
  loginUrl: string
  windowId: number
  osWinAppId: string
  loginHeaders: string
  tabItems: TkShopTabItemSetting[]
}

export interface TkShopTabItemSetting {
  id: string //todo:这个需要持久化吗？我觉得也不用吧...待定
  type: string //TAB_TYPES.XUNDA or TAB_TYPES.TIKTOK
  url: string
  focused: boolean
  enabled: boolean
}

export enum PageLoadStatus {
  Loading = 'Loading',
  TargetPage = 'TargetPage',
  ErrorPage = 'ErrorPage'
}

export interface TkShopOpenWindowPayload {
  id: string
  name: string
  region: string
  loginUrl: string
}
