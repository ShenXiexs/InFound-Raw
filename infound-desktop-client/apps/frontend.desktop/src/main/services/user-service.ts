import { AuthenticationException } from '../modules/exception/exception-types'
import { LoginTokenResponse, loginByPassword } from './api/auth-api'
import { BaseApiResponse } from '../utils/net-request'
import { checkTokenApi, getCurrentUserApi } from './api/user-api'
import { UserInfoResponse } from './dtos/user-info'

export interface LoginResult {
  loginId: string
  tokenName: string
  tokenValue: string
}

const isLoginSuccess = (result: any): boolean => {
  if (result?.code !== 200) return false
  if (typeof result?.data?.success === 'boolean') {
    return result.data.success
  }
  return true
}

const mapLoginError = (result: any): never => {
  const message = result?.msg || result?.message || '登录失败'
  const originalError = new Error(message)
  switch (result?.code) {
    case 2008: {
      throw new AuthenticationException(originalError, 'error.loginPause')
    }
    case 2103: {
      throw new AuthenticationException(originalError, 'error.loginExpired')
    }
    case 2003: {
      throw new AuthenticationException(originalError, 'error.loginNotExist')
    }
    case 2004: {
      throw new AuthenticationException(originalError, 'error.loginErrorPassword')
    }
    default: {
      throw new AuthenticationException(originalError, 'error.loginNotExist')
    }
  }
}

export async function loginAsync(mobile: string, password: string): Promise<LoginResult> {
  const normalizedMobile = mobile.trim()
  const normalizedPassword = password.trim()
  const loginPayload = {
    username: normalizedMobile,
    password: normalizedPassword
  }

  const result = await loginByPassword(loginPayload)

  if (isLoginSuccess(result)) {
    const loginData = (result.data || {}) as LoginTokenResponse
    const loginId = loginData.jti?.trim() || ''
    const tokenName = loginData.header?.trim() || 'Authorization'
    const tokenValue = loginData.token?.trim() || ''

    return {
      loginId,
      tokenName,
      tokenValue
    }
  }

  return mapLoginError(result)
}

export async function getCurrentUserAsync(): Promise<BaseApiResponse<UserInfoResponse>> {
  return await getCurrentUserApi()
}

export async function checkTokenAsync(): Promise<BaseApiResponse<Record<string, any>>> {
  return await checkTokenApi()
}
