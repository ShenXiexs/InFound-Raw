import { TkShopSetting } from '@common/types/tk-type'
import { TAB_TYPES } from '@common/app-constants'
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

  public getOpenShopIds(): string[] {
    return Object.keys(this.tkShopWindows).filter((id) => {
      const shopWindow = this.tkShopWindows[id]
      const baseWindow = shopWindow?.baseWindow
      return Boolean(baseWindow && !baseWindow.isDestroyed() && baseWindow.isVisible())
    })
  }

  /**
   * 在任意已打开的店铺窗口中打开 embed 标签（用于主窗口无 TkTabItemManager 时的回退）
   */
  public async openEmbedTab(buildUrl: (shopId: string) => Promise<string>): Promise<{ success: boolean; error?: string }> {
    const ids = Object.keys(this.tkShopWindows)
    if (ids.length === 0) {
      return { success: false, error: '请先打开店铺窗口' }
    }

    for (const id of ids) {
      const tkWin = this.tkShopWindows[id]
      const shopId = this.tkShopSettings[id]?.id
      if (!tkWin?.tabItemManager || !shopId) {
        continue
      }

      try {
        const url = await buildUrl(shopId)
        await tkWin.tabItemManager.openTabItem(url, TAB_TYPES.XUNDA)
        tkWin.showWindow()
        return { success: true }
      } catch (error: any) {
        logger.error(`[EmbedTab] 打开 embed 失败 shop=${id}`, error)
        return { success: false, error: error?.message || '打开页面失败' }
      }
    }

    return { success: false, error: '店铺窗口未就绪' }
  }
}
