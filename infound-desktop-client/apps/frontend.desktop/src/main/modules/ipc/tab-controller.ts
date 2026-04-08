import { IPCHandle } from './base/ipc-decorator'
import { IPC_CHANNELS, IPCGateway, IPCType } from '@common/types/ipc-type'
import { TAB_TYPES } from '@common/app-constants'
import { BrowserWindow } from 'electron'
import { logger } from '../../utils/logger'
import { TabManager } from '../../windows/tab-manager'
import { TkTabItemManager } from '../../windows/tk-tab-item-manager'
import { buildEmbedPageUrl } from '../../services/embed-page-url'
import { appWindowsAndViewsManager } from '../../windows/app-windows-and-views-manager'

export class TabController {
  constructor() {
    // 处理菜单窗口的切换标签请求
    /*ipcMain.handle('tabs-menu-switch-tab', async (event, tabId: string) => {
      console.log('收到菜单切换标签请求:', tabId)
      const win = BrowserWindow.fromWebContents(event.sender)
      if (!win) return
      const tabManager = (win as any).tabManager as TabManager
      if (tabManager) {
        tabManager.activateTab(tabId)
        tabManager.closeMenuWindow()
      }
    })

    // 处理菜单窗口的关闭标签请求
    ipcMain.handle('tabs-menu-close-tab', async (event, tabId: string) => {
      console.log('收到菜单关闭标签请求:', tabId)
      const win = BrowserWindow.fromWebContents(event.sender)
      if (!win) return
      const tabManager = (win as any).tabManager as TabManager
      if (tabManager) {
        tabManager.closeTab(tabId)
        tabManager.refreshMenuWindow()
      }
    })

    // 处理菜单窗口的拖拽排序请求
    ipcMain.handle('tabs-reorder-from-menu', async (event, orderedIds: string[]) => {
      console.log('收到菜单拖拽排序请求:', orderedIds)
      const win = BrowserWindow.fromWebContents(event.sender)
      if (!win) return
      const tabManager = (win as any).tabManager as TabManager
      if (tabManager) {
        tabManager.reorderTabs(orderedIds)
        tabManager.refreshMenuWindow()
      }
    })*/
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_ACTIVATE_ITEM, IPCType.INVOKE)
  async activateTab(event: Electron.IpcMainInvokeEvent, id: string): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) {
      logger.error('未找到对应的窗口')
      return
    }
    const tabManager = (win as any).tabManager as TabManager | undefined
    if (tabManager) {
      tabManager.activateTab(id)
    } else {
      logger.error('窗口未关联 TabManager')
    }
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_CLOSE_ITEM, IPCType.INVOKE)
  async closeTab(event: Electron.IpcMainInvokeEvent, id: string): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    const tkManager = (win as any).tkTabItemManager as TkTabItemManager
    if (tkManager) {
      tkManager.closeTabItem(id)
    } else {
      console.error('No TkTabItemManager found for window')
    }
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_NAVIGATE_BACK, IPCType.INVOKE)
  async goBack(event: Electron.IpcMainInvokeEvent): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    const tabManager = (win as any).tabManager as TabManager | undefined
    if (tabManager) {
      tabManager.goBack()
    }
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_NAVIGATE_FORWARD, IPCType.INVOKE)
  async goForward(event: Electron.IpcMainInvokeEvent): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    const tabManager = (win as any).tabManager as TabManager | undefined
    if (tabManager) {
      tabManager.goForward()
    }
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_NAVIGATE_RELOAD, IPCType.INVOKE)
  async reload(event: Electron.IpcMainInvokeEvent): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    const tabManager = (win as any).tabManager as TabManager | undefined
    if (tabManager) {
      tabManager.reload()
    }
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_OPEN_OUTREACH, IPCType.INVOKE)
  async openOutreachTab(event: Electron.IpcMainInvokeEvent): Promise<{ success: boolean; error?: string }> {
    try {
      const win = BrowserWindow.fromWebContents(event.sender)
      if (!win) {
        return { success: false, error: '未找到窗口' }
      }

      const tkManager = (win as any).tkTabItemManager as TkTabItemManager | undefined
      if (!tkManager) {
        logger.error('窗口未关联 TkTabItemManager')
        return { success: false, error: '窗口未关联 TkTabItemManager' }
      }

      const tabId = await tkManager.openTabItem(await buildEmbedPageUrl('/outreach', tkManager.getShopId()), TAB_TYPES.XUNDA)
      if (!tabId) {
        return { success: false, error: '创建标签页失败' }
      }

      return { success: true }
    } catch (error: any) {
      logger.error('[EmbedTab] 打开建联页失败', error)
      return { success: false, error: error?.message || '打开建联页失败' }
    }
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_OPEN_FULFILLMENT, IPCType.INVOKE)
  async openFulfillmentTab(event: Electron.IpcMainInvokeEvent): Promise<{ success: boolean; error?: string }> {
    try {
      const win = BrowserWindow.fromWebContents(event.sender)
      if (!win) {
        return { success: false, error: '未找到窗口' }
      }

      const tkManager = (win as any).tkTabItemManager as TkTabItemManager | undefined
      if (!tkManager) {
        logger.error('窗口未关联 TkTabItemManager')
        return { success: false, error: '窗口未关联 TkTabItemManager' }
      }

      const tabId = await tkManager.openTabItem(await buildEmbedPageUrl('/fulfillment', tkManager.getShopId()), TAB_TYPES.XUNDA)
      if (!tabId) {
        return { success: false, error: '创建标签页失败' }
      }

      return { success: true }
    } catch (error: any) {
      logger.error('[EmbedTab] 打开履约页失败', error)
      return { success: false, error: error?.message || '打开履约页失败' }
    }
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_OPEN_EMBED, IPCType.INVOKE)
  async openEmbedTab(
    event: Electron.IpcMainInvokeEvent,
    hashPath: string
  ): Promise<{ success: boolean; error?: string }> {
    const raw = typeof hashPath === 'string' ? hashPath.trim() : ''
    const normalized = raw.startsWith('/') ? raw : `/${raw || 'outreach'}`

    try {
      const win = BrowserWindow.fromWebContents(event.sender)
      if (!win) {
        return { success: false, error: '未找到窗口' }
      }

      const tkManager = (win as any).tkTabItemManager as TkTabItemManager | undefined
      if (tkManager) {
        const tabId = await tkManager.openTabItem(await buildEmbedPageUrl(normalized, tkManager.getShopId()), TAB_TYPES.XUNDA)
        if (!tabId) {
          return { success: false, error: '创建标签页失败' }
        }
        return { success: true }
      }

      return await appWindowsAndViewsManager.tkShopWindowManager.openEmbedTab(async (shopId) => {
        return await buildEmbedPageUrl(normalized, shopId)
      })
    } catch (error: any) {
      logger.error('[EmbedTab] 打开 embed 页失败', error)
      return { success: false, error: error?.message || '打开页面失败' }
    }
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_SHOW_ITEMS_MENU, IPCType.INVOKE)
  async showTabsMenu(_event: Electron.IpcMainInvokeEvent, _x: number, _y: number): Promise<void> {
    /*const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) {
      logger.error('未找到窗口')
      return
    }
    logger.debug(`找到窗口 ID=${win.id}`)
    const tabManager = (win as any).tabManager as TabManager | undefined
    if (tabManager && typeof tabManager.showTabsMenu === 'function') {
      logger.debug('调用 tabManager.showTabsMenu')
      tabManager.showTabsMenu(x, y)
    } else {
      logger.error('TabManager 未实现 showTabsMenu 方法')
    }*/
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_REORDER_ITEMS, IPCType.INVOKE)
  async reorderTabs(event: Electron.IpcMainInvokeEvent, orderedIds: string[]): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    const tabManager = (win as any).tabManager as TabManager
    if (tabManager) {
      tabManager.reorderTabs(orderedIds)
    }
  }

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_CREATE_TAB_MENU, IPCType.INVOKE)
  async createTabMenu(event: Electron.IpcMainInvokeEvent, x: number, y: number): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) {
      logger.error('未找到窗口')
      return
    }
    const tabManager = (win as any).tabManager as TabManager | undefined
    if (tabManager) {
      tabManager.showMenuWindow(x, y)
    } else {
      logger.error('窗口未关联 TabManager')
    }
  }

  // 菜单窗口切换标签
  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_MENU_SWITCH_TAB, IPCType.INVOKE)
  async menuSwitchTab(event: Electron.IpcMainInvokeEvent, tabId: string): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    const tabManager = (win as any).tabManager as TabManager | undefined
    if (tabManager) {
      tabManager.activateTab(tabId)
      tabManager.closeMenuWindow()
    }
  }

  // 菜单窗口关闭标签
  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_MENU_CLOSE_TAB, IPCType.INVOKE)
  async menuCloseTab(event: Electron.IpcMainInvokeEvent, tabId: string): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    const tabManager = (win as any).tabManager as TabManager | undefined
    if (tabManager) {
      tabManager.closeTab(tabId)
      tabManager.refreshMenuWindow()
    }
  }

  // 菜单窗口拖拽排序
  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_REORDER_FROM_MENU, IPCType.INVOKE)
  async menuReorderTabs(event: Electron.IpcMainInvokeEvent, orderedIds: string[]): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    const tabManager = (win as any).tabManager as TabManager | undefined
    if (tabManager) {
      tabManager.reorderTabs(orderedIds)
      tabManager.refreshMenuWindow()
    }
  }

}
