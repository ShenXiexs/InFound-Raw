import type { UserPermissionInfo } from './user-permission-type'

export interface AppInfo {
  name: string
  version: string
  description: string
  deviceId: string
  sessionId: number
}

export interface AppSetting {
  resourcesPath: string
  ui: {
    tabItemLeftSize: number
    splitSpace: number
  }
}

export interface CurrentUserInfo {
  userId: string
  username: string
  permission?: UserPermissionInfo
  email?: string
  phoneNumber?: string
  avatar?: string
  nickname?: string
  tokenName: string
  tokenValue: string
  startTime: number
  endTime: number
  maxShopsCount: number
  updateTime: number
  enableDebug: boolean
  inviteCode: string
}

export interface AppStoreSchema {
  appSetting: AppSetting
  currentUser?: CurrentUserInfo
  apiCookie: any
}

export interface AppState {
  appInfo: AppInfo
  appSetting: AppSetting
  isUpdating: boolean
  isLogin: boolean
  enableDebug: boolean
  currentUser?: CurrentUserInfo
}
