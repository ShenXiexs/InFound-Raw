import { IPC_CHANNELS, IPCGateway, IPCType } from '@common/types/ipc-type'
import { IPCHandle } from './base/ipc-decorator'
import { BrowserWindow, shell } from 'electron'
import { embedModalWindowManager } from '../../windows/embed-modal-window'

export class AppController {
  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_MINIMIZED, IPCType.SEND)
  async onMinimized(_event: any, windowId: number): Promise<void> {
    const win = BrowserWindow.fromId(windowId)
    win?.minimize()
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_MAXIMIZED, IPCType.INVOKE)
  async onMaximized(_event: any, windowId: number): Promise<{ success: boolean; isMaximized: boolean; error?: string }> {
    const win = BrowserWindow.fromId(windowId)
    if (!win) return { success: false, isMaximized: false }

    if (win.isMaximized()) {
      win.unmaximize()
      return { success: true, isMaximized: false }
    } else {
      win.maximize()
      return { success: true, isMaximized: true }
    }
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_CLOSED, IPCType.SEND)
  async onClosed(_event: any, windowId: number): Promise<void> {
    const win = BrowserWindow.fromId(windowId)
    win?.close()
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_OPEN_WINDOW_DEV_TOOLS, IPCType.SEND)
  async onOpenWindowDevTools(_event: any, windowId: number, mode: 'left' | 'right' | 'bottom' | 'undocked' | 'detach'): Promise<void> {
    const win = BrowserWindow.fromId(windowId)
    win?.webContents.openDevTools({ mode: mode })
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_OPEN_SUB_WINDOW_DEV_TOOLS, IPCType.SEND)
  async onOpenSubWindowDevTools(_event: any, _windowId: number, _mode: 'left' | 'right' | 'bottom' | 'undocked' | 'detach'): Promise<void> {
    throw new Error('Method not implemented.')
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_OPEN_EXTERNAL_LINK, IPCType.SEND)
  async onOpenExternalLink(_event: any, url: string): Promise<void> {
    if (!url?.trim()) return
    await shell.openExternal(url)
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_OPEN_EMBED_MODAL, IPCType.INVOKE)
  async openEmbedModal(
    event: Electron.IpcMainInvokeEvent,
    hashPath: string
  ): Promise<{ success: boolean; error?: string }> {
    const parent = BrowserWindow.fromWebContents(event.sender)
    if (!parent || parent.isDestroyed()) {
      return { success: false, error: '未找到父窗口' }
    }
    return await embedModalWindowManager.open(parent, hashPath)
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_CLOSE_EMBED_MODAL, IPCType.INVOKE)
  async closeEmbedModal(event: Electron.IpcMainInvokeEvent): Promise<{ success: boolean }> {
    embedModalWindowManager.closeFromWebContents(event.sender)
    return { success: true }
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_GET_WINDOW_ID, IPCType.INVOKE)
  async getWindowId(event: any): Promise<number> {
    const win = BrowserWindow.fromWebContents(event.sender)
    return win ? win.id : -1
  }
}
