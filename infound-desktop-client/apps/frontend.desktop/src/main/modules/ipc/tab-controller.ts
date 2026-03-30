import { IPCGateway, IPCHandle, IPCType } from './base/ipc-decorator'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { BrowserWindow } from 'electron'
import { logger } from '../../utils/logger'
import { TabManager } from '../../windows/tab-manager'
import { TkTabItemManager } from '../../windows/tk-tab-item-manager'

export class TabController {
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
}
