import { contextBridge } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'
import { loggerAPI } from './shared/logger-api'
import { ipcAPI } from './shared/ipc-api'

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('logger', loggerAPI)
    contextBridge.exposeInMainWorld('ipc', ipcAPI)
  } catch (error) {
    console.error(error)
  }
}
