import { TkShopSetting } from '@common/types/tk-type'
import { TkShopWindow } from './tk-shop-window'
import { logger } from '../utils/logger'

export class TkShopWindowManager {
  private tkWindowSettingMaps: Record<number, string> = {}
  private tkShopWindows: Record<string, TkShopWindow> = {}
  private tkShopSettings: Record<string, TkShopSetting> = {}

  public async openWindow(tkShopSetting: TkShopSetting): Promise<void> {
    const { id } = tkShopSetting

    // 1. 防止重复创建
    if (this.tkShopWindows[id]) {
      this.tkShopWindows[id].showWindow()
      return
    }

    try {
      const tkWindow = new TkShopWindow()
      await tkWindow.initWindow(tkShopSetting)
      tkWindow.showWindow()

      this.tkShopWindows[id] = tkWindow
      this.tkShopSettings[id] = tkShopSetting
      this.tkWindowSettingMaps[tkShopSetting.windowId] = id
    } catch (error) {
      logger.error(`初始化窗口失败: ${id}`, error)
      throw error // 向上抛出以便 UI 处理
    }
  }

  public getTkShopSetting(windowId: number): TkShopSetting | null {
    const tkShopSettingId = this.tkWindowSettingMaps[windowId]
    if (!tkShopSettingId) {
      return null
    }
    return this.tkShopSettings[tkShopSettingId]
  }
}
