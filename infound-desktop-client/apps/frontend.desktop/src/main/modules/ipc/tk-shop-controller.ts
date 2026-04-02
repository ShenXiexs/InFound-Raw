import { IPCGateway, IPCHandle, IPCType } from './base/ipc-decorator'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { appWindowsAndViewsManager } from '../../windows/app-windows-and-views-manager'
import { logger } from '../../utils/logger'
import type { TkShopOpenWindowPayload, TkShopSetting } from '@common/types/tk-type'
import type { AddShopPayload, DeleteShopPayload, UpdateShopPayload } from '../../services/shop-service'
import { addShopApi, deleteShopApi, getShopEntriesApi, getShopListApi, openShopApi, updateShopApi } from '../../services/shop-service'

export class TkShopController {
  @IPCHandle(IPCGateway.TK, IPC_CHANNELS.TK_SHOP_OPEN_WINDOW, IPCType.SEND)
  async openWindow(_event: any, payload: TkShopOpenWindowPayload): Promise<void> {
    const openResult = await openShopApi({ id: payload.id })
    if (openResult?.code !== 200) {
      logger.error('记录最近打开时间失败', openResult)
      return
    }
    logger.info(`打开 TK 店铺窗口: ${payload.id}`)
    const tkShopSetting = {
      id: payload.id,
      name: payload.name,
      region: payload.region,
      loginUrl: payload.loginUrl
    } as TkShopSetting
    await appWindowsAndViewsManager.tkShopWindowManager.openWindow(tkShopSetting)
  }

  @IPCHandle(IPCGateway.TK, IPC_CHANNELS.TK_SHOP_GET_TKSHOP_SETTING, IPCType.INVOKE)
  async getTkShopSetting(_event: any, windowId: number): Promise<{ success: boolean; data: TkShopSetting }> {
    const setting = appWindowsAndViewsManager.tkShopWindowManager.getTkShopSetting(windowId)
    if (setting) {
      return { success: true, data: setting }
    }
    throw new Error('未找到 TK 店铺设置')
  }

  @IPCHandle(IPCGateway.TK, IPC_CHANNELS.TK_SHOP_GET_ENTRIES, IPCType.INVOKE)
  async getShopEntries(): Promise<{ success: boolean; data?: Record<string, any>[]; error?: string }> {
    try {
      const result = await getShopEntriesApi()
      if (result?.code === 200) {
        return { success: true, data: result.data || [] }
      }
      return { success: false, error: result?.msg || '获取店铺入口信息失败' }
    } catch (error: any) {
      logger.error('获取店铺入口信息失败', error)
      return {
        success: false,
        error: error?.message || '获取店铺入口信息失败，请稍后重试'
      }
    }
  }

  @IPCHandle(IPCGateway.TK, IPC_CHANNELS.TK_SHOP_ADD, IPCType.INVOKE)
  async addShop(_event: any, payload: AddShopPayload): Promise<{ success: boolean; data?: Record<string, any>; error?: string }> {
    try {
      const result = await addShopApi(payload)
      if (result?.code === 200) {
        return { success: true, data: result.data || {} }
      }
      return { success: false, error: result?.msg || '新建店铺失败' }
    } catch (error: any) {
      logger.error('新建店铺失败', error)
      return {
        success: false,
        error: error?.message || '新建店铺失败，请稍后重试'
      }
    }
  }

  @IPCHandle(IPCGateway.TK, IPC_CHANNELS.TK_SHOP_LIST, IPCType.INVOKE)
  async getShopList(): Promise<{ success: boolean; data?: Record<string, any>[]; error?: string }> {
    try {
      const result = await getShopListApi()
      if (result?.code === 200) {
        return { success: true, data: result.data || [] }
      }
      return { success: false, error: result?.msg || '获取店铺列表失败' }
    } catch (error: any) {
      logger.error('获取店铺列表失败', error)
      return {
        success: false,
        error: error?.message || '获取店铺列表失败，请稍后重试'
      }
    }
  }

  @IPCHandle(IPCGateway.TK, IPC_CHANNELS.TK_SHOP_UPDATE, IPCType.INVOKE)
  async updateShop(_event: any, payload: UpdateShopPayload): Promise<{ success: boolean; data?: Record<string, any>; error?: string }> {
    try {
      const result = await updateShopApi(payload)
      if (result?.code === 200) {
        return { success: true, data: result.data || {} }
      }
      return { success: false, error: result?.msg || '修改店铺信息失败' }
    } catch (error: any) {
      logger.error('修改店铺信息失败', error)
      return {
        success: false,
        error: error?.message || '修改店铺信息失败，请稍后重试'
      }
    }
  }

  @IPCHandle(IPCGateway.TK, IPC_CHANNELS.TK_SHOP_DELETE, IPCType.INVOKE)
  async deleteShop(_event: any, payload: DeleteShopPayload): Promise<{ success: boolean; data?: Record<string, any>; error?: string }> {
    try {
      const result = await deleteShopApi(payload)
      if (result?.code === 200) {
        return { success: true, data: result.data || {} }
      }
      return { success: false, error: result?.msg || '删除店铺失败' }
    } catch (error: any) {
      logger.error('删除店铺失败', error)
      return {
        success: false,
        error: error?.message || '删除店铺失败，请稍后重试'
      }
    }
  }
}
