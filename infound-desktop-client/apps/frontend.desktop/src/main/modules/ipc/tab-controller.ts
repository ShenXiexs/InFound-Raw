import { IPCGateway, IPCHandle, IPCType } from './base/ipc-decorator'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { BrowserWindow, ipcMain } from 'electron'
import { logger } from '../../utils/logger'
import { TabManager } from '../../windows/tab-manager'
import { TkTabItemManager } from '../../windows/tk-tab-item-manager'

export class TabController {
  constructor() {
    // 处理菜单窗口的切换标签请求
    ipcMain.handle('tabs-menu-switch-tab', async (event, tabId: string) => {
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
    })
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

  @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_SHOW_ITEMS_MENU, IPCType.INVOKE)
  async showTabsMenu(event: Electron.IpcMainInvokeEvent, x: number, y: number): Promise<void> {
    const win = BrowserWindow.fromWebContents(event.sender)
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
    }
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

  //=================================todo:请@Thomas查看为什么这三个用IPC装饰器方法不起作用.......目前只能用原生的写在构造函数里了====================
  // 菜单窗口切换标签
  // @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_MENU_SWITCH_TAB, IPCType.INVOKE)
  // async menuSwitchTab(event: Electron.IpcMainInvokeEvent, tabId: string): Promise<void> {
  //   console.log('收到切换tab页命令' + tabId)
  //   const win = BrowserWindow.fromWebContents(event.sender)
  //   if (!win) return
  //   const tabManager = (win as any).tabManager as TabManager | undefined
  //   if (tabManager) {
  //     console.log('即将切换tab页' + tabId)
  //     tabManager.activateTab(tabId)
  //     tabManager.closeMenuWindow()
  //   }
  // }
  //
  // // 菜单窗口关闭标签
  // @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_MENU_CLOSE_TAB, IPCType.INVOKE)
  // async menuCloseTab(event: Electron.IpcMainInvokeEvent, tabId: string): Promise<void> {
  //   console.log('收到关闭tab页命令' + tabId)
  //   const win = BrowserWindow.fromWebContents(event.sender)
  //   if (!win) return
  //   const tabManager = (win as any).tabManager as TabManager | undefined
  //   if (tabManager) {
  //     tabManager.closeTab(tabId)
  //     tabManager.refreshMenuWindow()
  //   }
  // }
  //
  // // 菜单窗口拖拽排序
  // @IPCHandle(IPCGateway.TAB, IPC_CHANNELS.TABS_REORDER_FROM_MENU, IPCType.INVOKE)
  // async menuReorderTabs(event: Electron.IpcMainInvokeEvent, orderedIds: string[]): Promise<void> {
  //   const win = BrowserWindow.fromWebContents(event.sender)
  //   if (!win) return
  //   const tabManager = (win as any).tabManager as TabManager | undefined
  //   if (tabManager) {
  //     tabManager.reorderTabs(orderedIds)
  //     tabManager.refreshMenuWindow()
  //   }
  // }
}
