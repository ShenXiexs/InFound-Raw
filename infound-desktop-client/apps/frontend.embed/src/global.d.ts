import type { IPCAPI } from '@common/types/ipc-type'
import type { LoggerAPI } from '@infound/desktop-electron/types'

declare global {
  interface Window {
    logger: LoggerAPI
    ipc: IPCAPI
  }
}
