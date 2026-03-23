import { IPC_CHANNELS } from '@common/types/ipc-type'
import { IPCGateway, IPCHandle, IPCType } from './base/ipc-decorator'
import { TkShopTabItemSetting } from '@common/types/tk-type'
import WebContents = Electron.WebContents

export class MonitorController {
  private static instance: MonitorController

  // 1. 私有化构造函数，防止外部 new
  private constructor() {
    // 初始化逻辑
  }

  // 2. 提供获取单例的静态方法
  public static getInstance(): MonitorController {
    if (!MonitorController.instance) {
      MonitorController.instance = new MonitorController()
    }
    return MonitorController.instance
  }

  @IPCHandle(IPCGateway.MONITOR, IPC_CHANNELS.RENDERER_MONITOR_APP_GLOBAL_STATE_SYNC, IPCType.ON)
  syncAppGlobalState(_webContents: WebContents, _payload: { path: string; value: any }): void {
    // 这个方法在 register 之后会被自动替换为 webContents.send 逻辑
  }

  @IPCHandle(IPCGateway.MONITOR, IPC_CHANNELS.RENDERER_MONITOR_APP_SPLASH_WINDOW_STATE_SYNC, IPCType.ON)
  syncAppSplashWindowState(_webContents: WebContents, _payload: { percent: number; status: string }): void {
    // 这个方法在 register 之后会被自动替换为 webContents.send 逻辑
  }

  @IPCHandle(IPCGateway.MONITOR, IPC_CHANNELS.RENDERER_MONITOR_TK_SHOP_ALL_TAB_ITEM_SETTINGS_SYNC, IPCType.ON)
  syncTkShopAllTabItemSettings(_webContents: WebContents, _payload: Record<string, TkShopTabItemSetting>): void {
    // 这个方法在 register 之后会被自动替换为 webContents.send 逻辑
  }

  @IPCHandle(IPCGateway.MONITOR, IPC_CHANNELS.RENDERER_MONITOR_TABS_UPDATED, IPCType.ON)
  syncTabsUpdated(_webContents: WebContents, _payload: { activeId: string; tabs: any[] }): void {
    // 这个方法在 register 之后会被自动替换为 webContents.send 逻辑
  }

  @IPCHandle(IPCGateway.MONITOR, IPC_CHANNELS.RENDERER_MONITOR_TABS_NAVIGATION_STATE, IPCType.ON)
  syncTabsNavigationState(_webContents: WebContents, _payload: { canGoBack: boolean; canGoForward: boolean }): void {
    // 这个方法在 register 之后会被自动替换为 webContents.send 逻辑
  }
}
