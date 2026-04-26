import { ElectronAPI } from '@electron-toolkit/preload'
import { LoggerAPI } from '@infound/desktop-electron/types'
import { IPCAPI } from '@common/types/ipc-type'

declare global {
  interface Window {
    electron: ElectronAPI
    logger: LoggerAPI
    ipc: IPCAPI
  }
}
