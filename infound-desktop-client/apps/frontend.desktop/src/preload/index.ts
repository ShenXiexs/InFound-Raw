import { contextBridge } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'
import { loggerAPI } from './shared/logger-api'
import { ipcAPI } from './shared/ipc-api'
import { AppConfig } from '@common/app-config'
import { IPC_CHANNELS } from '@common/types/ipc-type'

window.addEventListener('keydown', async (e) => {
  if (AppConfig.IS_PRO) {
    // 禁用 F12
    if (e.key === 'F12') return e.preventDefault()
    // 禁用 Ctrl+Shift+I/J/C
    if (e.ctrlKey && e.shiftKey && ['I', 'J', 'C'].includes(e.key)) {
      return e.preventDefault()
    }
    // 禁用 Ctrl+U（查看源代码）
    if (e.ctrlKey && e.key === 'U') return e.preventDefault()
  } else {
    loggerAPI.info(`Key pressed: ${e.key}`)

    const windowId = await ipcAPI.getCurrentBrowserWindowId()
    if (e.key === 'F12') {
      ipcAPI.send(IPC_CHANNELS.APP_OPEN_WINDOW_DEV_TOOLS, windowId, 'undocked')
    }
  }
})

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('logger', loggerAPI)
    contextBridge.exposeInMainWorld('ipc', ipcAPI)
  } catch (error) {
    console.error(error)
  }
}
