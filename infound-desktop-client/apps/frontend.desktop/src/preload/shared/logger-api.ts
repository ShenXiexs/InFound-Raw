import { ipcRenderer } from 'electron'
import { IPC_CHANNELS, IPCGateway } from '@common/types/ipc-type'
import { LoggerAPI, LoggerLevel } from '@infound/desktop-electron/types'

const logAction = (level: LoggerLevel, message: string, ...args: any[]): void => {
  ipcRenderer.send(IPCGateway.APP, { channel: IPC_CHANNELS.APP_LOGGER, args: [level, message, ...args] })
}

export const loggerAPI: LoggerAPI = {
  debug: (m, ...a) => logAction(LoggerLevel.debug, m, ...a),
  info: (m, ...a) => logAction(LoggerLevel.info, m, ...a),
  warn: (m, ...a) => logAction(LoggerLevel.warn, m, ...a),
  error: (m, ...a) => logAction(LoggerLevel.error, m, ...a)
}
