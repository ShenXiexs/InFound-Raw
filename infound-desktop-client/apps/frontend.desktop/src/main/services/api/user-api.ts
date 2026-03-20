import openapiRequest from '../base/open-api-service'
import { BaseApiResponse } from '../../utils/net-request'
import { API_ENDPOINTS } from './endpoints'
import { UserInfoResponse } from '../dtos/user-info'

export async function getCurrentUserApi(): Promise<BaseApiResponse<UserInfoResponse>> {
  return await openapiRequest.get<BaseApiResponse<UserInfoResponse>>(API_ENDPOINTS.user.current)
}

export async function checkTokenApi(): Promise<BaseApiResponse<Record<string, any>>> {
  return await openapiRequest.get<BaseApiResponse<Record<string, any>>>(API_ENDPOINTS.user.checkToken)
}
