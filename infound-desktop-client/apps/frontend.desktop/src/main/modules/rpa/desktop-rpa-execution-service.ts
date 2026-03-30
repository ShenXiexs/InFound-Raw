import type { TaskLoggerLike } from '@desktop-rpa/seller-rpa/task-dsl/types'
import { PlaywrightSimulationService } from '@desktop-rpa/seller-rpa/playwright-simulation/playwright-simulation-service'
import { logger } from '../../utils/logger'

export const desktopRpaExecutionService = PlaywrightSimulationService.getInstance(
  logger as unknown as TaskLoggerLike
)
