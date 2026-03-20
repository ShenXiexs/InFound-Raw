import openapiRequest from '../base/open-api-service'
import { BaseApiResponse } from '../../utils/net-request'
import { API_ENDPOINTS } from './endpoints'

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginTokenResponse {
  success?: boolean
  jti?: string
  header?: string
  token?: string
}

export async function loginByPassword(payload: LoginRequest): Promise<BaseApiResponse<LoginTokenResponse>> {
  return await openapiRequest.post<BaseApiResponse<LoginTokenResponse>>(API_ENDPOINTS.auth.login, payload)
}

