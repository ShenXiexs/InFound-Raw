import { BaseApiResponse } from '../utils/net-request'
import openapiRequest from './base/open-api-service'
import { API_ENDPOINTS } from './endpoints'

export type ShopTypeCode = 'LOCAL' | 'CROSS_BORDER'

export interface ShopEntryInfo {
  entryId?: number
  regionCode: string
  regionName: string
  shopType: ShopTypeCode
  loginUrl: string
}

export interface ShopListInfo {
  id: string
  name: string
  entryId?: number
  remark?: string
  shopLastOpen?: string
  regionCode: string
  regionName: string
  shopType: ShopTypeCode
  loginUrl: string
}

export interface AddShopPayload {
  name: string
  entryId: number
  remark?: string
}

export interface UpdateShopPayload {
  id: string
  name: string
  entryId: number
  remark?: string
}

export interface DeleteShopPayload {
  id: string
}

export interface OpenShopPayload {
  id: string
}

export async function getShopEntriesApi(): Promise<BaseApiResponse<ShopEntryInfo[]>> {
  return await openapiRequest.get<BaseApiResponse<ShopEntryInfo[]>>(API_ENDPOINTS.tkShop.entries)
}

export async function addShopApi(payload: AddShopPayload): Promise<BaseApiResponse<Record<string, any>>> {
  return await openapiRequest.post<BaseApiResponse<Record<string, any>>>(API_ENDPOINTS.tkShop.add, payload)
}

export async function getShopListApi(): Promise<BaseApiResponse<ShopListInfo[]>> {
  return await openapiRequest.get<BaseApiResponse<ShopListInfo[]>>(API_ENDPOINTS.tkShop.list)
}

export async function updateShopApi(payload: UpdateShopPayload): Promise<BaseApiResponse<Record<string, any>>> {
  return await openapiRequest.put<BaseApiResponse<Record<string, any>>>(API_ENDPOINTS.tkShop.update, payload)
}

export async function deleteShopApi(payload: DeleteShopPayload): Promise<BaseApiResponse<Record<string, any>>> {
  return await openapiRequest.post<BaseApiResponse<Record<string, any>>>(API_ENDPOINTS.tkShop.delete, payload)
}

export async function openShopApi(payload: OpenShopPayload): Promise<BaseApiResponse<Record<string, any>>> {
  return await openapiRequest.post<BaseApiResponse<Record<string, any>>>(API_ENDPOINTS.tkShop.open, payload)
}
