import { IPCHandle, IPCType } from './base/ipc-decorator'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { logger } from '../../utils/logger'
import { LoggerLevel } from '@infound/desktop-shared'

export class LoggerController {
  @IPCHandle(IPC_CHANNELS.APP_LOGGER, IPCType.SEND)
  async log(_event: any, level: LoggerLevel, message: string, ...args: any[]): Promise<void> {
    try {
      switch (level) {
        case LoggerLevel.debug:
          logger.debug(message, ...args)
          break
        case LoggerLevel.error:
          logger.error(message, ...args)
          break
        case LoggerLevel.info:
          logger.info(message, ...args)
          break
        case LoggerLevel.warn:
          logger.warn(message, ...args)
          break
      }
    } catch (err) {
      // 这里必须使用原生 console.error，因为 logger 系统本身可能已经挂了
      console.error('LoggerController 记录日志失败:', err)
    }
  }
}
