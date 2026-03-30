import { AppConfig } from '@common/app-config'
import { LoggerOptions, LoggerService } from '@infound/desktop-electron'

export const logger = LoggerService.getInstance({
  level: AppConfig.LOG_LEVEL,
  enable: AppConfig.LOG_ENABLE
} as LoggerOptions)
