import { LoggerOptions, LoggerService } from '@infound/desktop-electron'
import { AppConfig } from '@common/app-config'

/*export const logger = LoggerService.getInstance({
  level: AppConfig.LOG_LEVEL,
  enable: AppConfig.LOG_ENABLE
} as LoggerOptions)*/

let _logger: LoggerService | null = null

export function initializeLogger(): LoggerService {
  if (!_logger) {
    _logger = LoggerService.getInstance({
      level: AppConfig.LOG_LEVEL,
      enable: AppConfig.LOG_ENABLE
    } as LoggerOptions)
  }
  return _logger
}

// 懒加载 logger 实例
export const logger = {
  info: (msg: string, ...args: any[]) => _logger?.info(msg, ...args),
  warn: (msg: string, ...args: any[]) => _logger?.warn(msg, ...args),
  error: (msg: string, ...args: any[]) => _logger?.error(msg, ...args),
  debug: (msg: string, ...args: any[]) => _logger?.debug(msg, ...args)
}
