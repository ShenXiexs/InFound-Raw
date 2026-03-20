import { IPC_CHANNELS } from '@common/types/ipc-type'
import { IPCHandle, IPCType } from './base/ipc-decorator'
import { appWindowsAndViewsManager } from '../../windows/app-windows-and-views-manager'

export class AppController {
  @IPCHandle(IPC_CHANNELS.APP_MINIMIZED, IPCType.SEND)
  async onMinimized(_event: any): Promise<void> {
    appWindowsAndViewsManager.mainWindow.baseWindow?.minimize()
  }

  @IPCHandle(IPC_CHANNELS.APP_MAXIMIZED, IPCType.INVOKE)
  async onMaximized(_event: any): Promise<{ success: boolean; isMaximized: boolean; error?: string }> {
    const win = appWindowsAndViewsManager.mainWindow.baseWindow!
    if (!win) return { success: false, isMaximized: false }

    if (win.isMaximized()) {
      win.unmaximize()
      return { success: true, isMaximized: false }
    } else {
      win.maximize()
      return { success: true, isMaximized: true }
    }
  }

  @IPCHandle(IPC_CHANNELS.APP_CLOSED, IPCType.SEND)
  async onClosed(_event: any): Promise<void> {
    appWindowsAndViewsManager.mainWindow.baseWindow?.close()
  }

  @IPCHandle(IPC_CHANNELS.APP_OPEN_WINDOW_DEV_TOOLS, IPCType.SEND)
  async onOpenWindowDevTools(_event: any, mode: 'left' | 'right' | 'bottom' | 'undocked' | 'detach'): Promise<void> {
    appWindowsAndViewsManager.mainWindow.baseWindow?.webContents.openDevTools({ mode: mode })
  }

  @IPCHandle(IPC_CHANNELS.APP_OPEN_SUB_WINDOW_DEV_TOOLS, IPCType.SEND)
  async onOpenSubWindowDevTools(_event: any, mode: 'left' | 'right' | 'bottom' | 'undocked' | 'detach'): Promise<void> {
    appWindowsAndViewsManager.tkWebContentView.getWebContentsView().webContents.openDevTools({ mode: mode })
  }
}
