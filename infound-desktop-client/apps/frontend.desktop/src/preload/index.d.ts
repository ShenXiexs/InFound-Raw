import { ElectronAPI } from '@electron-toolkit/preload'
import { IPCAPI } from '@common/types/ipc-type'
import { LoggerAPI } from '@infound/desktop-electron'

declare global {
  interface Window {
    electron: ElectronAPI
    logger: LoggerAPI
    ipc: IPCAPI
  }
}
