import type { TaskLoggerLike } from '@infound/desktop-rpa'
import { PlaywrightSimulationService } from '@infound/desktop-rpa'
import { getCleanUserAgent } from '@infound/desktop-electron'
import { AppConfig } from '@common/app-config'
import { logger } from '../../utils/logger'

export const desktopRpaExecutionService = PlaywrightSimulationService.getInstance(
  logger as unknown as TaskLoggerLike,
  getCleanUserAgent() || AppConfig.USER_AGENT,
  AppConfig.IS_PRO
)
