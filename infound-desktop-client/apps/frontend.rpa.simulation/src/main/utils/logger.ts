import { LoggerOptions, LoggerService } from '@infound/desktop-shared'
import { AppConfig } from '@common/app-config'

export const logger = LoggerService.getInstance({
  level: AppConfig.LOG_LEVEL,
  enable: AppConfig.LOG_ENABLE
} as LoggerOptions)
