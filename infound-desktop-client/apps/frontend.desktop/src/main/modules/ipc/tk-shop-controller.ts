import { IPCGateway, IPCHandle, IPCType } from './base/ipc-decorator'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { appWindowsAndViewsManager } from '../../windows/app-windows-and-views-manager'
import { logger } from '../../utils/logger'
import { TkShopSetting } from '@common/types/tk-type'

export class TkShopController {
  @IPCHandle(IPCGateway.TK, IPC_CHANNELS.TK_SHOP_OPEN_WINDOW, IPCType.SEND)
  async openWindow(_event: any, settingId: string): Promise<void> {
    logger.info(`打开 TK 店铺窗口: ${settingId}`)
    const tkShopSetting = {
      id: settingId,
      name: 'TK 店铺 A',
      region: 'mx',
      loginUrl: 'https://seller-mx.tiktok.com/'
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
}
