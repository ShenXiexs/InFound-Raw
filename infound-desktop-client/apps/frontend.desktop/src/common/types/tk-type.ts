import { WebContentsView } from 'electron'

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
  id: string
  type: 'tk' | 'xunda'
  name: string
  url: string
  icon: string
  focused: boolean
  enabled: boolean
}

export enum PageLoadStatus {
  Loading = 'Loading',
  TargetPage = 'TargetPage',
  ErrorPage = 'ErrorPage'
}

export interface TkShopTabItemView {
  targetUrl: string
  webContentsView: WebContentsView
  pageLoadStatus: PageLoadStatus
}
