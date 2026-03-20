export interface UserInfoResponse {
  userId: string
  username: string
  nickname?: string
  avatar?: string
  email?: string
  phoneNumber?: string
  enableDebug?: boolean
  permission: PermissionSetting
  updateTime?: number
  inviteCode?: string
  menuItemCount?: number
}

export interface PermissionSetting {
  availableCount?: number
  availableStartDate?: string
  availableEndDate?: string
  enableDebug: boolean
  startTime?: string
  endTime?: string
  maxTabs?: number
}
