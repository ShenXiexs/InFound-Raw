import { request } from './http'

export interface CurrentUserPayload {
  userId?: string
  username?: string
  phoneNumber?: string
  userType?: string
  permission?: {
    availableDateRang?: {
      startDate?: string
      endDate?: string
    }
    availabeDateRang?: {
      startDate?: string
      endDate?: string
    }
    maxShopCount?: number
    maxOutreachCountPerDay?: number
    maxRemindCreatorCountPerDay?: number
    enableExportCreatorData?: boolean
  }
}

interface UserCurrentResponse {
  code?: number | string
  msg?: string
  data?: CurrentUserPayload | { data?: CurrentUserPayload }
}

export interface ChangePasswordPayload {
  oldPassword: string
  newPassword: string
  confirmPassword: string
}

const isSuccessCode = (code: unknown): boolean => {
  return code === 0 || code === '0' || code === 200 || code === '200'
}

const normalizeCurrentUserPayload = (payload: UserCurrentResponse['data']): CurrentUserPayload | null => {
  if (!payload || typeof payload !== 'object') return null
  if ('username' in payload || 'phoneNumber' in payload || 'permission' in payload) {
    return payload as CurrentUserPayload
  }
  if ('data' in payload && payload.data && typeof payload.data === 'object') {
    return payload.data as CurrentUserPayload
  }
  return null
}

/**
 * 拉取当前登录用户信息（需 embed 已携带鉴权）
 */
export async function fetchCurrentUser(): Promise<CurrentUserPayload | null> {
  try {
    const res = await request<UserCurrentResponse>({
      method: 'get',
      url: '/user/current'
    })
    if (isSuccessCode(res?.code)) {
      return normalizeCurrentUserPayload(res?.data)
    }
  } catch {
    // 浏览器独立打开或未登录时可能失败，由页面展示占位
  }
  return null
}

export async function changePassword(payload: ChangePasswordPayload): Promise<void> {
  await request<void>({
    method: 'post',
    url: '/account/change-password',
    data: payload
  })
}
