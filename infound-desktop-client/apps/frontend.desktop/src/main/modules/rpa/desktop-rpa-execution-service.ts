import type { TaskLoggerLike } from '@infound/desktop-rpa'
import { PlaywrightSimulationService } from '@infound/desktop-rpa'
import { logger } from '../../utils/logger'

export const desktopRpaExecutionService = PlaywrightSimulationService.getInstance(
  logger as unknown as TaskLoggerLike
)
