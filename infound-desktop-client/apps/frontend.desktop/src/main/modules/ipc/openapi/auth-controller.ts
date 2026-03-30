import { CurrentUserInfo } from '@infound/desktop-base'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { IPCGateway, IPCHandle, IPCType } from '../base/ipc-decorator'
import { checkTokenAsync, getCurrentUserAsync, loginAsync } from '../../../services/user-service'
import { logger } from '../../../utils/logger'
import { globalState } from '../../state/global-state'
import { appStore } from '../../store/app-store'
import { CookieMap, parseSetCookie } from '../../../utils/set-cookie-parser'

const TOKEN_NAME_COOKIE = 'xunda_token_name'
const TOKEN_VALUE_COOKIE = 'xunda_token_value'
const AUTH_ERROR_TEXT: Record<string, string> = {
  'error.loginPause': '账号已停用',
  'error.loginExpired': '账号已过期',
  'error.loginNotExist': '账号不存在或密码错误',
  'error.loginErrorPassword': '账号或密码错误'
}

const readTokenFromApiCookie = (): { tokenName: string; tokenValue: string } => {
  const apiCookie = appStore.get<string | string[] | undefined>('apiCookie')
  if (!apiCookie) {
    return { tokenName: TOKEN_NAME_COOKIE, tokenValue: '' }
  }

  const cookieMap: CookieMap = parseSetCookie(apiCookie, { map: true })
  return {
    tokenName: cookieMap[TOKEN_NAME_COOKIE]?.value || TOKEN_NAME_COOKIE,
    tokenValue: cookieMap[TOKEN_VALUE_COOKIE]?.value || ''
  }
}

export class AuthController {
  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.API_AUTH_LOGIN, IPCType.INVOKE)
  async login(_event: any, mobile: string, password: string): Promise<{ success: boolean; error?: string }> {
    try {
      const loginResult = await loginAsync(mobile, password)
      const cookieToken = readTokenFromApiCookie()
      const token = {
        tokenName: cookieToken.tokenName,
        tokenValue: cookieToken.tokenValue
      }

      if (!token.tokenValue) {
        token.tokenName = loginResult.tokenName
        token.tokenValue = loginResult.tokenValue
      }

      if (!token.tokenValue) {
        return { success: false, error: '登录失败，未获取到登录令牌' }
      }

      const userInfoResult = await getCurrentUserAsync()
      if (userInfoResult?.code !== 200 || !userInfoResult?.data) {
        return { success: false, error: userInfoResult?.msg || '登录成功但获取用户信息失败' }
      }

      const serverUser = userInfoResult.data
      if (!serverUser.userId?.trim() || !serverUser.username?.trim()) {
        return { success: false, error: '登录成功但用户信息不完整' }
      }

      const enableDebug = Boolean(serverUser.permission?.enableDebug ?? serverUser.enableDebug)
      const currentUser: CurrentUserInfo = {
        ...serverUser,
        userId: serverUser.userId,
        username: serverUser.username,
        tokenName: token.tokenName,
        tokenValue: token.tokenValue,
        enableDebug: enableDebug
      } as CurrentUserInfo

      await globalState.saveState('currentUser', currentUser)
      await globalState.saveState('currentUser.tokenValue', currentUser.tokenValue)
      await globalState.saveState('isLogin', true)
      await globalState.saveState('enableDebug', enableDebug)

      return { success: true }
    } catch (error: any) {
      logger.error('登录失败', error)
      const rawMessage = error?.originalError?.message || error?.message
      const message = AUTH_ERROR_TEXT[rawMessage] || rawMessage
      return {
        success: false,
        error: message || '登录失败，请稍后重试'
      }
    }
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.API_AUTH_LOGOUT, IPCType.INVOKE)
  async logout(): Promise<{ success: boolean; error?: string }> {
    try {
      await globalState.saveState('currentUser.tokenValue', '')
      await globalState.saveState('currentUser', null)
      await globalState.saveState('isLogin', false)
      await globalState.saveState('enableDebug', false)
      appStore.set('apiCookie', null)
      return { success: true }
    } catch (error: any) {
      logger.error('退出登录失败', error)
      return {
        success: false,
        error: error?.message || '退出登录失败，请稍后重试'
      }
    }
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.API_AUTH_GET_CURRENT_USER, IPCType.INVOKE)
  async getCurrentUser(): Promise<{ success: boolean; data?: Record<string, any>; error?: string }> {
    try {
      const result = await getCurrentUserAsync()
      if (result?.code === 200) {
        return { success: true, data: result.data || {} }
      }
      return { success: false, error: result?.msg || '获取用户信息失败' }
    } catch (error: any) {
      logger.error('获取用户信息失败', error)
      return {
        success: false,
        error: error?.message || '获取用户信息失败，请稍后重试'
      }
    }
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.API_AUTH_CHECK_TOKEN, IPCType.INVOKE)
  async checkToken(): Promise<{ success: boolean; code?: number; data?: Record<string, any>; error?: string }> {
    try {
      const result = await checkTokenAsync()
      if (result?.code === 200) {
        return { success: true, code: result.code, data: result.data || {} }
      }
      return { success: false, code: result?.code, error: result?.msg || '校验 token 失败' }
    } catch (error: any) {
      logger.error('校验 token 失败', error)
      return {
        success: false,
        code: error?.code,
        error: error?.message || '校验 token 失败，请稍后重试'
      }
    }
  }
}
